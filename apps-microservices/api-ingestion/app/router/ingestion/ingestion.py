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
    
    if not channel:
        return BaseIngestionReponse(code=status.HTTP_503_SERVICE_UNAVAILABLE, message="La connexion à RabbitMQ n'est pas disponible.")

    exchange_name = "data_exchange"
    routing_key = routing_key_collection(payload.collection)
    
    success = publish_message(
        channel=channel,
        exchange_name=exchange_name,
        routing_key=routing_key,
        data=payload.data
    )

    if not success:
        return BaseIngestionReponse(code=status.HTTP_500_INTERNAL_SERVER_ERROR, message="Échec de la publication du message sur RabbitMQ.")

    return BaseIngestionReponseSucces(
        code=status.HTTP_202_ACCEPTED, 
        message="Le message a été mis en file d'attente pour publication.", 
        details={
            "exchange": exchange_name,
            "routing_key": routing_key,
            "collection": payload.collection
        }
    )