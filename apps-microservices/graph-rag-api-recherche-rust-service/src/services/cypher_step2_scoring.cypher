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
        WHEN ANY(pc IN item.matches WHERE
            size(item.conf.target_list) > 0 AND (toString(pc.id_source_valeur) IN item.conf.target_list OR toString(pc.valeur) IN item.conf.target_list)
        ) THEN 1.0

        // ============== BLOCKING CHECK (Fatal Mismatch) ==============
        WHEN ANY(pc IN item.matches WHERE
            (size(item.conf.blocking_list) > 0 AND (toString(pc.id_source_valeur) IN item.conf.blocking_list OR toString(pc.valeur) IN item.conf.blocking_list))
        ) THEN $blocked_val

        // ============== CONTINUOUS NUMERIC SCORING WITH THRESHOLD ==============
        WHEN ANY(pc IN item.matches WHERE
            item.conf.target_numeric IS NOT NULL
            AND (item.conf.target_numeric.unit IS NULL OR pc.unite_canonique = item.conf.target_numeric.unit)
        ) THEN
            apoc.coll.max([pc IN item.matches WHERE
                item.conf.target_numeric IS NOT NULL
                AND (item.conf.target_numeric.unit IS NULL OR pc.unite_canonique = item.conf.target_numeric.unit)
            |
                CASE
                    WHEN pc.type_donnee = 'numeric' THEN
                        CASE
                            // === EXACT ===
                            WHEN item.conf.target_numeric.exact IS NOT NULL THEN
                                CASE
                                    WHEN item.conf.target_numeric.exact = 0 THEN
                                        CASE WHEN pc.valeur_canonique = 0 THEN 1.0 ELSE 0.0 END
                                    ELSE
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

                            // === MIN ONLY ===
                            WHEN item.conf.target_numeric.min IS NOT NULL AND item.conf.target_numeric.max IS NULL THEN
                                CASE
                                    WHEN pc.valeur_canonique = 0 OR item.conf.target_numeric.min = 0 THEN 0.0
                                    ELSE
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

                            // === MAX ONLY ===
                            WHEN item.conf.target_numeric.max IS NOT NULL AND item.conf.target_numeric.min IS NULL THEN
                                CASE
                                    WHEN pc.valeur_canonique = 0 OR item.conf.target_numeric.max = 0 THEN 0.0
                                    ELSE
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

                            // === RANGE (min+max) ===
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
                            WHEN item.conf.target_numeric.exact IS NOT NULL THEN
                                CASE
                                    WHEN (pc.valeur_min_canonique IS NULL OR pc.valeur_min_canonique <= item.conf.target_numeric.exact)
                                         AND (pc.valeur_max_canonique IS NULL OR pc.valeur_max_canonique >= item.conf.target_numeric.exact)
                                    THEN 1.0
                                    ELSE 0.0
                                END

                            WHEN item.conf.target_numeric.min IS NOT NULL AND item.conf.target_numeric.max IS NULL THEN
                                CASE
                                    WHEN pc.valeur_max_canonique IS NOT NULL AND pc.valeur_max_canonique >= item.conf.target_numeric.min THEN
                                        toFloat(item.conf.target_numeric.min / pc.valeur_max_canonique)
                                    ELSE 0.0
                                END

                            WHEN item.conf.target_numeric.max IS NOT NULL AND item.conf.target_numeric.min IS NULL THEN
                                CASE
                                    WHEN pc.valeur_min_canonique IS NOT NULL AND pc.valeur_min_canonique <= item.conf.target_numeric.max THEN
                                        toFloat(pc.valeur_min_canonique / item.conf.target_numeric.max)
                                    ELSE 0.0
                                END

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
            WHEN size(item.conf.target_list) > 0 AND (toString(pc.id_source_valeur) IN item.conf.target_list OR toString(pc.valeur) IN item.conf.target_list)
            THEN 1.0
            WHEN (size(item.conf.blocking_list) > 0 AND (toString(pc.id_source_valeur) IN item.conf.blocking_list OR toString(pc.valeur) IN item.conf.blocking_list))
                OR
                (item.conf.blocking_numeric IS NOT NULL AND (item.conf.blocking_numeric.unit IS NULL OR pc.unite_canonique = item.conf.blocking_numeric.unit) AND (
                    (item.conf.blocking_numeric.min IS NOT NULL AND ((pc.type_donnee = 'numeric' AND pc.valeur_canonique >= item.conf.blocking_numeric.min) OR (pc.type_donnee = 'numeric_range' AND pc.valeur_min_canonique >= item.conf.blocking_numeric.min))) OR
                    (item.conf.blocking_numeric.max IS NOT NULL AND ((pc.type_donnee = 'numeric' AND pc.valeur_canonique <= item.conf.blocking_numeric.max) OR (pc.type_donnee = 'numeric_range' AND pc.valeur_max_canonique <= item.conf.blocking_numeric.max))) OR
                    (item.conf.blocking_numeric.exact IS NOT NULL AND ((pc.type_donnee = 'numeric' AND pc.valeur_canonique = item.conf.blocking_numeric.exact) OR (pc.type_donnee = 'numeric_range' AND pc.valeur_min_canonique <= item.conf.blocking_numeric.exact AND pc.valeur_max_canonique >= item.conf.blocking_numeric.exact)))
                ))
            THEN $blocked_val
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
            ELSE 0.0
        END
    })]
}] AS char_results

