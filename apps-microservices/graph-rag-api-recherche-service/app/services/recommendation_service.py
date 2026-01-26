import logging
import time
import asyncio
from typing import List, Dict, Any, Optional

from app.domain.models import ComplexFilterRequest, ResultProduct, ScoredProduct
from app.infrastructure.clients import clients


class RecommendationService:
    """
    Implements the V4 Hybrid Recommendation Logic (Inverted Index + Classic Scoring).
    Uses async gRPC calls for normalization.
    """

    def _extract_scalar(self, value: Any) -> Any:
        if isinstance(value, (list, tuple)):
            return value[0] if len(value) > 0 else None
        return value

    async def _get_characteristic_labels(self, char_ids: List[str]) -> Dict[str, str]:
        if not char_ids:
            return {}
        query = """
        MATCH (c:CaracteristiqueTechnique)
        WHERE c.id_source_caracteristique IN $ids
        RETURN DISTINCT c.id_source_caracteristique as id, c.label as label
        """
        try:
            # Ensure IDs are strings for Cypher
            safe_ids = [str(i) for i in char_ids]
            results = await clients.execute_cypher(query, {"ids": safe_ids})
            return {str(row["id"]): row["label"] for row in results}
        except Exception as e:
            logging.error(f"Error fetching characteristic labels: {e}")
            return {}

    async def _normalize_single_constraint(self, c: Any, label: str) -> Dict[str, Any]:
        """
        Helper to normalize a single constraint object asynchronously.
        """
        c_dict = c.model_dump()
        char_id = str(c_dict.get("id_caracteristique"))
        unit = c_dict.get("unite")

        target_num = None
        blocking_num = None

        # Prepare tasks for parallel normalization
        tasks = []

        # 1. Target Numeric
        raw_target = c_dict.get("valeurs_cibles")
        if isinstance(raw_target, dict):
            for k in ["min", "max", "exact"]:
                if raw_target.get(k) is not None:
                    tasks.append(clients.normalize_quantity(raw_target[k], unit, label))
                else:
                    tasks.append(
                        asyncio.sleep(0)
                    )  # Placeholder to keep index alignment

        # 2. Blocking Numeric
        raw_blocking = c_dict.get("valeurs_bloquantes")
        if isinstance(raw_blocking, dict):
            for k in ["min", "max", "exact"]:
                if raw_blocking.get(k) is not None:
                    tasks.append(
                        clients.normalize_quantity(raw_blocking[k], unit, label)
                    )
                else:
                    tasks.append(asyncio.sleep(0))

        # Execute all normalization calls for this constraint in parallel
        results = await asyncio.gather(*tasks)

        # Reconstruct structures
        res_idx = 0

        # Reconstruct Target
        if isinstance(raw_target, dict):
            norm = {"unit": None, "min": None, "max": None, "exact": None}
            for k in ["min", "max", "exact"]:
                res = results[res_idx]
                res_idx += 1
                if isinstance(res, dict) and res:
                    norm[k] = res.get("valeur_canonique")
                    norm["unit"] = res.get("unite_canonique")
            target_num = norm if norm["unit"] else None

        # Reconstruct Blocking
        if isinstance(raw_blocking, dict):
            norm = {"unit": None, "min": None, "max": None, "exact": None}
            for k in ["min", "max", "exact"]:
                res = results[res_idx]
                res_idx += 1
                if isinstance(res, dict) and res:
                    norm[k] = res.get("valeur_canonique")
                    norm["unit"] = res.get("unite_canonique")
            blocking_num = norm if norm["unit"] else None

        return {
            "id_caracteristique": char_id,
            "target_list": (
                c_dict.get("valeurs_cibles")
                if isinstance(c_dict.get("valeurs_cibles"), list)
                else []
            ),
            "blocking_list": (
                c_dict.get("valeurs_bloquantes")
                if isinstance(c_dict.get("valeurs_bloquantes"), list)
                else []
            ),
            "target_numeric": target_num,
            "blocking_numeric": blocking_num,
        }

    async def _normalize_constraints_for_unwind(
        self, request: ComplexFilterRequest
    ) -> List[Dict[str, Any]]:
        """
        Pre-processes constraints into a flat list suitable for Cypher UNWIND.
        Uses asyncio.gather to normalize all constraints in parallel.
        """
        all_char_ids = {
            str(c.id_caracteristique)
            for constraints in request.ids.values()
            for c in constraints
        }
        label_map = await self._get_characteristic_labels(list(all_char_ids))

        flat_filters = []
        normalization_tasks = []

        # First pass: Create tasks
        for rid, constraints in request.ids.items():
            for c in constraints:
                char_id = str(c.id_caracteristique)
                label = label_map.get(char_id, "dimensionless")
                normalization_tasks.append(self._normalize_single_constraint(c, label))

        # Execute all normalization tasks
        processed_constraints_flat = await asyncio.gather(*normalization_tasks)

        # Second pass: Re-group by RID
        # We need to map the flat list back to the structure: [{"rid": rid, "constraints": [...]}]

        # Create an iterator for the results
        res_iter = iter(processed_constraints_flat)

        for rid, constraints in request.ids.items():
            group_constraints = []
            for _ in constraints:
                group_constraints.append(next(res_iter))
            flat_filters.append({"rid": rid, "constraints": group_constraints})

        return flat_filters

    async def _get_question_weights(self, rids: List[str]) -> Dict[str, int]:
        if not rids:
            return {}
        query = """
        MATCH (r:Reponse)<-[:PROPOSE]-(q:Question)
        WHERE r.id_reponse IN $rids
        RETURN r.id_reponse as rid, q.ordre as ordre
        """
        try:
            results = await clients.execute_cypher(query, {"rids": rids})
            rid_to_order = {row["rid"]: row["ordre"] for row in results}
            unique_orders = sorted(list(set(rid_to_order.values())))
            total = len(unique_orders)
            order_to_weight = {
                order: (total - i) for i, order in enumerate(unique_orders)
            }
            return {
                rid: order_to_weight.get(order, 1)
                for rid, order in rid_to_order.items()
            }
        except Exception:
            return {rid: 1 for rid in rids}

    async def get_products_by_complex_filters(
        self, request: ComplexFilterRequest, target_product_id: Optional[str] = None
    ) -> ResultProduct:
        start_time = time.perf_counter()

        norm_start = time.perf_counter()
        flat_filters = await self._normalize_constraints_for_unwind(request)
        norm_time = time.perf_counter() - norm_start
        all_rids = [f["rid"] for f in flat_filters]
        weights_map = await self._get_question_weights(all_rids)

        # Build Cypher Query (V4)
        cypher_query = """
        // --- STEP 1: ANCHOR TRAVERSAL (V3 Strategy) ---
        // Find only relevant products first
        UNWIND $filters AS f
        MATCH (r:Reponse {id_reponse: f.rid})
        MATCH (r)<-[:EQUIVAUT_A|COUVRE]-(intermediate)<-[:A_POUR_CARACTERISTIQUE|EST_PROPOSE_PAR]-(p:Produit)
        
        WHERE ($target_product_id IS NULL OR p.id_produit = $target_product_id)
          AND ($id_categorie IS NULL OR p.id_categorie = $id_categorie)
        
        WITH DISTINCT p, $filters AS active_filters
        
        // --- STEP 2: CLASSIC SCORING (V1 Logic) ---
        // Broadcast filters to the reduced set of products
        UNWIND active_filters AS f
        
        // Bulk Match Characteristics for the specific Response (rid)
        OPTIONAL MATCH (p)-[:A_POUR_CARACTERISTIQUE]->(pc:CaracteristiqueTechnique)-[:EQUIVAUT_A]->(r:Reponse {id_reponse: f.rid})
        
        // Bundle Constraints with their matching Characteristics
        WITH p, f, collect(pc) AS pcs
        WITH p, f, [c IN f.constraints | {
            cid: c.id_caracteristique,
            conf: c,
            matches: [pc IN pcs WHERE toString(pc.id_source_caracteristique) = toString(c.id_caracteristique)]
        }] AS constraint_data
        
        // Evaluate Scores per Characteristic ID
        WITH p, f, [item IN constraint_data | {
            cid: item.cid,
            score: CASE 
                // Blocking Check
                WHEN ANY(pc IN item.matches WHERE 
                    (size(item.conf.blocking_list) > 0 AND (toString(pc.id_source_valeur) IN item.conf.blocking_list OR toString(pc.valeur) IN item.conf.blocking_list))
                    OR
                    (item.conf.blocking_numeric IS NOT NULL AND (item.conf.blocking_numeric.unit IS NULL OR pc.unite_canonique = item.conf.blocking_numeric.unit) AND (
                        (item.conf.blocking_numeric.min IS NOT NULL AND ((pc.type_donnee = 'numeric' AND pc.valeur_canonique >= item.conf.blocking_numeric.min) OR (pc.type_donnee = 'numeric_range' AND pc.valeur_min_canonique >= item.conf.blocking_numeric.min))) OR
                        (item.conf.blocking_numeric.max IS NOT NULL AND ((pc.type_donnee = 'numeric' AND pc.valeur_canonique <= item.conf.blocking_numeric.max) OR (pc.type_donnee = 'numeric_range' AND pc.valeur_max_canonique <= item.conf.blocking_numeric.max))) OR
                        (item.conf.blocking_numeric.exact IS NOT NULL AND ((pc.type_donnee = 'numeric' AND pc.valeur_canonique = item.conf.blocking_numeric.exact) OR (pc.type_donnee = 'numeric_range' AND pc.valeur_min_canonique <= item.conf.blocking_numeric.exact AND pc.valeur_max_canonique >= item.conf.blocking_numeric.exact)))
                    ))
                ) THEN -2.0
                // Target Check
                WHEN ANY(pc IN item.matches WHERE 
                    (size(item.conf.target_list) > 0 AND (toString(pc.id_source_valeur) IN item.conf.target_list OR toString(pc.valeur) IN item.conf.target_list))
                    OR
                    (item.conf.target_numeric IS NOT NULL AND (item.conf.target_numeric.unit IS NULL OR pc.unite_canonique = item.conf.target_numeric.unit) AND (
                        (item.conf.target_numeric.min IS NOT NULL AND ((pc.type_donnee = 'numeric' AND pc.valeur_canonique >= item.conf.target_numeric.min) OR (pc.type_donnee = 'numeric_range' AND (pc.valeur_max_canonique IS NULL OR pc.valeur_max_canonique >= item.conf.target_numeric.min)))) OR
                        (item.conf.target_numeric.max IS NOT NULL AND ((pc.type_donnee = 'numeric' AND pc.valeur_canonique <= item.conf.target_numeric.max) OR (pc.type_donnee = 'numeric_range' AND (pc.valeur_min_canonique IS NULL OR pc.valeur_min_canonique <= item.conf.target_numeric.max)))) OR
                        (item.conf.target_numeric.exact IS NOT NULL AND ((pc.type_donnee = 'numeric' AND pc.valeur_canonique = item.conf.target_numeric.exact) OR (pc.type_donnee = 'numeric_range' AND (pc.valeur_min_canonique IS NULL OR pc.valeur_min_canonique <= item.conf.target_numeric.exact) AND (pc.valeur_max_canonique IS NULL OR pc.valeur_max_canonique >= item.conf.target_numeric.exact))))
                    ))
                ) THEN 1.0
                // Connected Check
                WHEN size(item.matches) > 0 THEN 0.5
                // Default
                ELSE 0.1
            END,
            has_pc: size(item.matches) > 0,
            is_blocked: ANY(pc IN item.matches WHERE (size(item.conf.blocking_list) > 0 OR item.conf.blocking_numeric IS NOT NULL))
        }] AS char_results
        
        // Aggregate Response Score and Weights
        WITH p, f.rid AS rid, char_results,
             EXISTS((p)-[:EST_PROPOSE_PAR]->(:Fournisseur)-[:COUVRE]->(:Reponse {id_reponse: f.rid})) AS supplier_covers
        
        WITH p, rid, char_results, supplier_covers,
             [res IN char_results | res.score] AS raw_scores,
             [res IN char_results | CASE WHEN res.score = 0.5 AND supplier_covers THEN 1.0 ELSE res.score END] AS adjusted_scores
        
        WITH p, rid, char_results, adjusted_scores,
             CASE WHEN -2.0 IN adjusted_scores THEN -2.0 ELSE apoc.coll.max(adjusted_scores) END AS rid_score,
             (supplier_covers OR ANY(res IN char_results WHERE res.has_pc OR res.score = -2.0)) AS matched,
             coalesce($weights[rid], 1.0) as weight
        
        // Global Product Scoring and Detail Construction
        WITH p, collect({
            rid: rid, 
            score: rid_score, 
            weight: weight,
            matched: matched,
            ids: apoc.map.fromPairs([res IN char_results | [res.cid, res.score]])
        }) AS details
        
        WITH p, details,
             reduce(s = 0.0, d IN details | s + (d.score * d.weight)) AS numerator,
             reduce(w = 0.0, d IN details | w + d.weight) AS denominator
        
        WITH p, details, (numerator / denominator) AS global_score
        
        ORDER BY global_score DESC
        LIMIT $top_k
        
        RETURN p {.*} AS product_data, details, global_score
        """

        params = {
            "filters": flat_filters,
            "weights": weights_map,
            "id_categorie": str(request.id_categorie) if request.id_categorie else None,
            "top_k": int(request.top_k),
            "target_product_id": target_product_id,
        }

        # Debug: Log parameters with their types
        logging.info(f"📝 Cypher params being sent:")
        for key, value in params.items():
            if key not in ["filters", "weights"]:  # Skip large nested params
                logging.info(f"   {key}: {value} (type: {type(value).__name__})")
            else:
                logging.info(
                    f"   {key}: <{len(value) if isinstance(value, (list, dict)) else 1} items>"
                )

        try:
            query_start = time.perf_counter()
            # results = await clients.execute_cypher(cypher_query, params)
            # Use direct Neo4j connection to avoid gRPC serialization issues
            results = await clients.execute_cypher_direct(cypher_query, params)
            query_time = time.perf_counter() - query_start

            scored_products = []
            for rec in results:
                scored_products.append(
                    ScoredProduct(
                        **rec["product_data"],
                        score=rec.get("global_score", 0.0),
                        details=rec.get("details", []),
                        info={"weights": weights_map},
                    )
                )

            total_time = time.perf_counter() - start_time
            return ResultProduct(
                data=scored_products,
                info={
                    "query_time": query_time,
                    "normalization_time": norm_time,
                    "total_time": total_time,
                    "count": len(scored_products),
                    "version": "v4_classic_inverted",
                },
            )
        except Exception as e:
            logging.error(f"Recommendation Error: {e}", exc_info=True)
            return ResultProduct(data=[], info={"error": str(e)})


recommendation_service = RecommendationService()
