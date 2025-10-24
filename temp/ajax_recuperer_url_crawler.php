<?php

header('Content-Type: text/html; charset=UTF-8');

require_once($_SERVER['DOCUMENT_ROOT'] . "admin/secure/check_session.php");
require_once($_SERVER['DOCUMENT_ROOT'] . "admin/secure/connexion.php");
require_once($_SERVER['DOCUMENT_ROOT'] . "no_read_access/connexion_bdd_hellopro_ia.php");
require_once($_SERVER['DOCUMENT_ROOT'] . "fonctions/fonctions_hellopro.php");
require_once($_SERVER['DOCUMENT_ROOT'] . "fonctions/fonctions_generales.php");
// --- START: Crawler Service Migration ---
require_once($_SERVER['DOCUMENT_ROOT'] . 'admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/fonctions/fonctions_scrapping.php');
// --- END: Crawler Service Migration ---

function recuperer_contenu_dossier($chemin_complet_dossier) {
    $tab_fichier = [];

    if (!is_dir($chemin_complet_dossier) || !($handle = opendir($chemin_complet_dossier))) {
        return [];
    }

    while (false !== ($entry = readdir($handle))) {
        if ($entry != "." && $entry != "..") {
            $tab_fichier[] = $entry;
        }
    }

    closedir($handle);

    return $tab_fichier;
}

function est_historique_pret($fichier_historique,$date_fin_crawling) {
    if(!file_exists($fichier_historique)) {
        return false; 
    }

    $timestamp_fichier_historique = filemtime($fichier_historique);

    if(!empty($date_fin_crawling) && !is_null($date_fin_crawling)) {
        $timestamp_fin_crawling = strtotime($date_fin_crawling);
        return $timestamp_fin_crawling < $timestamp_fichier_historique;
    } else {
        return true;
    }
}

function urls_fiches_produits($id_domaine){
    $urls = [];
    $sql_url = "SELECT
                            url_sfpi
                        FROM
                            scrapping_fiche_produit_ia SFPI
                        WHERE
                            id_domaine_scrapping_produit_sfpi =  '". hellopro_traitement_donnee_annuaire_bo($id_domaine) ."'
                            AND SFPI.est_dernier_sfpi = 1
    ";

    $res_url = mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_url) or die(hellopro_mysql_error($sql_url, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));

    while($lig_url = mysqli_fetch_assoc($res_url))
    {
        $urls[] = $lig_url["url_sfpi"];
    }
    return array_unique($urls);
}

function liste_url_historique($base_path, $use_cache, $fichier_url_cache, $date_fin_crawling) {

    $tab_url_crawler = array();

    /**
     * INFO: To force getting fresh crawling data even if cache is valid
     * Need to add `statut_domaine` related verification on the if : $statut_domaine != 9
     */
    $force_else = true;
    
    // Cache logic is only for the legacy system.
    if ($use_cache && est_historique_pret($fichier_url_cache, $date_fin_crawling) && !$force_else) {
        $liste_url_crawler = file_get_contents($fichier_url_cache);
        try {
            $tab_url_crawler = json_decode($liste_url_crawler, true);
        } catch(Exception $e) { 
            $tab_url_crawler = array();
        }
    } else {
        $tab_fichier_crawling = recuperer_contenu_dossier($base_path);
        
        foreach($tab_fichier_crawling as $fichier) {
            try{
                $json_content = file_get_contents($base_path . "/" . $fichier);
                $tab_json     = json_decode($json_content, true);
                if (isset($tab_json["url"])) {
                    $url_trouve = trim(trim($tab_json["url"]), "/");
                    $tab_url_crawler[] = $url_trouve;
                }
            } catch(Exception $e) {
                // Log error if needed
            }
        }

        if ($use_cache) {
            if(!file_exists(dirname($fichier_url_cache))) {
                mkdir(dirname($fichier_url_cache), 0777, true);
            }
            file_put_contents($fichier_url_cache, json_encode($tab_url_crawler));
        }
    }

    return $tab_url_crawler;
}

$id_domaine = $_POST["id_domaine"];

if(empty($id_domaine)) {
    exit("NOK");
}

$sql_info_domaine = "
    SELECT
        domaine_dspi,
        chemin_crawling_dspi,
        date_fin_crawling_dspi,
        statut_dspi,
        systeme_dspi
    FROM
        domaine_scrapping_produit_ia DSPI
    WHERE
        id_domaine_scrapping_produit_ia = '". hellopro_traitement_donnee_annuaire_bo($id_domaine) ."'
