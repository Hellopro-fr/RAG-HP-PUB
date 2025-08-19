from typing import Annotated
import uuid
from pydantic import ConfigDict, BaseModel, Field


class BaseTrafilatura(BaseModel):
    url: Annotated[str, Field(title="L'url du site")]
    content: Annotated[str, Field(title="Le contenu du site")]
    fetch: Annotated[bool, Field(title="Récupérer le contenu du site en utilisant fetch fonction de trafilatura ")] = False


class BaseTrafilaturaReponse(BaseModel):
    url: Annotated[str, Field(title="L'url du site")]
    content: Annotated[str, Field(title="Le contenu du site")]

class TrafilaturaReponseHtml(BaseTrafilaturaReponse):
    html: Annotated[str, Field(title="Contenu html du site si fetch contenu")]

