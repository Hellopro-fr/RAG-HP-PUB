from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import List, Optional, Union, Dict, Any
from datetime import datetime
import re


class Constraint(BaseModel):
    id_caracteristique: str
    unite: Optional[str] = None
    valeurs_cibles: Optional[Union[List[str], Dict[str, Any]]] = None
    valeurs_bloquantes: Optional[Union[List[str], Dict[str, Any]]] = None


class ComplexFilterRequest(BaseModel):
    ids: Dict[str, List[Constraint]] = Field(
        ...,
        description="Map of Reponse ID to list of Constraints. Example: {'q_22_r_1': [{'id_caracteristique': '29', 'valeurs_cibles': ['3']}]}",
    )
    output_fields: Optional[List[str]] = Field(
        None,
        description="List of fields to return in the product data. If None, returns all fields.",
    )
    id_categorie: Optional[str] = Field(
        None,
        description="Optional Category ID to filter products. If provided, only products belonging to this category will be returned.",
    )
    top_k: int = 50
    v: int = 4
    blocked_val: int | float = -2
    different_val: int | float = -0.3


class CaracteristiqueConstraint(BaseModel):
    """Constraint for caracteristique-based filtering with weight included."""

    q_weight: float = Field(
        1.0, description="Weight for this caracteristique constraint"
    )
    unite: Optional[str] = None
    valeurs_cibles: Optional[Union[List[str], Dict[str, Any]]] = None
    valeurs_bloquantes: Optional[Union[List[str], Dict[str, Any]]] = None
    c_weight: float = Field(
        1.0, description="Weight for this caracteristique constraint"
    )


class FilterCaracteristiqueRequest(BaseModel):
    """Request model for filtering by CaracteristiqueTechnique ID with weights."""

    ids: Dict[str, List[CaracteristiqueConstraint]] = Field(
        ...,
        description="Map of Caracteristique ID to list of Constraints with weights. Example: {'29': [{'q_weight': 1.0, 'valeurs_cibles': ['3']}]}",
    )
    output_fields: Optional[List[str]] = Field(
        None,
        description="List of fields to return in the product data. If None, returns all fields.",
    )
    id_categorie: Optional[str] = Field(
        None,
        description="Optional Category ID to filter products.",
    )
    top_k: int = 50
    blocked_val: float = -2.0
    different_val: float = -0.3


class BaseNormalizer(BaseModel):
    @field_validator("*", mode="before")
    def normalize_whitespace(cls, v):
        if isinstance(v, str):
            return re.sub(r"\s+", " ", v).strip()
        return v


class ProduitPayload(BaseNormalizer):
    model_config = ConfigDict(exclude_none=True)

    url: Optional[str] = Field(None, description="URL de la page du produit")
    nom_produit: Optional[str] = Field(None, description="Nom commercial du produit")
    domaine: Optional[str] = Field(None, description="Domaine du site web source")
    fournisseur: Optional[str] = Field(
        None, description="Nom du fournisseur proposant le produit"
    )
    id_fournisseur: Optional[str] = Field(
        None, description="ID numérique du fournisseur"
    )
    categorie: Optional[str] = Field(
        None, description="Nom de la catégorie principale du produit"
    )
    id_categorie: Optional[str] = Field(
        None, description="ID numérique de la catégorie"
    )
    source: Optional[str] = Field(
        None, description="Origine de la donnée (ex: produits_bo)"
    )
    fichier_source: Optional[str] = Field(
        None, description="Nom du fichier d'où provient la donnée"
    )
    date_ajout: Optional[datetime] = Field(
        None, description="Date d'ajout du produit dans le système"
    )
    id_produit: Optional[str] = Field(
        None, description="ID alphanumérique original du produit"
    )
    sku: Optional[str] = Field(None, description="SKU (Stock Keeping Unit) du produit")
    ean: Optional[str] = Field(
        None, description="Code EAN (European Article Number) du produit"
    )
    url_image: Optional[str] = Field(None, description="URL vers les images du produit")
    reference: Optional[str] = Field(None, description="Référence fabricant du produit")
    prix_ttc: Optional[float] = Field(None, description="Prix Toutes Taxes Comprises")
    statut: Optional[str] = Field(
        None, description="Statut de disponibilité du produit (ex: En stock)"
    )
    description: Optional[str] = Field(
        None, description="Description technique ou commerciale du produit"
    )

    def get_graph_id(self) -> str:
        return f"id_produit_{self.id_produit}"


