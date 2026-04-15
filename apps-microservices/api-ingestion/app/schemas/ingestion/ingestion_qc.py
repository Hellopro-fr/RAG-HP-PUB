# app/schemas/ingestion/ingestion_qc.py
from typing import Annotated, Optional, List
from enum import Enum
from pydantic import BaseModel, Field


class QCServiceStep(str, Enum):
    """Enum des étapes/services du pipeline QC."""
    GENERATION_QUESTION1 = "question1"           # Step 1
    GENERATION_QUESTION2AN = "question2aN"       # Step 2
    GENERATION_CARACTERISTIQUES = "caracteristiques"  # Step 3
    GENERATION_VALEURS = "valeurs"               # Step 4
    ENRICHISSEMENT = "enrichissement"            # Step 5
    EQUIVALENCE = "equivalence"                  # Step 6
    CARACTERISATION = "caracterisation"          # Step 7
    # Hors pipeline QC 1-7 — routing & exchange distincts
    CARACTERISATION_PRIX = "caracterisation_prix"


# Mapping des services vers leurs routing keys
QC_ROUTING_KEYS = {
    QCServiceStep.GENERATION_QUESTION1: "qc.step1.start",
    QCServiceStep.GENERATION_QUESTION2AN: "qc.step2.start",
    QCServiceStep.GENERATION_CARACTERISTIQUES: "qc.step3.start",
    QCServiceStep.GENERATION_VALEURS: "qc.step4.start",
    QCServiceStep.ENRICHISSEMENT: "qc.step5.start",
    QCServiceStep.EQUIVALENCE: "qc.step6.start",
    QCServiceStep.CARACTERISATION: "qc.step7.start",
    QCServiceStep.CARACTERISATION_PRIX: "prix.caracterisation.start",
}

# Exchange distinct pour la caractérisation prix (indépendante du pipeline QC)
QC_EXCHANGES = {
    QCServiceStep.CARACTERISATION_PRIX: "prix_pipeline_exchange",
}


class QCIngestionRequest(BaseModel):
    """Schéma de requête pour l'ingestion vers les services QC."""
    id_categorie: Annotated[
        str,
        Field(
            title="ID de la catégorie",
            description="L'identifiant unique de la catégorie à traiter.",
            examples=["2005800", "2008383"]
        ),
    ]
    is_reset: Annotated[
        bool,
        Field(
            title="Mode reset",
            description="Si True, réinitialise le traitement pour cette catégorie.",
        ),
    ] = False
    service: Annotated[
        QCServiceStep,
        Field(
            title="Service de destination",
            description="Le service QC vers lequel publier le message. Par défaut: question1 (step 1).",
        ),
    ] = QCServiceStep.GENERATION_QUESTION1


class QCIngestionBatchRequest(BaseModel):
    """Schéma pour l'ingestion de plusieurs catégories."""
    categories: Annotated[
        List[str],
        Field(
            title="Liste des IDs de catégorie",
            description="Liste des identifiants de catégories à traiter.",
            examples=[["2005800", "2008383", "2009001"]]
        ),
    ]
    is_reset: Annotated[
        bool,
        Field(
            title="Mode reset",
            description="Si True, réinitialise le traitement pour toutes les catégories.",
        ),
    ] = False
    service: Annotated[
        QCServiceStep,
        Field(
            title="Service de destination",
            description="Le service QC vers lequel publier les messages.",
        ),
    ] = QCServiceStep.GENERATION_QUESTION1


class QCIngestionResponse(BaseModel):
    """Réponse standard pour l'ingestion QC."""
    code: Annotated[int, Field(title="Code de retour")]
    message: Annotated[str, Field(title="Message de retour")]


class QCIngestionResponseSuccess(QCIngestionResponse):
    """Réponse de succès avec détails."""
    details: Annotated[
        dict, 
        Field(title="Détails de la publication")
    ]


class QCIngestionBatchResponse(BaseModel):
    """Réponse pour l'ingestion batch."""
    code: Annotated[int, Field(title="Code de retour")]
    message: Annotated[str, Field(title="Message de retour")]
    total: Annotated[int, Field(title="Nombre total de messages")]
    success_count: Annotated[int, Field(title="Nombre de succès")]
    failed_count: Annotated[int, Field(title="Nombre d'échecs")]
    details: Annotated[
        List[dict], 
        Field(title="Détails par catégorie")
    ]
