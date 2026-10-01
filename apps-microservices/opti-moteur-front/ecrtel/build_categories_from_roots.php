<?php
/**
 * build_categories_from_roots.php
 * ================================
 * Recupere TOUTES les leaves (id_type_rubrique = 0) sous une ou plusieurs
 * rubriques racines (sections, niveau_1, niveau_n, peu importe).
 *
 * Cible par defaut :
 *   - 1000006 : Fabrication et processus (https://www.hellopro.fr/fabrication-et-processus-1000006-fr-rubrique.html)
 *   - 2000405 : Sante                     (https://www.hellopro.fr/sante-2000405-fr-rubrique.html)
 *
 * Methode : descente BFS (breadth-first) via id_rubrique_parent,
 *           fonctionne quel que soit le niveau de depart.
 *
 * Usage :
 *   php build_categories_from_roots.php
 *   php build_categories_from_roots.php 1000006 2000405 1000014
 *   ROOTS='1000006,2000405' php build_categories_from_roots.php
 *
 * Sortie :
 *   - categories_from_roots.csv     : vue complete (toutes leaves)
 *   - categories_from_roots.txt     : noms uniquement, prets pour ingestion
 */

require_once($_SERVER['DOCUMENT_ROOT'] . "include/connexion.php");
require_once($_SERVER['DOCUMENT_ROOT'] . "fonctions/fonctions_hellopro.php");


// =====================================================================
// CONFIG
// =====================================================================
define('RUB_TABLE', 'rubrique_front');

// Root ids a traiter
$root_ids = [];
if (!empty(getenv('ROOTS'))) {
    foreach (explode(',', getenv('ROOTS')) as $r) {
        $r = trim($r);
        if ($r !== '' && is_numeric($r)) $root_ids[] = (int) $r;
    }
} elseif ($argc > 1) {
    foreach (array_slice($argv, 1) as $r) {
        if (is_numeric($r)) $root_ids[] = (int) $r;
    }
} else {
    // Par defaut : Fabrication & processus + Sante
    $root_ids = [1000006, 2000405];
}

$out_csv = getenv('OUT_CSV') ?: 'categories_from_roots.csv';
$out_txt = getenv('OUT_TXT') ?: 'categories_from_roots.txt';
$max_depth = (int) (getenv('MAX_DEPTH') ?: 12);  // garde-fou contre cycles

$link = $GLOBALS['LINK_MYSQLI_ANNUAIRE_BO'];

echo "[CONFIG] Root ids : " . implode(', ', $root_ids) . "\n";
echo "[CONFIG] Table    : " . RUB_TABLE . "\n";
echo "[CONFIG] Outputs  : {$out_csv}, {$out_txt}\n\n";


// =====================================================================
// ETAPE 0 : Afficher les noms des racines pour verification
// =====================================================================
$ids_list = implode(',', $root_ids);
$sql0 = "
    SELECT id_rubrique, nom_rubrique_francais, id_type_rubrique, id_rubrique_parent,
           COALESCE(nombre_produits_rubrique, 0) AS nb_produits
    FROM " . RUB_TABLE . "
    WHERE id_rubrique IN ({$ids_list})
";
$res0 = mysqli_query($link, $sql0) or die(hellopro_mysql_error($sql0, $link));
echo "[ETAPE 0] Racines :\n";
while ($row = mysqli_fetch_assoc($res0)) {
    echo sprintf("  [%s] %s  (type=%s, parent=%s, nb_produits=%s)\n",
        $row['id_rubrique'],
        $row['nom_rubrique_francais'],
        $row['id_type_rubrique'],
        $row['id_rubrique_parent'],
        $row['nb_produits']);
}
mysqli_free_result($res0);
echo "\n";


// =====================================================================
// ETAPE 1 : BFS descent - collecte toutes les descendantes
// =====================================================================
$all_rubriques = [];    // id => row
$visited = [];          // id => true
$queue = $root_ids;
$depth = 0;

