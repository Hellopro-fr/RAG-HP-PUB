# app/router/rest-milvus_api.py
import logging
from fastapi import APIRouter, Request, HTTPException, status
from app.schemas.rest-milvus.rest-milvus import Baserest-milvus as rest-milvusRequest, Baserest-milvusReponse, Baserest-milvusReponseSucces
from app.messaging.publisher import publish_message
from app.core.rest-milvus.rest-milvus import routing_key_collection
from common_utils.rabbitmq.rabbitmq_connection import RabbitMQConnection

router = APIRouter()

@router.post("/publier", summary="Publier un message sur RabbitMQ")
def publish_to_rabbitmq(payload: rest-milvusRequest, request: Request) -> Baserest-milvusReponseSucces | Baserest-milvusReponse:
    """
    Reçoit des données et les publie dans la file d'attente RabbitMQ.

    - **payload**: Les données à envoyer, conformes au schéma `rest-milvusRequest`.
    """
    
    channel = request.app.state.rabbitmq_channel
    
    if not channel or channel.is_closed:
        connection = RabbitMQConnection().create_connection(max_retries=10, retry_delay=5)
        if connection:
            channel = connection.channel()
        else:
            return Baserest-milvusReponse(code=status.HTTP_503_SERVICE_UNAVAILABLE, message="La connexion à RabbitMQ n'est pas disponible.")

    exchange_name = f"data_exchange_{payload.collection}"
    routing_key = routing_key_collection(payload.collection)
    
    success = publish_message(
        channel=channel,
        exchange_name=exchange_name,
        routing_key=routing_key,
        data=payload.model_dump()
    )

    if not success:
        return Baserest-milvusReponse(code=status.HTTP_500_INTERNAL_SERVER_ERROR, message="Échec de la publication du message sur RabbitMQ.")

    return Baserest-milvusReponseSucces(
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
def publish_lot_rabbitmq(payloads: list[rest-milvusRequest], request: Request) -> list[Baserest-milvusReponseSucces | Baserest-milvusReponse]:
    """
    Reçoit des données et les publie dans la file d'attente RabbitMQ.

    - **payload**: Les données à envoyer, conformes au schéma `rest-milvusRequest`.
    """
    
    channel = request.app.state.rabbitmq_channel
    
    if not channel or channel.is_closed:
        connection = RabbitMQConnection().create_connection(max_retries=10, retry_delay=5)
        if connection:
            channel = connection.channel()
        else:
            return Baserest-milvusReponse(code=status.HTTP_503_SERVICE_UNAVAILABLE, message="La connexion à RabbitMQ n'est pas disponible.")

        return Baserest-milvusReponse(code=status.HTTP_503_SERVICE_UNAVAILABLE, message="La connexion à RabbitMQ n'est pas disponible.")

    
    response: list[Baserest-milvusReponseSucces | Baserest-milvusReponse] = []

    for payload in payloads:
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
                Baserest-milvusReponse(code=status.HTTP_500_INTERNAL_SERVER_ERROR, message="Échec de la publication du message sur RabbitMQ.")
            )
        else:
            response.append(
                Baserest-milvusReponseSucces(
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