// --- HIERARCHICAL SCORING ---
WITH p, f.cid AS cid, f.q_weight AS q_weight, char_results,
     reduce(s = 0.0, res IN char_results | s + (
         CASE WHEN res.score = $blocked_val THEN $blocked_val * res.c_weight
         ELSE res.score * res.c_weight END
     )) AS weighted_score_sum,
     reduce(w = 0.0, res IN char_results | w + res.c_weight) AS c_weight_sum,
     ANY(res IN char_results WHERE res.score = $blocked_val) AS has_blocking,
     ANY(res IN char_results WHERE res.has_pc) AS matched

WITH p, q_weight, cid, char_results,
     CASE
         WHEN has_blocking THEN $blocked_val
         WHEN c_weight_sum = 0 THEN 0.0
         ELSE weighted_score_sum / c_weight_sum
     END AS cid_score,
     c_weight_sum,
     matched,
     apoc.coll.flatten([res IN char_results | res.matched_nodes]) AS matched_nodes

WITH p, collect({
    cid: cid,
    score: cid_score,
    c_weight_sum: c_weight_sum,
    q_weight: q_weight,
    matched: matched,
    matched_nodes: matched_nodes
}) AS all_constraints

WITH p, all_constraints,
     apoc.coll.toSet([c IN all_constraints | c.q_weight]) AS unique_q_weights

