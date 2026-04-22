# app/router/ingestion/ingestion_QC.py
"""
API Router pour l'ingestion vers les 7 services QC du pipeline.

Services disponibles:
- question1 (Step 1): Génération des questions de niveau 1
- question2aN (Step 2): Génération des questions de niveau 2 à N
- caracteristiques (Step 3): Génération des caractéristiques
- valeurs (Step 4): Génération des valeurs
- enrichissement (Step 5): Enrichissement des données
- equivalence (Step 6): Calcul des équivalences
- caracterisation (Step 7): Caractérisation des produits
"""
import logging
import time
import asyncio
from itertools import islice
from collections import Counter
from datetime import datetime
from fastapi import APIRouter, Request, status

from app.schemas.ingestion.ingestion_qc import (
    QCIngestionRequest,
    QCIngestionBatchRequest,
    QCIngestionResponse,
    QCIngestionResponseSuccess,
    QCIngestionBatchResponse,
    QCServiceStep,
    QC_ROUTING_KEYS,
    QC_EXCHANGES,
)
from app.messaging.publisher import publish_message
from common_utils.rabbitmq.rabbitmq_connection import RabbitMQConnection
from common_utils.metrics.prometheus import PROCESSING_TIME_SECONDS

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

router = APIRouter()

# Nom de l'exchange par défaut pour le pipeline QC (steps 1-7)
QC_EXCHANGE_NAME = "qc_pipeline_exchange"


def get_routing_key(service: QCServiceStep) -> str:
    """Retourne la routing key pour le service spécifié."""
    return QC_ROUTING_KEYS.get(service, "qc.step1.start")


def get_exchange_name(service: QCServiceStep) -> str:
    """Retourne l'exchange pour le service. Les services hors pipeline QC 1-7
    (ex: caracterisation_prix) utilisent un exchange dédié."""
    return QC_EXCHANGES.get(service, QC_EXCHANGE_NAME)


