import time
from fastapi import APIRouter, HTTPException, status
from app.domain.models import ComplexFilterRequest, ResultProduct, MatchingPayload, MatchingResponse, Produit, CaracteristiqueMatching
from app.services.recommendation_service import recommendation_service

router = APIRouter()


@router.post("/filter", response_model=ResultProduct, response_model_exclude_none=True)
async def complex_filter_products(request: ComplexFilterRequest):
    """
    Advanced filter: Filters products based on detailed constraints.
    Uses V4 Hybrid Logic (Inverted Index + Classic Scoring).
    """
    try:
        if not request.ids:
            return ResultProduct(data=[], info={"message": "No filters provided"})

        # We only support V4 logic in this microservice implementation
        results = await recommendation_service.get_products_by_complex_filters(request)
        return results

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An internal error occurred while filtering products: {str(e)}",
        )


@router.post("/{product_id}/score", response_model=ResultProduct, response_model_exclude_none=True)
async def score_specific_product(product_id: str, request: ComplexFilterRequest):
    """
    Calculates the score of a specific product against the provided complex filters.
    """
    try:
        if not request.ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No filters provided for scoring.",
            )

        result = await recommendation_service.get_products_by_complex_filters(
            request, target_product_id=product_id
        )

        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product '{product_id}' not found or does not match the category filter.",
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An internal error occurred while scoring the product: {str(e)}",
        )



@router.post("/matching", response_model=MatchingResponse)
async def match_products(payload: MatchingPayload):
    """
    Endpoint pour effectuer le matching de produits.
    Recoit un contexte utilisateur et des critères, retourne une liste de produits scorés.
    """
    start_time = time.time()
    
    # Simulation de logique de matching (Dummy implementation)
    """ 
    {
        "id_categorie": 0,
        "top_k": 12,
        "metadonnee_utilisateurs": {
            "pays": "France",
            "typologie": "1"
        },
        "liste_caracteristique": [
            {
                "id_caracteristique": 10,
                "unite": "cm",
                "valeur_cible": {
                    "min": "3000"
                },
                "valeurs_bloquantes": {
                    "max": "2500"
                }
            },
            {
                "id_caracteristique": 11,
                "unite": "km",
                "valeurs_cibles": {
                    "min": "300"
                },
                "valeurs_bloquantes": {
                    "max": "500"
                }
            }
        ]
    } """

    # Ici vous connecterez votre logique métier réelle (IA, Algorithme, etc.)
    
    # Exemple de données mockées basées sur l'entrée
    #TODO: récupération des produits correspondant au requete cypher
    mock_produits = [
        Produit(
            rang=3,
            id_produit="prod_001",
            score=0.95,
            caracteristique=
               [
                    CaracteristiqueMatching(
                        statut_matching=1,
                        id_caracteristique=101,
                        id_valeur=[1, 2],
                        poids=30
                    ),
                    CaracteristiqueMatching(
                        statut_matching=2,
                        id_caracteristique=102,
                        id_valeur=[5],
                        poids=10
                    ),
                    CaracteristiqueMatching(
                        statut_matching=4,
                        id_caracteristique=103,
                        poids=5
                    )
                ],
            # raison_matching=f"par Pays"
        ),
        Produit(
            rang=1,
            id_produit="prod_002",
            score=0.88,
            caracteristique=
               [
                    CaracteristiqueMatching(
                        statut_matching=1,
                        id_caracteristique=101,
                        id_valeur=[1, 2],
                        poids=30
                    ),
                    CaracteristiqueMatching(
                        statut_matching=3,
                        id_caracteristique=102,
                        id_valeur=[5],
                        poids=10
                    )
                ],
            top_produit=True
            # raison_matching=f"par Pays"
        ),
        Produit(
            rang=2,
            id_produit="prod_003",
            score=0.75,
            caracteristique=
               [
                    CaracteristiqueMatching(
                        statut_matching=1,
                        id_caracteristique=105,
                        id_valeur=[],
                        poids=5
                    )
               ],
            top_produit=False
            # raison_matching=f"par Pays"
        )
    ]
    
    # Tri par rang (ordre croissant: rang 1, 2, 3...)
    mock_produits_sorted = sorted(mock_produits, key=lambda x: x.rang)
    # Appliquer le top_k après le tri
    resultats_finaux = mock_produits_sorted[:payload.top_k]

    alternatives = []
    if len(mock_produits_sorted) > payload.top_k:
        alternatives = mock_produits_sorted[payload.top_k:]

    return MatchingResponse(
        liste_produit=resultats_finaux,
        temps_de_traitement=time.time() - start_time,
        alternative_matching=alternatives
    )