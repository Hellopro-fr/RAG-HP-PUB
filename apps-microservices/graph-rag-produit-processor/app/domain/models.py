from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field


class ProduitPayload(BaseModel):
    """Product payload model for Graph RAG processing."""

    url: Optional[str] = Field(None, description="URL de la page du produit")
    nom_produit: str = Field(..., description="Nom commercial du produit")
    domaine: Optional[str] = Field(None, description="Domaine du site web source")
    fournisseur: Optional[str] = Field(None, description="Nom du fournisseur")
    id_fournisseur: str = Field(..., description="ID numérique du fournisseur")
    categorie: Optional[str] = Field(None, description="Nom de la catégorie principale")
    id_categorie: str = Field(..., description="ID numérique de la catégorie")
    source: Optional[str] = Field(None, description="Origine de la donnée")
    fichier_source: Optional[str] = Field(None, description="Fichier source")
    date_ajout: Optional[datetime] = Field(None, description="Date d'ajout")
    id_produit: str = Field(..., description="ID alphanumérique du produit")
    sku: Optional[str] = Field(None, description="SKU du produit")
    ean: Optional[str] = Field(None, description="Code EAN")
    url_image: Optional[str] = Field(None, description="URL image")
    reference: Optional[str] = Field(None, description="Référence fabricant")
    prix_ttc: Optional[float] = Field(None, description="Prix TTC")
    statut: Optional[str] = Field(None, description="Statut de disponibilité")
    description: Optional[str] = Field(None, description="Description du produit")

    def get_graph_id(self) -> str:
        return f"id_produit_{self.id_produit}"


class GraphRagProductMessage(BaseModel):
    """Message format for Graph RAG pipeline."""

    product: ProduitPayload
    graph_id: str
    database: str = "neo4j"
    origin: str = "bo"
    node_created: bool = False
