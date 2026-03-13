from pydantic import BaseModel, Field, validator
from typing import Optional
import re


class ProduitPrixPayload(BaseModel):
    """
    Schéma de validation du payload publié vers embedding pour la source 'message'.
    """

    # --- Champs obligatoires ---
    description_produit: str = Field(..., description="Description complète du produit (obligatoire)")
    nom_produit: str = Field(..., description="Nom / titre du produit (obligatoire)")
    valeur_prix: str = Field(..., description="Valeur numérique du prix, ex: '149.99' ou '100 - 200' (obligatoire)")

    # --- Champs optionnels ---
    source: Optional[str] = Field(None, description="Source du data prix (ex: 'produit' , 'message' , 'devis' , 'siteweb')")
    caracteristique: Optional[str] = Field(None, description="caracteristique du produit")
    id_categorie: Optional[str] = Field(None, description="ID de la catégorie")
    nom_categorie: Optional[str] = Field(None, description="Nom  de la catégorie")
    date_prix: Optional[str] = Field(None, description="Date du prix au format YYYY-MM-DD, ex: '2025-11-15'")
    id_lead: Optional[str] = Field(None, description="ID du lead / demande d'information associé")
    id_produit: Optional[str] = Field(None, description="ID du produit dans la base IA (scrapping_fiche_produit_ia)")
    source_chunk_id: Optional[str] = Field(None, description="ID du chunk source pour devis et siteweb")
    domaine: Optional[str] = Field(None, description="Domaine web d'origine du scrapping")
    id_societe_ia: Optional[str] = Field(None, description="ID interne IA du fournisseur (id_societe_ia)")
    valeur_reponse_q1: Optional[str] = Field(None, description="Valeur de la réponse Q1 associée à la catégorie")
    prix_original: Optional[str] = Field(None, description="Prix original tel qu'il apparaît dans les données brutes")
    structure_prix: Optional[str] = Field(None, description="Type de structure de prix: fixe, promotionnel, fourchette, à_partir_de")
    unite: Optional[str] = Field(None, description="Unité du prix (ex: 'par unité', 'par mois')")
    devise: Optional[str] = Field(None, description="Devise du prix (ex: '€', '$', '£')")
    taxe: Optional[str] = Field(None, description="Indication de taxe: 'HT', 'TTC' ou vide")
    type_transaction: Optional[str] = Field(None, description="Type de transaction (ex: 'vente', 'location')")
    perimetre: Optional[str] = Field(None, description="Périmètre géographique ou commercial du prix")
    id_fournisseur: Optional[str] = Field(None, description="ID BO du fournisseur (id_societe_bo)")
    fournisseur: Optional[str] = Field(None, description="Nom commercial du fournisseur")

    @validator("date_prix", pre=True, always=True)
    def validate_date_format(cls, v):
        """Valide que date_prix respecte le format YYYY-MM-DD si fourni."""
        if v is None or v == "":
            return None
        pattern = r"^\d{4}-\d{2}-\d{2}$"
        if not re.match(pattern, str(v)):
            raise ValueError(f"date_prix doit être au format YYYY-MM-DD, reçu: '{v}'")
        return str(v)

    @validator("valeur_prix", pre=True, always=True)
    def validate_valeur_prix(cls, v):
        """S'assure que valeur_prix n'est pas vide."""
        if not v or str(v).strip() == "":
            raise ValueError("valeur_prix ne peut pas être vide")
        return str(v).strip()

    class Config:
        # Permettre les champs supplémentaires non définis (ignorés silencieusement)
        extra = "ignore"
