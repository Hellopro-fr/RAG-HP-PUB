from typing import Annotated
import uuid
import uuid
from pydantic import ConfigDict, BaseModel, Field


class Base(BaseModel):
    nom: Annotated[str, Field(title="Nom de l'entrée")]
    model_config = ConfigDict(from_attributes=True)


class GetBase(Base):
    uid: uuid.UUID