class ScoredProduct(ProduitPayload):
    model_config = ConfigDict(exclude_none=True)

    score: float
    details: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="DEBUG: Detailed score breakdown per response.",
    )
    info: Dict[str, Any] = Field(
        default_factory=dict,
        description="DEBUG: List of information about the product.",
    )


class ResultProduct(BaseModel):
    model_config = ConfigDict(exclude_none=True)

    data: List[ScoredProduct]
    info: Dict[str, Any] = {}
    top_p: List[ScoredProduct] = []


# --- Product Models ---


class CaracteristiqueResponse(BaseModel):
    nom: str = Field(
        ...,
        description="Formatted name of the characteristic (e.g. 'Hauteur : 1500mm')",
    )
    label: str = Field(..., description="Generic label (e.g. 'Hauteur')")
    id_caracteristique: str = Field(..., description="ID of the characteristic")
    valeur: Any = Field(..., description="Raw value (numeric or string)")
    id_valeur: str = Field(..., description="ID of the value")
    unite: Optional[str] = Field(None, description="Unit of measurement if applicable")
    type_donnee: Optional[str] = Field(
        None, description="Data type (numeric, text, etc.)"
    )
    valeur_min: Optional[float] = None
    valeur_max: Optional[float] = None


# --- Query / RAG Models ---


class QueryRequest(BaseModel):
    query: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="User's question in natural language.",
    )
    route: Optional[str] = ""
    user_id: str = "anonymous"


class QueryResponse(BaseModel):
    question: Optional[Any] = None
    retrieved_context: Optional[Any] = None
    generated_cypher: Optional[str] = None
    search_type: Optional[str] = None
    cypher_params: Optional[Dict[str, Any]] = None
    answer: Optional[str] = None


# --- Admin Models ---


class CypherQueryRequest(BaseModel):
    query: str = Field(..., description="The raw Cypher query to execute.")
    params: Optional[Dict[str, Any]] = Field(
        default_factory=dict, description="Optional parameters for the Cypher query."
    )


class CypherQueryResponse(BaseModel):
    results: List[Dict[str, Any]] = Field(
        ..., description="List of records returned by the query."
    )
    info: Optional[Dict[str, Any]] = Field(
        default_factory=dict, description="Execution metadata."
    )


class CategorieCountResponse(BaseModel):
    id_categorie: Optional[str] = Field(None, description="Identifiant de la catégorie")
    fournisseur: int = Field(..., description="Nombre de fournisseurs distincts")
    produit: int = Field(..., description="Nombre de produits distincts")


""" 
 Modèles pour l'input : Payload d'entrée pour le matching de produits
 """


class ScoredProduct(BaseModel):
    id_produit: str
    nom_produit: str
    score: float
    details: List[Dict[str, Any]] = []
    info: Dict[str, Any] = {}
    # Including other product fields as flexible dict to avoid strict schema issues with Neo4j return
    extra_data: Dict[str, Any] = Field(default_factory=dict)


class ResultProduct(BaseModel):
    data: List[ScoredProduct]
    info: Dict[str, Any] = {}


class MetadonneUtilisateurs(BaseModel):
    pays: Optional[str] = Field(None, description="Localisation de l'acheteur")
    typologie: Optional[int] = Field(
        None,
        description="Typologie d'entreprise de l'acheteur, 1:professionnel, 2:particulier",
    )
    id_pays: Optional[int] = Field(None, description="ID du pays")
    cp: Optional[str] = Field(None, description="Code postal de l'acheteur")


class MatchingCaracteristique(BaseModel):
    id_caracteristique: int = Field(..., description="Id de la caractéristique")
    unite: Optional[str] = Field(None, description="Unité de la caractéristique")
    valeurs_cibles: Optional[Union[Dict[str, Any], List[Any]]] = Field(
        None, description="Liste des valeurs cibles"
    )
    valeurs_bloquantes: Optional[Union[Dict[str, Any], List[Any]]] = Field(
        None, description="Liste des valeurs bloquantes"
    )
    poids_question: Optional[int] = Field(
        1, description="Poids de la question associée à cette caractéristique"
    )
    poids_caracteristique: Optional[str] = Field(
        "critique", description="Poids de la caractéristique"
    )


