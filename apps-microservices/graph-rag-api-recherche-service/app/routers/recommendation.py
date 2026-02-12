import time
from fastapi import APIRouter, HTTPException, status
from app.domain.models import (
    ComplexFilterRequest,
    FilterCaracteristiqueRequest,
    ResultProduct,
    MatchingPayload,
    MatchingPayloadIdProduit,
    MatchingResponse,
    Produit,
    CaracteristiqueMatching,
)
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


@router.post(
    "/filter-by-caracteristique",
    response_model=MatchingResponse,
    response_model_exclude_none=True,
)
async def filter_by_caracteristique(request: MatchingPayload):
    """
    Filter products based on CaracteristiqueTechnique constraints.
    Uses MatchingPayload schema with MatchingOptions.Score for caracteristique weights.
    Weights are determined by poids_caracteristique ("critique" or "secondaire") mapped to options.score values.
    Returns MatchingResponse with liste_produit, top_produit, and temps_de_traitement.
    """
    try:
        if not request.liste_caracteristique:
            return MatchingResponse(
                top_produit=[],
                liste_produit=[],
                temps_de_traitement=0.0,
            )

        results = await recommendation_service.get_products_by_caracteristique_filters(
            request
        )
        return results

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An internal error occurred while filtering products: {str(e)}",
        )


@router.post(
    "/{product_id}/score",
    response_model=ResultProduct,
    response_model_exclude_none=True,
)
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


