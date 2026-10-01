<?php
/**
 * build_categories_list.php
 * ==========================
 * Pipeline :
 *   1. Trouve les LEAVES (id_type_rubrique = 0) dont le nom contient les keywords
 *   2. Pour chaque leaf, remonte vers son "rubrique niveau 1" via fonction recursive
 *   3. Dedoublonne les niveaux 1 obtenus
 *   4. Redescend depuis chaque niveau 1 pour recuperer TOUTES les leaves (type = 0)
 *      sous cet arbre, en utilisant les colonnes denormalisees id_rubrique_niveau_1..6
 *   5. Ecrit 2 fichiers :
 *      - categories_found.csv  : vue complete
 *      - categories_for_ingest.txt : juste les noms des leaves (prets pour ingest)
 *
 * Convention HelloPro :
 *   1000000 = racine virtuelle
 *   niveau_1 = rubrique dont le GRAND-PARENT est 1000000
 *
 * Usage :
 *   php build_categories_list.php
 *   php build_categories_list.php armoire pompe batterie ritmo soudure
 *   KEYWORDS='armoire,pompe,extincteur' php build_categories_list.php
 */

require_once($_SERVER['DOCUMENT_ROOT'] . "include/connexion.php");
require_once($_SERVER['DOCUMENT_ROOT'] . "fonctions/fonctions_hellopro.php");


// =====================================================================
// Table a utiliser pour la recursive walk-up.
// Si 'rubrique_front' n'existe pas dans ton env, remplace par 'rubrique'.
// =====================================================================
define('RUB_TABLE', 'rubrique_front');


// =====================================================================
// Fonction recursive : pour un id_rubrique, trouve son niveau_1 ancetre.
// Reprise du snippet fourni par l'utilisateur.
// =====================================================================
function rechercher_rubrique_niveau_1($id_rubrique)
{
    if (empty($id_rubrique)) return 0;

    $id_rubrique = (int) $id_rubrique;
    $t = RUB_TABLE;
    $sql = "
        SELECT R1.id_rubrique_parent, R2.id_rubrique_parent AS parent_du_parent
        FROM {$t} R1
        INNER JOIN {$t} R2 ON R1.id_rubrique_parent = R2.id_rubrique
        WHERE R1.id_rubrique = {$id_rubrique}
    ";
    $res = mysqli_query($GLOBALS['LINK_MYSQLI_ANNUAIRE_BO'], $sql)
        or die(hellopro_mysql_error($sql, $GLOBALS['LINK_MYSQLI_ANNUAIRE_BO']));
    $lig = mysqli_fetch_assoc($res);
    mysqli_free_result($res);
    if (!$lig) return 0;

    if ((int) $lig['id_rubrique_parent'] == 1000000) {
        // La rubrique courante est un "secteur top" (direct enfant de la racine).
        // Pas de niveau_1 au-dessus.
        return 0;
    } elseif ((int) $lig['parent_du_parent'] == 1000000) {
        // On est pile au niveau_1 : la rubrique courante IS le niveau_1.
        return $id_rubrique;
    } else {
        // Remonte d'un cran.
        return rechercher_rubrique_niveau_1($lig['id_rubrique_parent']);
    }
}


// =====================================================================
// Helper : affiche le chemin d'une rubrique jusqu'a la racine (1000000).
// Adaptation du chemin() de l'utilisateur.
// =====================================================================
function chemin_simple($id_rub_deb)
{
    $id_rub = (int) $id_rub_deb;
    $path = [];
    $t = RUB_TABLE;
    $max_iter = 20;  // garde-fou
    while ($id_rub && $max_iter-- > 0) {
        $sql = "SELECT id_rubrique, nom_rubrique_francais, id_rubrique_parent
                FROM {$t} WHERE id_rubrique = {$id_rub}";
        $res = mysqli_query($GLOBALS['LINK_MYSQLI_ANNUAIRE_BO'], $sql);
        if (!$res) break;
        $lig = mysqli_fetch_assoc($res);
        mysqli_free_result($res);
        if (!$lig) break;
        $path[] = sprintf("[%s] %s", $lig['id_rubrique'], $lig['nom_rubrique_francais']);
        if ((int) $lig['id_rubrique_parent'] == 1000000) break;
        $id_rub = (int) $lig['id_rubrique_parent'];
    }
    return implode(' > ', array_reverse($path));
}