class MatchingOptionsScore(BaseModel):
    critique: int = Field(5, description="Poids des caractéristiques critiques")
    secondaire: int = Field(1, description="Poids des caractéristiques secondaires")


class MatchingOptions(BaseModel):
    score: MatchingOptionsScore = Field(
        MatchingOptionsScore(critique=5, secondaire=1),
        description="Options pour le matching",
    )


class RerankingOptions(BaseModel):
    top_k: int = Field(24, description="Nombre de produits à reclasser")
    use_rerank: bool = False
    parcours: str = ""
    id_prompt: int = Field(112, description="ID du prompt")
    thinking_level: str = Field(
        "minimal", description="Niveau de réflexion du LLM (low, medium, high)"
    )


class ScoringOptions(BaseModel):
    z_unmatched: float = Field(
        0, description="Score pour les geolocalisation non matched"
    )
    e_unmatched: float = Field(0.9, description="Score pour les non client")
    g_unknown_score: float = Field(
        0.8, description="Score pour les géolocalisations inconnues"
    )
    c_unknown_score: float = Field(
        0, description="Score pour les caractéristiques inconnues"
    )
    v_blocked: float = Field(
        -20.0, description="Score pour les caractéristiques bloquées — P6 fix: pénalité forte pour éliminer les produits avec valeurs_bloquantes"
    )
    v_different: float = Field(
        -0.3, description="Score pour les caractéristiques différentes"
    )
    t_unmatched: float = Field(0.2, description="Score pour les typologies non matched")
    absolute_threshold: float = Field(
        0.2, description="Seuil absolu de score minimum pour les produits — P5 fix: assouplir seuil pour parcours à 0 résultats"
    )
    relative_tolerance: float = Field(
        0.15, description="Tolérance relative par rapport au meilleur score"
    )
    max_per_supplier_primary: int = Field(
        2, description="Nombre maximum de produits par fournisseur (passe primaire)"
    )
    max_per_supplier_extended: int = Field(
        3, description="Nombre maximum de produits par fournisseur (passe étendue)"
    )
    score_step: float = Field(
        0.2, description="Pas de score pour les tranches de diversité fournisseur"
    )
    diversity_lambda: float = Field(
        0.7,
        description="Lambda MMR: pondération entre pertinence (1.0) et diversité fournisseur (0.0). Valeur par défaut 0.7 = 70% pertinence, 30% diversité",
    )


class MatchingPayload(BaseModel):
    id_categorie: int = Field(..., description="Identifiant de la catégorie")
    top_k: int = Field(15, description="Nombre de résultats souhaités")
    # messages             : str                           = Field(None, description = "Contenu du message de l'acheteuur")
    metadonnee_utilisateurs: MetadonneUtilisateurs = Field(
        default_factory=list, description="Métadonnées liées à l'acheteur"
    )
    liste_caracteristique: List[MatchingCaracteristique] = Field(
        ..., description="Liste des caractéristiques à matcher"
    )
    champs_sortie: Optional[List[str]] = Field(
        None, description="Liste des champs de sortie souhaités"
    )
    options: Optional[MatchingOptions] = Field(
        MatchingOptions(score=MatchingOptionsScore(critique=5, secondaire=1)),
        description="Options pour le matching",
    )
    scoring: Optional[ScoringOptions] = Field(
        ScoringOptions(
            z_unmatched=0,
            e_unmatched=0.9,
            g_unknown_score=0.8,
            c_unknown_score=0,
            v_blocked=-20.0,
            v_different=-0.3,
            t_unmatched=0.2,
        ),
        description="Options pour le scoring",
    )
    rerank: Optional[RerankingOptions] = Field(
        RerankingOptions(top_k=24, use_rerank=False, parcours="", id_prompt=112),
        description="Options pour le reranking",
    )
    # autres_criteres        : Optional[Dict[str, Any]]      = Field(None, description = "Autres critères mentionnés par l'acheteur")