WITH p, all_constraints, [qw IN unique_q_weights | {
    q_weight: qw,
    constraints: [c IN all_constraints WHERE c.q_weight = qw],
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

// --- STEP 2.5: ZONE SCORING ---
OPTIONAL MATCH (p)-[:EST_PROPOSE_PAR]->(f:Fournisseur)
OPTIONAL MATCH (f)-[r_pays:COUVRE_PAYS]->(pays:Pays)
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

WITH p, info_soc, details, global_score, pays_rels, zone_rels,
     CASE
         WHEN size(pays_rels) > 0 AND pays_rels[0].pays IS NOT NULL THEN
             CASE
                 WHEN $user_id_pays IS NULL THEN $g_unknown_score
                 WHEN ANY(pr IN pays_rels WHERE toString(pr.id_pays) = toString($user_id_pays)) THEN
                     CASE
                         WHEN ANY(pr IN pays_rels WHERE toString(pr.id_pays) = toString($user_id_pays) AND pr.partiel = true) THEN
                             CASE
                                 WHEN $user_dept IS NULL THEN $g_unknown_score
                                 WHEN ANY(zr IN zone_rels WHERE zr.zone IS NOT NULL AND toString(zr.id_dept) = toString($user_dept)) THEN
                                     CASE
                                         WHEN ANY(zr IN zone_rels WHERE toString(zr.id_dept) = toString($user_dept) AND zr.couvre_tous = true) THEN 1.0
                                         WHEN ANY(zr IN zone_rels WHERE toString(zr.id_dept) = toString($user_dept) AND zr.couvre_tous = false AND $id_categorie IN coalesce(zr.couvre, [])) THEN 1.0
                                         WHEN ANY(zr IN zone_rels WHERE toString(zr.id_dept) = toString($user_dept) AND zr.couvre_tous = false AND $id_categorie IN coalesce(zr.ne_couvre_pas, [])) THEN $z_unmatched
                                         ELSE $g_unknown_score
                                     END
                                 ELSE $z_unmatched
                             END
                         ELSE
                             CASE
                                 WHEN ANY(pr IN pays_rels WHERE toString(pr.id_pays) = toString($user_id_pays) AND pr.couvre_tous = true) THEN 1.0
                                 WHEN ANY(pr IN pays_rels WHERE toString(pr.id_pays) = toString($user_id_pays) AND pr.couvre_tous = false AND $id_categorie IN coalesce(pr.couvre, [])) THEN 1.0
                                 WHEN ANY(pr IN pays_rels WHERE toString(pr.id_pays) = toString($user_id_pays) AND pr.couvre_tous = false AND $id_categorie IN coalesce(pr.ne_couvre_pas, [])) THEN $z_unmatched
                                 ELSE $g_unknown_score
                             END
                     END
                 ELSE $z_unmatched
             END
         WHEN size(zone_rels) > 0 AND zone_rels[0].zone IS NOT NULL THEN
             CASE
                 WHEN $user_dept IS NULL THEN $g_unknown_score
                 WHEN ANY(zr IN zone_rels WHERE zr.zone IS NOT NULL AND toString(zr.id_dept) = toString($user_dept)) THEN
                     CASE
                         WHEN ANY(zr IN zone_rels WHERE toString(zr.id_dept) = toString($user_dept) AND zr.couvre_tous = true) THEN 1.0
                         WHEN ANY(zr IN zone_rels WHERE toString(zr.id_dept) = toString($user_dept) AND zr.couvre_tous = false AND $id_categorie IN coalesce(zr.couvre, [])) THEN 1.0
                         WHEN ANY(zr IN zone_rels WHERE toString(zr.id_dept) = toString($user_dept) AND zr.couvre_tous = false AND $id_categorie IN coalesce(zr.ne_couvre_pas, [])) THEN $z_unmatched
                         ELSE $g_unknown_score
                     END
                 ELSE $z_unmatched
             END
         ELSE $g_unknown_score
     END AS zone_score

// Calculate score by Etat and affichage fournisseur
WITH p, info_soc, details, global_score, zone_score,
     CASE
        WHEN ((info_soc.id_etat = '1') OR ((info_soc.id_etat = '2') AND (info_soc.id_affichage = '1'))) THEN 1.0
        ELSE $e_unmatched
     END AS raw_etat_score

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

// Calculate typologie score
WITH p, details, global_score, zone_score, etat_score, info_soc,
     CASE
        WHEN etat_score = 1.0 THEN
            CASE
                WHEN $user_typologie IS NULL THEN 1.0
                WHEN ($user_typologie IN coalesce(info_soc.typologie, []) OR toString($user_typologie) IN coalesce(info_soc.typologie, [])) THEN 1.0
                ELSE $t_unmatched
            END
        ELSE 1.0
     END AS typo_score

// Calculate final_score (zone_geo and typo_score forced to 1)
WITH p, details, global_score, 1 AS zone_score, etat_score, 1 AS typo_score, info_soc,
    global_score * 1 * etat_score * 1 AS final_score
WHERE final_score >= $absolute_threshold OR $target_product_id IS NOT NULL
WITH p, details, global_score, zone_score, etat_score, typo_score, final_score, info_soc
ORDER BY final_score DESC

// --- SUPPLIER DIVERSITY ALGORITHM (Hybrid MMR + Round-Robin) ---
WITH collect({node: p, details: details, global_score: global_score, zone_score: zone_score, etat_score: etat_score, typo_score: typo_score, final_score: final_score, info_soc: info_soc}) AS all_scored

// Compute supplier average scores
WITH all_scored,
     apoc.map.fromPairs(
         [sid IN apoc.coll.toSet([si IN all_scored | toString(si.node.id_fournisseur)]) |
          [sid, reduce(acc = 0.0, item IN [fi IN all_scored WHERE toString(fi.node.id_fournisseur) = sid][0..5] | acc + item.final_score)
                / toFloat(size([sz IN all_scored WHERE toString(sz.node.id_fournisseur) = sid][0..5]))]]
     ) AS supplier_avg_map

// Enrich with supplier_avg_score
WITH [prod IN all_scored | {
    node: prod.node,
    details: prod.details,
    global_score: prod.global_score,
    zone_score: prod.zone_score,
    etat_score: prod.etat_score,
    typo_score: prod.typo_score,
    final_score: prod.final_score,
    info_soc: prod.info_soc,
    supplier_avg_score: supplier_avg_map[toString(prod.node.id_fournisseur)]
}] AS enriched

// Re-sort
UNWIND enriched AS e
WITH e ORDER BY e.final_score DESC, e.supplier_avg_score DESC
WITH collect(e) AS sorted_candidates

// MMR-INSPIRED SELECTION
WITH sorted_candidates,
     reduce(acc = {selected: [], counts: {}}, prod IN sorted_candidates |
         CASE
             WHEN size(acc.selected) >= $top_k + 4 THEN acc
             WHEN coalesce(acc.counts[toString(prod.node.id_fournisseur)], 0) < $max_per_supplier_extended THEN
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
                         mmr_score: $diversity_lambda * prod.final_score - (1.0 - $diversity_lambda) * (toFloat(coalesce(acc.counts[toString(prod.node.id_fournisseur)], 0)) / toFloat($max_per_supplier_extended))
                     }],
                     counts: apoc.map.merge(acc.counts, apoc.map.fromPairs([[toString(prod.node.id_fournisseur), coalesce(acc.counts[toString(prod.node.id_fournisseur)], 0) + 1]]))
                 }
             ELSE acc
         END
     ) AS mmr_result

