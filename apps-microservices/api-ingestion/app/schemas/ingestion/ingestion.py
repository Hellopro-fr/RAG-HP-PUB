from typing import Annotated, Dict
import uuid
from pydantic import ConfigDict, BaseModel, Field
from app.schemas.base import GetBase as Base


class BaseIngestion(BaseModel):
    data: Annotated[dict, Field(title="Les données à publier", description="Un objet JSON contenant les informations du produit ou autre.")]
    exchange_name: Annotated[str, Field(title="Nom de l'exchange RabbitMQ")] = "data_exchange"
    routing_key: Annotated[str, Field(title="Clé de routage pour le message")]


class BaseIngestionReponse(BaseModel):
    code: Annotated[int, Field(title="Code de retour")]
    message: Annotated[str, Field(title="Message de retour")]


class BaseIngestionReponseSucces(BaseIngestionReponse):
    details: Annotated[dict, Field(title="info de détails de retour de publication de message")]