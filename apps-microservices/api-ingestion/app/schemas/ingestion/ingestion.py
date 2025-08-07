from typing import Annotated, Dict
import uuid
from pydantic import ConfigDict, BaseModel, Field
from app.schemas.base import GetBase as Base
from app.core.ingestion.ingestion import CollectionName

class BaseIngestion(BaseModel):
    data: Annotated[dict, Field(title="Les données à publier", description="Un objet JSON contenant les informations du produit ou autre.")]
    collection: Annotated[
        CollectionName, # <-- Use the Enum as the type
        Field(title="Nom de la collection de destination")
    ] = CollectionName.PRODUIT


class BaseIngestionReponse(BaseModel):
    code: Annotated[int, Field(title="Code de retour")]
    message: Annotated[str, Field(title="Message de retour")]


class BaseIngestionReponseSucces(BaseIngestionReponse):
    details: Annotated[dict, Field(title="info de détails de retour de publication de message")]