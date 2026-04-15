import logging
import time
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict

from app.domain.models import (
    MatchingPayload,
    MatchingPayloadIdProduit,
    MatchingResponse,
    Produit,
    CaracteristiqueMatching,
)
from app.infrastructure.clients import clients

# Reuse normalization, enrichment, and scoring params from V1
from app.services.recommendation_service import recommendation_service as v1_service

logging.basicConfig(
    level=logging.WARNING, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Single-pass Cypher Queries — fetch candidates + chars + fournisseur in one call
# Uses IN clause for chars (no UNWIND cartesian product), scoring done in Python
# ---------------------------------------------------------------------------

CYPHER_V2_ANCHOR = """
MATCH (p:Produit)-[:A_POUR_CARACTERISTIQUE]->(pc:CaracteristiqueTechnique)
WHERE pc.id_source_caracteristique IN $all_cids
  AND ($id_categorie IS NULL OR p.id_categorie = $id_categorie)
  AND p.est_actif = true
WITH p, collect({id_source_caracteristique: pc.id_source_caracteristique, id_source_valeur: pc.id_source_valeur, valeur: pc.valeur, valeur_canonique: pc.valeur_canonique, valeur_min_canonique: pc.valeur_min_canonique, valeur_max_canonique: pc.valeur_max_canonique, unite_canonique: pc.unite_canonique, type_donnee: pc.type_donnee, unite: pc.unite, valeur_min: pc.valeur_min, valeur_max: pc.valeur_max}) AS all_chars
WHERE size(apoc.coll.toSet([c IN all_chars | c.id_source_caracteristique])) >= $min_matching_cids
OPTIONAL MATCH (p)-[:EST_PROPOSE_PAR]->(f:Fournisseur)
WITH p, all_chars, f
WHERE f IS NULL OR f.id_affichage <> "4"
RETURN p { .id_produit } AS product_data,
       all_chars,
       {id_etat: f.id_etat, id_affichage: f.id_affichage, typologie: f.typologie, id_fournisseur: f.id_fournisseur} AS info_soc
"""

CYPHER_V2_TARGET = """
MATCH (p:Produit)
WHERE p.id = $target_product_id AND p.est_actif = true
OPTIONAL MATCH (p)-[:A_POUR_CARACTERISTIQUE]->(pc:CaracteristiqueTechnique)
WHERE pc.id_source_caracteristique IN $all_cids
WITH p, collect({id_source_caracteristique: pc.id_source_caracteristique, id_source_valeur: pc.id_source_valeur, valeur: pc.valeur, valeur_canonique: pc.valeur_canonique, valeur_min_canonique: pc.valeur_min_canonique, valeur_max_canonique: pc.valeur_max_canonique, unite_canonique: pc.unite_canonique, type_donnee: pc.type_donnee, unite: pc.unite, valeur_min: pc.valeur_min, valeur_max: pc.valeur_max}) AS all_chars
OPTIONAL MATCH (p)-[:EST_PROPOSE_PAR]->(f:Fournisseur)
WITH p, all_chars, f
WHERE f IS NULL OR f.id_affichage <> "4"
RETURN p { .id_produit } AS product_data,
       all_chars,
       {id_etat: f.id_etat, id_affichage: f.id_affichage, typologie: f.typologie, id_fournisseur: f.id_fournisseur} AS info_soc
"""

CYPHER_V2_BY_IDS = """
MATCH (p:Produit)
WHERE p.id_produit IN $target_id_produits AND p.est_actif = true
OPTIONAL MATCH (p)-[:A_POUR_CARACTERISTIQUE]->(pc:CaracteristiqueTechnique)
WHERE pc.id_source_caracteristique IN $all_cids
WITH p, collect({id_source_caracteristique: pc.id_source_caracteristique, id_source_valeur: pc.id_source_valeur, valeur: pc.valeur, valeur_canonique: pc.valeur_canonique, valeur_min_canonique: pc.valeur_min_canonique, valeur_max_canonique: pc.valeur_max_canonique, unite_canonique: pc.unite_canonique, type_donnee: pc.type_donnee, unite: pc.unite, valeur_min: pc.valeur_min, valeur_max: pc.valeur_max}) AS all_chars
OPTIONAL MATCH (p)-[:EST_PROPOSE_PAR]->(f:Fournisseur)
WITH p, all_chars, f
WHERE f IS NULL OR f.id_affichage <> "4"
RETURN p PROJECTION_PLACEHOLDER AS product_data,
       all_chars,
       {id_etat: f.id_etat, id_affichage: f.id_affichage, typologie: f.typologie, id_fournisseur: f.id_fournisseur} AS info_soc
"""


# Pure scoring functions (stateless, no I/O)
# ---------------------------------------------------------------------------


def _score_numeric_single(
    pc_val: float, target_num: Dict, threshold: float = 0.8
) -> float:
    """Score a single numeric value against target constraints (exact/min/max/range)."""
    exact = target_num.get("exact")
    t_min = target_num.get("min")
    t_max = target_num.get("max")

    if exact is not None:
        if exact == 0:
            return 1.0 if pc_val == 0 else 0.0
        return max(
            exact / pc_val if pc_val >= exact else 0.0,
            pc_val / exact if pc_val <= exact else 0.0,
        )

    if t_min is not None and t_max is None:
        if pc_val == 0 or t_min == 0:
            return 0.0
        return max(
            t_min / pc_val if pc_val >= t_min else 0.0,
            (
                (pc_val / t_min if (pc_val / t_min) >= threshold else 0.0)
                if pc_val <= t_min
                else 0.0
            ),
        )

    if t_max is not None and t_min is None:
        if pc_val == 0 or t_max == 0:
            return 0.0
        return max(
            pc_val / t_max if pc_val <= t_max else 0.0,
            (
                (t_max / pc_val if (t_max / pc_val) >= threshold else 0.0)
                if pc_val >= t_max
                else 0.0
            ),
        )

    if t_min is not None and t_max is not None:
        if t_min <= pc_val <= t_max:
            return 1.0
        return 0.0

    return 1.0


def _score_numeric_range(pc_min: float, pc_max: float, target_num: Dict) -> float:
    """Score a numeric_range value against target constraints."""
    exact = target_num.get("exact")
    t_min = target_num.get("min")
    t_max = target_num.get("max")

    if exact is not None:
        if (pc_min is None or pc_min <= exact) and (pc_max is None or pc_max >= exact):
            return 1.0
        return 0.0

    if t_min is not None and t_max is None:
        if pc_max is not None and pc_max >= t_min:
            return t_min / pc_max
        return 0.0

    if t_max is not None and t_min is None:
        if pc_min is not None and pc_min <= t_max:
            return pc_min / t_max
        return 0.0

    if t_min is not None and t_max is not None:
        if pc_min is not None and pc_max is not None:
            if pc_max < t_min or pc_min > t_max:
                return 0.0
            if t_max - t_min == 0:
                return 1.0
            overlap_start = max(pc_min, t_min)
            overlap_end = min(pc_max, t_max)
            return (overlap_end - overlap_start) / (t_max - t_min)
        return 0.5

    return 1.0


def score_constraint(
    constraint: Dict, matched_nodes: List[Dict], scoring_params: Dict
) -> Tuple[float, List[Dict]]:
    """
    Score a single constraint against its matched characteristic nodes.
    Returns (score, scored_nodes_with_node_score).
    """
    blocked_val = scoring_params["blocked_val"]
    different_val = scoring_params["different_val"]
    # P1 (iter 1 — renforcement) — Pénalité pour caractéristique absente du produit.
    # Une absence doit être pénalisée (produits avec fiches incomplètes remontaient
    # indûment). Pénalité initiale -0.5 insuffisante (baseline conformité 57.05%).
    # Renforcée à -1.0 pour faire tomber les produits à fiche incomplète sous
    # `absolute_threshold` (0.3) et améliorer la conformité.
    c_unknown_score = min(scoring_params["c_unknown_score"], -1.0)

    target_list = constraint.get("target_list", [])
    blocking_list = constraint.get("blocking_list", [])
    target_numeric = constraint.get("target_numeric")

    if not matched_nodes:
        return c_unknown_score, []

    # Compute per-node scores
    scored_nodes = []
    for pc in matched_nodes:
        node_score = _score_single_node(pc, constraint, scoring_params)
        scored_nodes.append({**pc, "node_score": node_score})

    # Priority 1: target_list match
    if target_list:
        for pc in matched_nodes:
            if (
                str(pc.get("id_source_valeur", "")) in target_list
                or str(pc.get("valeur", "")) in target_list
            ):
                return 1.0, scored_nodes

    # Priority 2: blocking_list
    if blocking_list:
        for pc in matched_nodes:
            if (
                str(pc.get("id_source_valeur", "")) in blocking_list
                or str(pc.get("valeur", "")) in blocking_list
            ):
                return blocked_val, scored_nodes

    # Priority 3: numeric scoring
    if target_numeric is not None:
        target_unit = target_numeric.get("unit")
        best_score = None
        for pc in matched_nodes:
            if target_unit is not None and pc.get("unite_canonique") != target_unit:
                continue
            type_donnee = pc.get("type_donnee", "")
            if type_donnee == "numeric":
                val = pc.get("valeur_canonique")
                if val is not None:
                    s = _score_numeric_single(float(val), target_numeric)
                    if best_score is None or s > best_score:
                        best_score = s
            elif type_donnee == "numeric_range":
                val_min = pc.get("valeur_min_canonique")
                val_max = pc.get("valeur_max_canonique")
                s = _score_numeric_range(
                    float(val_min) if val_min is not None else None,
                    float(val_max) if val_max is not None else None,
                    target_numeric,
                )
                if best_score is None or s > best_score:
                    best_score = s
        if best_score is not None:
            return best_score, scored_nodes

    # Connected but no specific match
    return different_val, scored_nodes


def _score_single_node(pc: Dict, constraint: Dict, scoring_params: Dict) -> float:
    """Compute per-node score (mirrors Cypher matched_nodes node_score)."""
    target_list = constraint.get("target_list", [])
    blocking_list = constraint.get("blocking_list", [])
    target_numeric = constraint.get("target_numeric")
    blocked_val = scoring_params["blocked_val"]

    # Text target match
    if target_list:
        if (
            str(pc.get("id_source_valeur", "")) in target_list
            or str(pc.get("valeur", "")) in target_list
        ):
            return 1.0

    # Blocking match
    if blocking_list:
        if (
            str(pc.get("id_source_valeur", "")) in blocking_list
            or str(pc.get("valeur", "")) in blocking_list
        ):
            return blocked_val

    # Numeric scoring
    if target_numeric is not None:
        target_unit = target_numeric.get("unit")
        if target_unit is not None and pc.get("unite_canonique") != target_unit:
            return 0.0
        type_donnee = pc.get("type_donnee", "")
        if type_donnee == "numeric":
            val = pc.get("valeur_canonique")
            if val is not None:
                return _score_numeric_single(float(val), target_numeric)
        elif type_donnee == "numeric_range":
            val_min = pc.get("valeur_min_canonique")
            val_max = pc.get("valeur_max_canonique")
            return _score_numeric_range(
                float(val_min) if val_min is not None else None,
                float(val_max) if val_max is not None else None,
                target_numeric,
            )
    return 0.0


def score_product(
    characteristics: List[Dict],
    flat_filters: List[Dict],
    scoring_params: Dict,
) -> Tuple[float, List[Dict]]:
    """
    Score a product using hierarchical scoring: constraint -> cid -> q_weight -> global.
    Returns (global_score, details) matching V1 output format.
    """
    blocked_val = scoring_params["blocked_val"]

    # Build a map: cid -> matched_nodes from the fetched characteristics
    char_map = {}
    for entry in characteristics:
        cid = entry.get("cid", "")
        char_map[cid] = entry.get("matched_nodes", [])

    # Score per filter (cid), collecting details
    all_constraints = []
    for f in flat_filters:
        cid = f["cid"]
        q_weight = f["q_weight"]
        matched_nodes = char_map.get(cid, [])

        constraint_scores = []
        for c in f["constraints"]:
            c_weight = c.get("c_weight", 1)
            c_matched = [
                n
                for n in matched_nodes
                if n.get("id_source_caracteristique") == c["id_caracteristique"]
            ]
            c_score, scored_nodes = score_constraint(c, c_matched, scoring_params)
            constraint_scores.append(
                {
                    "cid": c["id_caracteristique"],
                    "score": c_score,
                    "c_weight": c_weight,
                    "has_pc": len(c_matched) > 0,
                    "matched_nodes": scored_nodes,
                }
            )

        # Aggregate per cid: weighted average by c_weight
        has_blocking = any(cs["score"] == blocked_val for cs in constraint_scores)
        c_weight_sum = sum(cs["c_weight"] for cs in constraint_scores)
        if has_blocking:
            cid_score = blocked_val
        elif c_weight_sum == 0:
            cid_score = 0.0
        else:
            cid_score = (
                sum(cs["score"] * cs["c_weight"] for cs in constraint_scores)
                / c_weight_sum
            )

        matched = any(cs["has_pc"] for cs in constraint_scores)

        all_constraints.append(
            {
                "cid": cid,
                "score": cid_score,
                "c_weight_sum": c_weight_sum,
                "q_weight": q_weight,
                "matched": matched,
                "matched_nodes": [
                    n for cs in constraint_scores for n in cs["matched_nodes"]
                ],
                "constraints": constraint_scores,
            }
        )

    # Group by q_weight and compute group scores
    q_groups = defaultdict(list)
    for c in all_constraints:
        q_groups[c["q_weight"]].append(c)

    q_weight_results = []
    for qw, group in q_groups.items():
        total_w = sum(c["c_weight_sum"] for c in group)
        if total_w == 0:
            group_score = 0.0
        else:
            group_score = sum(c["score"] * c["c_weight_sum"] for c in group) / total_w
        q_weight_results.append(
            {"q_weight": qw, "group_score": group_score, "constraints": group}
        )

    # Global score: weighted avg of group scores by q_weight
    denom = sum(g["q_weight"] for g in q_weight_results)
    if denom == 0:
        global_score = 0.0
    else:
        global_score = (
            sum(g["group_score"] * g["q_weight"] for g in q_weight_results) / denom
        )

    # Build details in V1-compatible format
    details = []
    for c in all_constraints:
        details.append(
            {
                "cid": c["cid"],
                "score": c["score"],
                "c_weight_sum": c["c_weight_sum"],
                "q_weight": c["q_weight"],
                "matched": c["matched"],
                "matched_nodes": c["matched_nodes"],
            }
        )

    return global_score, details


def compute_etat_score(
    info_soc: Dict, global_score: float, scoring_params: Dict
) -> Tuple[float, float]:
    """
    Compute etat score with cross-score adjustment.
    Returns (etat_score, adjusted_global_score).
    """
    e_unmatched = scoring_params["e_unmatched"]
    id_etat = info_soc.get("id_etat", "")
    id_affichage = info_soc.get("id_affichage", "")

    if id_etat == "1" or (id_etat == "2" and id_affichage == "1"):
        raw_etat = 1.0
    else:
        raw_etat = e_unmatched

    # Cross-score adjustments
    if raw_etat != 1.0 and global_score >= 0.8:
        etat_score = 1.0
    else:
        etat_score = raw_etat

    if raw_etat == 1.0 and 0.80 <= global_score <= 0.95:
        adjusted_global = min(global_score + 0.05, 1.0)
    else:
        adjusted_global = global_score

    return etat_score, adjusted_global


def compute_typo_score(
    info_soc: Dict,
    etat_score: float,
    user_typologie: Optional[str],
    scoring_params: Dict,
) -> float:
    """Compute typologie score."""
    t_unmatched = scoring_params["t_unmatched"]
    if etat_score != 1.0:
        return 1.0
    if user_typologie is None:
        return 1.0
    typologies = info_soc.get("typologie") or []
    if user_typologie in typologies or str(user_typologie) in typologies:
        return 1.0
    return t_unmatched


def apply_diversity_mmr(
    scored_products: List[Dict],
    top_k: int,
    max_per_supplier: int,
    diversity_lambda: float,
) -> Tuple[List[Dict], List[Dict]]:
    """
    Apply supplier diversity (MMR-inspired) and extract top_p.
    Returns (top_produit, liste_produit).
    """
    if not scored_products:
        return [], []

    # Step 1: supplier average scores (top 5 per vendor)
    vendor_products = defaultdict(list)
    for p in scored_products:
        vendor_products[p["id_fournisseur"]].append(p["final_score"])
    supplier_avg = {}
    for vid, scores in vendor_products.items():
        top5 = sorted(scores, reverse=True)[:5]
        supplier_avg[vid] = sum(top5) / len(top5)

    # Step 2: sort by final_score DESC, supplier_avg DESC
    for p in scored_products:
        p["supplier_avg_score"] = supplier_avg.get(p["id_fournisseur"], 0.0)
    scored_products.sort(key=lambda p: (-p["final_score"], -p["supplier_avg_score"]))

    # Step 3: MMR greedy selection
    selected = []
    vendor_counts = defaultdict(int)
    target_count = top_k + 4
    for prod in scored_products:
        if len(selected) >= target_count:
            break
        vid = prod["id_fournisseur"]
        if vendor_counts[vid] < max_per_supplier:
            mmr_score = diversity_lambda * prod["final_score"] - (
                1.0 - diversity_lambda
            ) * (vendor_counts[vid] / max_per_supplier)
            prod["mmr_score"] = mmr_score
            selected.append(prod)
            vendor_counts[vid] += 1

    # Step 4: re-sort by mmr_score
    selected.sort(key=lambda p: -p["mmr_score"])

    # Step 5: top_p = 1 best per unique fournisseur, limit 4
    seen_vendors = set()
    top_p = []
    for p in selected:
        vid = p["id_fournisseur"]
        if vid not in seen_vendors:
            top_p.append(p)
            seen_vendors.add(vid)
    top_p.sort(key=lambda p: -p["final_score"])
    top_p = top_p[:4]

    # Step 6: liste = remaining after removing top_p, limited to top_k
    top_p_ids = {p["id_produit"] for p in top_p}
    liste = [p for p in selected if p["id_produit"] not in top_p_ids][:top_k]

    return top_p, liste


# ---------------------------------------------------------------------------
# V2 Service Class
# ---------------------------------------------------------------------------


class RecommendationServiceV2:

    MIN_MATCHING_CIDS_DEFAULT = 1

    def _build_v2_cypher(self, request, target_product_id: Optional[str] = None) -> str:
        if target_product_id:
            return CYPHER_V2_TARGET
        return CYPHER_V2_ANCHOR

    def _build_v2_cypher_by_ids(self, request) -> str:
        projection = "{.*}"
        if request.champs_sortie and len(request.champs_sortie) > 0:
            champs = list(request.champs_sortie)
            if "id_produit" not in champs:
                champs.append("id_produit")
            if "id_fournisseur" not in champs:
                champs.append("id_fournisseur")
            projection = "{ " + ", ".join(f".{f}" for f in champs) + " }"
        return CYPHER_V2_BY_IDS.replace("PROJECTION_PLACEHOLDER", projection)

    def _build_v2_params(self, request, flat_filters, target_product_id=None, target_id_produits=None) -> Dict:
        all_cids = [f["cid"] for f in flat_filters]
        params = {
            "all_cids": all_cids,
            "id_categorie": str(request.id_categorie) if request.id_categorie is not None else None,
            "min_matching_cids": getattr(request, "min_matching_cids", self.MIN_MATCHING_CIDS_DEFAULT),
        }
        if target_product_id:
            params["target_product_id"] = str(f"id_produit_{request.id_produit}") if request.id_produit else None
        if target_id_produits:
            params["target_id_produits"] = target_id_produits
        return params

    def _score_single_row(self, row: Dict, flat_filters, scoring_params, user_id_pays, user_dept, user_typologie, id_categorie) -> Optional[Dict]:
        """Score a single Cypher result row (group all_chars by cid, then score)."""
        all_chars = row.get("all_chars", [])
        chars_by_cid = defaultdict(list)
        for pc in all_chars:
            cid = pc.get("id_source_caracteristique", "")
            chars_by_cid[cid].append(pc)
        characteristics = [
            {"cid": cid, "matched_nodes": nodes}
            for cid, nodes in chars_by_cid.items()
        ]
        raw = {
            "product_data": row.get("product_data", {}),
            "characteristics": characteristics,
            "info_soc": row.get("info_soc", {}),
        }
        return self._score_single_product(
            raw, flat_filters, scoring_params,
            user_id_pays, user_dept, user_typologie, id_categorie,
        )

    async def _stream_and_score(
        self,
        query: str,
        params: Dict,
        flat_filters: List[Dict],
        scoring_params: Dict,
        user_id_pays: Optional[str],
        user_dept: Optional[str],
        user_typologie: Optional[str],
        id_categorie: Optional[str],
    ) -> Tuple[List[Dict], float]:
        """
        Stream results from Neo4j and score each product as it arrives.
        Returns (scored_products, total_time).
        """
        scored = []
        count = 0
        start = time.perf_counter()
        first_record_time = None
        last_log_count = 0
        async for row in clients.execute_cypher_stream(query, params):
            count += 1
            elapsed = time.perf_counter() - start
            if count == 1:
                first_record_time = elapsed
                logging.warning("[V2-STREAM] first record at %.3fs", elapsed)
            if count % 100 == 0:
                logging.warning("[V2-STREAM] record #%d at %.3fs (delta %.3fs for last 100)", count, elapsed, elapsed - (time.perf_counter() - start) if last_log_count == 0 else elapsed - last_log_count)
                last_log_count = elapsed
            result = self._score_single_row(
                row, flat_filters, scoring_params,
                user_id_pays, user_dept, user_typologie, id_categorie,
            )
            if result is not None:
                scored.append(result)
        total = time.perf_counter() - start
        logging.warning(
            "[V2-TIMING] stream+score: %.3fs (%d fetched, %d scored) | first_record: %.3fs",
            total, count, len(scored), first_record_time or 0.0,
        )
        return scored, total

    def _score_raw_results(self, raw_results, flat_filters, scoring_params, user_id_pays, user_dept, user_typologie, id_categorie) -> List[Dict]:
        """Score all raw results (non-streaming fallback for requery)."""
        scored = []
        for row in (raw_results or []):
            result = self._score_single_row(row, flat_filters, scoring_params, user_id_pays, user_dept, user_typologie, id_categorie)
            if result is not None:
                scored.append(result)
        return scored

    def _score_single_product(
        self,
        raw: Dict,
        flat_filters: List[Dict],
        scoring_params: Dict,
        user_id_pays: Optional[str],
        user_dept: Optional[str],
        user_typologie: Optional[str],
        id_categorie: Optional[str],
    ) -> Optional[Dict]:
        """Score a single product — pure computation, no I/O."""
        product_data = raw.get("product_data", {})
        characteristics = raw.get("characteristics", [])
        info_soc = raw.get("info_soc", {})

        id_produit = str(product_data.get("id_produit", ""))
        id_fournisseur = str(
            info_soc.get("id_fournisseur", product_data.get("id_fournisseur", ""))
        )

        # 1. Characteristic scoring
        global_score, details = score_product(
            characteristics, flat_filters, scoring_params
        )

        # 2. Zone scoring — skipped (forced to 1 in final_score anyway)
        zone_score = scoring_params["g_unknown_score"]

        # 3. Etat scoring (with cross-adjustment)
        etat_score, global_score = compute_etat_score(
            info_soc, global_score, scoring_params
        )

        # 4. Typologie scoring
        typo_score = compute_typo_score(
            info_soc, etat_score, user_typologie, scoring_params
        )

        # 5. Final score (zone and typo forced to 1 as in V1)
        final_score = global_score * 1 * etat_score * 1

        # Apply absolute threshold
        absolute_threshold = scoring_params["absolute_threshold"]
        if final_score < absolute_threshold:
            return None

        return {
            "id_produit": id_produit,
            "id_fournisseur": id_fournisseur,
            "product_data": product_data,
            "details": details,
            "global_score": global_score,
            "zone_score": zone_score,
            "etat_score": etat_score,
            "typo_score": typo_score,
            "final_score": final_score,
            "info_soc": info_soc,
        }

    def _build_produit(
        self, scored: Dict, rang: int, request, blocked_val: float, different_val: float
    ) -> Produit:
        """Convert a scored product dict to a Produit model."""
        details = scored["details"]
        caracteristiques = []
        for detail in details:
            cid = detail.get("cid", "0")
            c_score = detail.get("score", 0.0)
            c_weight = detail.get("c_weight_sum", 1)
            q_weight = detail.get("q_weight", 1)
            matched_nodes = detail.get("matched_nodes", [])

            if c_score >= 0.8:
                statut = 1
            elif c_score == blocked_val:
                statut = 3
            elif c_score == different_val:
                statut = 2
            elif len(matched_nodes) == 0:
                statut = 4
            else:
                statut = 2

            valeur = None
            valeur_min = None
            valeur_max = None
            unite = None
            type_carac = 2
            id_valeurs = []

            if matched_nodes:
                node = max(matched_nodes, key=lambda n: n.get("node_score", 0))
                type_donnee = node.get("type_donnee", "")
                if node.get("valeur") and type_donnee != "text":
                    valeur = str(node.get("valeur", ""))
                if node.get("valeur_min") and type_donnee != "text":
                    valeur_min = str(node.get("valeur_min", ""))
                if node.get("valeur_max") and type_donnee != "text":
                    valeur_max = str(node.get("valeur_max", ""))
                unite = node.get("unite") or node.get("unite_canonique")
                type_carac = 1 if type_donnee in ["numeric", "numeric_range"] else 2
                if node.get("id_source_valeur"):
                    try:
                        id_valeurs = [int(node.get("id_source_valeur"))]
                    except (ValueError, TypeError):
                        id_valeurs = []
                elif c_score > 0 and type_donnee in ["numeric", "numeric_range"]:
                    statut = 1

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

        return Produit(
            rang=rang,
            id_produit=scored["id_produit"],
            score=float(scored["final_score"]),
            caracteristique=caracteristiques,
            info_produit=(
                scored["product_data"]
                if request.champs_sortie and len(request.champs_sortie) > 0
                else None
            ),
            coeff_geo=float(scored["zone_score"]),
            coeff_type_frns=float(scored["typo_score"]),
            coeff_etat_score=float(scored["etat_score"]),
            coeff_caracteristique=float(scored["global_score"]),
        )

    def _extract_all_cids(self, request) -> List[str]:
        """Extract CIDs directly from request — no normalization needed."""
        return [str(c.id_caracteristique) for c in request.liste_caracteristique]

    async def _fetch_raw_results(self, query: str, params: Dict) -> List[Dict]:
        """Collect all streamed results into a list."""
        results = []
        async for row in clients.execute_cypher_stream(query, params):
            results.append(row)
        return results

    async def get_products_by_caracteristique_filters(
        self,
        request: MatchingPayloadIdProduit,
        target_product_id: Optional[str] = None,
    ) -> MatchingResponse:
        start_time = time.perf_counter()

        if request.id_produit is not None:
            target_product_id = str(request.id_produit)

        # 1. Build Cypher params from raw request (no normalization needed)
        all_cids = self._extract_all_cids(request)
        cypher = self._build_v2_cypher(request, target_product_id)
        params = {
            "all_cids": all_cids,
            "id_categorie": str(request.id_categorie) if request.id_categorie is not None else None,
            "min_matching_cids": getattr(request, "min_matching_cids", self.MIN_MATCHING_CIDS_DEFAULT),
        }
        if target_product_id:
            params["target_product_id"] = str(f"id_produit_{request.id_produit}") if request.id_produit else None

        # 2. Run normalize + Neo4j fetch in PARALLEL
        parallel_start = time.perf_counter()
        flat_filters_task = v1_service._normalize_constraints_for_caracteristique(request)
        fetch_task = self._fetch_raw_results(cypher, params)

        flat_filters, raw_results = await asyncio.gather(flat_filters_task, fetch_task)
        parallel_time = time.perf_counter() - parallel_start
        logging.warning(
            "[V2-TIMING] parallel(normalize+fetch): %.3fs (%d results)",
            parallel_time, len(raw_results),
        )

        scoring_params = v1_service._extract_scoring_params(request)
        blocked_val = scoring_params["blocked_val"]
        different_val = scoring_params["different_val"]

        user_meta = request.metadonnee_utilisateurs
        user_cp = user_meta.cp if user_meta else None
        user_dept = user_cp[:2] if user_cp and len(user_cp) >= 2 else None
        user_id_pays = str(user_meta.id_pays) if user_meta and user_meta.id_pays else None
        user_typologie = user_meta.typologie if user_meta else None
        id_categorie = str(request.id_categorie) if request.id_categorie else None

        try:
            # 3. Score all products (normalize is done, results are buffered)
            score_start = time.perf_counter()
            scored = self._score_raw_results(
                raw_results, flat_filters, scoring_params,
                user_id_pays, user_dept, user_typologie, id_categorie,
            )
            score_time = time.perf_counter() - score_start
            logging.warning("[V2-TIMING] python_scoring: %.3fs (%d fetched, %d scored)", score_time, len(raw_results), len(scored))

            fetch_time = parallel_time

            if not scored:
                return MatchingResponse(top_produit=[], liste_produit=[], temps_de_traitement=time.perf_counter() - start_time)

            # 3. Diversity + top_p selection
            diversity_start = time.perf_counter()
            top_p_raw, liste_raw = apply_diversity_mmr(
                scored,
                top_k=request.top_k,
                max_per_supplier=scoring_params["max_per_supplier_extended"],
                diversity_lambda=scoring_params["diversity_lambda"],
            )
            diversity_time = time.perf_counter() - diversity_start
            logging.warning(
                "[V2-TIMING] diversity_mmr: %.3fs (top=%d, liste=%d)",
                diversity_time,
                len(top_p_raw),
                len(liste_raw),
            )

            # 5. Convert to Produit models
            top_produit = [
                self._build_produit(p, i + 1, request, blocked_val, different_val)
                for i, p in enumerate(top_p_raw)
            ]
            liste_produit = [
                self._build_produit(p, i + 1, request, blocked_val, different_val)
                for i, p in enumerate(liste_raw)
            ]

            total_time = time.perf_counter() - start_time
            logging.warning(
                "[V2-TIMING] === TOTAL: %.3fs === | parallel(norm+fetch): %.3fs | scoring: %.3fs | diversity: %.3fs",
                total_time,
                parallel_time,
                score_time,
                diversity_time,
            )

            return MatchingResponse(
                top_produit=top_produit,
                liste_produit=liste_produit,
                temps_de_traitement=total_time,
            )
        except Exception as e:
            logging.error(f"[V2] Caracteristique Filter Error: {e}", exc_info=True)
            return MatchingResponse(
                top_produit=[], liste_produit=[], temps_de_traitement=0.0
            )

    async def get_products_by_caracteristique_filters_rerank(
        self,
        request: MatchingPayloadIdProduit,
        target_product_id: Optional[str] = None,
    ) -> MatchingResponse:
        start_time = time.perf_counter()

        if request.id_produit is not None:
            target_product_id = str(request.id_produit)

        # 1. Build Cypher params from raw request + run normalize + fetch in PARALLEL
        all_cids = self._extract_all_cids(request)
        cypher = self._build_v2_cypher(request, target_product_id)
        params = {
            "all_cids": all_cids,
            "id_categorie": str(request.id_categorie) if request.id_categorie is not None else None,
            "min_matching_cids": getattr(request, "min_matching_cids", self.MIN_MATCHING_CIDS_DEFAULT),
        }
        if target_product_id:
            params["target_product_id"] = str(f"id_produit_{request.id_produit}") if request.id_produit else None

        parallel_start = time.perf_counter()
        flat_filters, raw_results = await asyncio.gather(
            v1_service._normalize_constraints_for_caracteristique(request),
            self._fetch_raw_results(cypher, params),
        )
        parallel_time = time.perf_counter() - parallel_start
        logging.warning("[V2-TIMING] parallel(normalize+fetch): %.3fs (%d results)", parallel_time, len(raw_results))

        scoring_params = v1_service._extract_scoring_params(request)
        blocked_val = scoring_params["blocked_val"]
        different_val = scoring_params["different_val"]

        user_meta = request.metadonnee_utilisateurs
        user_cp = user_meta.cp if user_meta else None
        user_dept = user_cp[:2] if user_cp and len(user_cp) >= 2 else None
        user_id_pays = str(user_meta.id_pays) if user_meta and user_meta.id_pays else None
        user_typologie = user_meta.typologie if user_meta else None
        id_categorie = str(request.id_categorie) if request.id_categorie else None

        try:
            score_start = time.perf_counter()
            scored = self._score_raw_results(
                raw_results, flat_filters, scoring_params,
                user_id_pays, user_dept, user_typologie, id_categorie,
            )
            score_time = time.perf_counter() - score_start
            logging.warning("[V2-TIMING] python_scoring: %.3fs (%d fetched, %d scored)", score_time, len(raw_results), len(scored))
            fetch_time = parallel_time

            if not scored:
                return MatchingResponse(top_produit=[], liste_produit=[], temps_de_traitement=time.perf_counter() - start_time)

            # 3. Diversity + top_p
            diversity_start = time.perf_counter()
            top_p_raw, liste_raw = apply_diversity_mmr(
                scored,
                top_k=request.rerank.top_k if request.rerank else request.top_k,
                max_per_supplier=scoring_params["max_per_supplier_extended"],
                diversity_lambda=scoring_params["diversity_lambda"],
            )
            diversity_time = time.perf_counter() - diversity_start

            # Convert to Produit
            top_produit = [
                self._build_produit(p, i + 1, request, blocked_val, different_val)
                for i, p in enumerate(top_p_raw)
            ]
            liste_produit = [
                self._build_produit(p, i + 1, request, blocked_val, different_val)
                for i, p in enumerate(liste_raw)
            ]

            # Build id_produit -> id_fournisseur map for post-LLM dedup
            produit_fournisseur_map = {
                str(p["id_produit"]): str(p["id_fournisseur"]) for p in scored
            }

            # 5. Enrich + LLM rerank (reuse V1)
            enrich_start = time.perf_counter()
            reranked_top, reranked_liste, ecarts = (
                await v1_service._enrich_and_rerank_with_llm(
                    top_produit,
                    liste_produit,
                    id_categorie or "",
                    request.rerank.parcours if request.rerank else "",
                    id_prompt=request.rerank.id_prompt if request.rerank else 112,
                    request=request,
                    thinking_level=(
                        request.rerank.thinking_level if request.rerank else "low"
                    ),
                )
            )
            enrich_time = time.perf_counter() - enrich_start
            logging.warning("[V2-TIMING] enrich_and_rerank_llm: %.3fs", enrich_time)

            # Post-LLM fournisseur deduplication on top_produit
            seen_vendors = set()
            deduped_top = []
            overflow = []
            for p in reranked_top:
                vid = produit_fournisseur_map.get(str(p.id_produit), "")
                if vid not in seen_vendors:
                    deduped_top.append(p)
                    seen_vendors.add(vid)
                else:
                    overflow.append(p)
            # Backfill from reranked_liste if we lost top slots
            for p in reranked_liste:
                if len(deduped_top) >= 4:
                    break
                vid = produit_fournisseur_map.get(str(p.id_produit), "")
                if vid not in seen_vendors:
                    deduped_top.append(p)
                    seen_vendors.add(vid)
            # Put overflow back into liste, exclude top from liste
            reranked_top = deduped_top[:4]
            top_ids = {str(p.id_produit) for p in reranked_top}
            reranked_liste = [
                p for p in (overflow + reranked_liste)
                if str(p.id_produit) not in top_ids
            ]

            # 6. Re-query with LLM-selected IDs (streaming fetch + score)
            llm_selected_ids = [
                str(p.id_produit) for p in reranked_top + reranked_liste
            ]

            if llm_selected_ids:
                requery_start = time.perf_counter()
                try:
                    # Re-fetch + score by IDs
                    requery_cypher = self._build_v2_cypher_by_ids(request)
                    requery_params = self._build_v2_params(request, flat_filters, target_id_produits=llm_selected_ids)
                    requery_results = await clients.execute_cypher_async(requery_cypher, requery_params)
                    requery_scored_list = self._score_raw_results(
                        requery_results or [], flat_filters, scoring_params,
                        user_id_pays, user_dept, user_typologie, id_categorie,
                    )
                    requery_scored = {r["id_produit"]: r for r in requery_scored_list}

                    # Rebuild preserving LLM order
                    final_top = []
                    for idx, p in enumerate(reranked_top):
                        pid = str(p.id_produit)
                        if pid in requery_scored:
                            rp = self._build_produit(
                                requery_scored[pid],
                                idx + 1,
                                request,
                                blocked_val,
                                different_val,
                            )
                            rp.llm_response = p.llm_response
                            final_top.append(rp)
                        else:
                            final_top.append(p)

                    final_liste = []
                    for idx, p in enumerate(reranked_liste):
                        pid = str(p.id_produit)
                        if pid in requery_scored:
                            rp = self._build_produit(
                                requery_scored[pid],
                                idx + 1,
                                request,
                                blocked_val,
                                different_val,
                            )
                            rp.llm_response = p.llm_response
                            final_liste.append(rp)
                        else:
                            final_liste.append(p)

                    reranked_top = final_top
                    reranked_liste = final_liste
                    requery_time = time.perf_counter() - requery_start
                    logging.warning("[V2-TIMING] requery_total: %.3fs", requery_time)
                except Exception as e:
                    logging.error("[V2] Re-query failed: %s", e, exc_info=True)

            total_time = time.perf_counter() - start_time
            logging.warning(
                "[V2-TIMING] === TOTAL: %.3fs === | parallel(norm+fetch): %.3fs | scoring: %.3fs | diversity: %.3fs | enrich+llm: %.3fs",
                total_time,
                parallel_time,
                score_time,
                diversity_time,
                enrich_time,
            )

            return MatchingResponse(
                top_produit=reranked_top,
                liste_produit=reranked_liste,
                ecarts=ecarts if ecarts else None,
                temps_de_traitement=total_time,
            )
        except Exception as e:
            logging.error(f"[V2] Rerank Error: {e}", exc_info=True)
            return MatchingResponse(
                top_produit=[], liste_produit=[], temps_de_traitement=0.0
            )


recommendation_service_v2 = RecommendationServiceV2()