@router.post(
    "/matching",
    response_model=MatchingResponse,
    response_model_exclude_none=True,
)
async def match_products(request: MatchingPayloadIdProduit):
    """
    Endpoint pour effectuer le matching de produits.
    Recoit un contexte utilisateur et des critères, retourne une liste de produits scorés.
    """
    # start_time = time.time()
    try:
        if not request.liste_caracteristique:
            return MatchingResponse(
                top_produit=[],
                liste_produit=[],
                temps_de_traitement=0.0,
            )

        results = await recommendation_service.get_products_by_caracteristique_filters(
            request
        )
        return results

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An internal error occurred while filtering products: {str(e)}",
        )

    # Simulation de logique de matching (Dummy implementation)
    # """
    # {
    #     "id_categorie": 0,
    #     "top_k": 12,
    #     "metadonnee_utilisateurs": {
    #         "pays": "France",
    #         "typologie": "1"
    #     },
    #     "liste_caracteristique": [
    #         {
    #             "id_caracteristique": 10,
    #             "unite": "cm",
    #             "valeur_cible": {
    #                 "min": "3000"
    #             },
    #             "valeurs_bloquantes": {
    #                 "max": "2500"
    #             }
    #         },
    #         {
    #             "id_caracteristique": 11,
    #             "unite": "km",
    #             "valeurs_cibles": {
    #                 "min": "300"
    #             },
    #             "valeurs_bloquantes": {
    #                 "max": "500"
    #             }
    #         }
    #     ],
    #     "champs_sortie": ["id_produit", "score", "caracteristique", "coeff_geo", "coeff_type_frns"]
    # } """

    # # Ici vous connecterez votre logique métier réelle (IA, Algorithme, etc.)

    # # Exemple de données mockées basées sur l'entrée
    # # TODO: récupération des produits correspondant au requete cypher
    # mock_produits = [
    #     Produit(
    #         rang=3,
    #         id_produit="617565",
    #         score=0.95,
    #         caracteristique=[
    #             CaracteristiqueMatching(
    #                 statut_matching=1,
    #                 id_caracteristique=101,
    #                 type_caracteristique=1,
    #                 valeur="500",
    #                 unite="m",
    #                 id_valeur=[1, 2],
    #                 poids=30,
    #                 bareme=-2.0,
    #                 poids_question=0,
    #             ),
    #             CaracteristiqueMatching(
    #                 statut_matching=2,
    #                 id_caracteristique=102,
    #                 type_caracteristique=2,
    #                 poids=10,
    #                 bareme=-2.0,
    #                 poids_question=0,
    #             ),
    #             CaracteristiqueMatching(
    #                 statut_matching=4,
    #                 id_caracteristique=103,
    #                 type_caracteristique=2,
    #                 poids=5,
    #                 bareme=-2.0,
    #                 poids_question=0,
    #             ),
    #         ],
    #         coeff_geo=1.2,
    #         coeff_type_frns=1.1,
    #         # raison_matching=f"par Pays"
    #     ),
    #     Produit(
    #         rang=1,
    #         id_produit="617564",
    #         score=0.88,
    #         caracteristique=[
    #             CaracteristiqueMatching(
    #                 statut_matching=1,
    #                 id_caracteristique=101,
    #                 type_caracteristique=2,
    #                 id_valeur=[1, 2],
    #                 poids=30,
    #                 bareme=-2.0,
    #                 poids_question=0,
    #             ),
    #             CaracteristiqueMatching(
    #                 statut_matching=3,
    #                 id_caracteristique=102,
    #                 type_caracteristique=2,
    #                 id_valeur=[5],
    #                 poids=10,
    #                 bareme=-2,
    #                 poids_question=1,
    #             ),
    #         ],
    #         coeff_geo=2,
    #         coeff_type_frns=1,
    #         # raison_matching=f"par Pays"
    #     ),
    #     Produit(
    #         rang=2,
    #         id_produit="617563",
    #         score=0.75,
    #         caracteristique=[
    #             CaracteristiqueMatching(
    #                 statut_matching=1,
    #                 id_caracteristique=105,
    #                 type_caracteristique=2,
    #                 id_valeur=[],
    #                 poids=5,
    #                 bareme=3.0,
    #                 poids_question=2,
    #             )
    #         ],
    #         coeff_geo=1.3,
    #         coeff_type_frns=1.5,
    #         # raison_matching=f"par Pays"
    #     ),
    #     Produit(
    #         rang=1,
    #         id_produit="617562",
    #         score=0.75,
    #         caracteristique=[
    #             CaracteristiqueMatching(
    #                 statut_matching=1,
    #                 id_caracteristique=105,
    #                 type_caracteristique=2,
    #                 id_valeur=[],
    #                 poids=5,
    #                 bareme=10.0,
    #                 poids_question=5,
    #             )
    #         ],
    #         coeff_geo=1.4,
    #         coeff_type_frns=1.6,
    #         # raison_matching=f"par Pays"
    #     ),
    #     Produit(
    #         rang=6,
    #         id_produit="617555",
    #         score=0.75,
    #         caracteristique=[
    #             CaracteristiqueMatching(
    #                 statut_matching=1,
    #                 id_caracteristique=105,
    #                 type_caracteristique=2,
    #                 id_valeur=[],
    #                 poids=5,
    #                 bareme=10.0,
    #                 poids_question=5,
    #             )
    #         ],
    #         coeff_geo=1.4,
    #         coeff_type_frns=1.6,
    #         # raison_matching=f"par Pays"
    #     ),
    #     Produit(
    #         rang=7,
    #         id_produit="617554",
    #         score=0.5,
    #         caracteristique=[
    #             CaracteristiqueMatching(
    #                 statut_matching=1,
    #                 id_caracteristique=105,
    #                 type_caracteristique=2,
    #                 id_valeur=[],
    #                 poids=5,
    #                 bareme=10.0,
    #                 poids_question=5,
    #             )
    #         ],
    #         coeff_geo=1.4,
    #         coeff_type_frns=1.6,
    #         # raison_matching=f"par Pays"
    #     ),
    #     Produit(
    #         rang=9,
    #         id_produit="617553",
    #         score=0.1,
    #         caracteristique=[
    #             CaracteristiqueMatching(
    #                 statut_matching=1,
    #                 id_caracteristique=105,
    #                 type_caracteristique=2,
    #                 id_valeur=[],
    #                 poids=5,
    #                 bareme=10.0,
    #                 poids_question=5,
    #             )
    #         ],
    #         coeff_geo=1.4,
    #         coeff_type_frns=1.6,
    #         # raison_matching=f"par Pays"
    #     ),
    #     Produit(
    #         rang=8,
    #         id_produit="617552",
    #         score=0.6,
    #         caracteristique=[
    #             CaracteristiqueMatching(
    #                 statut_matching=1,
    #                 id_caracteristique=105,
    #                 type_caracteristique=2,
    #                 id_valeur=[],
    #                 poids=5,
    #                 bareme=10.0,
    #                 poids_question=5,
    #             )
    #         ],
    #         coeff_geo=1.4,
    #         coeff_type_frns=1.6,
    #         # raison_matching=f"par Pays"
    #     ),
    # ]

    # mock_top_produits = [
    #     Produit(
    #         rang=2,
    #         id_produit="617561",
    #         score=0.5,
    #         caracteristique=[
    #             CaracteristiqueMatching(
    #                 statut_matching=1,
    #                 id_caracteristique=105,
    #                 type_caracteristique=2,
    #                 id_valeur=[],
    #                 poids=6,
    #                 bareme=11.0,
    #                 poids_question=4,
    #             )
    #         ],
    #         coeff_geo=1.2,
    #         coeff_type_frns=0.1,
    #         # raison_matching=f"par Pays"
    #     ),
    #     Produit(
    #         rang=4,
    #         id_produit="617559",
    #         score=0.75,
    #         caracteristique=[
    #             CaracteristiqueMatching(
    #                 statut_matching=1,
    #                 id_caracteristique=105,
    #                 type_caracteristique=2,
    #                 id_valeur=[],
    #                 poids=3,
    #                 bareme=12.0,
    #                 poids_question=3,
    #             )
    #         ],
    #         coeff_geo=0.2,
    #         coeff_type_frns=0.1,
    #         # raison_matching=f"par Pays"
    #     ),
    #     Produit(
    #         rang=3,
    #         id_produit="617557",
    #         score=0.75,
    #         caracteristique=[
    #             CaracteristiqueMatching(
    #                 statut_matching=1,
    #                 id_caracteristique=105,
    #                 type_caracteristique=2,
    #                 id_valeur=[],
    #                 poids=5,
    #                 bareme=10.0,
    #                 poids_question=5,
    #             )
    #         ],
    #         coeff_geo=3.2,
    #         coeff_type_frns=3.1,
    #     ),
    #     Produit(
    #         rang=1,
    #         id_produit="102808",
    #         score=0.3,
    #         caracteristique=[
    #             CaracteristiqueMatching(
    #                 statut_matching=1,
    #                 id_caracteristique=105,
    #                 type_caracteristique=2,
    #                 id_valeur=[],
    #                 poids=5,
    #                 bareme=10.0,
    #                 poids_question=5,
    #             )
    #         ],
    #         coeff_geo=3.2,
    #         coeff_type_frns=3.1,
    #     ),
    # ]
    # # Identifier le top produit
    # top_produit = sorted(mock_top_produits, key=lambda x: x.rang)

    # # Tri par rang (ordre croissant: rang 1, 2, 3...)
    # mock_produits_sorted = sorted(mock_produits, key=lambda x: x.rang)
    # # Appliquer le top_k après le tri
    # resultats_finaux = mock_produits_sorted[: payload.top_k]

    # # alternatives = []
    # # if len(mock_produits_sorted) > payload.top_k:
    # #     alternatives = mock_produits_sorted[payload.top_k:]

    # return MatchingResponse(
    #     top_produit=top_produit,
    #     liste_produit=resultats_finaux,
    #     temps_de_traitement=time.time() - start_time,
    #     # alternative_matching=alternatives
    # )
