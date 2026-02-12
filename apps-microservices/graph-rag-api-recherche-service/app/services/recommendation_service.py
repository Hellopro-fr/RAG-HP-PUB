import logging
import time
import asyncio
from typing import List, Dict, Any, Optional

from app.domain.models import (
    ComplexFilterRequest,
    FilterCaracteristiqueRequest,
    MatchingPayload,
    MatchingPayloadIdProduit,
    MatchingResponse,
    Produit,
    CaracteristiqueMatching,
    ResultProduct,
    ScoredProduct,
)
from app.infrastructure.clients import clients

# from app.services.unit_normalizer import unit_normalizer


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
                    val = self._extract_scalar(raw_target[k])
                    tasks.append(clients.normalize_quantity(val, unit, label))
                else:
                    tasks.append(
                        asyncio.sleep(0)
                    )  # Placeholder to keep index alignment

        # 2. Blocking Numeric
        raw_blocking = c_dict.get("valeurs_bloquantes")
        if isinstance(raw_blocking, dict):
            for k in ["min", "max", "exact"]:
                if raw_blocking.get(k) is not None:
                    val = self._extract_scalar(raw_blocking[k])
                    tasks.append(clients.normalize_quantity(val, unit, label))
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
                [str(x) for x in c_dict.get("valeurs_cibles")]
                if isinstance(c_dict.get("valeurs_cibles"), list)
                else []
            ),
            "blocking_list": (
                [str(x) for x in c_dict.get("valeurs_bloquantes")]
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
        # flat_filters_test = await self._normalize_constraints_for_unwind_test(request)
        # print(f"New implementation flat_filters: {flat_filters}")
        # print(f"Old implementation flat_filters: {flat_filters_test}")
        norm_time = time.perf_counter() - norm_start
        all_rids = [f["rid"] for f in flat_filters]
        weights_map = await self._get_question_weights(all_rids)

        blocked_val = float(request.blocked_val)
        different_val = float(request.different_val)

        # Build Cypher Query (V4) with top_p computed in Cypher
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
                ) THEN $blocked_val
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
                WHEN size(item.matches) > 0 THEN $different_val
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
             [res IN char_results | CASE WHEN res.score = $different_val AND supplier_covers THEN 1.0 ELSE res.score END] AS adjusted_scores
        
        WITH p, rid, char_results, adjusted_scores,
             CASE WHEN $blocked_val IN adjusted_scores THEN $blocked_val ELSE apoc.coll.max(adjusted_scores) END AS rid_score,
             (supplier_covers OR ANY(res IN char_results WHERE res.has_pc OR res.score = $blocked_val)) AS matched,
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
        
        // Collect all scored products
        WITH collect({node: p, details: details, global_score: global_score}) AS all_products
        
        // --- STEP 3: Compute top_p (one top product per fournisseur, limit 4) ---
        WITH all_products,
             // Group by id_fournisseur and get the top product per fournisseur
             [fournisseur_id IN apoc.coll.toSet([prod IN all_products | prod.node.id_fournisseur]) |
                 head([prod IN all_products WHERE prod.node.id_fournisseur = fournisseur_id | prod])
             ] AS top_per_fournisseur
        
        // Sort top_per_fournisseur by global_score descending and limit to 4
        WITH all_products, top_per_fournisseur
        UNWIND top_per_fournisseur AS p_top
        WITH all_products, p_top 
        ORDER BY p_top.global_score DESC 
        LIMIT 4
        
        // First alias the node, then project the node data
        WITH all_products, p_top.node AS top_node, p_top.global_score AS top_score, p_top.details AS top_details
        WITH all_products, top_node TOP_P_PROJECTION_PLACEHOLDER AS top_product_data, top_score, top_details
        WITH all_products, collect({
            product_data: top_product_data,
            score: top_score,
            details: top_details
        }) AS top_p
        
        UNWIND all_products AS prod
        WITH prod.node AS p_node, prod.details AS details, prod.global_score AS global_score, top_p
        RETURN p_node PROJECTION_PLACEHOLDER AS product_data, details, global_score, top_p
        """

        # Determine projection
        if request.output_fields:
            # Ensure we don't have empty list behavior if user sends []
            fields = (
                [f".{f}" for f in request.output_fields]
                if len(request.output_fields) > 0
                else [".*"]
            )
            projection = f"{{ {', '.join(fields)} }}"
        else:
            projection = "{.*}"

        # Inject projection - both placeholders use the same projection format
        cypher_query = cypher_query.replace("TOP_P_PROJECTION_PLACEHOLDER", projection)
        cypher_query = cypher_query.replace("PROJECTION_PLACEHOLDER", projection)

        params = {
            "filters": flat_filters,
            "weights": weights_map,
            "id_categorie": str(request.id_categorie) if request.id_categorie else None,
            "top_k": int(request.top_k),
            "target_product_id": target_product_id,
            "blocked_val": blocked_val,
            "different_val": different_val,
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
            results = await clients.execute_cypher(cypher_query, params)
            # Use direct Neo4j connection to avoid gRPC serialization issues
            # results = await clients.execute_cypher_direct(cypher_query, params)
            query_time = time.perf_counter() - query_start

            # Parse results - now returns rows of products, each containing the top_p list
            scored_products = []
            top_p = []

            if results:
                # Extract top_p from the first row (it's the same for all rows)
                raw_top_p = results[0].get("top_p", [])
                # Convert top_p entries to ScoredProduct objects
                for entry in raw_top_p:
                    if isinstance(entry, dict) and "product_data" in entry:
                        top_p.append(
                            ScoredProduct(
                                **entry["product_data"],
                                score=entry.get("score", 0.0),
                                details=entry.get("details", []),
                                info={"weights": weights_map},
                            )
                        )

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
                top_p=top_p,
            )
        except Exception as e:
            logging.error(f"Recommendation Error: {e}", exc_info=True)
            return ResultProduct(data=[], info={"error": str(e)})

    async def _normalize_constraints_for_caracteristique(
        self, request: MatchingPayload
    ) -> List[Dict[str, Any]]:
        """
        Pre-processes constraints for caracteristique-based filtering.
        Uses MatchingPayload schema with MatchingOptions.Score for weights.
        """
        # Extract caracteristique IDs from the list
        all_char_ids = [
            str(c.id_caracteristique) for c in request.liste_caracteristique
        ]
        label_map = await self._get_characteristic_labels(all_char_ids)

        # Get score weights from options
        score_options = request.options.score if request.options else None
        critique_weight = score_options.critique if score_options else 5
        secondaire_weight = score_options.secondaire if score_options else 1

        flat_filters = []
        normalization_tasks = []
        task_metadata = []  # Track (cid, q_weight, c_weight) for each task

        # First pass: Create tasks
        for c in request.liste_caracteristique:
            cid = str(c.id_caracteristique)
            label = label_map.get(cid, "dimensionless")
            normalization_tasks.append(
                self._normalize_single_constraint_for_matching_payload(c, cid, label)
            )
            # Resolve c_weight from poids_caracteristique using MatchingOptions.Score
            poids_carac = c.poids_caracteristique or "critique"
            if poids_carac == "critique":
                c_weight = critique_weight
            elif poids_carac == "secondaire":
                c_weight = secondaire_weight
            else:
                c_weight = critique_weight  # Default to critique

            q_weight = c.poids_question or 1
            task_metadata.append((cid, q_weight, c_weight))

        # Execute all normalization tasks
        processed_constraints_flat = await asyncio.gather(*normalization_tasks)

        # Second pass: Re-group by caracteristique ID with hierarchical weights
        grouped = {}
        for i, processed in enumerate(processed_constraints_flat):
            cid, q_weight, c_weight = task_metadata[i]
            if cid not in grouped:
                grouped[cid] = {"cid": cid, "q_weight": q_weight, "constraints": []}
            # Add c_weight to the processed constraint
            processed["c_weight"] = c_weight
            grouped[cid]["constraints"].append(processed)

        flat_filters = list(grouped.values())
        return flat_filters

    async def _normalize_single_constraint_for_matching_payload(
        self, c: Any, char_id: str, label: str
    ) -> Dict[str, Any]:
        """
        Helper to normalize a single constraint from MatchingCaracteristique.
        """
        c_dict = c.model_dump()
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
                    val = self._extract_scalar(raw_target[k])
                    tasks.append(clients.normalize_quantity(val, unit, label))
                else:
                    tasks.append(asyncio.sleep(0))

        # 2. Blocking Numeric
        raw_blocking = c_dict.get("valeurs_bloquantes")
        if isinstance(raw_blocking, dict):
            for k in ["min", "max", "exact"]:
                if raw_blocking.get(k) is not None:
                    val = self._extract_scalar(raw_blocking[k])
                    tasks.append(clients.normalize_quantity(val, unit, label))
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
                [str(x) for x in c_dict.get("valeurs_cibles")]
                if isinstance(c_dict.get("valeurs_cibles"), list)
                else []
            ),
            "blocking_list": (
                [str(x) for x in c_dict.get("valeurs_bloquantes")]
                if isinstance(c_dict.get("valeurs_bloquantes"), list)
                else []
            ),
            "target_numeric": target_num,
            "blocking_numeric": blocking_num,
        }

    async def get_products_by_caracteristique_filters(
        self,
        request: MatchingPayloadIdProduit,
        target_product_id: Optional[str] = None,
    ) -> MatchingResponse:
        """
        Get products filtered and scored by CaracteristiqueTechnique constraints.
        Uses MatchingPayload schema with MatchingOptions.Score for caracteristique weights.
        Includes geographic zone scoring based on MetadonneUtilisateurs.
        """
        start_time = time.perf_counter()

        if request.id_produit is not None:
            target_product_id = str(request.id_produit)
            logging.warning(f"Target product ID: {target_product_id}")

        norm_start = time.perf_counter()
        flat_filters = await self._normalize_constraints_for_caracteristique(request)
        norm_time = time.perf_counter() - norm_start

        # Build weights map from request (cid -> q_weight)
        weights_map = {f["cid"]: f["q_weight"] for f in flat_filters}

        # Use default values for blocked_val and different_val
        blocked_val = -2.0
        different_val = -0.3

        # Extract user location data from metadonnee_utilisateurs
        user_meta = request.metadonnee_utilisateurs
        user_cp = user_meta.cp if user_meta else None
        user_dept = user_cp[:2] if user_cp and len(user_cp) >= 2 else None
        user_id_pays = user_meta.id_pays if user_meta else None
        user_typologie = user_meta.typologie if user_meta else None

        z_unmatched = 0.2
        e_unmatched = 0.8
        g_unknown_score = 0.8
        c_unknown_score = 0.5

        if target_product_id:
            logging.info(f"Target product ID: {target_product_id}")
            logging.info(f"Filters: {flat_filters}")

        # Build Cypher Query Step 1 (Dynamic)
        if target_product_id:
            logging.warning(f"Target product ID: {target_product_id}")
            query_step_1 = """
             MATCH (p:Produit)
             WHERE toString(p.id) = $target_product_id
             WITH p, $filters AS active_filters
             """
        else:
            query_step_1 = """
             UNWIND $filters AS f
             MATCH (pc:CaracteristiqueTechnique)
             WHERE toString(pc.id_source_caracteristique) = f.cid
             MATCH (p:Produit)-[:A_POUR_CARACTERISTIQUE]->(pc)
             
             WHERE ($id_categorie IS NULL OR p.id_categorie = $id_categorie)
             
             WITH DISTINCT p, $filters AS active_filters
             """

        # --- STEP 2: SCORING ---
        query_step_2 = """
        // --- STEP 2: SCORING by CaracteristiqueTechnique with CONTINUOUS SCORING ---
        UNWIND active_filters AS f
        
        // Match Characteristics for the specific caracteristique ID
        OPTIONAL MATCH (p)-[:A_POUR_CARACTERISTIQUE]->(pc:CaracteristiqueTechnique)
        WHERE toString(pc.id_source_caracteristique) = f.cid
        
        // Bundle Constraints with their matching Characteristics
        WITH p, f, collect(pc) AS pcs
        WITH p, f, [c IN f.constraints | {
            cid: c.id_caracteristique,
            conf: c,
            matches: [pc IN pcs WHERE toString(pc.id_source_caracteristique) = toString(c.id_caracteristique)]
        }] AS constraint_data
        
        // Evaluate Scores per Characteristic ID with CONTINUOUS SCORING FORMULAS
        WITH p, f, [item IN constraint_data | {
            cid: item.cid,
            score: CASE 
                // ============== TARGET LIST CHECK (Priority for text type) ==============
                // If ANY node matches a target value, prioritize it over blocking
                // This handles products with multiple text nodes for the same characteristic
                WHEN ANY(pc IN item.matches WHERE 
                    size(item.conf.target_list) > 0 AND (toString(pc.id_source_valeur) IN item.conf.target_list OR toString(pc.valeur) IN item.conf.target_list)
                ) THEN 1.0
                
                // ============== BLOCKING CHECK (Fatal Mismatch) ==============
                // Only reached if no target list match was found above
                WHEN ANY(pc IN item.matches WHERE 
                    (size(item.conf.blocking_list) > 0 AND (toString(pc.id_source_valeur) IN item.conf.blocking_list OR toString(pc.valeur) IN item.conf.blocking_list))
                    OR
                    (item.conf.blocking_numeric IS NOT NULL AND (item.conf.blocking_numeric.unit IS NULL OR pc.unite_canonique = item.conf.blocking_numeric.unit) AND (
                        (item.conf.blocking_numeric.min IS NOT NULL AND ((pc.type_donnee = 'numeric' AND pc.valeur_canonique >= item.conf.blocking_numeric.min) OR (pc.type_donnee = 'numeric_range' AND pc.valeur_min_canonique >= item.conf.blocking_numeric.min))) OR
                        (item.conf.blocking_numeric.max IS NOT NULL AND ((pc.type_donnee = 'numeric' AND pc.valeur_canonique <= item.conf.blocking_numeric.max) OR (pc.type_donnee = 'numeric_range' AND pc.valeur_max_canonique <= item.conf.blocking_numeric.max))) OR
                        (item.conf.blocking_numeric.exact IS NOT NULL AND ((pc.type_donnee = 'numeric' AND pc.valeur_canonique = item.conf.blocking_numeric.exact) OR (pc.type_donnee = 'numeric_range' AND pc.valeur_min_canonique <= item.conf.blocking_numeric.exact AND pc.valeur_max_canonique >= item.conf.blocking_numeric.exact)))
                    ))
                ) THEN $blocked_val
                
                // ============== CONTINUOUS NUMERIC SCORING WITH THRESHOLD ==============
                // New logic: Calculate direct score + inverted score, apply 0.8 threshold each
                WHEN ANY(pc IN item.matches WHERE 
                    item.conf.target_numeric IS NOT NULL 
                    AND (item.conf.target_numeric.unit IS NULL OR pc.unite_canonique = item.conf.target_numeric.unit)
                ) THEN
                    apoc.coll.max([pc IN item.matches WHERE 
                        item.conf.target_numeric IS NOT NULL 
                        AND (item.conf.target_numeric.unit IS NULL OR pc.unite_canonique = item.conf.target_numeric.unit)
                    | 
                        // Get the target value (use exact, or min, or max as the reference)
                        CASE
                            WHEN pc.type_donnee = 'numeric' THEN
                                CASE
                                    // === EXACT: Calculate as min=X AND max=X with threshold ===
                                    WHEN item.conf.target_numeric.exact IS NOT NULL THEN
                                        // Direct: Check if product >= exact (min check)
                                        // Inverted: Check if product <= exact (max check)
                                        CASE 
                                            WHEN item.conf.target_numeric.exact = 0 THEN 
                                                CASE WHEN pc.valeur_canonique = 0 THEN 1.0 ELSE 0.0 END
                                            ELSE
                                                // min_score: N/P if P >= N, else 0
                                                // max_score: P/N if P <= N, else 0
                                                    apoc.coll.max([
                                                        CASE 
                                                            WHEN pc.valeur_canonique >= item.conf.target_numeric.exact 
                                                            THEN CASE 
                                                                WHEN toFloat(item.conf.target_numeric.exact / pc.valeur_canonique) >= 0.8 
                                                                THEN toFloat(item.conf.target_numeric.exact / pc.valeur_canonique)
                                                                ELSE 0.0 
                                                            END
                                                            ELSE 0.0 
                                                        END,
                                                        CASE 
                                                            WHEN pc.valeur_canonique <= item.conf.target_numeric.exact 
                                                            THEN CASE 
                                                                WHEN toFloat(pc.valeur_canonique / item.conf.target_numeric.exact) >= 0.8 
                                                                THEN toFloat(pc.valeur_canonique / item.conf.target_numeric.exact)
                                                                ELSE 0.0 
                                                            END
                                                            ELSE 0.0 
                                                        END
                                                    ])
                                        END
                                        
                                    // === MIN ONLY: Direct=min score, Inverted=max score ===
                                    WHEN item.conf.target_numeric.min IS NOT NULL AND item.conf.target_numeric.max IS NULL THEN
                                        CASE
                                            WHEN pc.valeur_canonique = 0 OR item.conf.target_numeric.min = 0 THEN 0.0
                                            ELSE
                                                // direct_score: N_min / P_val (if P >= N_min)
                                                // inverted_score: P_val / N_min (if P <= N_min, treat as max)
                                                apoc.coll.max([
                                                    CASE 
                                                        WHEN pc.valeur_canonique >= item.conf.target_numeric.min 
                                                        THEN CASE 
                                                            WHEN toFloat(item.conf.target_numeric.min / pc.valeur_canonique) >= 0.8 
                                                            THEN toFloat(item.conf.target_numeric.min / pc.valeur_canonique)
                                                            ELSE 0.0 
                                                        END
                                                        ELSE 0.0 
                                                    END,
                                                    CASE 
                                                        WHEN pc.valeur_canonique <= item.conf.target_numeric.min 
                                                        THEN CASE 
                                                            WHEN toFloat(pc.valeur_canonique / item.conf.target_numeric.min) >= 0.8 
                                                            THEN toFloat(pc.valeur_canonique / item.conf.target_numeric.min)
                                                            ELSE 0.0 
                                                        END
                                                        ELSE 0.0 
                                                    END
                                                ])
                                        END
                                        
                                    // === MAX ONLY: Direct=max score, Inverted=min score ===
                                    WHEN item.conf.target_numeric.max IS NOT NULL AND item.conf.target_numeric.min IS NULL THEN
                                        CASE
                                            WHEN pc.valeur_canonique = 0 OR item.conf.target_numeric.max = 0 THEN 0.0
                                            ELSE
                                                // direct_score: P_val / N_max (if P <= N_max)
                                                // inverted_score: N_max / P_val (if P >= N_max, treat as min)
                                                apoc.coll.max([
                                                    CASE 
                                                        WHEN pc.valeur_canonique <= item.conf.target_numeric.max 
                                                        THEN CASE 
                                                            WHEN toFloat(pc.valeur_canonique / item.conf.target_numeric.max) >= 0.8 
                                                            THEN toFloat(pc.valeur_canonique / item.conf.target_numeric.max)
                                                            ELSE 0.0 
                                                        END
                                                        ELSE 0.0 
                                                    END,
                                                    CASE 
                                                        WHEN pc.valeur_canonique >= item.conf.target_numeric.max 
                                                        THEN CASE 
                                                            WHEN toFloat(item.conf.target_numeric.max / pc.valeur_canonique) >= 0.8 
                                                            THEN toFloat(item.conf.target_numeric.max / pc.valeur_canonique)
                                                            ELSE 0.0 
                                                        END
                                                        ELSE 0.0 
                                                    END
                                                ])
                                        END
                                        
                                    // === RANGE (min+max): Keep existing logic ===
                                    WHEN item.conf.target_numeric.min IS NOT NULL AND item.conf.target_numeric.max IS NOT NULL THEN
                                        CASE
                                            WHEN pc.valeur_canonique >= item.conf.target_numeric.min 
                                                 AND pc.valeur_canonique <= item.conf.target_numeric.max 
                                            THEN 1.0
                                            ELSE 0.0
                                        END
                                        
                                    ELSE 1.0
                                END
                                
                            // === PRODUCT HAS RANGE ===
                            WHEN pc.type_donnee = 'numeric_range' THEN
                                CASE
                                    // EXACT: Check if exact value is within product range
                                    WHEN item.conf.target_numeric.exact IS NOT NULL THEN
                                        CASE
                                            WHEN (pc.valeur_min_canonique IS NULL OR pc.valeur_min_canonique <= item.conf.target_numeric.exact)
                                                 AND (pc.valeur_max_canonique IS NULL OR pc.valeur_max_canonique >= item.conf.target_numeric.exact)
                                            THEN 1.0
                                            ELSE 0.0
                                        END
                                        
                                    // MIN ONLY: Use product's max capability with threshold
                                    WHEN item.conf.target_numeric.min IS NOT NULL AND item.conf.target_numeric.max IS NULL THEN
                                        CASE
                                            WHEN pc.valeur_max_canonique IS NOT NULL AND pc.valeur_max_canonique >= item.conf.target_numeric.min THEN
                                                CASE 
                                                    WHEN toFloat(item.conf.target_numeric.min / pc.valeur_max_canonique) >= 0.8 
                                                    THEN toFloat(item.conf.target_numeric.min / pc.valeur_max_canonique)
                                                    ELSE 0.0 
                                                END
                                            ELSE 0.0
                                        END
                                        
                                    // MAX ONLY: Use product's min capability with threshold
                                    WHEN item.conf.target_numeric.max IS NOT NULL AND item.conf.target_numeric.min IS NULL THEN
                                        CASE
                                            WHEN pc.valeur_min_canonique IS NOT NULL AND pc.valeur_min_canonique <= item.conf.target_numeric.max THEN
                                                CASE 
                                                    WHEN toFloat(pc.valeur_min_canonique / item.conf.target_numeric.max) >= 0.8 
                                                    THEN toFloat(pc.valeur_min_canonique / item.conf.target_numeric.max)
                                                    ELSE 0.0 
                                                END
                                            ELSE 0.0
                                        END
                                        
                                    // RANGE: Jaccard-style overlap
                                    WHEN item.conf.target_numeric.min IS NOT NULL AND item.conf.target_numeric.max IS NOT NULL THEN
                                        CASE
                                            WHEN pc.valeur_min_canonique IS NOT NULL AND pc.valeur_max_canonique IS NOT NULL THEN
                                                CASE
                                                    WHEN pc.valeur_max_canonique < item.conf.target_numeric.min 
                                                         OR pc.valeur_min_canonique > item.conf.target_numeric.max 
                                                    THEN 0.0
                                                    WHEN item.conf.target_numeric.max - item.conf.target_numeric.min = 0 THEN 1.0
                                                    ELSE toFloat(
                                                        (CASE 
                                                            WHEN pc.valeur_max_canonique < item.conf.target_numeric.max 
                                                            THEN pc.valeur_max_canonique 
                                                            ELSE item.conf.target_numeric.max 
                                                        END
                                                        -
                                                        CASE 
                                                            WHEN pc.valeur_min_canonique > item.conf.target_numeric.min 
                                                            THEN pc.valeur_min_canonique 
                                                            ELSE item.conf.target_numeric.min 
                                                        END)
                                                        /
                                                        (item.conf.target_numeric.max - item.conf.target_numeric.min)
                                                    )
                                                END
                                            ELSE 0.5
                                        END
                                        
                                    ELSE 1.0
                                END
                                
                            ELSE 1.0
                        END
                    ])
                
                // Connected Check
                WHEN size(item.matches) > 0 THEN $different_val
                // Default
                ELSE $c_unknown_score
            END,
            has_pc: size(item.matches) > 0,
            c_weight: item.conf.c_weight,
            // Matched nodes with per-node score for best-node selection
            matched_nodes: [pc IN item.matches | apoc.map.merge(properties(pc), {
                node_score: CASE
                    // Text target match
                    WHEN size(item.conf.target_list) > 0 AND (toString(pc.id_source_valeur) IN item.conf.target_list OR toString(pc.valeur) IN item.conf.target_list)
                    THEN 1.0
                    // Text blocking match
                    WHEN (size(item.conf.blocking_list) > 0 AND (toString(pc.id_source_valeur) IN item.conf.blocking_list OR toString(pc.valeur) IN item.conf.blocking_list))
                        OR
                        (item.conf.blocking_numeric IS NOT NULL AND (item.conf.blocking_numeric.unit IS NULL OR pc.unite_canonique = item.conf.blocking_numeric.unit) AND (
                            (item.conf.blocking_numeric.min IS NOT NULL AND ((pc.type_donnee = 'numeric' AND pc.valeur_canonique >= item.conf.blocking_numeric.min) OR (pc.type_donnee = 'numeric_range' AND pc.valeur_min_canonique >= item.conf.blocking_numeric.min))) OR
                            (item.conf.blocking_numeric.max IS NOT NULL AND ((pc.type_donnee = 'numeric' AND pc.valeur_canonique <= item.conf.blocking_numeric.max) OR (pc.type_donnee = 'numeric_range' AND pc.valeur_max_canonique <= item.conf.blocking_numeric.max))) OR
                            (item.conf.blocking_numeric.exact IS NOT NULL AND ((pc.type_donnee = 'numeric' AND pc.valeur_canonique = item.conf.blocking_numeric.exact) OR (pc.type_donnee = 'numeric_range' AND pc.valeur_min_canonique <= item.conf.blocking_numeric.exact AND pc.valeur_max_canonique >= item.conf.blocking_numeric.exact)))
                        ))
                    THEN $blocked_val
                    // Numeric target scoring (same formulas as the score field above)
                    WHEN item.conf.target_numeric IS NOT NULL AND (item.conf.target_numeric.unit IS NULL OR pc.unite_canonique = item.conf.target_numeric.unit)
                    THEN
                        CASE
                            WHEN pc.type_donnee = 'numeric' THEN
                                CASE
                                    WHEN item.conf.target_numeric.exact IS NOT NULL THEN
                                        CASE 
                                            WHEN item.conf.target_numeric.exact = 0 THEN 
                                                CASE WHEN pc.valeur_canonique = 0 THEN 1.0 ELSE 0.0 END
                                            ELSE
                                                apoc.coll.max([
                                                    CASE WHEN pc.valeur_canonique >= item.conf.target_numeric.exact AND toFloat(item.conf.target_numeric.exact / pc.valeur_canonique) >= 0.8 THEN toFloat(item.conf.target_numeric.exact / pc.valeur_canonique) ELSE 0.0 END,
                                                    CASE WHEN pc.valeur_canonique <= item.conf.target_numeric.exact AND toFloat(pc.valeur_canonique / item.conf.target_numeric.exact) >= 0.8 THEN toFloat(pc.valeur_canonique / item.conf.target_numeric.exact) ELSE 0.0 END
                                                ])
                                        END
                                    WHEN item.conf.target_numeric.min IS NOT NULL AND item.conf.target_numeric.max IS NULL THEN
                                        CASE WHEN pc.valeur_canonique = 0 OR item.conf.target_numeric.min = 0 THEN 0.0 ELSE
                                            apoc.coll.max([
                                                CASE WHEN pc.valeur_canonique >= item.conf.target_numeric.min AND toFloat(item.conf.target_numeric.min / pc.valeur_canonique) >= 0.8 THEN toFloat(item.conf.target_numeric.min / pc.valeur_canonique) ELSE 0.0 END,
                                                CASE WHEN pc.valeur_canonique <= item.conf.target_numeric.min AND toFloat(pc.valeur_canonique / item.conf.target_numeric.min) >= 0.8 THEN toFloat(pc.valeur_canonique / item.conf.target_numeric.min) ELSE 0.0 END
                                            ])
                                        END
                                    WHEN item.conf.target_numeric.max IS NOT NULL AND item.conf.target_numeric.min IS NULL THEN
                                        CASE WHEN pc.valeur_canonique = 0 OR item.conf.target_numeric.max = 0 THEN 0.0 ELSE
                                            apoc.coll.max([
                                                CASE WHEN pc.valeur_canonique <= item.conf.target_numeric.max AND toFloat(pc.valeur_canonique / item.conf.target_numeric.max) >= 0.8 THEN toFloat(pc.valeur_canonique / item.conf.target_numeric.max) ELSE 0.0 END,
                                                CASE WHEN pc.valeur_canonique >= item.conf.target_numeric.max AND toFloat(item.conf.target_numeric.max / pc.valeur_canonique) >= 0.8 THEN toFloat(item.conf.target_numeric.max / pc.valeur_canonique) ELSE 0.0 END
                                            ])
                                        END
                                    WHEN item.conf.target_numeric.min IS NOT NULL AND item.conf.target_numeric.max IS NOT NULL THEN
                                        CASE WHEN pc.valeur_canonique >= item.conf.target_numeric.min AND pc.valeur_canonique <= item.conf.target_numeric.max THEN 1.0 ELSE 0.0 END
                                    ELSE 1.0
                                END
                            WHEN pc.type_donnee = 'numeric_range' THEN
                                CASE
                                    WHEN item.conf.target_numeric.exact IS NOT NULL THEN
                                        CASE WHEN (pc.valeur_min_canonique IS NULL OR pc.valeur_min_canonique <= item.conf.target_numeric.exact) AND (pc.valeur_max_canonique IS NULL OR pc.valeur_max_canonique >= item.conf.target_numeric.exact) THEN 1.0 ELSE 0.0 END
                                    WHEN item.conf.target_numeric.min IS NOT NULL AND item.conf.target_numeric.max IS NULL THEN
                                        CASE WHEN pc.valeur_max_canonique IS NOT NULL AND pc.valeur_max_canonique >= item.conf.target_numeric.min THEN
                                            CASE WHEN toFloat(item.conf.target_numeric.min / pc.valeur_max_canonique) >= 0.8 THEN toFloat(item.conf.target_numeric.min / pc.valeur_max_canonique) ELSE 0.0 END
                                        ELSE 0.0 END
                                    WHEN item.conf.target_numeric.max IS NOT NULL AND item.conf.target_numeric.min IS NULL THEN
                                        CASE WHEN pc.valeur_min_canonique IS NOT NULL AND pc.valeur_min_canonique <= item.conf.target_numeric.max THEN
                                            CASE WHEN toFloat(pc.valeur_min_canonique / item.conf.target_numeric.max) >= 0.8 THEN toFloat(pc.valeur_min_canonique / item.conf.target_numeric.max) ELSE 0.0 END
                                        ELSE 0.0 END
                                    WHEN item.conf.target_numeric.min IS NOT NULL AND item.conf.target_numeric.max IS NOT NULL THEN
                                        CASE WHEN pc.valeur_min_canonique IS NOT NULL AND pc.valeur_max_canonique IS NOT NULL THEN
                                            CASE
                                                WHEN pc.valeur_max_canonique < item.conf.target_numeric.min OR pc.valeur_min_canonique > item.conf.target_numeric.max THEN 0.0
                                                WHEN item.conf.target_numeric.max - item.conf.target_numeric.min = 0 THEN 1.0
                                                ELSE toFloat(
                                                    (CASE WHEN pc.valeur_max_canonique < item.conf.target_numeric.max THEN pc.valeur_max_canonique ELSE item.conf.target_numeric.max END
                                                     - CASE WHEN pc.valeur_min_canonique > item.conf.target_numeric.min THEN pc.valeur_min_canonique ELSE item.conf.target_numeric.min END)
                                                    / (item.conf.target_numeric.max - item.conf.target_numeric.min)
                                                )
                                            END
                                        ELSE 0.5 END
                                    ELSE 1.0
                                END
                            ELSE 0.0
                        END
                    // Connected but no specific match
                    ELSE 0.0
                END
            })]
        }] AS char_results
        
        // --- HIERARCHICAL SCORING ---
        // Formula:
        //   score_char = matching_score × c_weight
        //   score_q = Σ(score_char) / Σ(c_weight) for same q_weight group
        //   score_final = Σ(score_q) / Σ(q_weight)
        
        // Aggregate per caracteristique with c_weight weighted scores
        WITH p, f.cid AS cid, f.q_weight AS q_weight, char_results,
             // Calculate weighted score: matching_score × c_weight
             reduce(s = 0.0, res IN char_results | s + (
                 CASE WHEN res.score = $blocked_val THEN $blocked_val * res.c_weight
                 ELSE res.score * res.c_weight END
             )) AS weighted_score_sum,
             reduce(w = 0.0, res IN char_results | w + res.c_weight) AS c_weight_sum,
             ANY(res IN char_results WHERE res.score = $blocked_val) AS has_blocking,
             ANY(res IN char_results WHERE res.has_pc) AS matched
        
        // Calculate score per q_weight group: Σ(score × c_weight) / Σ(c_weight)
        WITH p, q_weight, cid, char_results,
             CASE 
                 WHEN has_blocking THEN $blocked_val
                 WHEN c_weight_sum = 0 THEN 0.0
                 ELSE weighted_score_sum / c_weight_sum
             END AS cid_score,
             c_weight_sum,
             matched,
             // Flatten matched nodes from all char_results
             apoc.coll.flatten([res IN char_results | res.matched_nodes]) AS matched_nodes
        
        // Collect all cid scores grouped by q_weight
        WITH p, collect({
            cid: cid, 
            score: cid_score,
            c_weight_sum: c_weight_sum,
            q_weight: q_weight,
            matched: matched,
            matched_nodes: matched_nodes
        }) AS all_constraints
        
        // Group by q_weight and calculate score per q_weight group
        WITH p, all_constraints,
             apoc.coll.toSet([c IN all_constraints | c.q_weight]) AS unique_q_weights
        
        WITH p, all_constraints, [qw IN unique_q_weights | {
            q_weight: qw,
            constraints: [c IN all_constraints WHERE c.q_weight = qw],
            // score_q = Σ(cid_score × c_weight_sum) / Σ(c_weight_sum) for this q_weight
            // Actually per formula: score_q = Σ(score_char) / Σ(c_weight) = cid_score (already computed)
            // Since each cid has one cid_score, score_q = average of cid_scores in group weighted by c_weight_sum
            group_score: CASE 
                WHEN reduce(w = 0.0, c IN [c IN all_constraints WHERE c.q_weight = qw] | w + c.c_weight_sum) = 0 
                THEN 0.0
                ELSE reduce(s = 0.0, c IN [c IN all_constraints WHERE c.q_weight = qw] | s + (c.score * c.c_weight_sum)) 
                     / reduce(w = 0.0, c IN [c IN all_constraints WHERE c.q_weight = qw] | w + c.c_weight_sum)
            END
        }] AS q_weight_groups
        
        // Final score: Σ(score_q) / Σ(q_weight)
        WITH p, q_weight_groups,
             reduce(s = 0.0, g IN q_weight_groups | s + (g.group_score * g.q_weight)) AS numerator,
             reduce(w = 0.0, g IN q_weight_groups | w + g.q_weight) AS denominator
        
        WITH p, q_weight_groups AS details, 
             CASE WHEN denominator = 0 THEN 0.0 ELSE (numerator / denominator) END AS global_score
        
        // --- STEP 2.5: ZONE SCORING based on MetadonneUtilisateurs ---
        // Get the product's fournisseur
        OPTIONAL MATCH (p)-[:EST_PROPOSE_PAR]->(f:Fournisseur)
        
        // Check for COUVRE_PAYS relationships with couvre_tous, couvre, ne_couvre_pas properties
        OPTIONAL MATCH (f)-[r_pays:COUVRE_PAYS]->(pays:Pays)
        
        // Check for COUVRE_ZONE relationships with couvre_tous, couvre, ne_couvre_pas properties
        OPTIONAL MATCH (f)-[r_zone:COUVRE_ZONE]->(zone:ZoneGeo)
        
        WITH p, details, global_score, f,
             collect(DISTINCT {
                 pays: pays, 
                 id_pays: pays.id_pays, 
                 partiel: r_pays.partiel,
                 couvre_tous: r_pays.couvre_tous, 
                 couvre: r_pays.couvre, 
                 ne_couvre_pas: r_pays.ne_couvre_pas
             }) AS pays_rels,
             collect(DISTINCT {
                 zone: zone,
                 id_dept: zone.id_dept,
                 couvre_tous: r_zone.couvre_tous,
                 couvre: r_zone.couvre,
                 ne_couvre_pas: r_zone.ne_couvre_pas
             }) AS zone_rels,
             { id_etat: f.id_etat, id_affichage: f.id_affichage, typologie: f.typologie } AS info_soc
        
        // Calculate zone_score based on the algorithm:
        // 1. If has pays relation:
        //    a. Check partiel:
        //       - If partiel=true: full algorithm (couvre_tous + categorie + dept-level zone check)
        //       - If partiel=false: only check couvre_tous + categorie (no dept drill-down)
        // 2. If no pays relation but has zonegeographique relation: same logic as above
        // 3. If neither exists: score=g_unknown_score
        WITH p, info_soc, details, global_score, pays_rels, zone_rels,
             CASE
                 // Case 1: Has pays relations
                 WHEN size(pays_rels) > 0 AND pays_rels[0].pays IS NOT NULL THEN
                     CASE
                         // Case 1a: partiel=true -> full algorithm (couvre_tous + categorie + dept check)
                         WHEN ANY(pr IN pays_rels WHERE pr.partiel = true) THEN
                             CASE
                                 // couvre_tous=false -> check categorie, then dept
                                 WHEN ANY(pr IN pays_rels WHERE pr.partiel = true AND pr.couvre_tous = false) THEN
                                     CASE
                                         // Check if id_categorie is in couvre list
                                         WHEN ANY(pr IN pays_rels WHERE pr.partiel = true AND pr.couvre_tous = false AND $id_categorie IN coalesce(pr.couvre, [])) THEN
                                             // Now check if user_dept matches any zone id_dept
                                             CASE
                                                 WHEN $user_dept IS NULL THEN $g_unknown_score
                                                 WHEN ANY(zr IN zone_rels WHERE zr.zone IS NOT NULL AND toString(zr.id_dept) = toString($user_dept)) THEN 1.0
                                                 ELSE $g_unknown_score
                                             END
                                         // Check if id_categorie is in ne_couvre_pas list
                                         WHEN ANY(pr IN pays_rels WHERE pr.partiel = true AND pr.couvre_tous = false AND $id_categorie IN coalesce(pr.ne_couvre_pas, [])) THEN $z_unmatched
                                         // id_categorie not in either list
                                         ELSE $g_unknown_score
                                     END
                                 // couvre_tous=true -> check only pays match
                                 ELSE
                                     CASE
                                         WHEN $user_id_pays IS NULL THEN $g_unknown_score
                                         WHEN ANY(pr IN pays_rels WHERE toString(pr.id_pays) = toString($user_id_pays)) THEN 1.0
                                         ELSE $z_unmatched
                                     END
                             END
                         // Case 1b: partiel=false -> only check couvre_tous + categorie (no dept drill-down)
                         ELSE
                             CASE
                                 // couvre_tous=true -> just match by id_pays
                                 WHEN ANY(pr IN pays_rels WHERE pr.couvre_tous = true) THEN
                                     CASE
                                         WHEN $user_id_pays IS NULL THEN $g_unknown_score
                                         WHEN ANY(pr IN pays_rels WHERE toString(pr.id_pays) = toString($user_id_pays)) THEN 1.0
                                         ELSE $z_unmatched
                                     END
                                 // couvre_tous=false -> only check categorie (no dept)
                                 ELSE
                                     CASE
                                         WHEN ANY(pr IN pays_rels WHERE pr.couvre_tous = false AND $id_categorie IN coalesce(pr.couvre, [])) THEN 1.0
                                         WHEN ANY(pr IN pays_rels WHERE pr.couvre_tous = false AND $id_categorie IN coalesce(pr.ne_couvre_pas, [])) THEN $z_unmatched
                                         ELSE $g_unknown_score
                                     END
                             END
                     END
                 // Case 2: No pays relation but has zonegeographique relation
                 WHEN size(zone_rels) > 0 AND zone_rels[0].zone IS NOT NULL THEN
                     CASE
                         // Case 2a: couvre_tous=false -> check categorie in couvre/ne_couvre_pas, then check dept
                         WHEN ANY(zr IN zone_rels WHERE zr.couvre_tous = false) THEN
                             CASE
                                 // Check if id_categorie is in couvre list
                                 WHEN ANY(zr IN zone_rels WHERE zr.couvre_tous = false AND $id_categorie IN coalesce(zr.couvre, [])) THEN
                                     // Now check if user_dept matches zone id_dept
                                     CASE
                                         WHEN $user_dept IS NULL THEN $g_unknown_score
                                         WHEN ANY(zr IN zone_rels WHERE zr.zone IS NOT NULL AND toString(zr.id_dept) = toString($user_dept)) THEN 1.0
                                         ELSE $g_unknown_score
                                     END
                                 // Check if id_categorie is in ne_couvre_pas list
                                 WHEN ANY(zr IN zone_rels WHERE zr.couvre_tous = false AND $id_categorie IN coalesce(zr.ne_couvre_pas, [])) THEN $z_unmatched
                                 // id_categorie not in either list
                                 ELSE $g_unknown_score
                             END
                         // Case 2b: couvre_tous=true -> check only dept match
                         ELSE
                             CASE
                                 WHEN $user_dept IS NULL THEN $g_unknown_score
                                 WHEN ANY(zr IN zone_rels WHERE toString(zr.id_dept) = toString($user_dept)) THEN 1.0
                                 ELSE $z_unmatched
                             END
                     END
                 // Case 3: Neither exists
                 ELSE $g_unknown_score
             END AS zone_score

        // Calculate score by Etat and affichage fournisseur
        WITH p, info_soc, details, global_score, zone_score,
             CASE
                WHEN ((info_soc.id_etat = '1') OR ((info_soc.id_etat = '2') AND (info_soc.id_affichage = '1'))) THEN 1.0
                ELSE $e_unmatched
             END AS etat_score
        
        // Calculate typologie score
        WITH p, details, global_score, zone_score, etat_score, info_soc,
             CASE
                WHEN etat_score = 1.0 THEN
                    CASE
                        WHEN $user_typologie IS NOT NULL AND ($user_typologie IN coalesce(info_soc.typologie, []) OR toString($user_typologie) IN coalesce(info_soc.typologie, [])) THEN 1.0
                        ELSE 0.2
                    END
                ELSE 1.0
             END AS typo_score
        
        // Calculate final_score = global_score * zone_score * etat_score * typo_score
        // Filter out products with negative final_score
        // forcer zone_geo à 1
        // global_score * zone_score * etat_score * typo_score AS final_score
        WITH p, details, global_score, 1.0 AS zone_score, etat_score, typo_score, info_soc,
             global_score * zone_score * etat_score * typo_score AS final_score
        WHERE final_score >= 0 OR $target_product_id IS NOT NULL
        WITH p, details, global_score, zone_score, etat_score, typo_score, final_score, info_soc
        ORDER BY final_score DESC
        LIMIT $top_k + 4
        
        // Collect all scored products
        WITH collect({node: p, details: details, global_score: global_score, zone_score: zone_score, etat_score: etat_score, typo_score: typo_score, final_score: final_score, info_soc: info_soc}) AS all_products
        
        // --- STEP 3: Compute top_p (one top product per fournisseur, limit 4) ---
        WITH all_products,
             [fournisseur_id IN apoc.coll.toSet([prod IN all_products | prod.node.id_fournisseur]) |
                 head([prod IN all_products WHERE prod.node.id_fournisseur = fournisseur_id | prod])
             ] AS top_per_fournisseur
        
        // Sort top_per_fournisseur by final_score descending and limit to 4
        WITH all_products, top_per_fournisseur
        UNWIND top_per_fournisseur AS p_top
        WITH all_products, p_top 
        ORDER BY p_top.final_score DESC 
        LIMIT 4
        
        // First alias the node, then project the node data
        WITH all_products, p_top.node AS top_node, p_top.final_score AS top_score, p_top.details AS top_details, p_top.zone_score AS top_zone_score, p_top.global_score AS top_global_score, p_top.etat_score AS top_etat_score, p_top.typo_score AS top_typo_score, p_top.info_soc AS top_info_soc
        WITH all_products, top_node TOP_P_PROJECTION_PLACEHOLDER AS top_product_data, top_score, top_details, top_node.id_produit AS top_id, top_zone_score, top_global_score, top_etat_score, top_typo_score, top_info_soc
        WITH all_products, collect({
            product_data: top_product_data,
            score: top_score,
            details: top_details,
            zone_score: top_zone_score,
            global_score: top_global_score,
            etat_score: top_etat_score,
            typo_score: top_typo_score,
            info_soc: top_info_soc
        }) AS top_p, collect(top_id) AS top_p_ids
        
        // Filter out top_p products from all_products and limit to top_k
        WITH [prod IN all_products WHERE NOT prod.node.id_produit IN top_p_ids][0..$top_k] AS filtered_products, top_p
        
        UNWIND filtered_products AS prod
        WITH prod.node AS p_node, prod.details AS details, prod.global_score AS global_score, prod.zone_score AS zone_score, prod.etat_score AS etat_score, prod.typo_score AS typo_score, prod.final_score AS final_score, prod.info_soc AS info_soc, top_p
        RETURN p_node PROJECTION_PLACEHOLDER AS product_data, details, global_score, zone_score, etat_score, typo_score, final_score, info_soc, top_p
        """

        cypher_query = query_step_1 + query_step_2

        # Determine projection
        if request.champs_sortie:
            fields = (
                [f".{f}" for f in request.champs_sortie]
                if len(request.champs_sortie) > 0
                else [".*"]
            )
            projection = f"{{ {', '.join(fields)} }}"
        else:
            projection = "{.*}"

        # Inject projection
        cypher_query = cypher_query.replace("TOP_P_PROJECTION_PLACEHOLDER", projection)
        cypher_query = cypher_query.replace("PROJECTION_PLACEHOLDER", projection)

        params = {
            "filters": flat_filters,
            "weights": weights_map,
            "id_categorie": (
                str(request.id_categorie) if request.id_categorie is not None else None
            ),
            "top_k": int(request.top_k),
            "target_product_id": (
                str(f"""id_produit_{request.id_produit}""")
                if request.id_produit is not None
                else None
            ),
            "blocked_val": blocked_val,
            "different_val": different_val,
            "user_dept": user_dept,
            "user_id_pays": user_id_pays,
            "z_unmatched": z_unmatched,
            "e_unmatched": e_unmatched,
            "g_unknown_score": g_unknown_score,
            "c_unknown_score": c_unknown_score,
            "user_typologie": user_typologie,
        }

        # Debug: Log parameters
        logging.info("📝 Caracteristique filter params:")
        for key, value in params.items():
            if key not in ["filters", "weights"]:
                logging.info(f"   {key}: {value} (type: {type(value).__name__})")
            else:
                logging.info(
                    f"   {key}: <{len(value) if isinstance(value, (list, dict)) else 1} items>"
                )

        try:
            query_start = time.perf_counter()
            results = await clients.execute_cypher(cypher_query, params)
            query_time = time.perf_counter() - query_start

            # Parse results and convert to MatchingResponse format
            liste_produit = []
            top_produit = []

            def convert_to_caracteristique_matching(
                details: List[Dict[str, Any]], score: float
            ) -> List[CaracteristiqueMatching]:
                """Convert Cypher details to CaracteristiqueMatching list."""
                caracteristiques = []
                for detail in details:
                    # Each detail is a q_weight group containing constraints
                    q_weight = detail.get("q_weight", 1)
                    constraints = detail.get("constraints", [])

                    for constraint in constraints:
                        cid = constraint.get("cid", "0")
                        c_score = constraint.get("score", 0.0)
                        c_weight = constraint.get("c_weight_sum", 1)
                        matched_nodes = constraint.get("matched_nodes", [])

                        # Determine statut_matching based on score
                        # 1: matche (score >= 0.8), 2: ecart (0 < score < 0.8), 3: bloquant (score < 0), 4: non_renseigne (no match)
                        if c_score >= 0.8:
                            statut = 1  # Matche
                        elif c_score == blocked_val:
                            statut = 3  # Bloquant
                        elif c_score == different_val:
                            statut = 2  # Ecart
                        elif len(matched_nodes) == 0:
                            statut = 4  # Non renseigné
                        else:
                            statut = 2  # Ecart

                        # Extract value and unit from the best-scoring matched node
                        valeur = None
                        valeur_min = None
                        valeur_max = None
                        unite = None
                        type_carac = 2  # Default to textuelle
                        id_valeurs = []

                        if matched_nodes:
                            # Pick the node with the highest node_score (computed in Cypher)
                            node = max(
                                matched_nodes, key=lambda n: n.get("node_score", 0)
                            )
                            valeur = (
                                str(node.get("valeur", ""))
                                if node.get("valeur")
                                and node.get("type_donnee") != "text"
                                else None
                            )
                            valeur_min = (
                                str(node.get("valeur_min", ""))
                                if node.get("valeur_min")
                                and node.get("type_donnee") != "text"
                                else None
                            )
                            valeur_max = (
                                str(node.get("valeur_max", ""))
                                if node.get("valeur_max")
                                and node.get("type_donnee") != "text"
                                else None
                            )
                            unite = node.get("unite") or node.get("unite_canonique")
                            type_donnee = node.get("type_donnee", "")
                            type_carac = (
                                1 if type_donnee in ["numeric", "numeric_range"] else 2
                            )
                            if node.get("id_source_valeur"):
                                try:
                                    id_valeurs = [int(node.get("id_source_valeur"))]
                                except (ValueError, TypeError):
                                    id_valeurs = []

                        caracteristiques.append(
                            CaracteristiqueMatching(
                                statut_matching=statut,
                                id_caracteristique=int(cid) if cid.isdigit() else 0,
                                type_caracteristique=type_carac,
                                valeur=valeur,
                                valeur_min=valeur_min,
                                valeur_max=valeur_max,
                                unite=unite,
                                id_valeur=id_valeurs,
                                poids=int(c_weight),
                                bareme=float(c_score),
                                poids_question=int(q_weight),
                            )
                        )

                return caracteristiques

            def build_produit(rec: Dict[str, Any], rang: int) -> Produit:
                """Convert a result record to Produit."""
                product_data = rec.get("product_data", {})
                details = rec.get("details", [])
                final_score = rec.get("final_score", 0.0)
                zone_score = rec.get("zone_score", 1.0)
                etat_score = rec.get("etat_score", 1.0)
                typo_score = rec.get("typo_score", 1.0)
                info_soc = rec.get("info_soc", {})
                carac_score = rec.get("global_score", 0.0)

                if etat_score < 1.0:
                    logging.warning(
                        f"⚠️ [DEBUG] Low etat_score ({etat_score}) for product {product_data.get('id_produit')}. "
                        f"Fournisseur info: {info_soc}"
                    )

                caracteristiques = convert_to_caracteristique_matching(
                    details, final_score
                )

                return Produit(
                    rang=rang,
                    id_produit=str(product_data.get("id_produit", "")),
                    score=float(final_score),
                    caracteristique=caracteristiques,
                    coeff_geo=float(zone_score),
                    coeff_type_frns=float(typo_score),
                    coeff_etat_score=float(etat_score),
                    coeff_caracteristique=float(carac_score),
                )

            if results:
                # Extract top_p from first result
                raw_top_p = results[0].get("top_p", [])

                # Build top_produit list
                for idx, entry in enumerate(raw_top_p):
                    if isinstance(entry, dict) and "product_data" in entry:
                        top_zone_score = entry.get("zone_score", 1.0)
                        top_final_score = entry.get("score", 0.0)
                        top_etat_score = entry.get("etat_score", 1.0)
                        top_typo_score = entry.get("typo_score", 1.0)
                        top_carac_score = entry.get("global_score", 0.0)
                        produit = Produit(
                            rang=idx + 1,
                            id_produit=str(entry["product_data"].get("id_produit", "")),
                            score=float(top_final_score),
                            caracteristique=convert_to_caracteristique_matching(
                                entry.get("details", []), top_final_score
                            ),
                            coeff_geo=float(top_zone_score),
                            coeff_type_frns=float(top_typo_score),
                            coeff_etat_score=float(top_etat_score),
                            coeff_caracteristique=float(top_carac_score),
                        )
                        top_produit.append(produit)

                # Build liste_produit
                for idx, rec in enumerate(results):
                    liste_produit.append(build_produit(rec, idx + 1))

            total_time = time.perf_counter() - start_time
            return MatchingResponse(
                top_produit=top_produit,
                liste_produit=liste_produit,
                temps_de_traitement=total_time,
            )
        except Exception as e:
            logging.error(f"Caracteristique Filter Error: {e}", exc_info=True)
            return MatchingResponse(
                top_produit=[],
                liste_produit=[],
                temps_de_traitement=0.0,
            )


recommendation_service = RecommendationService()