@router.post(
    "/publier",
    summary="Publier un message vers un service QC",
    description="Publie un message pour une catégorie vers l'un des 7 services QC du pipeline.",
    response_model=QCIngestionResponseSuccess | QCIngestionResponse,
)
async def publish_to_qc_service(
    payload: QCIngestionRequest,
    request: Request,
) -> QCIngestionResponseSuccess | QCIngestionResponse:
    """
    Publie un message vers un service QC spécifique.

    - **id_categorie**: L'identifiant de la catégorie à traiter
    - **is_reset**: Si True, réinitialise le traitement
    - **service**: Le service QC de destination (question1, question2aN, caracteristiques, etc.)
    """
    channel = request.app.state.rabbitmq_channel

    # Vérifier/rétablir la connexion RabbitMQ
    if not channel or channel.is_closed:
        connection = RabbitMQConnection().create_connection(
            max_retries=10, retry_delay=5
        )
        if connection:
            channel = connection.channel()
        else:
            return QCIngestionResponse(
                code=status.HTTP_503_SERVICE_UNAVAILABLE,
                message="La connexion à RabbitMQ n'est pas disponible.",
            )

    routing_key = get_routing_key(payload.service)
    exchange_name = get_exchange_name(payload.service)

    # Préparer le message
    message_data = {
        "id_categorie": payload.id_categorie,
        "is_reset": payload.is_reset,
    }

    success = publish_message(
        channel=channel,
        exchange_name=exchange_name,
        routing_key=routing_key,
        data=message_data,
    )

    if not success:
        return QCIngestionResponse(
            code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Échec de la publication du message sur RabbitMQ.",
        )

    logger.info(f"📤 Message publié pour catégorie {payload.id_categorie} vers {payload.service.value} ({exchange_name})")

    return QCIngestionResponseSuccess(
        code=status.HTTP_202_ACCEPTED,
        message="Le message a été mis en file d'attente pour publication.",
        details={
            "exchange": exchange_name,
            "routing_key": routing_key,
            "service": payload.service.value,
            "id_categorie": payload.id_categorie,
            "is_reset": payload.is_reset,
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
    )


@router.post(
    "/publier-lot",
    summary="Publier plusieurs catégories vers un service QC (traitement parallèle)",
    description="Publie des messages pour plusieurs catégories vers un service QC avec traitement parallèle.",
    response_model=QCIngestionBatchResponse,
)
async def publish_batch_to_qc_service(
    payload: QCIngestionBatchRequest,
    request: Request,
) -> QCIngestionBatchResponse:
    """
    Publie des messages pour plusieurs catégories vers un service QC avec traitement parallèle.

    - **categories**: Liste des IDs de catégories à traiter
    - **is_reset**: Si True, réinitialise le traitement pour toutes les catégories
    - **service**: Le service QC de destination
    """
    # --- MANUAL INSTRUMENTATION START ---
    start_time = time.monotonic()
    metric_status = "success"
    category_counter = Counter()
    # --- END MANUAL INSTRUMENTATION START ---

    try:
        channel = request.app.state.rabbitmq_channel

        # Vérifier/rétablir la connexion RabbitMQ
        if not channel or channel.is_closed:
            connection = RabbitMQConnection().create_connection(
                max_retries=10, retry_delay=5
            )
            if connection:
                channel = connection.channel()
            else:
                return QCIngestionBatchResponse(
                    code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    message="La connexion à RabbitMQ n'est pas disponible.",
                    total=len(payload.categories),
                    success_count=0,
                    failed_count=len(payload.categories),
                    details=[],
                )

        routing_key = get_routing_key(payload.service)
        exchange_name = get_exchange_name(payload.service)

        semaphore = asyncio.Semaphore(4)  # Limite les connexions concurrentes
        loop = asyncio.get_running_loop()
        batch_size = 20  # Traite 20 messages par connexion

        def chunked(iterable, n):
            """Divise un itérable en chunks de taille n."""
            it = iter(iterable)
            while True:
                chunk = list(islice(it, n))
                if not chunk:
                    return
                yield chunk

        def publish_batch(batch_categories: list[str]) -> list[dict]:
            """Publie un batch de catégories dans un thread dédié."""
            batch_results = []
            
            # Créer une connexion dédiée pour ce thread/batch
            try:
                connection = RabbitMQConnection().create_connection(max_retries=3, retry_delay=2)
                local_channel = connection.channel()
            except Exception as e:
                logging.error(f"Échec création connexion pour batch: {e}")
                return [
                    {
                        "id_categorie": cat_id,
                        "status": "failed",
                        "error": "Connexion RabbitMQ indisponible",
                    } for cat_id in batch_categories
                ]

            try:
                for cat_id in batch_categories:
                    # Mise à jour du compteur (thread-safe pour Counter)
                    category_counter[str(payload.service.value)] += 1
                    
                    message_data = {
                        "id_categorie": cat_id,
                        "is_reset": payload.is_reset,
                    }

                    try:
                        success = publish_message(
                            channel=local_channel,
                            exchange_name=exchange_name,
                            routing_key=routing_key,
                            data=message_data,
                        )
                        
                        if success:
                            batch_results.append({
                                "id_categorie": cat_id,
                                "status": "success",
                                "routing_key": routing_key,
                            })
                            logger.info(f"📤 Message publié pour catégorie {cat_id} vers {payload.service.value}")
                        else:
                            batch_results.append({
                                "id_categorie": cat_id,
                                "status": "failed",
                                "error": "Échec de publication",
                            })
                    except Exception as e:
                        batch_results.append({
                            "id_categorie": cat_id,
                            "status": "failed",
                            "error": str(e),
                        })
            finally:
                # Fermer la connexion après le batch
                if connection and not connection.is_closed:
                    connection.close()
            
            return batch_results

        async def process_batch_async(batch):
            """Traite un batch de manière asynchrone avec sémaphore."""
            async with semaphore:
                return await loop.run_in_executor(None, publish_batch, batch)

        # Exécuter les batches en parallèle
        results_list = await asyncio.gather(
            *(process_batch_async(batch) for batch in chunked(payload.categories, batch_size))
        )
        
        # Aplatir les résultats
        details = [item for sublist in results_list for item in sublist]
        
        # Compter les succès/échecs
        success_count = sum(1 for d in details if d["status"] == "success")
        failed_count = sum(1 for d in details if d["status"] == "failed")
        total = len(payload.categories)
        
        if failed_count == 0:
            message = f"Tous les {total} messages ont été publiés avec succès."
            code = status.HTTP_202_ACCEPTED
        elif success_count == 0:
            message = f"Échec de la publication de tous les {total} messages."
            code = status.HTTP_500_INTERNAL_SERVER_ERROR
        else:
            message = f"{success_count}/{total} messages publiés, {failed_count} échecs."
            code = status.HTTP_207_MULTI_STATUS

        return QCIngestionBatchResponse(
            code=code,
            message=message,
            total=total,
            success_count=success_count,
            failed_count=failed_count,
            details=details,
        )

    except Exception:
        metric_status = "failure"
        raise
    finally:
        duration = time.monotonic() - start_time
        if not category_counter:
            PROCESSING_TIME_SECONDS.labels(
                service_name="api-ingestion-qc",
                status=metric_status,
                collection_type="empty_batch",
            ).observe(duration)
        else:
            for service_type, count in category_counter.items():
                metric = PROCESSING_TIME_SECONDS.labels(
                    service_name="api-ingestion-qc",
                    status=metric_status,
                    collection_type=service_type,
                )
                metric.observe(duration)
                if count > 1:
                    for _ in range(count - 1):
                        metric.observe(0)


@router.get(
    "/services",
    summary="Liste des services QC disponibles",
    description="Retourne la liste des services QC disponibles avec leurs routing keys.",
)
async def list_qc_services():
    """Retourne la liste des services QC disponibles."""
    services = []
    for service in QCServiceStep:
        services.append({
            "name": service.value,
            "step": list(QCServiceStep).index(service) + 1,
            "exchange": get_exchange_name(service),
            "routing_key": QC_ROUTING_KEYS[service],
            "description": {
                "question1": "Génération des questions de niveau 1",
                "question2aN": "Génération des questions de niveau 2 à N",
                "caracteristiques": "Génération des caractéristiques",
                "valeurs": "Génération des valeurs",
                "enrichissement": "Enrichissement des données",
                "equivalence": "Calcul des équivalences",
                "caracterisation": "Caractérisation des produits",
                "caracterisation_prix": "Caractérisation des prix Milvus (hors pipeline QC 1-7)",
            }.get(service.value, ""),
        })

    return {
        "exchange": QC_EXCHANGE_NAME,
        "services": services,
    }
