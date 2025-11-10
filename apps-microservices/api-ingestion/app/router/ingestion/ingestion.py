# app/router/ingestion_api.py
import logging
import time
from collections import Counter
from fastapi import APIRouter, Request, HTTPException, status
from app.schemas.ingestion.ingestion import BaseIngestion as IngestionRequest, BaseIngestionReponse, BaseIngestionReponseSucces
from app.messaging.publisher import publish_message
from app.core.ingestion.ingestion import routing_key_collection
from common_utils.rabbitmq.rabbitmq_connection import RabbitMQConnection

from common_utils.metrics.prometheus import measure_processing_time, PROCESSING_TIME_SECONDS

router = APIRouter()

@router.post("/publier", summary="Publier un message sur RabbitMQ")
@measure_processing_time(service_name="api-ingestion", payload_arg_name="payload")
def publish_to_rabbitmq(payload: IngestionRequest, request: Request) -> BaseIngestionReponseSucces | BaseIngestionReponse:
    """
    Reçoit des données et les publie dans la file d'attente RabbitMQ.

    - **payload**: Les données à envoyer, conformes au schéma `IngestionRequest`.
    """
    
    channel = request.app.state.rabbitmq_channel
    
    if not channel or channel.is_closed:
        connection = RabbitMQConnection().create_connection(max_retries=10, retry_delay=5)
        if connection:
            channel = connection.channel()
        else:
            return BaseIngestionReponse(code=status.HTTP_503_SERVICE_UNAVAILABLE, message="La connexion à RabbitMQ n'est pas disponible.")

    exchange_name = f"data_exchange_{payload.collection}"
    # if payload.collection == "produits_2":
    #     exchange_name = f"data_exchange_produits"
        
    routing_key = routing_key_collection(payload.collection)
    
    success = publish_message(
        channel=channel,
        exchange_name=exchange_name,
        routing_key=routing_key,
        data=payload.model_dump()
    )

    if not success:
        return BaseIngestionReponse(code=status.HTTP_500_INTERNAL_SERVER_ERROR, message="Échec de la publication du message sur RabbitMQ.")

    return BaseIngestionReponseSucces(
        code=status.HTTP_202_ACCEPTED, 
        message="Le message a été mis en file d'attente pour publication.", 
        details={
            "exchange": exchange_name,
            "routing_key": routing_key,
            "collection": payload.collection,
            "database": payload.database
        }
    )

@router.post("/publier-lot", summary="Publier plusieurs lots sur RabbitMQ")
def publish_lot_rabbitmq(payloads: list[IngestionRequest], request: Request) -> list[BaseIngestionReponseSucces | BaseIngestionReponse]:
    """
    Reçoit des données et les publie dans la file d'attente RabbitMQ.

    - **payload**: Les données à envoyer, conformes au schéma `IngestionRequest`.
    """
    # --- MANUAL INSTRUMENTATION START ---
    start_time = time.monotonic()
    status = 'success'
    collection_counter = Counter()
    # --- END MANUAL INSTRUMENTATION START ---

    try:
        channel = request.app.state.rabbitmq_channel
        
        if not channel or channel.is_closed:
            connection = RabbitMQConnection().create_connection(max_retries=10, retry_delay=5)
            if connection:
                channel = connection.channel()
            else:
                return [BaseIngestionReponse(code=status.HTTP_503_SERVICE_UNAVAILABLE, message="La connexion à RabbitMQ n'est pas disponible.")]

        response: list[BaseIngestionReponseSucces | BaseIngestionReponse] = []

        for payload in payloads:
            # Increment the counter for each collection type
            collection_counter[str(payload.collection)] += 1

            exchange_name = f"data_exchange_{payload.collection}"
            routing_key = routing_key_collection(payload.collection)
            
            success = publish_message(
                channel=channel,
                exchange_name=exchange_name,
                routing_key=routing_key,
                data=payload.model_dump()
            )

            if not success:
                response.append(
                    BaseIngestionReponse(code=status.HTTP_500_INTERNAL_SERVER_ERROR, message="Échec de la publication du message sur RabbitMQ.")
                )
            else:
                response.append(
                    BaseIngestionReponseSucces(
                        code=status.HTTP_202_ACCEPTED, 
                        message="Le message a été mis en file d'attente pour publication.", 
                        details={
                            "exchange": exchange_name,
                            "routing_key": routing_key,
                            "collection": payload.collection,
                            "database": payload.database
                        }
                    )
                )
        return response

    except Exception:
        status = 'failure'
        raise # Re-raise the exception to let FastAPI handle it
    finally:
        # --- MANUAL INSTRUMENTATION REPORTING ---
        duration = time.monotonic() - start_time
        if not collection_counter: # Handle case of empty payload list
             PROCESSING_TIME_SECONDS.labels(
                service_name="api-ingestion", 
                status=status, 
                collection_type='empty_batch'
            ).observe(duration)
        else:
            for collection, count in collection_counter.items():
                # Manually increment the sum and count for the histogram
                metric_labels = {
                    "service_name": "api-ingestion",
                    "status": status,
                    "collection_type": collection
                }
                PROCESSING_TIME_SECONDS.labels(**metric_labels)._sum.inc(duration)
                PROCESSING_TIME_SECONDS.labels(**metric_labels)._count.inc(count)
        # --- END MANUAL INSTRUMENTATION REPORTING ---