while (!empty($queue) && $depth < $max_depth) {
    $ids_q = implode(',', array_map('intval', $queue));
    $sql = "
        SELECT id_rubrique, nom_rubrique_francais, id_type_rubrique,
               id_rubrique_parent,
               COALESCE(nombre_produits_rubrique, 0) AS nb_produits
        FROM " . RUB_TABLE . "
        WHERE id_rubrique_parent IN ({$ids_q})
    ";
    $res = mysqli_query($link, $sql) or die(hellopro_mysql_error($sql, $link));

    $next_queue = [];
    $new_count = 0;
    while ($row = mysqli_fetch_assoc($res)) {
        $id = (int) $row['id_rubrique'];
        if (isset($visited[$id])) continue;
        $visited[$id] = true;
        $row['depth'] = $depth + 1;
        $all_rubriques[$id] = $row;
        $next_queue[] = $id;
        $new_count++;
    }
    mysqli_free_result($res);

    echo sprintf("  [depth=%d] %d nouvelles rubriques trouvees (total cumule : %d)\n",
        $depth + 1, $new_count, count($all_rubriques));

    $queue = $next_queue;
    $depth++;
}
echo "\n";


// =====================================================================
// ETAPE 2 : Filtrage leaves (id_type_rubrique = 0) + stats
// =====================================================================
$leaves = [];
$branches = [];
$total_produits_leaves = 0;
foreach ($all_rubriques as $r) {
    if ((int) $r['id_type_rubrique'] == 0) {
        $leaves[] = $r;
        $total_produits_leaves += (int) $r['nb_produits'];
    } else {
        $branches[] = $r;
    }
}

// Tri : nb_produits desc
usort($leaves, function($a, $b) {
    return ((int) $b['nb_produits']) - ((int) $a['nb_produits']);
});

echo "[ETAPE 2] Stats descente :\n";
echo "  - Branches (type=1)      : " . count($branches) . "\n";
echo "  - Leaves (type=0)        : " . count($leaves) . "\n";
echo "  - Total rubriques        : " . count($all_rubriques) . "\n";
echo "  - Produits cumules leaves: {$total_produits_leaves}\n\n";


// =====================================================================
// ETAPE 3 : Ecriture fichiers
// =====================================================================
// CSV complet (leaves seulement)
$fp = fopen($out_csv, 'w');
fputcsv($fp, ['id_rubrique', 'nom', 'type', 'depth', 'parent', 'nb_produits']);
foreach ($leaves as $c) {
    fputcsv($fp, [
        $c['id_rubrique'],
        $c['nom_rubrique_francais'],
        $c['id_type_rubrique'],
        $c['depth'],
        $c['id_rubrique_parent'],
        $c['nb_produits'],
    ]);
}
fclose($fp);

// TXT (noms uniquement, avec produits > 0)
$fp = fopen($out_txt, 'w');
fwrite($fp, "# Categories leaves (type=0) sous rubriques racines\n");
fwrite($fp, "# Racines : " . implode(', ', $root_ids) . "\n");
fwrite($fp, "# Date    : " . date('Y-m-d H:i:s') . "\n\n");
$nb_with_prod = 0;
foreach ($leaves as $c) {
    if ((int) $c['nb_produits'] > 0) {
        fwrite($fp, $c['nom_rubrique_francais'] . "\n");
        $nb_with_prod++;
    }
}
fclose($fp);

echo "[DONE]\n";
echo "  -> {$out_csv}   (" . count($leaves) . " leaves)\n";
echo "  -> {$out_txt}   ({$nb_with_prod} leaves avec produits)\n\n";


// =====================================================================
// Apercu TOP 50
// =====================================================================
echo "[TOP 50 leaves par nb_produits]\n";
printf("  %10s  %5s  %9s  %s\n", "ID", "DEPTH", "PRODUITS", "NOM");
echo "  " . str_repeat("-", 100) . "\n";
$top = array_slice($leaves, 0, 50);
foreach ($top as $c) {
    printf("  %10s  %5s  %9s  %s\n",
        $c['id_rubrique'],
        $c['depth'],
        $c['nb_produits'],
        mb_strimwidth($c['nom_rubrique_francais'], 0, 70, '...')
    );
}
echo "\n";