class MatchingPayloadIdProduit(MatchingPayload):
    id_produit: Optional[int] = Field(None, description="Identifiant du produit")
    v: int = Field(
        2, description="Pipeline version: 1=Cypher scoring, 2=Python scoring"
    )
    min_matching_cids: int = Field(
        1, description="V2 only: minimum distinct CIDs a product must match to be scored"
    )


""" 
Modèles pour le output : Réponse du matching de produits
 """


class CaracteristiqueMatching(BaseModel):
    statut_matching: int = Field(
        ...,
        description="statut de la matching, 1     : matche, 2   : ecart, 3: bloquant, 4: no_renseigne",
    )
    id_caracteristique: int = Field(
        ..., description="Identifiant de la caractéristique"
    )
    type_caracteristique: int = Field(
        ..., description="Type de la caractéristique, 1: numerique, 2: textuelle"
    )
    valeur: Optional[str] = Field(
        None, description="Valeur associée à la caractéristique numérique"
    )
    valeur_min: Optional[str] = Field(
        None, description="Valeur minimale associée à la caractéristique numérique"
    )
    valeur_max: Optional[str] = Field(
        None, description="Valeur maximale associée à la caractéristique numérique"
    )
    unite: Optional[str] = Field(
        None, description="Unité de la caractéristique numérique"
    )
    id_valeur: Optional[List[int]] = Field(
        default_factory=list,
        description="Liste des valeurs associées à la caractéristique",
    )
    poids: int = Field(..., description="Poids de la caractéristique dans le score")
    bareme: float = Field(
        ..., description="Barème de notation pour cette caractéristique"
    )
    poids_question: int = Field(
        ..., description="Poids de la question associée à cette caractéristique"
    )


class Produit(BaseModel):
    rang: int = Field(..., description="Classement du produit")
    id_produit: str = Field(..., description="Identifiant unique du produit")
    score: float = Field(..., description="Score de matching")
    caracteristique: List[CaracteristiqueMatching] = Field(
        ..., description="Détail du matching par caractéristique"
    )
    coeff_geo: float = Field(..., description="Coefficient zone Géographique")
    coeff_type_frns: float = Field(..., description="Coefficient type de fournisseur")
    coeff_etat_score: float = Field(..., description="Coefficient etat score")
    coeff_caracteristique: float = Field(..., description="Coefficient caractéristique")
    info_produit: Optional[Dict[str, Any]] = Field(
        None, description="Informations sur le produit"
    )
    llm_response: Optional[Dict[str, Any]] = Field(
        None, description="Réponse du LLM pour le produit"
    )
    # top_produit    : Optional[bool]                = Field(False, description = "Indique si le produit fait partie des top produits pour la récommendation")
    # raison_matching: str                           = Field(default_factory  = "", description = "Explication du résultat du matching")


class MatchingResponse(BaseModel):
    top_produit: List[Produit] = Field(
        default_factory=list,
        description="Liste des top produits trouvés classés par score",
    )
    liste_produit: List[Produit] = Field(
        default_factory=list, description="Liste des produits trouvés classés par score"
    )
    ecarts: Optional[List[Produit]] = Field(
        None, description="Produits écartés par le LLM lors du reranking"
    )
    temps_de_traitement: float = Field(
        ..., description="Temps pris pour effectuer le matching en secondes"
    )
    # alternative_matching: List[Produit] = Field(default_factory  = list, description = "Liste d'alternatives si applicable")


class PaysCouverture(BaseModel):
    id_pays: str = Field(..., description="Identifiant du pays")
    nom_pays: str = Field(..., description="Nom du pays")
    couvre_partiel: bool = Field(
        ...,
        description="Indique si le fournisseur couvre partiellement le pays (True) ou totalement (False)",
    )


class DepartementCouverture(BaseModel):
    id_dept: str = Field(..., description="Identifiant du département")
    nom_dept: str = Field(..., description="Nom du département")


class FournisseurGeoResponse(BaseModel):
    pays: List[PaysCouverture] = Field(
        default_factory=list, description="Liste des pays couverts par le fournisseur"
    )
    departements: List[DepartementCouverture] = Field(
        default_factory=list,
        description="Liste des départements couverts par le fournisseur",
    )
