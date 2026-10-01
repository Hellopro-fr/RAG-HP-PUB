-- Trouver toutes les rubriques (branches niveau 1 + leaves) contenant les mots-cles.
-- A lancer dans phpMyAdmin (hp-phpmyadmin sur port 8082) ou via mysql CLI.
--
-- Logique :
--   1. Trouver les rubriques niveau 1 (id_type_rubrique = 1) qui matchent les keywords
--   2. Recuperer RECURSIVEMENT toutes leurs descendantes (branches + leaves)
--   3. Retourner les leaves (id_type_rubrique = 0) et branches avec le nombre de produits

WITH RECURSIVE matching_tree AS (
    -- Ancrage : rubriques niveau 1 matchant les keywords
    SELECT
        id_rubrique,
        nom_rubrique_francais,
        id_rubrique_parent,
        id_type_rubrique,
        0 AS depth,
        CAST(id_rubrique AS CHAR(200)) AS path
    FROM rubrique_front
    WHERE id_type_rubrique = 1
      AND (
          LOWER(nom_rubrique_francais) LIKE '%armoire%'
       OR LOWER(nom_rubrique_francais) LIKE '%pompe%'
       OR LOWER(nom_rubrique_francais) LIKE '%batterie%'
       OR LOWER(nom_rubrique_francais) LIKE '%ritmo%'
       OR LOWER(nom_rubrique_francais) LIKE '%soudure%'
       OR LOWER(nom_rubrique_francais) LIKE '%soudage%'
      )

    UNION ALL

    -- Recursion : descendants
    SELECT
        r.id_rubrique,
        r.nom_rubrique_francais,
        r.id_rubrique_parent,
        r.id_type_rubrique,
        mt.depth + 1,
        CONCAT(mt.path, '>', r.id_rubrique)
    FROM rubrique_front r
    INNER JOIN matching_tree mt ON r.id_rubrique_parent = mt.id_rubrique
    WHERE mt.depth < 10  -- garde-fou contre cycles
)
SELECT
    mt.id_rubrique,
    mt.nom_rubrique_francais AS rubrique,
    mt.id_type_rubrique AS type_rub,
    mt.depth,
    COUNT(DISTINCT p.id_produit) AS nb_produits
FROM matching_tree mt
LEFT JOIN produit_front p ON p.id_rubrique = mt.id_rubrique
GROUP BY mt.id_rubrique, mt.nom_rubrique_francais, mt.id_type_rubrique, mt.depth
ORDER BY mt.depth, mt.nom_rubrique_francais;