";

$res_info_domaine = mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_info_domaine) or die(hellopro_mysql_error($sql_info_domaine, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));
$lig_info_domaine = mysqli_fetch_assoc($res_info_domaine);

if (!$lig_info_domaine) {
    exit("Domaine non trouvé.");
}

$domaine = $lig_info_domaine["domaine_dspi"];
$systeme = (int)$lig_info_domaine["systeme_dspi"];
$date_fin_crawling = $lig_info_domaine["date_fin_crawling_dspi"];

$tab_url_crawler = [];
$tab_url_crawler_erreur = [];
$temporary_path_to_clean = null;

try {
    if ($systeme === SYSTEM_API) {
        $permanent_path_success = !empty($lig_info_domaine["chemin_crawling_dspi"]) ? $_SERVER['DOCUMENT_ROOT'] . $lig_info_domaine["chemin_crawling_dspi"] : null;
        $permanent_path_error = $permanent_path_success ? str_replace($domaine, "error-{$domaine}", $permanent_path_success) : null;

        if ($permanent_path_success && is_dir($permanent_path_success)) {
            // Data is permanently synced, read from local disk
            $tab_url_crawler = liste_url_historique($permanent_path_success, false, null, null);
            if (is_dir($permanent_path_error)) {
                $tab_url_crawler_erreur = liste_url_historique($permanent_path_error, false, null, null);
            }
        } else {
            // Data not synced, fetch a temporary live copy from the API
            $api_service = get_crawler_api_service();
            $include = ['dataset', 'dataset_error'];
            $temporary_path_to_clean = $api_service->getTemporaryResultsPath($id_domaine, $include);

            if ($temporary_path_to_clean === false) {
                exit("<div class='font-16 font-weight-600 font-color-rouge'>Erreur: Impossible de récupérer les résultats depuis le service de crawl.</div>");
            }
            
            $base_temp_path = $temporary_path_to_clean . '/storage/datasets/';
            $temp_path_success = $base_temp_path . $domaine;
            $temp_path_error = $base_temp_path . 'error-' . $domaine;
            
            $tab_url_crawler = liste_url_historique($temp_path_success, false, null, null);
            $tab_url_crawler_erreur = liste_url_historique($temp_path_error, false, null, null);
        }
    } else {
        // --- Legacy System Logic ---
        $chemin_crawling = $lig_info_domaine["chemin_crawling_dspi"];
        if(empty($chemin_crawling)) {
            $chemin_crawling = "/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/tools/crawler/storage/datasets/".$domaine."/";
        }

        if(strpos($chemin_crawling,$_SERVER["DOCUMENT_ROOT"]) === false) {
            $base_path_success = $_SERVER["DOCUMENT_ROOT"] . $chemin_crawling;
        } else {
            $base_path_success = $chemin_crawling;
        }

        $fichier_url_crawler = $_SERVER["DOCUMENT_ROOT"] . "admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/tools/crawler/storage/datasets/cache_historique/". $domaine ."_url_crawler.json";
        $tab_url_crawler = liste_url_historique($base_path_success, true, $fichier_url_crawler, $date_fin_crawling);
        
        $base_path_error = str_replace($domaine, "error-{$domaine}", $base_path_success);
        $fichier_url_crawler_erreur = $_SERVER["DOCUMENT_ROOT"] . "admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/tools/crawler/storage/datasets/cache_historique/error-". $domaine ."_url_crawler.json";
        $tab_url_crawler_erreur = liste_url_historique($base_path_error, true, $fichier_url_crawler_erreur, $date_fin_crawling);
    }

    // --- HTML Generation (Remains the Same) ---

    // recuperer url fiche produit
    $urls_fp = urls_fiches_produits($id_domaine);

    //trimmer les espace et "/" les urls fiches produits et les urls crawlées
    $urls_fp = array_map(function($url_fp) {
        return trim(trim($url_fp), "/");
    }, $urls_fp);
    $tab_url_crawler = array_map(function($url_crawler) {
        return trim(trim($url_crawler), "/");
    }, $tab_url_crawler);

    $html = "<div style='flex-basis: 100%'>Liste des URLs scrap&eacute;s pour le domaine <span class='font-weight-600'>". $domaine ." (". count($tab_url_crawler) .")</span></div>";
    $html .= <<<HTML
            <div class="d-flex align-items-center gp-8 mb-16 justify-content-space-between" style="flex-basis: 100%">
                <div class="d-flex gp-12">
                    <label class="label font-12 font-weight-700">Filtre :</label>
                    <select id="filtre_url_scraper">
                        <option selected="" value="all">Tous les urls sans erreur</option>
                        <option value="fp">Fiches produits</option>
                        <option value="autres">Autres Urls</option>
                        <option value="all_error">Tous les urls avec erreur</option>
                    </select>
                </div>
                <button class="btn btn-secondary btn-bleu btn-sm ml-8" id="btn_open_random_url">Ouvrir 5 pages al&eacute;atoirement</button>
            </div>
            <div class='d-flex gp-12 justify-content-space-between'>
            <div class='d-flex flex-d-column gp-8 all_url_fp all_url_content d-none' data-type='fp'>
    HTML;

    if(!empty($urls_fp)) {
        foreach($urls_fp as $nb_url_fp => $url_fp) {
            $url_fp = htmlspecialchars($url_fp);
            $html .= '<span class="font-14 font-weight-400 lh-20">'.($nb_url_fp+1).' - <a class="font-color-noir link-historique" href="'.$url_fp.'" target="_blank" rel="noopener noreferrer">'.$url_fp.'</a></span>';
        }
    } else {
        $html .= "<span class='font-16 font-weight-600 font-color-rouge'>Aucune URL de fiche produit trouv&eacute;e</span>";
    }
    $html .= "</div>";

    $html .="<div class='d-flex flex-d-column gp-8 all_url_scrapper all_url_content' data-type='all' style='word-break: break-all;'>";
    if(count($tab_url_crawler) > 0) {
        foreach($tab_url_crawler as $nb_url => $url_crawler) {
            $url_crawler = htmlspecialchars($url_crawler);
            $html .= '<span class="font-14 font-weight-400 lh-20">'.($nb_url+1).' - <a class="font-color-noir link-historique" href="'.$url_crawler.'" target="_blank" rel="noopener noreferrer">'.$url_crawler.'</a></span>';
        }
    } else {
        $html .= "<span class='font-16 font-weight-600 font-color-rouge'>Aucune URL crawl&eacute;e sans erreur</span>";
    }
    $html .= "</div>";

    $tab_autres_url = array_values(array_diff($tab_url_crawler, $urls_fp));

    $html .= "<div class='d-flex flex-d-column gp-8 all_url_autres all_url_content d-none' data-type='autres' style='word-break: break-all;'>";

    if(count($tab_autres_url) > 0) {
        foreach($tab_autres_url as $nb_url => $url_autres) {
            $url_autres = htmlspecialchars($url_autres);
            $html .= '<span class="font-14 font-weight-400 lh-20">'.($nb_url+1).' - <a class="font-color-noir link-historique" href="'.$url_autres.'" target="_blank" rel="noopener noreferrer">'.$url_autres.'</a></span>';
        }
    } else {
        $html .= "<span class='font-16 font-weight-600 font-color-rouge'>Aucune URL autre que fiche produit</span>";
    }

    $html .= "</div>";

    $html .= "<div class='d-flex flex-d-column gp-8 all_url_scrapper_erreur all_url_content d-none' data-type='all_error' style='word-break: break-all;'>";

    if(count($tab_url_crawler_erreur) > 0) {
        foreach($tab_url_crawler_erreur as $nb_url => $url_crawler_erreur) {
            $url_crawler_erreur = htmlspecialchars($url_crawler_erreur);
            $html .= '<span class="font-14 font-weight-400 lh-20">'.($nb_url+1).' - <a class="font-color-noir link-historique" href="'.$url_crawler_erreur.'" target="_blank" rel="noopener noreferrer">'.$url_crawler_erreur.'</a></span>';
        }
    } else {
        $html .= "<span class='font-16 font-weight-600 font-color-rouge'>Aucune URL en erreur de crawling</span>";
    }

    $html .= "</div></div>";
    echo $html;

} finally {
    // --- START: Crawler Service Migration ---
    // Always clean up the temporary directory if it was created
    if ($temporary_path_to_clean) {
        get_crawler_api_service()->cleanupTemporaryPath($temporary_path_to_clean);
    }
    // --- END: Crawler Service Migration ---
}
exit();
?>