// Re-sort by mmr_score DESC
WITH mmr_result.selected AS mmr_selected
UNWIND mmr_selected AS ms
WITH ms ORDER BY ms.mmr_score DESC
WITH collect(ms) AS all_products,
     collect({id_produit: toString(ms.node.id_produit), id_fournisseur: toString(ms.node.id_fournisseur), final_score: ms.final_score, mmr_score: ms.mmr_score, supplier_avg_score: ms.supplier_avg_score}) AS pre_diversity_debug

// --- top_p (one top product per fournisseur, limit 4) ---
WITH all_products, pre_diversity_debug,
     [fournisseur_id IN apoc.coll.toSet([prod IN all_products | prod.node.id_fournisseur]) |
         head([prod IN all_products WHERE prod.node.id_fournisseur = fournisseur_id | prod])
     ] AS top_per_fournisseur

WITH all_products, pre_diversity_debug, top_per_fournisseur
UNWIND top_per_fournisseur AS p_top
WITH all_products, pre_diversity_debug, p_top
ORDER BY p_top.final_score DESC
LIMIT 4

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

// Filter out top_p products and limit to top_k
WITH [prod IN all_products WHERE NOT prod.node.id_produit IN top_p_ids][0..$top_k] AS filtered_products, top_p, pre_diversity_debug

UNWIND (CASE WHEN size(filtered_products) = 0 THEN [null] ELSE filtered_products END) AS prod
WITH prod.node AS p_node, prod.details AS details, prod.global_score AS global_score, prod.zone_score AS zone_score, prod.etat_score AS etat_score, prod.typo_score AS typo_score, prod.final_score AS final_score, prod.info_soc AS info_soc, top_p, pre_diversity_debug
RETURN p_node PROJECTION_PLACEHOLDER AS product_data, details, global_score, zone_score, etat_score, typo_score, final_score, info_soc, top_p, pre_diversity_debug