// =====================================================================
// CONFIG
// =====================================================================
$keywords = [];
if (!empty(getenv('KEYWORDS'))) {
    foreach (explode(',', getenv('KEYWORDS')) as $k) {
        $k = trim($k);
        if ($k !== '') $keywords[] = $k;
    }
} elseif ($argc > 1) {
    $keywords = array_slice($argv, 1);
} else {
    $keywords = ['armoire', 'pompe', 'batterie', 'ritmo', 'soudure', 'soudage'];
}

$out_csv = getenv('OUT_CSV') ?: 'categories_found.csv';
$out_txt = getenv('OUT_TXT') ?: 'categories_for_ingest.txt';

$link = $GLOBALS['LINK_MYSQLI_ANNUAIRE_BO'];

echo "[CONFIG] Keywords : " . implode(', ', $keywords) . "\n\n";


// =====================================================================
// ETAPE 1 : Leaves (id_type_rubrique = 0) matchant les keywords
// =====================================================================
$like_clauses = [];
foreach ($keywords as $kw) {
    $kw_esc = mysqli_real_escape_string($link, mb_strtolower($kw));
    $like_clauses[] = "LOWER(nom_rubrique_francais) LIKE '%{$kw_esc}%'";
}
$where_kw = implode(' OR ', $like_clauses);

$req1 = "
    SELECT id_rubrique, nom_rubrique_francais, id_rubrique_parent,
           COALESCE(nombre_produits_rubrique, 0) AS nb_produits
    FROM rubrique_front
    WHERE id_type_rubrique = 0
      AND ({$where_kw})
";
$res1 = mysqli_query($link, $req1) or die(hellopro_mysql_error($req1, $link));

$matching_leaves = [];
while ($row = mysqli_fetch_assoc($res1)) {
    $matching_leaves[] = $row;
}
mysqli_free_result($res1);

echo "[ETAPE 1] " . count($matching_leaves) . " leaves (type=0) matchent les keywords\n";
if (empty($matching_leaves)) {
    echo "[STOP] Aucune leaf ne matche. Revois les keywords.\n";
    exit(1);
}


// =====================================================================
// ETAPE 2 : Remonter chaque leaf a son niveau_1, deduplier
// + afficher le chemin pour les 10 premieres leaves (verification visuelle)
// =====================================================================
$niveau_1_map = [];  // id_niveau_1 => true
$i = 0;
echo "[ETAPE 2] Remontee vers niveau_1 (10 exemples affiches) :\n";
foreach ($matching_leaves as $leaf) {
    $n1 = rechercher_rubrique_niveau_1((int) $leaf['id_rubrique']);
    if ($n1 > 0) {
        $niveau_1_map[(int) $n1] = true;
    }
    if ($i < 10) {
        $path = chemin_simple((int) $leaf['id_rubrique']);
        echo sprintf("  [%s] %s\n    niveau_1 = %s\n    chemin   = %s\n\n",
            $leaf['id_rubrique'],
            $leaf['nom_rubrique_francais'],
            $n1 > 0 ? $n1 : "AUCUN (leaf au niveau section)",
            $path
        );
    }
    $i++;
}
$niveau_1_ids = array_keys($niveau_1_map);

echo "  => " . count($niveau_1_ids) . " rubriques niveau_1 distinctes derriere les leaves matchees\n\n";

// Affichage des niveau_1 trouvees
if (!empty($niveau_1_ids)) {
    $ids_list = implode(',', array_map('intval', $niveau_1_ids));
    $t = RUB_TABLE;
    $req_n1 = "
        SELECT id_rubrique, nom_rubrique_francais, id_rubrique_parent,
               COALESCE(nombre_produits_rubrique, 0) AS nb_produits
        FROM {$t}
        WHERE id_rubrique IN ({$ids_list})
        ORDER BY nom_rubrique_francais
    ";
    $res_n1 = mysqli_query($link, $req_n1) or die(hellopro_mysql_error($req_n1, $link));
    echo "[ETAPE 2 bis] Liste des niveau_1 retenus :\n";
    while ($row = mysqli_fetch_assoc($res_n1)) {
        echo sprintf("  [%s] %s  (parent=%s, nb_produits=%s)\n",
            $row['id_rubrique'], $row['nom_rubrique_francais'],
            $row['id_rubrique_parent'], $row['nb_produits']);
    }
    mysqli_free_result($res_n1);
}
echo "\n";


