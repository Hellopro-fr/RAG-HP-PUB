from typing import Annotated, Dict
import uuid
from pydantic import ConfigDict, BaseModel, Field
from app.schemas.base import GetBase as Base
from app.core.rest-milvus.rest-milvus import CollectionName

class Baserest-milvus(BaseModel):
    data: Annotated[dict, Field(title="Les données à publier", description="Un objet JSON contenant les informations du produit ou autre.")]
    collection: Annotated[
        CollectionName, # <-- Use the Enum as the type
        Field(title="Nom de la collection de destination")
    ] = CollectionName.PRODUIT
    database: Annotated[str, Field(title="Nom de la base de données", description="La base de données dans laquelle les données seront stockées. Par défaut, c'est 'qdrant'.")] = "qdrant"


class Baserest-milvusReponse(BaseModel):
    code: Annotated[int, Field(title="Code de retour")]
    message: Annotated[str, Field(title="Message de retour")]


class Baserest-milvusReponseSucces(Baserest-milvusReponse):
    details: Annotated[dict, Field(title="info de détails de retour de publication de message")]