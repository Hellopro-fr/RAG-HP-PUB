import logging
import time
import re
import json
import asyncio
from typing import List, Dict, Any, Optional

from toon_format import encode as toon_encode

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
from app.infrastructure.hellopro_api_client import hellopro_api_client, ETAT_SOCIETE_MAP
from app.infrastructure.gemini_client import gemini_client

# from app.services.unit_normalizer import unit_normalizer

logging.basicConfig(
    level=logging.warning, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


class RecommendationService:
    """
    Implements the V4 Hybrid Recommendation Logic (Inverted Index + Classic Scoring).
    Uses async gRPC calls for normalization.
    """

    # --- Centralized Cypher Query Constants ---

    CYPHER_STEP1_TARGET = """
         MATCH (p:Produit)
         WHERE p.id = $target_product_id AND p.est_actif = true
         WITH p, $filters AS active_filters
         """

    CYPHER_STEP1_ANCHOR = """
         UNWIND $filters AS f
         MATCH (pc:CaracteristiqueTechnique)
         WHERE pc.id_source_caracteristique = f.cid
         MATCH (p:Produit)-[:A_POUR_CARACTERISTIQUE]->(pc)
         
         WHERE ($id_categorie IS NULL OR p.id_categorie = $id_categorie) AND p.est_actif = true
         
         WITH DISTINCT p, $filters AS active_filters
         """

    CYPHER_STEP1_BY_IDS = """
         MATCH (p:Produit)
         WHERE p.id_produit IN $target_id_produits AND p.est_actif = true
         WITH p, $filters AS active_filters
         """

    CYPHER_STEP2_SCORING = """
        // --- STEP 2: SCORING by CaracteristiqueTechnique with CONTINUOUS SCORING ---
        UNWIND active_filters AS f
        
        // Match Characteristics for the specific caracteristique ID
        OPTIONAL MATCH (p)-[:A_POUR_CARACTERISTIQUE]->(pc:CaracteristiqueTechnique)
        WHERE pc.id_source_caracteristique = f.cid
        
        // Bundle Constraints with their matching Characteristics
        WITH p, f, collect(pc) AS pcs
        WITH p, f, [c IN f.constraints | {
            cid: c.id_caracteristique,
            conf: c,
            matches: [pc IN pcs WHERE pc.id_source_caracteristique = c.id_caracteristique]
        }] AS constraint_data
        
        // Evaluate Scores per Characteristic ID with CONTINUOUS SCORING FORMULAS
        WITH p, f, [item IN constraint_data | {
            cid: item.cid,
            score: CASE 
                // ============== TARGET LIST CHECK (Priority for text type) ==============
                // If ANY node matches a target value, prioritize it over blocking
                // This handles products with multiple text nodes for the same characteristic
                WHEN ANY(pc IN item.matches WHERE 
                    size(item.conf.target_list) > 0 AND (pc.id_source_valeur IN item.conf.target_list OR toString(pc.valeur) IN item.conf.target_list)
                ) THEN 1.0
                
                // ============== BLOCKING CHECK (Fatal Mismatch) ==============
                // Only reached if no target list match was found above
                WHEN ANY(pc IN item.matches WHERE 
                    (size(item.conf.blocking_list) > 0 AND (pc.id_source_valeur IN item.conf.blocking_list OR toString(pc.valeur) IN item.conf.blocking_list))
                    // OR
                    // (item.conf.blocking_numeric IS NOT NULL AND (item.conf.blocking_numeric.unit IS NULL OR pc.unite_canonique = item.conf.blocking_numeric.unit) AND (
                    //     (item.conf.blocking_numeric.min IS NOT NULL AND ((pc.type_donnee = 'numeric' AND pc.valeur_canonique >= item.conf.blocking_numeric.min) OR (pc.type_donnee = 'numeric_range' AND pc.valeur_min_canonique >= item.conf.blocking_numeric.min))) OR
                    //     (item.conf.blocking_numeric.max IS NOT NULL AND ((pc.type_donnee = 'numeric' AND pc.valeur_canonique <= item.conf.blocking_numeric.max) OR (pc.type_donnee = 'numeric_range' AND pc.valeur_max_canonique <= item.conf.blocking_numeric.max))) OR
                    //     (item.conf.blocking_numeric.exact IS NOT NULL AND ((pc.type_donnee = 'numeric' AND pc.valeur_canonique = item.conf.blocking_numeric.exact) OR (pc.type_donnee = 'numeric_range' AND pc.valeur_min_canonique <= item.conf.blocking_numeric.exact AND pc.valeur_max_canonique >= item.conf.blocking_numeric.exact)))
                    // ))
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
                                                            THEN toFloat(item.conf.target_numeric.exact / pc.valeur_canonique)
                                                            ELSE 0.0 
                                                        END,
                                                        CASE 
                                                            WHEN pc.valeur_canonique <= item.conf.target_numeric.exact 
                                                            THEN toFloat(pc.valeur_canonique / item.conf.target_numeric.exact)
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
                                                        THEN toFloat(item.conf.target_numeric.min / pc.valeur_canonique)
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
                                                        THEN toFloat(pc.valeur_canonique / item.conf.target_numeric.max)
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
                                                toFloat(item.conf.target_numeric.min / pc.valeur_max_canonique)
                                            ELSE 0.0
                                        END
                                        
                                    // MAX ONLY: Use product's min capability with threshold
                                    WHEN item.conf.target_numeric.max IS NOT NULL AND item.conf.target_numeric.min IS NULL THEN
                                        CASE
                                            WHEN pc.valeur_min_canonique IS NOT NULL AND pc.valeur_min_canonique <= item.conf.target_numeric.max THEN
                                                toFloat(pc.valeur_min_canonique / item.conf.target_numeric.max)
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
                    WHEN size(item.conf.target_list) > 0 AND (pc.id_source_valeur IN item.conf.target_list OR toString(pc.valeur) IN item.conf.target_list)
                    THEN 1.0
                    // Text blocking match
                    WHEN (size(item.conf.blocking_list) > 0 AND (pc.id_source_valeur IN item.conf.blocking_list OR toString(pc.valeur) IN item.conf.blocking_list))
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
                                                    CASE WHEN pc.valeur_canonique >= item.conf.target_numeric.exact THEN toFloat(item.conf.target_numeric.exact / pc.valeur_canonique) ELSE 0.0 END,
                                                    CASE WHEN pc.valeur_canonique <= item.conf.target_numeric.exact THEN toFloat(pc.valeur_canonique / item.conf.target_numeric.exact) ELSE 0.0 END
                                                ])
                                        END
                                    WHEN item.conf.target_numeric.min IS NOT NULL AND item.conf.target_numeric.max IS NULL THEN
                                        CASE WHEN pc.valeur_canonique = 0 OR item.conf.target_numeric.min = 0 THEN 0.0 ELSE
                                            apoc.coll.max([
                                                CASE WHEN pc.valeur_canonique >= item.conf.target_numeric.min THEN toFloat(item.conf.target_numeric.min / pc.valeur_canonique) ELSE 0.0 END,
                                                CASE WHEN pc.valeur_canonique <= item.conf.target_numeric.min AND toFloat(pc.valeur_canonique / item.conf.target_numeric.min) >= 0.8 THEN toFloat(pc.valeur_canonique / item.conf.target_numeric.min) ELSE 0.0 END
                                            ])
                                        END
                                    WHEN item.conf.target_numeric.max IS NOT NULL AND item.conf.target_numeric.min IS NULL THEN
                                        CASE WHEN pc.valeur_canonique = 0 OR item.conf.target_numeric.max = 0 THEN 0.0 ELSE
                                            apoc.coll.max([
                                                CASE WHEN pc.valeur_canonique <= item.conf.target_numeric.max THEN toFloat(pc.valeur_canonique / item.conf.target_numeric.max) ELSE 0.0 END,
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
                                            toFloat(item.conf.target_numeric.min / pc.valeur_max_canonique)
                                        ELSE 0.0 END
                                    WHEN item.conf.target_numeric.max IS NOT NULL AND item.conf.target_numeric.min IS NULL THEN
                                        CASE WHEN pc.valeur_min_canonique IS NOT NULL AND pc.valeur_min_canonique <= item.conf.target_numeric.max THEN
                                            toFloat(pc.valeur_min_canonique / item.conf.target_numeric.max)
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
        
        // --- STEP 2.5: FOURNISSEUR SCORING (zone geo disabled — forced to 1) ---
        OPTIONAL MATCH (p)-[:EST_PROPOSE_PAR]->(f:Fournisseur)

        // NOTE: COUVRE_PAYS and COUVRE_ZONE matching is disabled (zone_score forced to 1 in final_score).
        // Kept as comment for future re-enablement:
        // OPTIONAL MATCH (f)-[r_pays:COUVRE_PAYS]->(pays:Pays)
        // OPTIONAL MATCH (f)-[r_zone:COUVRE_ZONE]->(zone:ZoneGeo)

        WITH p, details, global_score,
             { id_etat: f.id_etat, id_affichage: f.id_affichage, typologie: f.typologie } AS info_soc

        // Calculate score by Etat and affichage fournisseur
        WITH p, info_soc, details, global_score, $g_unknown_score AS zone_score,
             CASE
                WHEN ((info_soc.id_etat = '1') OR ((info_soc.id_etat = '2') AND (info_soc.id_affichage = '1'))) THEN 1.0
                ELSE $e_unmatched
             END AS raw_etat_score
        
        // Post-process etat_score and global_score based on cross-score rules:
        // If etat_score = 1 and global_score between 0.80 and 0.95: add 0.05 to global_score (max 1.0)
        // If etat_score != 1 and global_score >= 0.8: set etat_score to 1.0
        WITH p, info_soc, details, zone_score,
             CASE
                 WHEN raw_etat_score <> 1.0 AND global_score >= 0.8 THEN 1.0
                 ELSE raw_etat_score
             END AS etat_score,
             CASE
                 WHEN raw_etat_score = 1.0 AND global_score >= 0.80 AND global_score <= 0.95 THEN
                     CASE WHEN global_score + 0.05 > 1.0 THEN 1.0 ELSE global_score + 0.05 END
                 ELSE global_score
             END AS global_score
        
        // NOTE: Typologie scoring disabled (typo_score forced to 1 in final_score).
        // Kept as comment for future re-enablement:
        // WITH p, details, global_score, zone_score, etat_score, info_soc,
        //      CASE WHEN etat_score = 1.0 THEN
        //          CASE WHEN $user_typologie IS NULL THEN 1.0
        //                WHEN $user_typologie IN coalesce(info_soc.typologie, []) THEN 1.0
        //                ELSE $t_unmatched END
        //      ELSE 1.0 END AS typo_score

        // Calculate final_score (zone_score and typo_score forced to 1)
        WITH p, details, global_score, 1 AS zone_score, etat_score, 1 AS typo_score, info_soc,
            global_score * etat_score AS final_score
        WHERE final_score >= $absolute_threshold OR $target_product_id IS NOT NULL
        WITH p, details, global_score, zone_score, etat_score, typo_score, final_score, info_soc
        ORDER BY final_score DESC
        
        // --- SUPPLIER DIVERSITY ALGORITHM (Hybrid MMR + Round-Robin) ---
        // Step 1: Collect all scored products (already sorted by final_score DESC)
        WITH collect({node: p, details: details, global_score: global_score, zone_score: zone_score, etat_score: etat_score, typo_score: typo_score, final_score: final_score, info_soc: info_soc}) AS all_scored
        
        // Step 2: Compute supplier average scores for tie-breaking (top 5 products per vendor)
        WITH all_scored,
             apoc.map.fromPairs(
                 [sid IN apoc.coll.toSet([si IN all_scored | si.node.id_fournisseur]) |
                  [sid, reduce(acc = 0.0, item IN [fi IN all_scored WHERE fi.node.id_fournisseur = sid][0..5] | acc + item.final_score)
                        / toFloat(size([sz IN all_scored WHERE sz.node.id_fournisseur = sid][0..5]))]]
             ) AS supplier_avg_map
        
        // Step 3: Enrich products with supplier_avg_score and sort by score DESC, supplier_avg DESC
        WITH [prod IN all_scored | {
            node: prod.node,
            details: prod.details,
            global_score: prod.global_score,
            zone_score: prod.zone_score,
            etat_score: prod.etat_score,
            typo_score: prod.typo_score,
            final_score: prod.final_score,
            info_soc: prod.info_soc,
            supplier_avg_score: supplier_avg_map[prod.node.id_fournisseur]
        }] AS enriched
        
        // Re-sort by final_score DESC, then supplier_avg_score DESC for tie-breaking
        UNWIND enriched AS e
        WITH e ORDER BY e.final_score DESC, e.supplier_avg_score DESC
        WITH collect(e) AS sorted_candidates
        
        // Step 4: MMR-INSPIRED SELECTION
        // mmr_score = λ × final_score - (1-λ) × (vendor_count / MAX_PER_VENDOR)
        // Accepts product if vendor_count < MAX_PER_VENDOR and total < K
        WITH sorted_candidates,
             reduce(acc = {selected: [], counts: {}}, prod IN sorted_candidates |
                 CASE 
                     WHEN size(acc.selected) >= $top_k + 4 THEN acc
                     WHEN coalesce(acc.counts[prod.node.id_fournisseur], 0) < $max_per_supplier_extended THEN
                         {
                             selected: acc.selected + [{
                                 node: prod.node,
                                 details: prod.details,
                                 global_score: prod.global_score,
                                 zone_score: prod.zone_score,
                                 etat_score: prod.etat_score,
                                 typo_score: prod.typo_score,
                                 final_score: prod.final_score,
                                 info_soc: prod.info_soc,
                                 supplier_avg_score: prod.supplier_avg_score,
                                 mmr_score: $diversity_lambda * prod.final_score - (1.0 - $diversity_lambda) * (toFloat(coalesce(acc.counts[prod.node.id_fournisseur], 0)) / toFloat($max_per_supplier_extended))
                             }],
                             counts: apoc.map.merge(acc.counts, apoc.map.fromPairs([[prod.node.id_fournisseur, coalesce(acc.counts[prod.node.id_fournisseur], 0) + 1]]))
                         }
                     ELSE acc
                 END
             ) AS mmr_result
        
        // Step 5: Re-sort selected products by mmr_score DESC (diversity-adjusted ranking)
        WITH mmr_result.selected AS mmr_selected
        UNWIND mmr_selected AS ms
        WITH ms ORDER BY ms.mmr_score DESC
        WITH collect(ms) AS all_products,
             collect({id_produit: ms.node.id_produit, id_fournisseur: ms.node.id_fournisseur, final_score: ms.final_score, mmr_score: ms.mmr_score, supplier_avg_score: ms.supplier_avg_score}) AS pre_diversity_debug
        
        // --- STEP 6: Compute top_p (one top product per fournisseur, limit 4) ---
        WITH all_products, pre_diversity_debug,
             [fournisseur_id IN apoc.coll.toSet([prod IN all_products | prod.node.id_fournisseur]) |
                 head([prod IN all_products WHERE prod.node.id_fournisseur = fournisseur_id | prod])
             ] AS top_per_fournisseur
        
        // Sort top_per_fournisseur by final_score descending and limit to 4
        WITH all_products, pre_diversity_debug, top_per_fournisseur
        UNWIND top_per_fournisseur AS p_top
        WITH all_products, pre_diversity_debug, p_top 
        ORDER BY p_top.final_score DESC 
        LIMIT 4
        
        // First alias the node, then project the node data
        WITH all_products, pre_diversity_debug, p_top.node AS top_node, p_top.final_score AS top_score, p_top.details AS top_details, p_top.zone_score AS top_zone_score, p_top.global_score AS top_global_score, p_top.etat_score AS top_etat_score, p_top.typo_score AS top_typo_score, p_top.info_soc AS top_info_soc
        WITH all_products, pre_diversity_debug, top_node TOP_P_PROJECTION_PLACEHOLDER AS top_product_data, top_score, top_details, top_node.id_produit AS top_id, top_zone_score, top_global_score, top_etat_score, top_typo_score, top_info_soc
        WITH all_products, pre_diversity_debug, collect({
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
        WITH [prod IN all_products WHERE NOT prod.node.id_produit IN top_p_ids][0..$top_k] AS filtered_products, top_p, pre_diversity_debug
        
        UNWIND (CASE WHEN size(filtered_products) = 0 THEN [null] ELSE filtered_products END) AS prod
        WITH prod.node AS p_node, prod.details AS details, prod.global_score AS global_score, prod.zone_score AS zone_score, prod.etat_score AS etat_score, prod.typo_score AS typo_score, prod.final_score AS final_score, prod.info_soc AS info_soc, top_p, pre_diversity_debug
        RETURN p_node PROJECTION_PLACEHOLDER AS product_data, details, global_score, zone_score, etat_score, typo_score, final_score, info_soc, top_p, pre_diversity_debug
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
            matches: [pc IN pcs WHERE pc.id_source_caracteristique = c.id_caracteristique]
        }] AS constraint_data
        
        // Evaluate Scores per Characteristic ID
        WITH p, f, [item IN constraint_data | {
            cid: item.cid,
            score: CASE 
                // Blocking Check
                WHEN ANY(pc IN item.matches WHERE 
                    (size(item.conf.blocking_list) > 0 AND (pc.id_source_valeur IN item.conf.blocking_list OR toString(pc.valeur) IN item.conf.blocking_list))
                    OR
                    (item.conf.blocking_numeric IS NOT NULL AND (item.conf.blocking_numeric.unit IS NULL OR pc.unite_canonique = item.conf.blocking_numeric.unit) AND (
                        (item.conf.blocking_numeric.min IS NOT NULL AND ((pc.type_donnee = 'numeric' AND pc.valeur_canonique >= item.conf.blocking_numeric.min) OR (pc.type_donnee = 'numeric_range' AND pc.valeur_min_canonique >= item.conf.blocking_numeric.min))) OR
                        (item.conf.blocking_numeric.max IS NOT NULL AND ((pc.type_donnee = 'numeric' AND pc.valeur_canonique <= item.conf.blocking_numeric.max) OR (pc.type_donnee = 'numeric_range' AND pc.valeur_max_canonique <= item.conf.blocking_numeric.max))) OR
                        (item.conf.blocking_numeric.exact IS NOT NULL AND ((pc.type_donnee = 'numeric' AND pc.valeur_canonique = item.conf.blocking_numeric.exact) OR (pc.type_donnee = 'numeric_range' AND pc.valeur_min_canonique <= item.conf.blocking_numeric.exact AND pc.valeur_max_canonique >= item.conf.blocking_numeric.exact)))
                    ))
                ) THEN $blocked_val
                // Target Check
                WHEN ANY(pc IN item.matches WHERE 
                    (size(item.conf.target_list) > 0 AND (pc.id_source_valeur IN item.conf.target_list OR toString(pc.valeur) IN item.conf.target_list))
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

        // Apply deduplication: return only top_p products (one per fournisseur, max 4)
        UNWIND top_p AS top_product
        WITH top_product.product_data AS p_node, top_product.details AS details, top_product.score AS global_score
        RETURN p_node PROJECTION_PLACEHOLDER AS product_data, details, global_score
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
        logging.warning(f"📝 Cypher params being sent:")
        for key, value in params.items():
            if key not in ["filters", "weights"]:  # Skip large nested params
                logging.warning(f"   {key}: {value} (type: {type(value).__name__})")
            else:
                logging.warning(
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

    def _extract_scoring_params(
        self, request: MatchingPayloadIdProduit
    ) -> Dict[str, Any]:
        """
        Extract all scoring parameters from request.scoring with defaults.
        Returns a flat dict of scoring values.
        """
        blocked_val = (
            request.scoring.v_blocked if request.scoring.v_blocked is not None else -2.0
        )
        different_val = (
            request.scoring.v_different
            if request.scoring.v_different is not None
            else -0.3
        )
        z_unmatched = (
            request.scoring.z_unmatched
            if request.scoring.z_unmatched is not None
            else 0
        )
        e_unmatched = (
            request.scoring.e_unmatched
            if request.scoring.e_unmatched is not None
            else 0.9
        )
        g_unknown_score = (
            request.scoring.g_unknown_score
            if request.scoring.g_unknown_score is not None
            else 0.8
        )
        c_unknown_score = (
            request.scoring.c_unknown_score
            if request.scoring.c_unknown_score is not None
            else 0
        )
        t_unmatched = (
            request.scoring.t_unmatched
            if request.scoring.t_unmatched is not None
            else 0.2
        )
        absolute_threshold = (
            request.scoring.absolute_threshold
            if request.scoring.absolute_threshold is not None
            else 0.3
        )
        relative_tolerance = (
            request.scoring.relative_tolerance
            if request.scoring.relative_tolerance is not None
            else 0.1
        )
        max_per_supplier_primary = (
            request.scoring.max_per_supplier_primary
            if request.scoring.max_per_supplier_primary is not None
            else 10
        )
        max_per_supplier_extended = (
            request.scoring.max_per_supplier_extended
            if request.scoring.max_per_supplier_extended is not None
            else 20
        )
        score_step = (
            request.scoring.score_step
            if request.scoring.score_step is not None
            else 0.1
        )
        diversity_lambda = (
            request.scoring.diversity_lambda
            if request.scoring.diversity_lambda is not None
            else 0.7
        )

        return {
            "blocked_val": blocked_val,
            "different_val": different_val,
            "z_unmatched": z_unmatched,
            "e_unmatched": e_unmatched,
            "g_unknown_score": g_unknown_score,
            "c_unknown_score": c_unknown_score,
            "t_unmatched": t_unmatched,
            "absolute_threshold": absolute_threshold,
            "relative_tolerance": relative_tolerance,
            "max_per_supplier_primary": max_per_supplier_primary,
            "max_per_supplier_extended": max_per_supplier_extended,
            "score_step": score_step,
            "diversity_lambda": diversity_lambda,
        }

    def _build_cypher_query(
        self,
        request: MatchingPayloadIdProduit,
        target_product_id: Optional[str] = None,
    ) -> str:
        """
        Build the full Cypher query (Step 1 + Step 2), ensure required champs_sortie,
        and inject projection placeholders.
        """
        # Build Cypher Query Step 1 (Dynamic) using centralized constants
        if target_product_id:
            query_step_1 = self.CYPHER_STEP1_TARGET
        else:
            query_step_1 = self.CYPHER_STEP1_ANCHOR

        # --- STEP 2: SCORING (centralized) ---
        query_step_2 = self.CYPHER_STEP2_SCORING

        cypher_query = query_step_1 + query_step_2

        if (
            request.champs_sortie is not None
            and len(request.champs_sortie) > 0
            and "id_produit" not in request.champs_sortie
        ):
            request.champs_sortie.append("id_produit")
        if (
            request.champs_sortie is not None
            and len(request.champs_sortie) > 0
            and "id_fournisseur" not in request.champs_sortie
        ):
            request.champs_sortie.append("id_fournisseur")

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

        return cypher_query

    def _build_cypher_query_by_ids(
        self,
        request: MatchingPayloadIdProduit,
    ) -> str:
        """
        Build a Cypher query that matches products by a list of id_produit values
        (CYPHER_STEP1_BY_IDS + CYPHER_STEP2_SCORING), with the same projection logic.
        """
        query_step_1 = self.CYPHER_STEP1_BY_IDS
        query_step_2 = self.CYPHER_STEP2_SCORING
        cypher_query = query_step_1 + query_step_2

        if (
            request.champs_sortie is not None
            and len(request.champs_sortie) > 0
            and "id_produit" not in request.champs_sortie
        ):
            request.champs_sortie.append("id_produit")
        if (
            request.champs_sortie is not None
            and len(request.champs_sortie) > 0
            and "id_fournisseur" not in request.champs_sortie
        ):
            request.champs_sortie.append("id_fournisseur")

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

        return cypher_query

    def _build_cypher_params(
        self,
        request: MatchingPayloadIdProduit,
        flat_filters: List[Dict[str, Any]],
        weights_map: Dict[str, Any],
        scoring_params: Dict[str, Any],
        top_k: int,
        target_product_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Build the full Cypher parameter dict. The top_k argument allows the caller
        to pass either request.top_k or request.rerank.top_k.
        """
        # Extract user location data from metadonnee_utilisateurs
        user_meta = request.metadonnee_utilisateurs
        user_cp = user_meta.cp if user_meta else None
        user_dept = user_cp[:2] if user_cp is not None and len(user_cp) >= 2 else None
        user_id_pays = user_meta.id_pays if user_meta else None
        user_typologie = user_meta.typologie if user_meta else None

        return {
            "filters": flat_filters,
            "weights": weights_map,
            "id_categorie": (
                str(request.id_categorie) if request.id_categorie is not None else None
            ),
            "top_k": int(top_k),
            "target_product_id": (
                str(f"""id_produit_{request.id_produit}""")
                if request.id_produit is not None
                else None
            ),
            "blocked_val": scoring_params["blocked_val"],
            "different_val": scoring_params["different_val"],
            "user_dept": user_dept,
            "user_id_pays": str(user_id_pays) if user_id_pays is not None else None,
            "z_unmatched": scoring_params["z_unmatched"],
            "e_unmatched": scoring_params["e_unmatched"],
            "g_unknown_score": scoring_params["g_unknown_score"],
            "c_unknown_score": scoring_params["c_unknown_score"],
            "user_typologie": user_typologie,
            "t_unmatched": scoring_params["t_unmatched"],
            "absolute_threshold": scoring_params["absolute_threshold"],
            "relative_tolerance": scoring_params["relative_tolerance"],
            "max_per_supplier_primary": scoring_params["max_per_supplier_primary"],
            "max_per_supplier_extended": scoring_params["max_per_supplier_extended"],
            "score_step": scoring_params["score_step"],
            "diversity_lambda": scoring_params["diversity_lambda"],
        }

    def _parse_matching_results(
        self,
        results: List[Dict[str, Any]],
        request: MatchingPayloadIdProduit,
        blocked_val: float,
        different_val: float,
    ) -> tuple:
        """
        Parse Cypher results into (liste_produit, top_produit) lists of Produit objects.
        Returns a tuple of (liste_produit, top_produit).
        """
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
                        node = max(matched_nodes, key=lambda n: n.get("node_score", 0))
                        valeur = (
                            str(node.get("valeur", ""))
                            if node.get("valeur") and node.get("type_donnee") != "text"
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
                        elif c_score > 0 and type_donnee in [
                            "numeric",
                            "numeric_range",
                        ]:
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

            return caracteristiques

        def build_produit(rec: Dict[str, Any], rang: int) -> Produit:
            """Convert a result record to Produit."""
            product_data = rec.get("product_data", {})
            details = rec.get("details", [])
            final_score = rec.get("final_score", 0.0)
            zone_score = rec.get("zone_score", 1.0)
            etat_score = rec.get("etat_score", 1.0)
            typo_score = rec.get("typo_score", 1.0)
            carac_score = rec.get("global_score", 0.0)
            info_produit = rec.get("product_data", {})

            caracteristiques = convert_to_caracteristique_matching(details, final_score)

            return Produit(
                rang=rang,
                id_produit=str(product_data.get("id_produit", "")),
                score=float(final_score),
                caracteristique=caracteristiques,
                info_produit=(
                    info_produit
                    if request.champs_sortie is not None
                    and len(request.champs_sortie) > 0
                    else None
                ),
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
                        info_produit=(
                            entry.get("product_data", {})
                            if request.champs_sortie is not None
                            and len(request.champs_sortie) > 0
                            else None
                        ),
                        coeff_geo=float(top_zone_score),
                        coeff_type_frns=float(top_typo_score),
                        coeff_etat_score=float(top_etat_score),
                        coeff_caracteristique=float(top_carac_score),
                    )
                    top_produit.append(produit)

            # Build liste_produit
            for idx, rec in enumerate(results):
                if rec.get("product_data"):
                    liste_produit.append(build_produit(rec, idx + 1))

        return liste_produit, top_produit

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

        norm_start = time.perf_counter()
        flat_filters = await self._normalize_constraints_for_caracteristique(request)
        norm_time = time.perf_counter() - norm_start

        # Build weights map from request (cid -> q_weight)
        weights_map = {f["cid"]: f["q_weight"] for f in flat_filters}

        # Extract scoring parameters
        scoring_params = self._extract_scoring_params(request)
        blocked_val = scoring_params["blocked_val"]
        different_val = scoring_params["different_val"]

        # Build Cypher query with projection
        cypher_query = self._build_cypher_query(request, target_product_id)

        # Build Cypher params with request.top_k
        params = self._build_cypher_params(
            request,
            flat_filters,
            weights_map,
            scoring_params,
            top_k=request.top_k,
            target_product_id=target_product_id,
        )

        try:
            query_start = time.perf_counter()
            results = await clients.execute_cypher(cypher_query, params)
            query_time = time.perf_counter() - query_start

            # --- DEBUG: Diversity Algorithm Output ---
            if results:
                pre_diversity_debug = results[0].get("pre_diversity_debug", [])
                raw_top_p_debug = results[0].get("top_p", [])

                # logging.warning("=" * 80)
                # logging.warning("DIVERSITY ALGORITHM DEBUG")
                # logging.warning("=" * 80)
                # logging.warning(
                #     f"Query time: {query_time:.4f}s | Total results: {len(results)} | absolute_threshold: {scoring_params['absolute_threshold']}"
                # )
                # logging.warning(
                #     f"Parameters: top_k={int(request.top_k)}, K(target)={int(request.top_k) + 4}, max_per_supplier_extended={scoring_params['max_per_supplier_extended']}, diversity_lambda={scoring_params['diversity_lambda']}"
                # )

                # # Log pre-diversity debug (products selected by the MMR algorithm)
                # logging.warning("-" * 40)
                # logging.warning("MMR SELECTION (re-sorted by mmr_score DESC):")
                # logging.warning(
                #     f"  Total selected: {len(pre_diversity_debug)} / K={int(request.top_k) + 4}"
                # )

                # Log vendor distribution
                vendor_counts = {}
                for p in pre_diversity_debug:
                    vid = p.get("id_fournisseur", "?")
                    vendor_counts[vid] = vendor_counts.get(vid, 0) + 1
                # logging.warning(f"  Vendor distribution: {vendor_counts}")

                # Log each selected product
                # for i, p in enumerate(pre_diversity_debug):
                #     logging.warning(
                #         f"  [{i+1}] "
                #         f"id_produit={p.get('id_produit')} | "
                #         f"id_fournisseur={p.get('id_fournisseur')} | "
                #         f"final_score={p.get('final_score', 0):.4f} | "
                #         f"mmr_score={p.get('mmr_score', 0):.4f} | "
                #         f"supplier_avg={p.get('supplier_avg_score', 0):.4f}"
                #     )

                # Log top_p (best per vendor)
                # logging.warning("-" * 40)
                # logging.warning(
                #     f"TOP_P (1 per vendor, max 4): {len(raw_top_p_debug)} products"
                # )
                # for i, entry in enumerate(raw_top_p_debug):
                #     if isinstance(entry, dict) and "product_data" in entry:
                #         logging.warning(
                #             f"  [top_{i+1}] id_produit={entry['product_data'].get('id_produit')} | "
                #             f"id_fournisseur={entry['product_data'].get('id_fournisseur')} | "
                #             f"score={entry.get('score', 0):.4f} | "
                #             f"zone={entry.get('zone_score', 0):.4f} | "
                #             f"etat={entry.get('etat_score', 0):.4f} | "
                #             f"typo={entry.get('typo_score', 0):.4f}"
                #         )

                # Log final product list
                # logging.warning("-" * 40)
                final_count = sum(1 for r in results if r.get("product_data"))
                # logging.warning(
                #     f"FINAL RESULT: {final_count} products in liste_produit (after removing top_p, limited to top_k={int(request.top_k)})"
                # )
                for i, rec in enumerate(results):
                    pd = rec.get("product_data", {})
                    # if pd:
                    # logging.warning(
                    #     f"  [{i+1}] id_produit={pd.get('id_produit')} | "
                    #     f"id_fournisseur={pd.get('id_fournisseur')} | "
                    #     f"final_score={rec.get('final_score', 0):.4f}"
                    # )
                # logging.warning("=" * 80)

            # Parse results and convert to MatchingResponse format
            liste_produit, top_produit = self._parse_matching_results(
                results,
                request,
                blocked_val,
                different_val,
            )

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

    async def _enrich_and_rerank_with_llm(
        self,
        top_produit: List[Produit],
        liste_produit: List[Produit],
        id_categorie: str,
        parcours: str = "",
        id_prompt: int = 112,
        request: Optional[MatchingPayloadIdProduit] = None,
        thinking_level: str = "low",
    ) -> tuple:
        """
        Enrich products with HelloPro API data and rerank using Gemini LLM.

        1. Extract all id_produit from top_produit + liste_produit
        2. Fetch product info + characteristics + category definitions in parallel
        3. Build BESOIN_ACHETEUR, CARACTERISTIQUES_CRITIQUES, LISTE_PRODUITS
        4. Format system prompt with template variables and call Gemini
        5. Reorder results based on LLM response

        Returns (reranked_top_produit, reranked_liste_produit, ecarts)
        """
        # 1. Extract all product IDs
        all_produits = top_produit + liste_produit
        if not all_produits:
            logging.warning("[RERANK] No products to rerank, returning empty")
            return top_produit, liste_produit, []

        id_produits = [p.id_produit for p in all_produits]
        produit_map = {p.id_produit: p for p in all_produits}
        # logging.warning(
        #     f"[RERANK] Starting rerank for {len(id_produits)} products "
        #     f"(top={len(top_produit)}, liste={len(liste_produit)}), "
        #     f"id_categorie={id_categorie}"
        # )
        # logging.warning(f"[RERANK] Product IDs: {id_produits}")

        # 2. Fetch product info + characteristics + category definitions + prompt in parallel
        logging.warning(
            "[RERANK] Fetching product info, characteristics, and category definitions from HelloPro API..."
        )
        try:
            api_fetch_start = time.perf_counter()
            products_info, all_caracs, category_caracs, prompt_data = await asyncio.gather(
                hellopro_api_client.fetch_products_info(id_categorie, id_produits),
                hellopro_api_client.fetch_all_product_caracteristiques(id_produits),
                hellopro_api_client.fetch_category_caracteristiques(id_categorie),
                hellopro_api_client.fetch_prompt(str(id_prompt) or "112"),
            )
            api_fetch_time = time.perf_counter() - api_fetch_start
            logging.warning("[RERANK-TIMING] hellopro_api_fetch (parallel): %.3fs", api_fetch_time)
        except Exception as e:
            logging.error(f"[RERANK] HelloPro API enrichment error: {e}", exc_info=True)
            return top_produit, liste_produit, []

        # logging.warning(
        #     f"[RERANK] HelloPro API results: "
        #     f"products_info={len(products_info)} items, "
        #     f"all_caracs={len(all_caracs)} products with caracs, "
        #     f"category_caracs={len(category_caracs)} category definitions"
        # )

        # 3. Format enriched data for LLM
        format_start = time.perf_counter()
        formatted_products = []
        # logging.warning(f"[RERANK] product_info: {products_info}")
        liste_carac_id = []
        for carac in request.liste_caracteristique:
            liste_carac_id.append(str(carac.id_caracteristique))

        for id_produit in id_produits:
            info = products_info.get(
                id_produit, products_info.get(str(id_produit), {})
            ).get("produit", {})
            info_fournisseur = products_info.get(
                id_produit, products_info.get(str(id_produit), {})
            ).get("vendeur", {})
            caracs = all_caracs.get(id_produit, all_caracs.get(str(id_produit), []))
            # logging.warning(f"[RERANK] caracs: {caracs}")

            # Determine fournisseur type from coeff_etat_score
            produit_obj = produit_map.get(id_produit)
            etat_societe_label = (
                "Client"
                if produit_obj and produit_obj.coeff_etat_score == 1.0
                else "Prospect"
            )

            # Build caracteristiques, stripping empty values to reduce tokens
            filtered_caracs = []
            if caracs:
                for c in caracs:
                    if str(c.get("id_caracteristique", "")) in liste_carac_id:
                        carac_entry = {"nom": c.get("nom_caracteristique", c.get("label", ""))}
                        valeur = c.get("valeur", "")
                        if valeur:
                            carac_entry["valeur"] = valeur
                        unite = c.get("unite", "")
                        if unite:
                            carac_entry["unite"] = unite
                        filtered_caracs.append(carac_entry)

            raw_desc = re.sub(
                r"\s+",
                " ",
                re.sub(r"<[^>]+>", "", info.get("description_produit", "")).replace(
                    "\xa0", " "
                ),
            ).strip()
            formatted_product = {
                "id_produit": str(id_produit),
                "description": raw_desc if raw_desc else "[AUCUN DESCRIPTIF DISPONIBLE]",
                "titre": info.get(
                    "titre_produit", info.get("nom_produit", info.get("titre", ""))
                ),
                "fournisseur": {
                    "nom": info_fournisseur.get("nom", ""),
                    "type": etat_societe_label,
                },
                "caracteristiques": filtered_caracs,
            }
            formatted_products.append(formatted_product)

        # logging.warning(
        #     f"[RERANK] Formatted {len(formatted_products)} products for LLM"
        # )
        # for fp in formatted_products:
        #     logging.warning(
        #         f"[RERANK]   Product {fp['id_produit']}: "
        #         f"titre='{fp['titre'][:50]}...', "
        #         f"fournisseur={fp['fournisseur']['type']}, "
        #         # f"score_matching={fp['score_matching']}, "
        #         f"nb_caracs={len(fp['caracteristiques'])}"
        #     )

        # 4. Build BESOIN_ACHETEUR, CARACTERISTIQUES_CRITIQUES, LISTE_PRODUITS

        # BESOIN_ACHETEUR = rerank.parcours
        besoin_acheteur = parcours if parcours else "Non renseigné"

        # CARACTERISTIQUES_CRITIQUES: format from request.liste_caracteristique
        # enriched with category characteristic definitions (names)
        # Build a map from id_caracteristique -> category definition for name lookup
        category_carac_map = {}
        for cat_def in category_caracs:
            cid = str(cat_def.get("id_caracteristique", ""))
            category_carac_map[cid] = cat_def

        caracteristiques_critiques_lines = []
        if request and request.liste_caracteristique:
            for carac in request.liste_caracteristique:
                cid = str(carac.id_caracteristique)
                poids_q = carac.poids_question or 1
                poids_c = carac.poids_caracteristique or "critique"
                unite = carac.unite or ""

                # P8 (iter 7 PROD) — Expose secondaire (🟡) en plus de critique (🔴)
                # au LLM reranker. Le system_prompt distingue déjà critique vs secondaire.

                # Get the name from category definitions, fallback to id
                cat_def = category_carac_map.get(cid, {})
                nom = cat_def.get("nom", f"Caractéristique #{cid}")
                if not unite and cat_def.get("unite"):
                    unite = cat_def.get("unite", "")

                # Determine icon based on poids_caracteristique
                icon = "🔴" if poids_c == "critique" else "🟡"

                # Format valeurs_cibles
                valeur_parts = []
                if isinstance(carac.valeurs_cibles, dict):
                    # Numeric range: {min: X, max: Y, exact: Z}
                    if carac.valeurs_cibles.get("min") is not None:
                        valeur_parts.append(
                            f"min: {carac.valeurs_cibles['min']} {unite}".strip()
                        )
                    if carac.valeurs_cibles.get("max") is not None:
                        valeur_parts.append(
                            f"max: {carac.valeurs_cibles['max']} {unite}".strip()
                        )
                    if carac.valeurs_cibles.get("exact") is not None:
                        valeur_parts.append(
                            f"{carac.valeurs_cibles['exact']} {unite}".strip()
                        )
                elif isinstance(carac.valeurs_cibles, list):
                    # Text values: look up human-readable names from category definition
                    cat_valeurs = cat_def.get("valeurs", [])
                    valeur_id_to_name = {
                        str(v.get("id_valeur", "")): v.get("valeur", "")
                        for v in cat_valeurs
                    }
                    text_values = []
                    for v in carac.valeurs_cibles:
                        readable = valeur_id_to_name.get(str(v), str(v))
                        text_values.append(readable)
                    valeur_parts.append(", ".join(text_values))

                valeur_str = ", ".join(valeur_parts) if valeur_parts else "Non spécifié"
                line = f"{icon} {nom} (poids: {poids_q}) : {valeur_str}"
                caracteristiques_critiques_lines.append(line)

        caracteristiques_critiques = "\n".join(caracteristiques_critiques_lines)

        # logging.warning(
        #     f"[RERANK] BESOIN_ACHETEUR (parcours): {besoin_acheteur[:200]}..."
        # )
        # logging.warning(
        #     f"[RERANK] CARACTERISTIQUES_CRITIQUES ({len(caracteristiques_critiques_lines)} lines):\n"
        #     f"{caracteristiques_critiques}"
        # )

        format_time = time.perf_counter() - format_start
        logging.warning("[RERANK-TIMING] format_products: %.3fs (%d products)", format_time, len(formatted_products))

        # LISTE_PRODUITS = formatted product list as TOON (Token-Oriented Object Notation)
        # TOON uses ~40% fewer tokens than JSON for structured data sent to LLMs
        toon_start = time.perf_counter()
        liste_produits_json = toon_encode(formatted_products)
        toon_time = time.perf_counter() - toon_start
        logging.warning("[RERANK-TIMING] toon_encode: %.3fs (%d chars)", toon_time, len(liste_produits_json))
        # logging.warning(
        #     f"[RERANK] LISTE_PRODUITS JSON size: {len(liste_produits_json)} chars"
        # )

        # 5. Use pre-fetched prompt data (fetched in parallel above) and call Gemini
        logging.warning(
            "[RERANK] Using pre-fetched prompt from HelloPro API (id_prompt=%s)...", id_prompt
        )

        prompt_temperature = None
        if prompt_data and prompt_data.get("contenu_prompt"):
            system_prompt = prompt_data["contenu_prompt"]
            logging.warning(
                "[RERANK] Successfully fetched prompt from API (length=%d chars)",
                len(system_prompt),
            )

            # Parse temperature from the API response
            raw_temperature = prompt_data.get("temperature")
            if raw_temperature is not None:
                try:
                    prompt_temperature = float(raw_temperature)
                    logging.warning(
                        "[RERANK] Using temperature from API: %s", prompt_temperature
                    )
                except (ValueError, TypeError):
                    logging.warning(
                        "[RERANK] Invalid temperature value from API: %s, using default",
                        raw_temperature,
                    )
                    prompt_temperature = None
        else:
            logging.warning(
                "[RERANK] Failed to fetch prompt from API, using hardcoded fallback"
            )
            system_prompt = """
            ## RÔLE ET OBJECTIF

            Tu es un expert en matching acheteur-produit pour une marketplace B2B.
            Tu reçois une liste de produits pré-sélectionnés par un système de scoring automatique
            et la demande d'un acheteur professionnel. Tu produis un classement final fiable en
            écartant les produits incompatibles et en repositionnant les autres selon leur
            pertinence réelle.


            ## VARIABLES D'ENTRÉE

            - **[BESOIN_ACHETEUR]** : les réponses de l'acheteur au questionnaire
            - **[CARACTERISTIQUES_CRITIQUES]** : les critères prioritaires et leur niveau
            (critique ou secondaire)
            - **[LISTE_PRODUITS]** : les produits pré-sélectionnés avec leurs caractéristiques,
            incluant pour chaque produit le statut du fournisseur associé (client actif ou non)


            ## ÉTAPES DE TRAITEMENT

            ### ÉTAPE 1 — Analyser chaque produit individuellement

            **Pré-qualification contextuelle (obligatoire avant toute vérification de critères)**

            Avant d'examiner les critères individuels, qualifie le besoin de l'acheteur en trois dimensions :
            - **Type de produit attendu** : quelle est la famille de produit précise, pas le nom générique
            (ex. : pas le nom de la catégorie seul, mais le type exact avec ses caractéristiques structurantes)
            - **Contexte d'utilisation** : quel est l'environnement, le secteur, le type d'usage
            (professionnel/résidentiel, intérieur/extérieur, usage intensif/occasionnel, etc.)
            - **Profil de l'utilisateur final** : à qui est destiné le produit
            (garagiste, agriculteur, exploitant forestier, etc.)

            Pour chaque produit, vérifie en priorité si son espace d'usage correspond à celui qualifié
            ci-dessus. Un produit dont l'espace d'usage est structurellement différent est écarté à
            cette étape, avant toute vérification de critères.

            Un espace d'usage est structurellement différent quand le changement de contexte implique
            des exigences techniques différentes, même si le nom du produit est identique.
            Exemples types : même nom de produit mais usage professionnel ≠ usage résidentiel /
            même nom de produit mais usage intensif ≠ usage occasionnel / produit neuf ≠ produit d'occasion.

            **A. Compatibilité de type, de segment et d'usage**
            Deux produits peuvent partager le même nom générique tout en étant incompatibles.
            Les écarts suivants sont éliminatoires :
            - Porteur ou interface différent de ce qui est demandé
            - État (neuf / occasion) différent de ce qui est demandé
            - Capacité, puissance ou charge significativement inférieure à la cible
            - Usage spécialisé ne couvrant pas le besoin général exprimé
            - Segment ou contexte d'utilisation structurellement différent
            (résidentiel vs professionnel, mobile vs fixe, entrée de gamme vs usage lourd)

            **B. Respect des contraintes absolues**
            Vérifie chaque critère critique de [CARACTERISTIQUES_CRITIQUES] :
            - Valeur numérique inférieure à un minimum exigé : ÉCARTÉ
            - Valeur numérique supérieure à un maximum exigé : ÉCARTÉ
            - Valeur textuelle incompatible avec la cible : ÉCARTÉ
            - Valeur non renseignée : non validable, ne suppose pas de compatibilité par défaut


            ### ÉTAPE 2 — Calculer le score de chaque produit non écarté

            Le score est calculé sur l'ensemble des caractéristiques de [CARACTERISTIQUES_CRITIQUES],
            qu'elles soient renseignées ou non dans la fiche produit.

            Formule : Score = Somme(Points_i × Poids_i) / Somme(Poids_i)
            où la somme porte sur TOUS les critères, renseignés ou non.

            Barème des points :
            - Valeur dans la cible ou dans la fourchette numérique : 1.0
            - Correspondance partielle sur critère secondaire : 0.5
            - Valeur hors fourchette sur critère secondaire : 0.1
            - Caractéristique non renseignée dans la fiche produit : 0.0
            - Valeur incompatible sur critère critique : ÉCARTÉ

            Poids : critique = 2 / secondaire = 1

            **Score de complétude informationnelle**

            Après calcul du score principal, attribue un score de complétude de 1 à 5 selon la grille
            suivante :

            - **5** — Tous les critères critiques sont renseignés ET plus de 75% des critères
            secondaires sont renseignés
            - **4** — Tous les critères critiques sont renseignés ET entre 50% et 75% des critères
            secondaires sont renseignés
            - **3** — Tous les critères critiques sont renseignés ET moins de 50% des critères
            secondaires sont renseignés
            - **2** — Au moins un critère critique non renseigné, mais des critères secondaires présents
            - **1** — Aucun critère critique renseigné, ou moins de 2 caractéristiques renseignées
            au total

            **Plafonnement du score par niveau de complétude**

            Le score final ne peut pas dépasser le plafond associé au niveau de complétude du produit :

            - Complétude **5** → plafond **1.0**
            - Complétude **4** → plafond **0.90**
            - Complétude **3** → plafond **0.75**
            - Complétude **2** → plafond **0.60**
            - Complétude **1** → plafond **0.40**

            Le score affiché en output est le score après application du plafond,
            exprimé comme un nombre décimal entre 0 et 1 (ex: 0.85).

            Seuils de décision (appliqués sur le score plafonné) :
            - Score ≥ 0.70 : VALIDE
            - Score entre 0.40 et 0.69 : DÉGRADÉ
            - Score < 0.40 : ÉCARTÉ par score insuffisant

            Règles de décision forcées, non contournables par le score :
            - Aucune caractéristique critique renseignée : décision forcée DÉGRADÉ
            - Une ou plusieurs caractéristiques critiques manquantes : décision plafonnée à DÉGRADÉ
            - Score ≥ 0.70 et tous les critères critiques renseignés et compatibles : VALIDE confirmé

            Ce score de complétude est un critère de classement actif, appliqué systématiquement
            après le score principal et avant la règle fournisseur. À score principal égal ou proche
            (écart ≤ 5 points), le produit avec la complétude la plus élevée est positionné en priorité.

            L'ordre de priorité dans le classement est donc :
            1. Score principal plafonné (décroissant)
            2. Score de complétude (décroissant) si écart de score principal ≤ 5 points
            3. Statut fournisseur client (dans la marge de 10 points sur le score principal)

            Le score de complétude est affiché dans l'output pour chaque produit classé.


            ### ÉTAPE 3 — Appliquer la règle fournisseur

            La règle fournisseur s'applique après calcul des scores et application du score de
            complétude. Elle peut modifier l'ordre de classement selon les conditions suivantes :

            **Condition d'application :** un produit dont le fournisseur est client actif peut être
            repositionné devant un produit de fournisseur prospect si et seulement si l'écart de score
            principal entre les deux est inférieur ou égal à 10 points.

            **Cette règle ne s'applique jamais dans le sens inverse** : un produit prospect ne peut
            jamais remonter devant un produit client, quelle que soit la situation.

            **La règle s'applique aussi entre paliers de décision** (ex. : un produit client DÉGRADÉ
            peut passer devant un produit prospect VALIDE si l'écart de score principal est ≤ 10 points).

            Au-delà de 10 points d'écart, le score prime toujours, quel que soit le statut fournisseur.


            ### ÉTAPE 4 — Produire le classement final

            - Top produits : les 4 meilleurs produits VALIDES ou DÉGRADÉS par score décroissant.
            Si moins de 4 produits sont éligibles, le top est réduit en conséquence.
            - Autres produits : jusqu'à 8 produits VALIDES ou DÉGRADÉS restants par score décroissant.
            - Produits écartés : listés séparément avec leur score et leur raison d'exclusion.
            Jamais dans le top ni dans les autres produits.


            ## RÈGLES GÉNÉRALES

            - Un seul écart sur un critère critique suffit à écarter le produit, sans calcul.
            - Ne jamais supposer qu'une information manquante est favorable au produit.
            - Si l'acheteur a répondu "Je ne sais pas", n'applique pas d'exigence sur ce critère.
            - Reste factuel. Si tu ne peux pas conclure faute d'information, indique-le
            dans la justification.


            ## FORMAT DE SORTIE

            La réponse doit être un objet JSON valide et uniquement un objet JSON,
            sans texte avant ou après.

            {{
            "besoin_acheteur": "Reformulation synthétique du besoin en 2-3 phrases.",
            "top_produits": [
                {{
                "rang": 1,
                "id_produit": "XXXXX",
                "nom": "Nom du produit",
                "score": 0.85,
                "completude": 4,
                "base_calcul": "X/Y critères renseignés",
                "decision": "VALIDE",
                "fournisseur_client": true,
                "justification": "Raison courte de ce positionnement."
                }}
            ],
            "autres_produits": [
                {{
                "rang": 5,
                "id_produit": "XXXXX",
                "nom": "Nom du produit",
                "score": 0.52,
                "completude": 2,
                "base_calcul": "X/Y critères renseignés",
                "decision": "DÉGRADÉ",
                "fournisseur_client": false,
                "justification": "Raison courte de ce positionnement."
                }}
            ],
            "produits_ecartes": [
                {{
                "id_produit": "XXXXX",
                "nom": "Nom du produit",
                "score": 0.35,
                "fournisseur_client": false,
                "raison_exclusion": "Raison factuelle de l'exclusion."
                }}
            ]
            }}


            ## CHECKLIST AVANT SORTIE

            - [ ] Pré-qualification contextuelle effectuée avant toute vérification de critères
            - [ ] Chaque critère critique vérifié pour chaque produit
            - [ ] Incompatibilités de segment et d'usage traitées comme éliminatoires
            - [ ] Valeurs numériques hors fourchette sur critères critiques traitées comme bloquantes
            - [ ] Score calculé sur l'ensemble des critères, les non renseignés comptent 0
            - [ ] Règles de décision forcées appliquées après le calcul
            - [ ] Score de complétude calculé et plafond appliqué pour chaque produit
            - [ ] Classement appliqué dans l'ordre : score principal → complétude (si écart ≤ 5 pts) → fournisseur (si écart ≤ 10 pts)
            - [ ] Règle fournisseur appliquée avec marge de 10 points, jamais dans le sens prospect → client
            - [ ] Aucun produit écarté dans le top ou les autres produits
            - [ ] Top limité à 4 produits, autres produits limités à 8
            - [ ] Champ base_calcul et champ completude renseignés pour chaque produit classé
            - [ ] Champ score renseigné pour chaque produit écarté
            - [ ] Sortie JSON valide sans texte en dehors du JSON


            DONNÉES D'ENTRÉE

            [BESOIN_ACHETEUR]
            {besoin_acheteur}

            [CARACTERISTIQUES_CRITIQUES]
            {caracteristiques_critiques}

            [LISTE_PRODUITS]
            {liste_produits_json}
            """

        # Format the template variables into the system prompt
        system_prompt = system_prompt.format(
            besoin_acheteur=besoin_acheteur,
            caracteristiques_critiques=caracteristiques_critiques,
            liste_produits_json=liste_produits_json,
        )

        logging.warning("[RERANK] Calling Gemini LLM for reranking...")
        try:
            gemini_start = time.perf_counter()
            llm_response = await gemini_client.generate_rerank_response(
                system_prompt, temperature=prompt_temperature, thinking_level=thinking_level
            )
            gemini_time = time.perf_counter() - gemini_start
            logging.warning("[RERANK] Gemini LLM call completed in %.3fs", gemini_time)
        except Exception as e:
            logging.error(f"[RERANK] Gemini rerank call error: {e}", exc_info=True)
            return top_produit, liste_produit, []

        if not llm_response:
            logging.warning(
                "[RERANK] Gemini returned no usable response, keeping original order"
            )
            return top_produit, liste_produit, []

        # logging.warning(
        #     f"[RERANK] Gemini response received: {json.dumps(llm_response, ensure_ascii=False, default=str)[:1000]}"
        # )

        # 5. Reorder results based on LLM response
        llm_top = llm_response.get("top_produits", [])
        llm_autres = llm_response.get("autres_produits", [])
        llm_ecartes = llm_response.get("produits_ecartes", [])

        # Build a map of id_produit -> LLM score and full LLM entry from all sections
        llm_score_map = {}
        llm_response_map = {}
        for entry in llm_top + llm_autres + llm_ecartes:
            if isinstance(entry, dict):
                pid = str(entry.get("id_produit", ""))
                if pid:
                    llm_response_map[pid] = entry
                    score = entry.get("score")
                    if score is not None:
                        try:
                            llm_score_map[pid] = float(score)
                        except (ValueError, TypeError):
                            pass

        # Ensure all are string ID lists
        llm_top_ids = [
            str(x.get("id_produit", x) if isinstance(x, dict) else x) for x in llm_top
        ]
        llm_autres_ids = [
            str(x.get("id_produit", x) if isinstance(x, dict) else x)
            for x in llm_autres
        ]
        llm_ecartes_ids = [
            str(x.get("id_produit", x) if isinstance(x, dict) else x)
            for x in llm_ecartes
        ]

        # logging.warning(
        #     f"[RERANK] LLM classification: "
        #     f"top_produits={llm_top_ids}, "
        #     f"autres_produits={llm_autres_ids}, "
        #     f"produits_ecartes={llm_ecartes_ids}"
        # )
        # logging.warning(f"[RERANK] LLM score map: {llm_score_map}")

        # Rebuild ordered lists from LLM output, using LLM score when available
        reranked_top = []
        for idx, pid in enumerate(llm_top_ids):
            if pid in produit_map:
                p = produit_map[pid]
                reranked_top.append(
                    Produit(
                        rang=idx + 1,
                        id_produit=p.id_produit,
                        score=llm_score_map.get(pid, p.score),
                        caracteristique=p.caracteristique,
                        coeff_geo=p.coeff_geo,
                        coeff_type_frns=p.coeff_type_frns,
                        coeff_etat_score=p.coeff_etat_score,
                        coeff_caracteristique=p.coeff_caracteristique,
                        info_produit=p.info_produit,
                        llm_response=llm_response_map.get(pid, {}),
                    )
                )

        reranked_liste = []
        for idx, pid in enumerate(llm_autres_ids):
            if pid in produit_map:
                p = produit_map[pid]
                reranked_liste.append(
                    Produit(
                        rang=idx + 1,
                        id_produit=p.id_produit,
                        score=llm_score_map.get(pid, p.score),
                        caracteristique=p.caracteristique,
                        coeff_geo=p.coeff_geo,
                        coeff_type_frns=p.coeff_type_frns,
                        coeff_etat_score=p.coeff_etat_score,
                        coeff_caracteristique=p.coeff_caracteristique,
                        info_produit=p.info_produit,
                        llm_response=llm_response_map.get(pid, {}),
                    )
                )

        ecarts = []
        for idx, pid in enumerate(llm_ecartes_ids):
            if pid in produit_map:
                p = produit_map[pid]
                ecarts.append(
                    Produit(
                        rang=idx + 1,
                        id_produit=p.id_produit,
                        score=llm_score_map.get(pid, p.score),
                        caracteristique=p.caracteristique,
                        coeff_geo=p.coeff_geo,
                        coeff_type_frns=p.coeff_type_frns,
                        coeff_etat_score=p.coeff_etat_score,
                        coeff_caracteristique=p.coeff_caracteristique,
                        info_produit=p.info_produit,
                        llm_response=llm_response_map.get(pid, {}),
                    )
                )

        # Any products not mentioned by LLM go into liste_produit at the end
        all_llm_ids = set(llm_top_ids + llm_autres_ids + llm_ecartes_ids)
        for pid, p in produit_map.items():
            if pid not in all_llm_ids:
                reranked_liste.append(
                    Produit(
                        rang=len(reranked_liste) + 1,
                        id_produit=p.id_produit,
                        score=p.score,
                        caracteristique=p.caracteristique,
                        coeff_geo=p.coeff_geo,
                        coeff_type_frns=p.coeff_type_frns,
                        coeff_etat_score=p.coeff_etat_score,
                        coeff_caracteristique=p.coeff_caracteristique,
                        info_produit=p.info_produit,
                        llm_response=llm_response_map.get(pid, {}),
                    )
                )

        return reranked_top, reranked_liste, ecarts

    async def get_products_by_caracteristique_filters_rerank(
        self,
        request: MatchingPayloadIdProduit,
        target_product_id: Optional[str] = None,
    ) -> MatchingResponse:
        """
        Get products filtered and scored by CaracteristiqueTechnique constraints,
        using rerank.top_k instead of request.top_k.
        Same core functionality as get_products_by_caracteristique_filters,
        then enriches with HelloPro API data and reranks via Gemini LLM.
        Called when rerank.use_rerank is True.
        """
        start_time = time.perf_counter()

        if request.id_produit is not None:
            target_product_id = str(request.id_produit)

        norm_start = time.perf_counter()
        flat_filters = await self._normalize_constraints_for_caracteristique(request)
        norm_time = time.perf_counter() - norm_start
        logging.warning("[RERANK-TIMING] normalize_constraints: %.3fs", norm_time)

        # Build weights map from request (cid -> q_weight)
        build_params_start = time.perf_counter()
        weights_map = {f["cid"]: f["q_weight"] for f in flat_filters}

        # Extract scoring parameters
        scoring_params = self._extract_scoring_params(request)
        blocked_val = scoring_params["blocked_val"]
        different_val = scoring_params["different_val"]

        # Build Cypher query with projection
        cypher_query = self._build_cypher_query(request, target_product_id)

        # Build Cypher params with rerank.top_k instead of request.top_k
        params = self._build_cypher_params(
            request,
            flat_filters,
            weights_map,
            scoring_params,
            top_k=request.rerank.top_k,
            target_product_id=target_product_id,
        )
        build_params_time = time.perf_counter() - build_params_start
        logging.warning("[RERANK-TIMING] build_query+params: %.3fs", build_params_time)

        try:
            query_start = time.perf_counter()
            results = await clients.execute_cypher(cypher_query, params)
            query_time = time.perf_counter() - query_start
            logging.warning("[RERANK-TIMING] cypher_query: %.3fs (%d results)", query_time, len(results) if results else 0)

            # --- DEBUG: Diversity Algorithm Output ---
            if results:
                pre_diversity_debug = results[0].get("pre_diversity_debug", [])
                raw_top_p_debug = results[0].get("top_p", [])

                # Log vendor distribution
                vendor_counts = {}
                for p in pre_diversity_debug:
                    vid = p.get("id_fournisseur", "?")
                    vendor_counts[vid] = vendor_counts.get(vid, 0) + 1

                final_count = sum(1 for r in results if r.get("product_data"))
                for i, rec in enumerate(results):
                    pd = rec.get("product_data", {})

            # Parse results and convert to MatchingResponse format
            parse_start = time.perf_counter()
            liste_produit, top_produit = self._parse_matching_results(
                results,
                request,
                blocked_val,
                different_val,
            )
            parse_time = time.perf_counter() - parse_start
            logging.warning("[RERANK-TIMING] parse_results: %.3fs (top=%d, liste=%d)", parse_time, len(top_produit), len(liste_produit))

            # --- Enrich with HelloPro API data and rerank via Gemini LLM ---
            id_categorie = str(request.id_categorie) if request.id_categorie else ""
            parcours = request.rerank.parcours if request.rerank else ""

            enrich_start = time.perf_counter()
            reranked_top, reranked_liste, ecarts = (
                await self._enrich_and_rerank_with_llm(
                    top_produit,
                    liste_produit,
                    id_categorie,
                    parcours,
                    id_prompt=request.rerank.id_prompt if request.rerank else 112,
                    request=request,
                    thinking_level=request.rerank.thinking_level if request.rerank else "low",
                )
            )
            enrich_time = time.perf_counter() - enrich_start
            logging.warning("[RERANK-TIMING] enrich_and_rerank_llm: %.3fs", enrich_time)

            # --- Re-query Cypher with only LLM-selected product IDs ---
            llm_selected_ids = [
                str(p.id_produit) for p in reranked_top + reranked_liste
            ]

            if llm_selected_ids:
                logging.warning(
                    "[RERANK-REQUERY] Re-running Cypher query with %d LLM-selected product IDs: %s",
                    len(llm_selected_ids),
                    llm_selected_ids,
                )
                requery_total_start = time.perf_counter()
                try:
                    # Build Cypher query restricted to LLM-selected IDs
                    requery_cypher = self._build_cypher_query_by_ids(request)
                    requery_params = self._build_cypher_params(
                        request,
                        flat_filters,
                        weights_map,
                        scoring_params,
                        top_k=len(llm_selected_ids),
                        target_product_id=None,
                    )
                    # Add the target_id_produits parameter for CYPHER_STEP1_BY_IDS
                    requery_params["target_id_produits"] = llm_selected_ids

                    requery_start = time.perf_counter()
                    requery_results = await clients.execute_cypher(
                        requery_cypher, requery_params
                    )
                    requery_time = time.perf_counter() - requery_start
                    logging.warning(
                        "[RERANK-REQUERY] Re-query completed in %.3fs, got %d results",
                        requery_time,
                        len(requery_results) if requery_results else 0,
                    )

                    # Parse re-queried results into Produit objects
                    requery_parse_start = time.perf_counter()
                    requery_liste, requery_top = self._parse_matching_results(
                        requery_results,
                        request,
                        blocked_val,
                        different_val,
                    )
                    requery_parse_time = time.perf_counter() - requery_parse_start
                    logging.warning("[RERANK-TIMING] requery_parse_results: %.3fs", requery_parse_time)

                    # Build a map of id_produit -> re-queried Produit for fast lookup
                    requery_map = {}
                    for p in requery_top + requery_liste:
                        requery_map[str(p.id_produit)] = p

                    # Rebuild reranked_top preserving LLM order and LLM response data
                    final_top = []
                    for idx, p in enumerate(reranked_top):
                        pid = str(p.id_produit)
                        if pid in requery_map:
                            rp = requery_map[pid]
                            final_top.append(
                                Produit(
                                    rang=idx + 1,
                                    id_produit=rp.id_produit,
                                    score=rp.score,
                                    caracteristique=rp.caracteristique,
                                    coeff_geo=rp.coeff_geo,
                                    coeff_type_frns=rp.coeff_type_frns,
                                    coeff_etat_score=rp.coeff_etat_score,
                                    coeff_caracteristique=rp.coeff_caracteristique,
                                    info_produit=rp.info_produit,
                                    llm_response=p.llm_response,
                                )
                            )
                        else:
                            final_top.append(p)

                    # Rebuild reranked_liste preserving LLM order and LLM response data
                    final_liste = []
                    for idx, p in enumerate(reranked_liste):
                        pid = str(p.id_produit)
                        if pid in requery_map:
                            rp = requery_map[pid]
                            final_liste.append(
                                Produit(
                                    rang=idx + 1,
                                    id_produit=rp.id_produit,
                                    score=rp.score,
                                    caracteristique=rp.caracteristique,
                                    coeff_geo=rp.coeff_geo,
                                    coeff_type_frns=rp.coeff_type_frns,
                                    coeff_etat_score=rp.coeff_etat_score,
                                    coeff_caracteristique=rp.coeff_caracteristique,
                                    info_produit=rp.info_produit,
                                    llm_response=p.llm_response,
                                )
                            )
                        else:
                            final_liste.append(p)

                    reranked_top = final_top
                    reranked_liste = final_liste
                    requery_total_time = time.perf_counter() - requery_total_start
                    logging.warning(
                        "[RERANK-TIMING] requery_total (cypher+parse+rebuild): %.3fs",
                        requery_total_time,
                    )
                    logging.warning(
                        "[RERANK-REQUERY] Successfully rebuilt %d top + %d liste products from re-query",
                        len(reranked_top),
                        len(reranked_liste),
                    )
                except Exception as e:
                    logging.error(
                        "[RERANK-REQUERY] Re-query failed, keeping LLM-reranked results: %s",
                        e,
                        exc_info=True,
                    )

            total_time = time.perf_counter() - start_time
            logging.warning(
                "[RERANK-TIMING] === TOTAL: %.3fs === | normalize: %.3fs | build_params: %.3fs | cypher: %.3fs | parse: %.3fs | enrich+llm: %.3fs",
                total_time, norm_time, build_params_time, query_time, parse_time, enrich_time,
            )
            return MatchingResponse(
                top_produit=reranked_top,
                liste_produit=reranked_liste,
                ecarts=ecarts if ecarts else None,
                temps_de_traitement=total_time,
            )
        except Exception as e:
            logging.error(f"Caracteristique Filter Rerank Error: {e}", exc_info=True)
            return MatchingResponse(
                top_produit=[],
                liste_produit=[],
                temps_de_traitement=0.0,
            )


recommendation_service = RecommendationService()