// =====================================================================
// ETAPE 3 : Redescendre - toutes les leaves (type=0) sous ces niveau_1
// Utilise les colonnes denormalisees id_rubrique_niveau_1..6.
// =====================================================================
$t = RUB_TABLE;
$req3 = "
    SELECT
        id_rubrique,
        nom_rubrique_francais,
        id_type_rubrique,
        id_rubrique_parent,
        id_rubrique_niveau_1,
        COALESCE(nombre_produits_rubrique, 0) AS nb_produits
    FROM {$t}
    WHERE id_type_rubrique = 0
      AND (id_rubrique_niveau_1 IN ({$ids_list})
        OR id_rubrique_niveau_2 IN ({$ids_list})
        OR id_rubrique_niveau_3 IN ({$ids_list})
        OR id_rubrique_niveau_4 IN ({$ids_list})
        OR id_rubrique_niveau_5 IN ({$ids_list})
        OR id_rubrique_niveau_6 IN ({$ids_list}))
    ORDER BY nombre_produits_rubrique DESC, nom_rubrique_francais
";
$res3 = mysqli_query($link, $req3) or die(hellopro_mysql_error($req3, $link));

$all_leaves = [];
$total_produits = 0;
while ($row = mysqli_fetch_assoc($res3)) {
    $all_leaves[] = $row;
    $total_produits += (int) $row['nb_produits'];
}
mysqli_free_result($res3);

echo "[ETAPE 3] " . count($all_leaves) . " leaves (type=0) au total sous les " . count($niveau_1_ids) . " niveau_1\n";
echo "          Cumul nb_produits : {$total_produits}\n\n";


// =====================================================================
// ETAPE 4 : Ecriture fichiers
// =====================================================================

// CSV complet (id, nom, type=0 partout, niveau_1, parent, nb_produits)
$fp = fopen($out_csv, 'w');
fputcsv($fp, ['id_rubrique', 'nom', 'type', 'niveau_1', 'parent', 'nb_produits']);
foreach ($all_leaves as $c) {
    fputcsv($fp, [
        $c['id_rubrique'],
        $c['nom_rubrique_francais'],
        $c['id_type_rubrique'],
        $c['id_rubrique_niveau_1'],
        $c['id_rubrique_parent'],
        $c['nb_produits'],
    ]);
}
fclose($fp);

// TXT : noms des leaves, uniquement celles avec produits
$fp = fopen($out_txt, 'w');
fwrite($fp, "# Categories leaves pour ingestion - generees par build_categories_list.php\n");
fwrite($fp, "# Keywords : " . implode(', ', $keywords) . "\n");
fwrite($fp, "# Niveau_1 sources : " . count($niveau_1_ids) . " rubriques\n");
fwrite($fp, "# Date     : " . date('Y-m-d H:i:s') . "\n\n");
$nb_with_prod = 0;
foreach ($all_leaves as $c) {
    if ((int) $c['nb_produits'] > 0) {
        fwrite($fp, $c['nom_rubrique_francais'] . "\n");
        $nb_with_prod++;
    }
}
fclose($fp);

echo "[DONE]\n";
echo "  -> {$out_csv}   (" . count($all_leaves) . " lignes)\n";
echo "  -> {$out_txt}   ({$nb_with_prod} categories avec produits)\n\n";


// =====================================================================
// Apercu TOP 30
// =====================================================================
echo "[TOP 30 leaves par nb_produits]\n";
printf("  %10s  %9s  %s\n", "ID", "PRODUITS", "NOM");
echo "  " . str_repeat("-", 90) . "\n";
$top = array_slice($all_leaves, 0, 30);
foreach ($top as $c) {
    printf("  %10s  %9s  %s\n",
        $c['id_rubrique'],
        $c['nb_produits'],
        mb_strimwidth($c['nom_rubrique_francais'], 0, 70, '...')
    );
}
echo "\n";
