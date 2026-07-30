from typing import List, Optional

from pydantic import BaseModel, Field


class RequestFabricantReference(BaseModel):
    """Requete de lancement de l'extraction pour une categorie."""
    id_categorie: str = Field(..., description="ID de la categorie a traiter")
    source: str = Field(default="bo", description="Origine des produits: bo ou ia")
    is_reset: bool = Field(default=False, description="Reinitialise le process avant de traiter")


class ExtractionProduit(BaseModel):
    """Resultat d'extraction pour un produit — reflet exact de la sortie du prompt 133.

    `modele` n'est pas produit par le prompt 133 (sa `reference` EST le code modele) :
    le champ est un passe-plat, prêt si un champ modele/gamme est ajoute au prompt.
    """
    id_produit: str
    marque: Optional[str] = None
    reference: Optional[str] = None
    modele: Optional[str] = None
    provenance: str = "absente"
    extrait_marque: Optional[str] = None
    alertes: List[str] = Field(default_factory=list)


class FabricantReferenceResult(BaseModel):
    """Compte rendu d'un run d'extraction sur une categorie."""
    id_categorie: str
    nom_rubrique: str = ""
    total_processed: int = 0        # produits enregistres (marque trouvee ou abstention)
    total_marques: int = 0          # produits avec une marque retenue
    total_echecs: int = 0           # batchs perdus, a reprendre au run suivant
    status: str = "completed"       # completed, completed_with_errors, error, stopped
