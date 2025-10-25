<?php 
header('Content-Type: text/html; charset=UTF-8');

require_once($_SERVER['DOCUMENT_ROOT'] . "admin/secure/check_session.php");
require_once($_SERVER['DOCUMENT_ROOT'] . "include/connexion.php");
require_once($_SERVER['DOCUMENT_ROOT'] . "no_read_access/connexion_bdd_hellopro_ia.php");
require_once($_SERVER['DOCUMENT_ROOT'] . "fonctions/fonctions_hellopro.php");
require_once($_SERVER['DOCUMENT_ROOT'] . "fonctions/fonctions_generales.php");
require_once($_SERVER['DOCUMENT_ROOT'] . 'admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/fonctions/fonctions_scrapping.php');

// --- START: Legacy Functions ---
function get_nb_fichier($repertoire) {
    $count = shell_exec("find ". $repertoire ." -type f | wc -l");    
    return $count;
}

function obtenir_fichier_plus_recent($chemin_dossier)
{
    if (!is_dir($chemin_dossier)) {
        return [
            'fichier' => null,
            'date_modification' => null,
            'erreur' => "Le dossier spécifié n'existe pas."
        ];
    }

    $commande = "ls -tp " . escapeshellarg($chemin_dossier) . " | grep -v / | head -n 1";
    $nom_fichier = trim(shell_exec($commande));

    if (empty($nom_fichier)) {
        return [
            'fichier' => null,
            'date_modification' => null,
            'erreur' => "Aucun fichier trouvé dans le dossier."
        ];
    }

    $chemin_complet = rtrim($chemin_dossier, '/') . '/' . $nom_fichier;
    $timestamp_modification = filemtime($chemin_complet);
    $date_modification = date("d/m/Y H:i", $timestamp_modification);

    return [
        'fichier' => $nom_fichier,
        'date_modification' => $date_modification,
        'erreur' => null
    ];
}
// --- END: Legacy Functions ---

$id_domaine = $_POST["id_domaine"];

if(empty($id_domaine)) {
    exit("nok");
}

$sql_info_domaine = "
    SELECT
        domaine_dspi, systeme_dspi
    FROM
        domaine_scrapping_produit_ia DSPI
    WHERE
        id_domaine_scrapping_produit_ia = '". hellopro_traitement_donnee_annuaire_bo($id_domaine) ."'
";
$res_info_domaine = mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_info_domaine) or die(hellopro_mysql_error($sql_info_domaine, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));
$lig_info_domaine = mysqli_fetch_assoc($res_info_domaine);

if (!$lig_info_domaine) {
    exit("Domaine non trouvé");
}

$nom_domaine = $lig_info_domaine["domaine_dspi"];
$systeme = (int)$lig_info_domaine["systeme_dspi"];

$nb_fichier_crawler_ok = 0;
$nb_fichier_crawler_avec_erreur = 0;
$date_modification = "N/A";

if ($systeme === SYSTEM_API) {
    // --- New API System Logic ---
    $api_service = get_crawler_api_service();
    $status = $api_service->getStatus($id_domaine);

    if ($status && isset($status['urls_crawled'])) {
        $nb_fichier_crawler_ok = $status['urls_crawled'];
        $nb_fichier_crawler_avec_erreur = $status['error_urls_crawled'];
        if (!empty($status['last_activity'])) {
            $date_modification = date("d/m/Y H:i", strtotime($status['last_activity']));
        }
    } else {
        $date_modification = "Erreur API";
    }

} else {
    // --- Legacy System Logic ---
    $chemin_crawling_ok = $_SERVER["DOCUMENT_ROOT"] . "admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/tools/crawler/storage/datasets/{$nom_domaine}/";
    $chemin_crawling_erreur = $_SERVER["DOCUMENT_ROOT"] . "admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/tools/crawler/storage/datasets/error-{$nom_domaine}/";
    
    $nb_fichier_crawler_ok = get_nb_fichier($chemin_crawling_ok);
    $nb_fichier_crawler_avec_erreur = get_nb_fichier($chemin_crawling_erreur);

    $info_fichier_recent = obtenir_fichier_plus_recent($chemin_crawling_ok);
    $date_modification = $info_fichier_recent["date_modification"] ?? "N/A";
}
?>

<div>
    <span class="font-color-noir font-weight-500">Nb d'URL crawlés :</span>
    <span class="font-color-gris font-weight-600"><?= $nb_fichier_crawler_ok ?></span>
</div>
<div>
    <span class="font-color-noir font-weight-500">Nb d'URL avec erreur crawling :</span>
    <span class="font-color-gris font-weight-600"><?= $nb_fichier_crawler_avec_erreur ?></span>
</div>
<div>
    <span class="font-color-noir font-weight-500">Date du dernier crawl :</span>
    <span class="font-color-gris font-weight-600"><?= $date_modification ?></span>
</div>