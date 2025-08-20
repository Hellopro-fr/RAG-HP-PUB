# app/router/ingestion_api.py
import logging
from fastapi import APIRouter, Request, HTTPException, status
from app.schemas.ingestion.ingestion import BaseIngestion as IngestionRequest, BaseIngestionReponse, BaseIngestionReponseSucces
from app.messaging.publisher import publish_message
from app.core.ingestion.ingestion import routing_key_collection

router = APIRouter()

@router.post("/publier", summary="Publier un message sur RabbitMQ")
def publish_to_rabbitmq(payload: IngestionRequest, request: Request) -> BaseIngestionReponseSucces | BaseIngestionReponse:
    """
    Reçoit des données et les publie dans la file d'attente RabbitMQ.

    - **payload**: Les données à envoyer, conformes au schéma `IngestionRequest`.
    """
    
    channel = request.app.state.rabbitmq_channel
    
    if not channel or channel.is_closed:
        return BaseIngestionReponse(code=status.HTTP_503_SERVICE_UNAVAILABLE, message="La connexion à RabbitMQ n'est pas disponible.")

    exchange_name = f"data_exchange_{payload.collection}"
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
    
    channel = request.app.state.rabbitmq_channel
    
    if not channel or channel.is_closed:
        return BaseIngestionReponse(code=status.HTTP_503_SERVICE_UNAVAILABLE, message="La connexion à RabbitMQ n'est pas disponible.")

    
    response: list[BaseIngestionReponseSucces | BaseIngestionReponse] = []

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