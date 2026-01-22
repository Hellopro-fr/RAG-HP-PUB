# app/router/ingestion_api.py
import logging
import time
from collections import Counter
from fastapi import APIRouter, Request, HTTPException, status
from app.schemas.ingestion.ingestion import (
    BaseIngestion as IngestionRequest,
    BaseIngestionReponse,
    BaseIngestionReponseSucces,
)
from app.messaging.publisher import publish_message
from app.core.ingestion.ingestion import routing_key_collection_graph
from common_utils.rabbitmq.rabbitmq_connection import RabbitMQConnection

from common_utils.metrics.prometheus import (
    measure_processing_time,
    PROCESSING_TIME_SECONDS,
)
from datetime import datetime

router = APIRouter()


@router.post("/publier", summary="Publier un message sur RabbitMQ")
# @measure_processing_time(service_name="api-ingestion", payload_arg_name="payload")
async def publish_to_rabbitmq(
    payload: IngestionRequest, request: Request
) -> BaseIngestionReponseSucces | BaseIngestionReponse:
    """
    Reçoit des données et les publie dans la file d'attente RabbitMQ.

    - **payload**: Les données à envoyer, conformes au schéma `IngestionRequest`.
    """

    channel = request.app.state.rabbitmq_channel

    if not channel or channel.is_closed:
        connection = RabbitMQConnection().create_connection(
            max_retries=10, retry_delay=5
        )
        if connection:
            channel = connection.channel()
        else:
            return BaseIngestionReponse(
                code=status.HTTP_503_SERVICE_UNAVAILABLE,
                message="La connexion à RabbitMQ n'est pas disponible.",
            )

    exchange_name = f"data_exchange_{payload.collection}"
    # if payload.collection == "produits_2":
    #     exchange_name = f"data_exchange_produits"

    routing_key = routing_key_collection_graph(payload.collection)

    success = publish_message(
        channel=channel,
        exchange_name=exchange_name,
        routing_key=routing_key,
        data=payload.model_dump(),
    )

    if not success:
        return BaseIngestionReponse(
            code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Échec de la publication du message sur RabbitMQ.",
        )

    return BaseIngestionReponseSucces(
        code=status.HTTP_202_ACCEPTED,
        message="Le message a été mis en file d'attente pour publication.",
        details={
            "exchange": exchange_name,
            "routing_key": routing_key,
            "collection": payload.collection,
            "database": payload.database,
            "date": datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        },
    )


@router.post("/publier-lot", summary="Publier plusieurs lots sur RabbitMQ")
async def publish_lot_rabbitmq(
    payloads: list[IngestionRequest], request: Request
) -> list[BaseIngestionReponseSucces | BaseIngestionReponse]:
    """
    Reçoit des données et les publie dans la file d'attente RabbitMQ.

    - **payload**: Les données à envoyer, conformes au schéma `IngestionRequest`.
    """
    # --- MANUAL INSTRUMENTATION START ---
    start_time = time.monotonic()
    # --- FIX 1: Rename 'status' to 'metric_status' ---
    metric_status = "success"
    collection_counter = Counter()
    # --- END MANUAL INSTRUMENTATION START ---

    try:
        channel = request.app.state.rabbitmq_channel

        if not channel or channel.is_closed:
            connection = RabbitMQConnection().create_connection(
                max_retries=10, retry_delay=5
            )
            if connection:
                channel = connection.channel()
            else:
                return [
                    BaseIngestionReponse(
                        code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        message="La connexion à RabbitMQ n'est pas disponible.",
                    )
                ]

        import asyncio
        from itertools import islice

        semaphore = asyncio.Semaphore(4)  # Limit concurrent connections (Safe limit for 40 max connections)
        loop = asyncio.get_running_loop()
        batch_size = 20  # Process 20 messages per connection

        def chunked(iterable, n):
            it = iter(iterable)
            while True:
                chunk = list(islice(it, n))
                if not chunk:
                    return
                yield chunk

        def publish_batch(batch_payloads: list[IngestionRequest]) -> list[BaseIngestionReponseSucces | BaseIngestionReponse]:
            batch_responses = []
            # Create a dedicated connection for this thread/batch
            try:
                # We do not use the shared app state connection here to avoid thread-safety issues
                connection = RabbitMQConnection().create_connection(max_retries=3, retry_delay=2)
                local_channel = connection.channel()
            except Exception as e:
                # If connection fails, return errors for the whole batch
                logging.error(f"Failed to create connection for batch: {e}")
                return [
                    BaseIngestionReponse(
                        code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        message="La connexion à RabbitMQ n'est pas disponible pour ce lot.",
                    ) for _ in batch_payloads
                ]

            try:
                for payload in batch_payloads:
                    # Update counter (thread-safe for Counter)
                    collection_counter[str(payload.collection)] += 1
                    
                    exchange_name = f"data_exchange_{payload.collection}"
                    routing_key = routing_key_collection_graph(payload.collection)
                    data = payload.model_dump()

                    try:
                        # Use the local_channel
                        success = publish_message(
                            channel=local_channel,
                            exchange_name=exchange_name,
                            routing_key=routing_key,
                            data=data,
                        )
                        
                        if not success:
                            batch_responses.append(
                                BaseIngestionReponse(
                                    code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                    message="Échec de la publication du message sur RabbitMQ.",
                                )
                            )
                        else:
                            batch_responses.append(
                                BaseIngestionReponseSucces(
                                    code=status.HTTP_202_ACCEPTED,
                                    message="Le message a été mis en file d'attente pour publication.",
                                    details={
                                        "exchange": exchange_name,
                                        "routing_key": routing_key,
                                        "collection": payload.collection,
                                        "database": payload.database,
                                        "date": datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
                                    },
                                )
                            )
                    except Exception as e:
                         batch_responses.append(
                            BaseIngestionReponse(
                                code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                message=f"Erreur inattendue: {str(e)}",
                            )
                        )
            finally:
                # Ensure connection is closed after batch is done
                if connection and not connection.is_closed:
                    connection.close()
            
            return batch_responses

        async def process_batch_async(batch):
            async with semaphore:
                return await loop.run_in_executor(None, publish_batch, batch)

        # Execute batches concurrently
        results_list = await asyncio.gather(*(process_batch_async(batch) for batch in chunked(payloads, batch_size)))
        
        # Flatten results
        response = [item for sublist in results_list for item in sublist]
        return response

    except Exception:
        metric_status = "failure"
        raise
    finally:
        duration = time.monotonic() - start_time
        if not collection_counter:  # Handle case of empty payload list
            PROCESSING_TIME_SECONDS.labels(
                service_name="api-ingestion",
                status=metric_status,
                collection_type="empty_batch",
            ).observe(duration)
        else:
            # --- FIX 2: Use the correct .observe() pattern for manual instrumentation ---
            for collection, count in collection_counter.items():
                metric = PROCESSING_TIME_SECONDS.labels(
                    service_name="api-ingestion",
                    status=metric_status,
                    collection_type=collection,
                )
                # Observe the full duration once to increment the sum correctly
                metric.observe(duration)
                # Observe a zero duration for the rest of the items to increment the count correctly
                if count > 1:
                    for _ in range(count - 1):
                        metric.observe(0)
