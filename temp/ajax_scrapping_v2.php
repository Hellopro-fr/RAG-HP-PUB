<?php
header('Content-Type: text/html; charset=UTF-8');

// Constants
define('BATCH_SIZE', 100);
define('MAX_EXECUTION_TIME', 30);

// --- START: MODIFIED FOR MIGRATION ---
// Cache constants are no longer needed here, will be managed via Redis TTL.
// define('MAX_CACHE_SIZE', 100 * 1024 * 1024); // 100MB max
// define('MAX_CACHE_AGE', 300); // 5 minutes
// --- END: MODIFIED FOR MIGRATION ---

// Set execution time limit
set_time_limit(MAX_EXECUTION_TIME);
require_once($_SERVER['DOCUMENT_ROOT'] . "admin/secure/check_session.php");
require_once($_SERVER['DOCUMENT_ROOT'] . "admin/secure/connexion.php");
require_once($_SERVER['DOCUMENT_ROOT'] . "no_read_access/connexion_bdd_hellopro_ia.php");
require_once($_SERVER['DOCUMENT_ROOT'] . "fonctions/fonctions_hellopro.php");
require_once($_SERVER['DOCUMENT_ROOT'] . "fonctions/fonctions_generales.php");
require_once($_SERVER["DOCUMENT_ROOT"] . "fichiers_communs_bo_front/partenaires_externes/zoho/class/Records.php");
require_once($_SERVER["DOCUMENT_ROOT"] . "admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/fonctions/fonctions_scrapping.php");
require_once($_SERVER["DOCUMENT_ROOT"] . "admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/class/ComparateurSelecteur.php");
require_once($_SERVER['DOCUMENT_ROOT'] . "admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/class/BatchProcessor.php");

// --- START: Crawler Service Migration ---
$GLOBALS['temp_paths_to_clean'] = [];

register_shutdown_function(function() {
    if (!empty($GLOBALS['temp_paths_to_clean'])) {
        $api_service = get_crawler_api_service();
        foreach ($GLOBALS['temp_paths_to_clean'] as $path) {
            $api_service->cleanupTemporaryPath($path);
        }
    }
});

/**
 * Determines the correct path to crawl data, handling both legacy and API systems.
 * For API systems, it checks for a permanently synced path first, then falls back to a temporary download.
 *
 * @param int $id_domaine
 * @param string $component The component to fetch (e.g., 'dataset', 'dataset_error').
 * @return string|false The absolute path to the data, or false on failure.
 */
function _get_crawl_data_path($id_domaine, $component) {
    $sql = "SELECT domaine_dspi, chemin_crawling_dspi, systeme_dspi FROM domaine_scrapping_produit_ia WHERE id_domaine_scrapping_produit_ia = '" . hellopro_traitement_donnee_annuaire_bo($id_domaine) . "'";
    $res = mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql);
    $domain_info = mysqli_fetch_assoc($res);

    if (!$domain_info) {
        return false;
    }

    $domaine = $domain_info['domaine_dspi'];
    $systeme = (int)$domain_info['systeme_dspi'];
    $permanent_path = !empty($domain_info['chemin_crawling_dspi']) ? $_SERVER['DOCUMENT_ROOT'] . $domain_info['chemin_crawling_dspi'] : null;

    $dataset_map = [
        'dataset' => $domaine,
        'dataset_error' => 'error-' . $domaine,
        'dataset_nfr' => 'nfr-' . $domaine,
    ];
    $folder_name = $dataset_map[$component] ?? $domaine;

    if ($systeme === SYSTEM_API) {
        if ($permanent_path && is_dir($permanent_path)) {
            // Crawl is finished and synced, use the permanent local path.
            return str_replace($domaine, $folder_name, $permanent_path);
        } else {
            // In-progress or failed crawl, fetch a temporary copy from the API.
            $api_service = get_crawler_api_service();
            $temp_path = $api_service->getTemporaryResultsPath($id_domaine, [$component]);

            if ($temp_path === false) {
                return false;
            }

            // Register path for cleanup and return the specific component path.
            $GLOBALS['temp_paths_to_clean'][$temp_path] = $temp_path;
            return $temp_path . '/storage/datasets/' . $folder_name;
        }
    } else {
        // Legacy system logic.
        $chemin_crawling = $domain_info["chemin_crawling_dspi"] ?: "/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/tools/crawler/storage/datasets/".$domaine."/";
        if ($component === 'dataset_error') {
            $chemin_crawling = str_replace($domaine, $folder_name, $chemin_crawling);
        }
        return $_SERVER['DOCUMENT_ROOT'] . $chemin_crawling;
    }
}
// --- END: Crawler Service Migration ---


$records = new Records([
    "endpoint"     => "",
    "access_token" => "",
    "api_domain"   => ""
]);

function get_info_adminstr($id_admin) {
    
    $sql = "
        SELECT
            login_administrateur
        FROM administrateur A
        WHERE id_administrateur = '".hellopro_traitement_donnee_annuaire_bo($id_admin)."'
    ";
    $res_user = mysqli_query($GLOBALS['LINK_MYSQLI_ANNUAIRE_BO'], $sql) or die(hellopro_mysql_error($sql, $GLOBALS['LINK_MYSQLI_ANNUAIRE_BO']));
    $result = mysqli_fetch_assoc($res_user);
    
    return !empty($result["login_administrateur"]) ? $result["login_administrateur"] : "";
}

function trait_filtre() {
    global $list_filtre, $ordre, $_POST;

    $page = (!empty($_POST['page'])) ? $_POST['page'] : 1;
    $size = (!empty($_POST['size'])) ? $_POST['size'] : 100;
    $index = $page > 0 ? $size * ($page - 1) : 0;
    $limit = " LIMIT $index, $size ";

    $corres_champs = [
        "id_domaine_scrapping_produit_ia" => "DSPI.id_domaine_scrapping_produit_ia",
        "domaine_dspi"                    => "DSPI.domaine_dspi",
        "date_creation_dspi"              => "DSPI.date_creation_dspi",
        "cms_dspi"                        => "DSPI.cms_dspi",
        "statut_dspi"                     => "DSPI.statut_dspi",
        "utilisateur_dspi"                => "DSPI.utilisateur_dspi",
        "statut_crawler_eci"              => "ECI.statut_crawler_eci",
    ];

    $liste_type_2 = ["domaine_dspi"];
    $liste_type_1 = ["id_domaine_scrapping_produit_ia", "cms_dspi", "statut_dspi", "utilisateur_dspi" , "statut_crawler_eci"];
    $liste_type_4 = ["date_creation_dspi"];
    $ordonable = ["id_domaine_scrapping_produit_ia", "date_creation_dspi", "cms_dspi", "statut_dspi"];

    $where_filtre = [];

    // Gestion des filtres
    if (!empty($list_filtre)) {
        foreach ($list_filtre as $champs => $filtre) {
            $condition = $filtre["condition"];
            $filtre["new_value"] = hellopro_traitement_donnee_annuaire_bo($filtre["new_value"]);

            if (in_array($champs, $liste_type_1)) {
                if ($champs === "cms_dspi") {
                    $filtre["new_value"] = !empty($filtre["new_value"]) ? $filtre["new_value"] : "";
                    switch ($condition) {
                        case "est":
                            $where_filtre[] = "JSON_EXTRACT(DSPI.cms_dspi, '$.cms_name') = '" . $filtre["new_value"] . "'";
                            break;
                        case "n_est_pas":
                            $where_filtre[] = "JSON_EXTRACT(DSPI.cms_dspi, '$.cms_name') != '" . $filtre["new_value"] . "'";
                            break;
                        case "contient":
                            $where_filtre[] = "JSON_EXTRACT(DSPI.cms_dspi, '$.cms_name') LIKE '%" . $filtre["new_value"] . "%'";
                            break;
                        case "est_vide":
                            $where_filtre[] = "(JSON_EXTRACT(DSPI.cms_dspi, '$.cms_name') IS NULL OR JSON_EXTRACT(DSPI.cms_dspi, '$.cms_name') = '')";
                            break;
                        case "n_est_pas_vide":
                            $where_filtre[] = "(JSON_EXTRACT(DSPI.cms_dspi, '$.cms_name') IS NOT NULL AND JSON_EXTRACT(DSPI.cms_dspi, '$.cms_name') <> '')";
                            break;
                    }
                } else {
                    $filtre_traite = implode("','", $filtre["values"]);
                    switch ($condition) {
                        case "est":
                            $where_filtre[] = $corres_champs[$champs] . " IN ('" . $filtre_traite . "')";
                            break;
                        case "n_est_pas":
                            $where_filtre[] = $corres_champs[$champs] . " NOT IN ('" . $filtre_traite . "')";
                            break;
                    }
                }
            } elseif (in_array($champs, $liste_type_2)) {
                switch ($condition) {
                    case "est":
                        if ($filtre["new_value"]) {
                            $where_filtre[] = $corres_champs[$champs] . " = '" . $filtre["new_value"] . "'";
                        }
                        break;
                    case "n_est_pas":
                        if ($filtre["new_value"]) {
                            $where_filtre[] = $corres_champs[$champs] . " <> '" . $filtre["new_value"] . "'";
                        }
                        break;
                    case "est_vide":
                        $where_filtre[] = "(" . $corres_champs[$champs] . " = '' OR " . $corres_champs[$champs] . " IS NULL)";
                        break;
                    case "n_est_pas_vide":
                        $where_filtre[] = "(" . $corres_champs[$champs] . " <> '' AND " . $corres_champs[$champs] . " IS NOT NULL)";
                        break;
                    case "contient":
                        if ($filtre["new_value"]) {
                            if($champs == "domaine_dspi") {
                                $where_filtre[] = " ( " . $corres_champs[$champs] . " LIKE '%" . $filtre["new_value"] . "%' OR " . "JSON_EXTRACT(DSPI.data_crawling_dspi, '$.old_url') LIKE '%" . $filtre["new_value"] . "%' ) ";
                            }
                            else
                            {
                                $where_filtre[] = $corres_champs[$champs] . " LIKE '%" . $filtre["new_value"] . "%'";
                            }
                        }
                        
                        break;
                }
            } elseif (in_array($champs, $liste_type_4)) {
                $date_debut = $filtre["values"][0];
                if (!empty(trim($date_debut))) {
                    $date_debut = DateTime::createFromFormat('d/m/Y', $date_debut);
                    $date_debut = $date_debut->format('Y-m-d');
                    $date_fin = isset($filtre["values"][1]) ? $filtre["values"][1] : '';

                    if (!empty(trim($date_fin))) {
                        $date_fin = DateTime::createFromFormat('d/m/Y', $date_fin);
                        $date_fin = $date_fin->format('Y-m-d');
                    }

                    switch ($condition) {
                        case "est":
                            $where_filtre[] = $corres_champs[$champs] . " BETWEEN '" . $date_debut . " 00:00:00' AND '" . $date_debut . " 23:59:59'";
                            break;
                        case "avant":
                            $where_filtre[] = $corres_champs[$champs] . " < '" . $date_debut . " 00:00:00'";
                            break;
                        case "apres":
                            $where_filtre[] = $corres_champs[$champs] . " > '" . $date_debut . " 23:59:59'";
                            break;
                        case "entre":
                            if (!empty(trim($date_fin))) {
                                $where_filtre[] = $corres_champs[$champs] . " BETWEEN '" . $date_debut . " 00:00:00' AND '" . $date_fin . " 23:59:59'";
                            }
                            break;
                    }
                }
            }
        }
    } else {
        // Si aucun filtre n'est envoyé, inclure tous les statuts sauf "Non commencé"
        $where_filtre[] = "DSPI.statut_dspi > 0";
    }

    // Toujours inclure la condition DSPI.statut_dspi > 0
    if (!in_array("DSPI.statut_dspi > 0", $where_filtre)) {
        $where_filtre[] = "DSPI.statut_dspi > 0";
    }

    // Construire la clause WHERE
    $str_filtre = !empty($where_filtre) ? " WHERE " . implode(" AND ", $where_filtre) : "";   
    
    //skipper les domaines qu'ont ne va pas crawler
    $skip_upload = " DSPI.id_upload_dspi NOT IN (25,26,27,28,29,30,31,32) OR DSPI.id_upload_dspi IS NULL ";
    $str_filtre = empty($str_filtre) ? " WHERE " . $skip_upload : $str_filtre . " AND ( " . $skip_upload . " ) ";

    $sql_order_by = "";
    $tab_order_by = [];
    $corres_ordre = ["asc" => "ASC", "desc" => "DESC"];

    foreach ($ordre as $champs => $value) {
        if (in_array($champs, $ordonable)) {
            $tab_order_by[] = $corres_champs[$champs] . " " . $corres_ordre[$value];
        }
    }

    $sql_order_by = empty($tab_order_by) ? " DSPI.id_domaine_scrapping_produit_ia DESC " : implode(", ", $tab_order_by);

    return [
        "sql_order_by" => $sql_order_by,
        "str_filtre"   => $str_filtre,
        "limit"        => $limit
    ];
}

function generateProgressBar($current_step, $total_steps = 6) {
    global $data_statut;
    $progress_bars = '';

    $class_parent_en_cours_crawling = "";
    $container_info = "";
    # Cas des en cours crawling et des erreurs crawlings
    if(in_array($current_step,array(1,9))) {
            $class_parent_en_cours_crawling = "p-relative cursor-pointer voir-stat-crawling";
            $container_info = '
                <div class="info-en-cours-crawling p-absolute p-12 border-radius-4 d-none">
                    <div class="d-flex flex-d-column gp-8 text-align-left">
                        <div class="text-align-center">
                            <i class="loader loader-xs"></i>
                        </div>
                    </div>
                </div>
            ';
        }
    // Si l'étape est 7 ou 8 (indéterminée)
    if (in_array($current_step, [7, 8 , 9 , 10 , 12])) {
        $status_class = 'progress-indeterminate'; // Animation pour indéterminée
        // Ajouter la ligne de progression pour l'état indéterminé
        $progress_bars = "<div class='progress-line {$status_class} {$class_parent_en_cours_crawling}'>{$container_info}</div>";
    } else if($current_step == 14) {
        $status_class = 'progress-sans-fp';  // Ligne verte
        // Ajouter la ligne de progression pour l'état indéterminé
        $progress_bars = "<div class='progress-line {$status_class} {$class_parent_en_cours_crawling}'>{$container_info}</div>";
    }
     else {
        // Parcours de toutes les étapes de 1 à $total_steps
        if($current_step == 11) {
            $current_step = 1;
        }
        for ($step = 1; $step <= $total_steps; $step++) {
            // Si l'étape est terminée (avant l'étape en cours)
            if ($step < $current_step) {
                $status_class = 'completed';  // Ligne verte
            }
            // Si l'étape est l'étape en cours
            elseif ($step == $current_step) {
                $status_class = ($step !== 6) ? 'current' : 'completed'; // orange sinon verte
            }
            // Si l'étape n'a pas encore commencé
            else {
                $status_class = 'upcoming';  // Ligne grise
            }

            $step = $step == 6 && $current_step == 13 ? 13 : $step;

            $tooltip = $status_class == 'completed' ? " tooltip-position='bottom' data-tooltip='tooltip' data-position='bottom'  data-direction='up' data-content='" .$data_statut[$step] ." '" : '';
         
            if($status_class != "current") {
                $class_parent_en_cours_crawling = "";
                $container_info = "";
            }
            
            // Ajouter la ligne de progression pour chaque étape
            $progress_bars .= "<div class='progress-line {$status_class} {$class_parent_en_cours_crawling}'  {$tooltip} >{$container_info}</div>";
        }
    }

    // Retourner la barre complète
    return "<div class='progress-bar'>{$progress_bars}</div>";
}

 // Récupérer les URLs fiches produits
 function urls_fiches_produits($id_domaine, $withContent = false) {
    $urls = [];
    $whileContent = $withContent ? " , contenu_scrapping_sfpi " : "";
    $sql_url = "SELECT DISTINCT
                    id_scrapping_fiche_produit_ia,
                    url_sfpi
                    {$whileContent}
                FROM
                    scrapping_fiche_produit_ia SFPI
                WHERE
                    id_domaine_scrapping_produit_sfpi = '". hellopro_traitement_donnee_annuaire_bo($id_domaine) ."'
                    AND SFPI.est_dernier_sfpi = 1";

    $res_url = mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_url) 
        or die(hellopro_mysql_error($sql_url, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));

    while($lig_url = mysqli_fetch_assoc($res_url)) {
        // Correction de la structure du tableau
        $tempData = [
            'id' => $lig_url['id_scrapping_fiche_produit_ia'],
            'url' => trim(trim($lig_url["url_sfpi"]), '/')
        ]; 
        if ($withContent) {
            $tempData['content'] = $lig_url['contenu_scrapping_sfpi'] ?? '';
        }
        $urls[] = $tempData;
        
    }
    return $urls; // Retourne un tableau avec id et url
}

// Récupérer les URLs crawlées
function get_crawled_urls($id_domaine, $withContent = false) {
    // --- START: MODIFIED FOR MIGRATION ---
    $base_path = _get_crawl_data_path($id_domaine, 'dataset');
    if ($base_path === false || !is_dir($base_path)) {
        return [];
    }
    // --- END: MODIFIED FOR MIGRATION ---

    // The rest of the function logic remains the same but uses the determined base_path
    $urls = [];
    if ($handle = opendir($base_path)) {
        while (false !== ($file = readdir($handle))) {
            if ($file != "." && $file != ".." && pathinfo($file, PATHINFO_EXTENSION) == 'json') {
                $json = json_decode(file_get_contents($base_path . DIRECTORY_SEPARATOR . $file), true);
                if (isset($json['url'])) {
                    $url_autre = trim(trim($json['url']), '/');
                    if($withContent)
                    {
                        $urls[$url_autre] = [
                            'url' => $url_autre,
                            'content' => $json['content'] ?? ''
                        ];
                    }
                    else{
                        $urls[] = $url_autre;
                    }
                }
            }
        }
        closedir($handle);
    }
    return !$withContent ? array_unique($urls) : $urls ;
}


function getJsonContentFromCache($id_domaine) {
    // --- START: MODIFIED FOR MIGRATION ---
    // This function now uses a shared Redis cache for high performance across multiple AJAX calls.
    
    $redis = get_redis_client(); // Assumes a global function to get a Redis client instance
    $cache_key = "cache:crawl_content:" . $id_domaine;
    
    // 1. Try to get data from Redis cache
    if ($redis) {
        $cached_data = $redis->get($cache_key);
        if ($cached_data) {
            return json_decode($cached_data, true);
        }
    }

    // 2. If not in cache (Cache Miss), load data from source
    $sql = "SELECT chemin_crawling_dspi, urls_fiches_produits_dspi, systeme_dspi, domaine_dspi 
            FROM domaine_scrapping_produit_ia 
            WHERE id_domaine_scrapping_produit_ia = '".hellopro_traitement_donnee_annuaire_bo($id_domaine)."'";
    
    $res = mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql) or die(hellopro_mysql_error($sql, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));
    $data = mysqli_fetch_assoc($res);
    
    if (!$data) {
        return null;
    }

    $systeme = (int)$data['systeme_dspi'];
    $domaine = $data['domaine_dspi'];
    $permanent_path_synced = !empty($data['chemin_crawling_dspi']) && is_dir($_SERVER['DOCUMENT_ROOT'] . $data['chemin_crawling_dspi']);

    $chemin_crawling = null;

    if ($systeme === SYSTEM_API && !$permanent_path_synced) {
        $api_service = get_crawler_api_service();
        $temp_path = $api_service->getTemporaryResultsPath($id_domaine, ['dataset']);

        if ($temp_path === false) return null;

        $GLOBALS['temp_paths_to_clean'][$temp_path] = $temp_path;
        $chemin_crawling = $temp_path . '/storage/datasets/' . $domaine;
    } else {
        $chemin_crawling = $_SERVER['DOCUMENT_ROOT'] . ltrim($data['chemin_crawling_dspi'], '\\');
    }
    
    // Traiter les fichiers par lots pour économiser la mémoire
    $urlsContent = [];
    if ($chemin_crawling && is_dir($chemin_crawling)) {
        $dir = dir($chemin_crawling);
        if ($dir) {
            while (false !== ($file = $dir->read())) {
                if ($file != "." && $file != ".." && pathinfo($file, PATHINFO_EXTENSION) == 'json') {
                    $filePath = $chemin_crawling . '/' . $file;
                    $fileContent = file_get_contents($filePath);
                    if ($fileContent === false) {
                        error_log("Failed to read file: " . $filePath);
                        continue;
                    }
                    
                    $json = json_decode($fileContent, true);
                    if (!$json || !isset($json['url'], $json['content'])) {
                        error_log("Invalid JSON in file: " . $filePath);
                        continue;
                    }

                    $normalizedUrl = trim(trim($json['url']), '/');
                    $urlsContent[$normalizedUrl] = $json['content'];
                    
                    // Libérer la mémoire
                    unset($fileContent, $json);
                }
            }
            $dir->close();
        }
    }
    
    $result_data = [
        'urls_content' => $urlsContent,
        'nb_produit_fp' => intval($data['urls_fiches_produits_dspi'])
    ];

    // 3. Store the newly loaded data in Redis with a 5-minute TTL
    if ($redis) {
        $redis->set($cache_key, json_encode($result_data), ['ex' => 300]); // 300 seconds = 5 minutes
    }
    
    return $result_data;
    // --- END: MODIFIED FOR MIGRATION ---
}

function is_valid_regex($pattern) {
    // //verifier s'il commence par un / ou # si non ajouter un / 
    // if (!preg_match('/^[\/#]/', $pattern)) {
    //     $pattern = '/' . $pattern . '/i';
    // }
    return @preg_match($pattern, '') !== false;
}

$data_statut = get_statut_crawling();
$etat_enqueue = [
    0 => "En attente",
    1 => "En cours",
    2 => "Terminé" ,
    3 => "Partiellement terminé",
    4 => "Erreur",
];

$input = json_decode(file_get_contents('php://input'), true);
$action      = isset($input['action']) ? $input['action'] : $_POST['action'];
$list_filtre = isset($input['filtre']) ? $input['filtre'] : $_POST['filtre'];
$ordre       = isset($input['ordre']) ? $input['ordre'] : $_POST['ordre'];

$maxExecutionTime = 30; // 30 seconds max execution time
$batchSize = 100; // Default batch size for processing

// Initialize global session array if not exists
if (!isset($_SESSION['qualification_processing'])) {
    $_SESSION['qualification_processing'] = [];
}

switch ($action) {
    case 'charger_donnees_scrapping':
        extract(trait_filtre());
    
        // Requête principale pour récupérer les données paginées
        $sql_main = "
                SELECT
                    DSPI.id_domaine_scrapping_produit_ia,
                    DSPI.domaine_dspi,
                    DSPI.date_creation_dspi,
                    DSPI.cms_dspi,
                    DSPI.statut_dspi,
                    DSPI.utilisateur_dspi,
                    DSPI.id_societe_dspi,
                    DSPI.id_upload_dspi,
                    ECI.statut_crawler_eci,
                    ECI.nb_retry_eci,
                    DSPI.id_upload_scrapping_produit_ia,
                    DSPI.data_crawling_dspi
                FROM domaine_scrapping_produit_ia DSPI
                LEFT JOIN enqueue_crawling_ia ECI ON DSPI.id_domaine_scrapping_produit_ia = ECI.id_domaine_scrapping_produit_ia
                {$str_filtre}
                GROUP BY
                    DSPI.id_domaine_scrapping_produit_ia
                ORDER BY
                    {$sql_order_by} 
                ";
    
        // Requête pour compter le nombre total de domaines (sans pagination)
        $sql_count = "
            SELECT COUNT(DISTINCT DSPI.id_domaine_scrapping_produit_ia) AS total
            FROM domaine_scrapping_produit_ia DSPI
            LEFT JOIN enqueue_crawling_ia ECI ON DSPI.id_domaine_scrapping_produit_ia = ECI.id_domaine_scrapping_produit_ia
            {$str_filtre}
        ";
    
        $res_count = mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_count) or die(hellopro_mysql_error($sql_count, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));
        $row_count = mysqli_fetch_assoc($res_count);
        $nb_total_domaine = $row_count['total'];
    
        // Requête paginée
        $sql_scrapping = $sql_main . $limit;
        $res_scrapping = mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_scrapping) or die(hellopro_mysql_error($sql_scrapping, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));
    
        $tbody_content = [];
        $nb_skip = 0;
        while ($lig_scrapping = mysqli_fetch_assoc($res_scrapping)) {
            $id_dspi       = $lig_scrapping['id_domaine_scrapping_produit_ia'];
            $id_upload     = $lig_scrapping['id_upload_dspi'];
            $domaine       = $lig_scrapping['domaine_dspi'];
            $date_creation = date("d/m/Y H:i", strtotime($lig_scrapping['date_creation_dspi']));
            $info_cms      = json_decode($lig_scrapping['cms_dspi'], true);
            $statut        = $data_statut[$lig_scrapping['statut_dspi']];
            $id_societe    = $lig_scrapping['id_societe_dspi'];
            $id_upload_scrapping = $lig_scrapping['id_upload_scrapping_produit_ia'];
            $data_crawl    = json_decode($lig_scrapping['data_crawling_dspi'] , true);
            $homepage      = !empty($data_crawl['homepage']) ? $data_crawl['homepage'] : "https://".$domaine; 
            $old_url       = !empty($data_crawl['old_url']) ? " <br>→ Url avant redirection : " . $data_crawl['old_url'] : "";
            if ($statut == 'Non commencé') continue;
    
            $enqueue        = $etat_enqueue[$lig_scrapping['statut_crawler_eci']];

            if($lig_scrapping['statut_crawler_eci'] == 4 && !empty($lig_scrapping['nb_retry_eci'])) {
                $enqueue .= " ( ".$lig_scrapping['nb_retry_eci']." relances )";
            }

            # Id upload pour les passifs
            if(empty($id_upload)) {
                $sql_get_id_upload = "
                    SELECT
                        id_upload_df
                    FROM domaine_francais DF
                    WHERE domaine_df = '". hellopro_traitement_donnee_annuaire_bo($domaine) ."'
                ";
                $res_get_id_upload = mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_get_id_upload) or die(hellopro_mysql_error($sql_get_id_upload, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));
                $lig_get_id_upload = mysqli_fetch_assoc($res_get_id_upload);
                $id_upload = $lig_get_id_upload["id_upload_df"];
                //skipper les domaines qu'ont ne va pas crawler
                if(in_array($id_upload , [25,26,27,28,29,30,31,32]) && empty($id_upload_scrapping))
                {
                    $nb_total_domaine--;
                    continue;
                }
            }

            $statut_key = $lig_scrapping['statut_dspi'];
            // Générer la barre de progression
            $progress_bar = generateProgressBar($statut_key);
            $statut_span = "";
            if (in_array($statut_key,[6,13])) {
                $statut_span = "<span class='badge badge-success-2'><i class='bx bxs-check-circle'></i> $statut</span>";
            } elseif (in_array($statut_key, [1, 3, 5 , 11])) {
                $statut_span = "<span class='badge badge-warning-2'><i class='bx bx-alarm-exclamation'></i> $statut</span>";
            } elseif (in_array($statut_key, [2, 4, 14])) {
                $statut_span = "<span class='badge badge-info-2'><i class='bx bx-search'></i> $statut</span>";
                if($statut_key == 14) {
                    $statut_span = "<span class='badge badge-info-2'><i class='bx bx-x-circle'></i> $statut</span>";
                }
            } else if (in_array($statut_key, [7, 8 , 9 , 10 , 12])) {
                $statut_span = "<span class='badge badge-danger'><i class='bx bx-x-circle'></i> $statut</span>";
            } else {
                $statut_span = "<span class='badge badge-secondary-2'><i class='bx bx-time-five'></i> $statut</span>";
            }

            $utilisateur      = !empty($lig_scrapping['utilisateur_dspi']) ? get_info_adminstr($lig_scrapping['utilisateur_dspi']) : "";
            
            $link_details  = "";
            $link_fiche_societe = "";
            $link_domaine_sans_fp = "";
            if($statut_key == '2')
            {
                $link_details     = "<a class='btn-link-details' data-url='https://{$_SERVER['HTTP_HOST']}/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/verification_resultat.php?id_domaine={$id_dspi}&p=keywords' target='_blank'>Détails Top fiche</a>";
            }
            else if($statut_key == '4')
            {
                $link_details     = "<a class='btn-link-details' data-url='https://{$_SERVER['HTTP_HOST']}/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/verification_resultat.php?id_domaine={$id_dspi}' target='_blank'>Détails Sélecteurs</a>";                
            } 
            else if(in_array($statut_key,[6,13]))
            {
                $link_details     = "<a class='btn-link-details' data-url='https://{$_SERVER['HTTP_HOST']}/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/detail_fiche_produit.php?id_domaine={$id_dspi}' target='_blank'>Voir les fiches produits</a>";                
            }
            $btn_link_show = (!empty($link_details)) 
            ? "<span class='d-flex gp-4 font-color-gris font-weight-500 cursor-pointer btn-action-crawling'><i class='bx bxs-show'></i>{$link_details}</span>" 
            : "";

            if($statut_key == '7')
            {
                $btn_link_show = "<span class='d-flex gp-4 font-color-gris font-weight-500 cursor-pointer btn-action-crawling btn-maj-domaine' data-domaine='{$domaine}' data-id='{$id_dspi}' data-home='{$homepage}'  data-modal='show' data-target='modal_maj_domaine'><i class='bx bxs-show'></i>Modifier domaine</span>";                
            }

            if($id_societe != 0)
            {
                $link_fiche_societe = '<span class="d-flex gp-4 font-color-gris font-weight-500 cursor-pointer btn-action-crawling">
                                            <i class="bx bx-alarm"></i>
                                            <a target="_blank" class="font-color-gris btn-action-crawling" href="https://'.$_SERVER['HTTP_HOST'].'/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/fiche_societe.php?id_societe='.$id_societe.'">  Fiche société</a>
                                        </span>';
            }

            if(!in_array($statut_key, [14])) {
                $link_domaine_sans_fp = '<span class="d-flex gp-4 font-color-gris font-weight-500 cursor-pointer btn-action-sansfp" data-id_domaine="'.trim($id_dspi).'">
                                            <i class="bx bx-file"></i>
                                            Domaine sans fiche produits
                                        </span>';
            }
           

            $link_historique = "";
            if(!empty($btn_link_show) || in_array($statut_key, [8 , 9 , 10 , 12, 14])) {
                $link_historique = '
                    <span class="voir-historique d-flex gp-4 font-color-gris font-weight-500 cursor-pointer btn-action-crawling" data-id_domaine="'.$id_dspi.'">
                        <i class="bx bx-alarm"></i>
                        Historique
                    </span>
                '; 
            }

            //option de relance crawl
            $link_relance_crawl = "";
            if(in_array($statut_key, [7, 9 , 10 , 12, 14])) {
                $link_relance_crawl = '                            
                            <span class="relaunch-crawl d-flex gp-4 font-color-gris font-weight-500 cursor-pointer btn-action-crawling"  data-id="'. $id_dspi .'" data-domaine="'. $domaine .'" data-home="'. $homepage .'"  data-modal="show" data-target="modal_relance_crawl">
                                <i class="bx bx-edit"></i>
                                Relancer le crawl
                            </span>                    
                ';
            }

            //option d'arrêter crawl
            if(in_array($statut_key, [1])) {
                $link_relance_crawl = '                            
                            <span class="stop-crawl d-flex gp-4 font-color-gris font-weight-500 cursor-pointer btn-action-crawling"  data-id="'. $id_dspi .'" data-domaine="'. $domaine .'"  data-modal="show" data-target="modal_stop_crawl">
                                <i class="bx bx-edit"></i>
                                Arrêter le crawl
                            </span>                    
                ';
            }

            //option de rectifier fiche_produit
            $link_rectif_fiche_produit = "";
            if (!in_array($statut_key, [1, 9, 12, 14])) {
                $link_rectif_fiche_produit = "<span class='d-flex gp-4 font-color-gris font-weight-500 cursor-pointer btn-show-modal-qualification' 
                    data-id_domaine='{$id_dspi}' 
                    data-domaine='{$domaine}'
                    data-statut='{$statut_key}'
                    data-modal='show' 
                    data-target='modal_qualification_urls'>
                    <i class='bx bx-list-check'></i>
                    Qualification des URLs
                </span>";
            }

            //option d'affichage confi crawl
            $link_config_crawl = '                            
                        <span class="stop-crawl d-flex gp-4 font-color-gris font-weight-500 cursor-pointer btn-action-config-crawling"  data-id="'. $id_dspi .'" data-domaine="'. $domaine .'"  data-modal="show" data-target="modal_config_crawl">
                            <i class="bx bx-edit"></i>
                            Configuration du crawl
                        </span>                    
            ';

            
            $nb_item = 0;
            if(!empty($btn_link_show)) {
                $nb_item += 2;
            }
            if(!empty($link_fiche_societe)) {
                $nb_item++;
            }
            if(!empty($link_relance_crawl)) {
                $nb_item++;
            }
            if(empty($btn_link_show)) {
                $nb_item++;
            }
            if(empty($link_rectif_fiche_produit)) {
                $nb_item++;
            }
            $class_action_crawling = $nb_item > 0 ? "nb_item_".$nb_item : "";

            $action_container = "";
            if(!empty($btn_link_show) || !empty($link_fiche_societe) || !empty($link_relance_crawl) || !empty($link_rectif_fiche_produit)) 
            {
                $action_container = '
                            <div class="d-flex flex-d-column gp-8">
                                '. $btn_link_show .'
                                '. $link_historique .'
                                '. $link_fiche_societe .'
                                '. $link_relance_crawl .'
                                '. $link_rectif_fiche_produit .'
                                '. $link_domaine_sans_fp .'
                                '. $link_config_crawl .'
                            </div>
                       
                ';
            }

            $style_chx = $statut_key == 6 ? "" : "style='visibility: hidden;'";

            $tbody_content[]  = <<<HTML_CONTENT
                    <tr data-id="{$id_dspi}">
                        <td class="table-default-vue">
                            <input class="check-box-domaine" type="checkbox" {$style_chx}>
                        </td>
                        <td data-champs="id_domaine_scrapping_produit_ia"><div class=""> {$id_dspi}</div></td>
                        <td data-champs="id_upload_dspi"><div class=""><a class="link-idp font-color-gris cursor-pointer" href="https://{$_SERVER['HTTP_HOST']}/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/tableau_bord.php?id_upload={$id_upload}" target="_blank">{$id_upload}</a></div></td>
                        <td data-champs="domaine_dspi"><div class=""> {$domaine} {$old_url}</div></td>
                        <td data-champs="date_creation_dspi"><div class=""> {$date_creation}</div></td>
                        <td data-champs="cms_dspi"><div class=""> {$info_cms['cms_name']}</div></td>
                        <td data-champs="statut_dspi"><div class="d-flex justify-content-center"> {$statut_span}</div><div>{$progress_bar}</div></td>
                        <td data-champs="utilisateur_dspi"><div class=""> {$utilisateur}</div></td>
                        <td data-champs="statut_crawler_eci"><div class=""> {$enqueue}</div></td>
                        <td class="table-default-vue"><div class="d-flex ">{$action_container}</div>
                        </td>
                    </tr>
            HTML_CONTENT;
        }

        $tbody_content = implode("", $tbody_content);
    
        echo json_encode([
            "tbody_content"    => $tbody_content,
            "nb_total_domaine" => $nb_total_domaine, // Correct total count
            "sql_main"         => $sql_main,        // Debugging information
        ], JSON_INVALID_UTF8_IGNORE);
        break;
    

    case "modifier_selecteur":

        $id_scrapping  = $_POST['id_scrapping'];
        $id_domaine    = $_POST['id_domaine'];
        $id_info       = $_POST['info'];
        $selecteurs    = json_decode($_POST['sel'],true);
        $url_top_fiche = json_decode($_POST['url_top_fiche'], true);

        $action_historique = [
            "titre"         => 11,
            "description"   => 13,
            "prix"          => 15,
            "image"         => 17,
            "categorie"     => 19,
            "livraison"     => 21,
            "stock"         => 23
        ];

        $tab_traiter_sel = []; 

        if(in_array($id_info,['titre','description','stock','image'])) {
            foreach($selecteurs as $tab_sel) {
                $tab_traiter_sel[] = $tab_sel['selecteur'];
            }
        } else {
            foreach($selecteurs as $tab_sel) {
                $tab_traiter_sel[] = $tab_sel;
            }
        }

        $tab_selecteurs = $tab_traiter_sel;
        $list_top_fiche = [];
        $sql_top = "SELECT
                        tops_fiches_dspi
                    FROM domaine_scrapping_produit_ia DSPI
                    WHERE id_domaine_scrapping_produit_ia = '".hellopro_traitement_donnee_annuaire_bo($id_domaine)."' ";
        $res_top = mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_top) or die(hellopro_mysql_error($sql_top, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));   
        while($lig_top = mysqli_fetch_assoc($res_top)) {
            $tops_fiches_dspi = json_decode($lig_top['tops_fiches_dspi'] , true);
            if(isset($tops_fiches_dspi[$id_info])) {
                $list_top_fiche = $tops_fiches_dspi[$id_info];
            }   
        }

        $list_top_fiche[] = $id_scrapping;
        $list_top_fiche = array_unique(array_filter($list_top_fiche));
        
        foreach($list_top_fiche as  $id_scrapping) {   
            $sql_info = "
                SELECT
                    url_sfpi,
                    contenu_scrapping_sfpi
                FROM scrapping_fiche_produit_ia SFPI
                WHERE id_scrapping_fiche_produit_ia = '".hellopro_traitement_donnee_annuaire_bo($id_scrapping)."'
            ";

            $res_info = mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_info) or die(hellopro_mysql_error($sql_info, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));
            $lig_info = mysqli_fetch_assoc($res_info);
            $url      = $lig_info['url_sfpi'];
            $contenu  = $lig_info['contenu_scrapping_sfpi'];

            $domXPath = creerDOMEtXPath(traitement_contenu_web($contenu));
            $dom      = $domXPath['dom'];
            $xpath    = $domXPath['xpath'];

            $dataToSynthese = [
                'id'        => $id_scrapping,
                'url'       => $url,
                'contenu'   => $contenu,
                'dom'       => $dom,
                'xpath'     => $xpath,
                'selecteur' => $tab_selecteurs
            ];

            $dataSelecteurToProcess[$id_domaine][$id_info][] = $dataToSynthese;
        }
        // echo "<pre>".print_r($dataSelecteurToProcess,true)."</pre>";
        // die();
        $ComparateurSelecteur = new ComparateurSelecteur();
        $res_synthese = $ComparateurSelecteur->lancer_synthetisation_selecteur($dataSelecteurToProcess,true,false,true);
        
        $sql_update_tag ="UPDATE
                            historique_reajustement_selecteur_ia
                        SET
                            tag_restaurer_hrsi = 0
                        WHERE
                            id_domaine_hrsi = '".hellopro_traitement_donnee_annuaire_bo($id_domaine)."'
                        AND tag_restaurer_hrsi = 1
                        LIMIT 1";
         $res_update_tag = mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_update_tag) or die(hellopro_mysql_error($sql_update_tag, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));

         historique_action_utilisateur($_SESSION['user_bo'], $id_domaine, "", $action_historique[$id_info]);
         maj_utilisateur_dspi($id_domaine,$_SESSION['user_bo']);
        
        echo "<pre>".print_r($res_synthese, true)."</pre>";
        echo "<pre>MODIFICATION CONTENU RECUPERER:.$id_info.</pre>";
        if ($id_info != "image") {
            include_once($_SERVER["DOCUMENT_ROOT"] . "admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/ajax/ajax_recuperer_contenu_top_fiche.php");
        } else {
            $trace_shell_exec = date("Y-m-d-H-i-s") . "-trace-shell-exec.txt";
            $repertoire = "script/fichiers/chatgpt/scrapping_produit/".date("Y")."/";
            if (!is_dir($_SERVER['DOCUMENT_ROOT'] . $repertoire)) {
                if (!mkdir($_SERVER['DOCUMENT_ROOT'] . $repertoire, 0777, true)) {
                    return false;
                }
            }

            $handle_trace = fopen($_SERVER["DOCUMENT_ROOT"] . $repertoire . $trace_shell_exec, "a+");
            $lien_script = "script_scrapping_produit_ia_traitement_image.php";
    
            fwrite($handle_trace, "-----------------------------------------------\n");
            fwrite($handle_trace, "Appel du traitement de récuperation contenu selecteur image \n");

            $server_name = $GLOBALS['protocol_http_host_bo'] . "script.hellopro.fr"; // PROD
            // $server_name = $GLOBALS['protocol_http_host_bo'] . "dev-script.hellopro.fr"; // DEV
            $test_temp   = $_SERVER['DOCUMENT_ROOT'] . 'tmp/script_scrapping_produit_ia_recup_img' . date('Ymdhis') . '.log';
            $command = sprintf(
                "cd %s; wget -q -b -t 1 %s -a %s",
                escapeshellarg($_SERVER['DOCUMENT_ROOT'] . 'tmp/'),
                escapeshellarg($server_name . "/script/chatgpt/" . $lien_script . "?id_domaine={$id_domaine}&id_info={$id_info}&" . http_build_query(['url_top_fiche' => $url_top_fiche])),
                escapeshellarg($test_temp)
            );
            $a = shell_exec($command);
    
            fwrite($handle_trace, "-----------------------------------------------\n");
            fwrite($handle_trace, "Retour shell exec : {$command} \n {$a} \n\n");
            fclose($handle_trace);
        }
    
        echo json_encode(['success' => true, 'synthese' => $res_synthese]);
        break;

    // Nouveau case pour charger le contenu des onglets
    case "load_tab_content":
        $id_domaine = intval($_POST['id_domaine']);
        $tab = $_POST['tab'];

         // Récupérer le nombre de fiches produits
         $fiches = urls_fiches_produits($id_domaine);
         $fichesCount = count($fiches);
         
         // Récupérer le nombre total d'URLs
         $allUrls = get_crawled_urls($id_domaine);
         $autresCount = count(array_diff(
             $allUrls, 
             array_map(function($item) {
                 return trim(trim($item['url']), '/');
             }, $fiches)
         ));

        // Préparer le contenu selon l'onglet
        $content = '';
        if ($tab == 'fiches-produits') {
            $urls = urls_fiches_produits($id_domaine);
            $count = count($urls);

            foreach ($urls as $url_data) {
                $content .= sprintf('
                    <tr>
                        <td><input type="checkbox" class="form-check-input check-fiche" data-id="%d" value="%s"></td>
                        <td style="word-break: break-all;"><a class="url-link font-color-noir" href="%s" target="_blank">%s</a></td>
                    </tr>',
                    $url_data['id'],
                    htmlspecialchars($url_data['url']),
                    htmlspecialchars($url_data['url']),
                    htmlspecialchars($url_data['url'])
                    
                );
            }
        } else {
            // Pour l'onglet "autres-urls", exclure les URLs fiches produits
            $all_urls = get_crawled_urls($id_domaine);

            // Extraire uniquement les URLs du tableau de fiches produits
            $fiche_urls = array_map(function($item) {
            return trim(trim($item['url']), '/');
            }, urls_fiches_produits($id_domaine));

            // Maintenant array_diff fonctionnera correctement
            $autres_urls = array_diff($all_urls, $fiche_urls);
            $count = count($autres_urls);

            foreach ($autres_urls as $url) {
                $content .= sprintf('
                    <tr>
                        <td><input type="checkbox" class="form-check-input check-autre" value="%s"></td>
                        <td style="word-break: break-all;"><a class="url-link font-color-noir" href="%s" target="_blank">%s</a></small></td>
                    </tr>',
                    htmlspecialchars($url),
                    htmlspecialchars($url),
                    htmlspecialchars($url)
                );
            }
        }

        $content = $content ?: '<tr><td colspan="4" class="text-center">Aucune URL trouvée</td></tr>';

        echo json_encode([
            'success' => true,
            'content' => $content,
            'fichesCount' => $fichesCount,
            'autresCount' => $autresCount
        ]);
        break;

    // Nouveau cas pour traiter la qualification        
    case "process_qualification":
        $response = ['success' => false, 'message' => ''];
        $jsonData = json_decode(file_get_contents('php://input'), true);

        $action_historique = [
            'qualify_urls' => 4,
            'disqualify_urls' => 5
        ];
        
        if (empty($jsonData['id_domaine'])) {
            $response['message'] = 'ID domaine manquant';
            echo json_encode($response);
            break;
        }
        
        $id_domaine = intval($jsonData['id_domaine']);
        $qualification_action = $jsonData['qualification_action'] ?? '';
        
        try {
            $batchProcessor = new BatchProcessor($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], BATCH_SIZE);
            
            switch ($qualification_action) {
                case 'qualify_urls':
                    if (empty($jsonData['urls'])) {
                        throw new Exception('URLs manquantes');
                    }
                    
                    $urlsContent = getJsonContentFromCache($id_domaine)['urls_content'] ?? [];
                    if (empty($urlsContent)) {
                        throw new Exception('Erreur lors de la récupération des données du cache');
                    }
                    
                    $result = $batchProcessor->qualifyUrls($id_domaine, $jsonData['urls'], $urlsContent, null);
                    $actionMessage = 'qualifiées';
                    break;

                case 'disqualify_urls':
                    if (empty($jsonData['ids'])) {
                        throw new Exception('IDs manquants');
                    }
                    
                    $result = $batchProcessor->disqualifyUrls($id_domaine, array_map('intval', $jsonData['ids']), null);
                    $actionMessage = 'disqualifiées';
                    break;

                default:
                    throw new Exception('Action de qualification invalide');
            }

            historique_action_utilisateur($_SESSION['user_bo'], $id_domaine, "", $action_historique[$qualification_action]);
            maj_utilisateur_dspi($id_domaine,$_SESSION['user_bo']);
            
            $response['success'] = $result['success'];
            $response['message'] = $result['success'] 
                ? sprintf("Traitement réussi: %d URLs %s", $result['processed'], $actionMessage)
                : implode(', ', $result['errors']);
                
        } catch (Exception $e) {
            $response['message'] = $e->getMessage();
            error_log("Error in process_qualification: " . $e->getMessage());
        }
        
        echo json_encode($response);
        break;

    case "launch_tops_script" :
        $id_domaine = intval($_POST['id_domaine']);
        
        if (empty($id_domaine)){
            echo json_encode([
                'success' => false,
                'message' => 'Domaine manquant'
            ]);
            break;
        }
        $p[] = 'id_domaine=' . $id_domaine;

        //6 = [Qualification Urls] - Relance récupération top fiches
        historique_action_utilisateur($_SESSION['user_bo'], $id_domaine, "", 6);
        maj_utilisateur_dspi($id_domaine, $_SESSION['user_bo']);

        $file_name = "qualification_relance_top_fiche_";
        $lien_script = "/script/chatgpt/script_qualification_relance_top_fiche.php?" . implode('&', $p);
        $test_temp = $_SERVER['DOCUMENT_ROOT'] . 'tmp/ajax_scrapping_v2_' . $file_name . date('Ymdhis') . '.log';

        $server_name = $GLOBALS['protocol_http_host_bo'] . "script.hellopro.fr"; // PROD
        //$server_name = $GLOBALS['protocol_http_host_bo'] . "dev-script.hellopro.fr"; // DEV

        // (avec -b pour background)
        $command_sel = "cd " . $_SERVER['DOCUMENT_ROOT'] . "tmp/; wget -q -b -t 1 '" . $server_name . $lien_script . "' -a '" . $test_temp . "'";
        shell_exec($command_sel);

        echo json_encode([
            'success' => true,
            'message' => 'Script lancé avec succès'
        ]);

        break;
    case "search_selector" :
        $id_domaine     = intval($_POST['id_domaine']);
        $tab            = $_POST['tabId'];
        $searchValue    = $_POST['searchValue'] ?? '';
        $searchType     = $_POST['searchType'] ?? 'contains';
        $isContains     = $searchType === 'contains';
        $typeUse     = $_POST['typeUse'] === 'selector' ? 'selector' : 'contenu';
        
        if (empty($id_domaine) || empty($searchValue)) {
            echo json_encode([
                'success' => false,
                'message' => 'Domaine ou searchValue manquant'
            ]);
            break;
        }
        
        $final_urls = [];
        $count = "";
        if ($tab == 'fiches-produits') {
            $urls = urls_fiches_produits($id_domaine , true);           
            $count .= " - " .  count($urls);
            foreach ($urls as $url_data) {

                // Vérifier si le sélecteur est présent dans le contenu
                if($typeUse == 'selector') {                    
                    if(has_contenu_selecteur( [$searchValue]  ,  $url_data['content']) === $isContains)
                    {
                        $final_urls[] = $url_data['url'];
                    }
                } 
                // Vérifier si le contenu contient la valeur recherchée
                else {  
                                   
                    if ( (stripos($url_data['content'], $searchValue) !== false)  === $isContains ) {
                        $final_urls[] = $url_data['url'];
                    }
                    elseif (is_valid_regex($searchValue)) {
                            $pattern =  $searchValue;            
                            $resPattern = preg_match($pattern, $url_data['content']) ? true : false;
                            if( $resPattern === $isContains) {
                                $final_urls[] = $url_data['url'];
                            }
                    }
                }
                
            }
        } else {
             // Extraire uniquement les URLs du tableau de fiches produits
            $fiche_urls = array_map(function($item) {
            return trim(trim($item['url']), '/');
            }, urls_fiches_produits($id_domaine));

            // Pour l'onglet "autres-urls", exclure les URLs fiches produits
            $all_urls = get_crawled_urls($id_domaine , true);

            $count .= " - " .  count($fiche_urls);
            $count .= " - " .  count($all_urls);

            foreach($all_urls as $key =>  $url_data) {
                if(in_array($key , $fiche_urls)) 
                {
                   unset($all_urls[$key]);
                }
                // Vérifier si le sélecteur est présent dans le contenu
                elseif($typeUse == 'selector') {                 
                    if(has_contenu_selecteur( [$searchValue]  ,  $url_data['content']  )  === $isContains )
                    {
                        $final_urls[] = $url_data['url'];
                    }   
                }
                // Vérifier si le contenu contient la valeur recherchée
                else
                {
                    if ( (stripos($url_data['content'], $searchValue) !== false)  === $isContains ) {
                        $final_urls[] = $url_data['url'];
                    }
                    elseif (is_valid_regex($searchValue)) {
                            $pattern =  $searchValue; 
                            $resPattern = preg_match($pattern, $url_data['content']) ? true : false;
                            if( $resPattern === $isContains) {
                                $final_urls[] = $url_data['url'];
                            }
                    }
                }          
            }
            $count .= " - " .  count($all_urls);
            
        }


        echo json_encode([
            'success' => true,
            'urls' => $final_urls,
            'total' => $count
        ]);
        break;
    // Sauvegarder les paramètres de qualification (historique)
    case 'save_qualif_params':
        $id_domaine = intval($_POST['id_domaine']);
        $allParams = isset($_POST['allParams']) ? $_POST['allParams'] : null;
        $forcedModeQualif = intval($_POST['modeQualif']);
        if (!$id_domaine || !$allParams) {
            echo json_encode(['success' => false, 'message' => 'Paramètres manquants']);
            break;
        }
        // Correction : décoder $allParams si c'est une chaîne JSON
        if (is_string($allParams)) {
            $allParams = json_decode($allParams, true);
        }
        if (!is_array($allParams)) {
            echo json_encode(['success' => false, 'message' => 'Paramètres invalides']);
            break;
        }

        $isMulti = count($allParams) > 1;
        foreach ($allParams as $oneParams) {
          
            $allId = [];
            $hasRelation = count($oneParams) == 1 ? false : true;

            $dataParams = [];
            foreach ($oneParams as $params) {

                //Par défaut ul
                $typeFiltre = 1;
                if ($params['regex']) {
                    $typeFiltre = 2;
                } elseif ($params['selector']) {
                    $typeFiltre = 3;
                } elseif ($params['content']) {
                    $typeFiltre = 4;
                }

                // si venant de fiches-produits cela veut dire  exclus (2)
                // sinon  inclus (1)
                // $inclus = $params['tabId'] == 'fiches-produits' ? '2' : '1';
                $modeQualif = $params['modeQualif'] == '2' ? '2' : '1';
                if (!empty($forcedModeQualif)) {
                    $modeQualif = $forcedModeQualif;
                }

                $data = [
                    'searchType' => $params['searchType'] == 'not-contains' ? '2' : '1',
                    'searchValue' => $params['searchValue'],
                    'typeFiltre' => $typeFiltre,
                    'modeQualif' => $modeQualif,
                    'origine' => 1 //qualification urls            
                ];

                $dataParams[] = $data;
            }

            if ($hasRelation && verif_doublon_relation_filtre($id_domaine, $dataParams)) {
                if(!$isMulti) {
                    echo json_encode(['success' => false, 'doublon' => true]);                
                    break 2; // Sortie de la boucle principale si doublon trouvé
                } else {
                    // Si c'est un multi, on continue à ajouter les autres paramètres
                    continue;
                }
                
            }

            foreach ($dataParams as $data) {
                $id_filtre_qualif =  add_filtre_qualification($id_domaine, $data, $hasRelation);
                $allId[] = $id_filtre_qualif;
            }

            if (!$hasRelation && $id_filtre_qualif == 0) {   
                if(!$isMulti) {  
                    echo json_encode(['success' => false, 'doublon' => true]);
                    break 2;
                } else {
                    // Si c'est un multi, on continue à ajouter les autres paramètres
                    continue;
                }
            }

            if ($hasRelation) {
                add_filtre_qualif_relation($id_domaine, $allId);
            }
  
        }


        historique_action_utilisateur($_SESSION['user_bo'], $id_domaine, "", 35);
        echo json_encode(['success' => true, 'history' => $data, 'doublon' => false]);
        break;

    // Récupérer l'historique des paramètres de qualification
    case 'get_qualif_params':
        $id_domaine = intval($_POST['id_domaine']);
        $sql = "SELECT
                id_filtre_qualification_domaine_ia,
                search_type_fqdi,
                search_value_fqdi,
                type_filtre_fqdi,
                mode_qualification_fqdi,
                date_fqdi,
                origine_fqdi
            FROM filtre_qualification_domaine_ia FQDI
            WHERE id_domaine_fqdi = '" . hellopro_traitement_donnee_annuaire_bo($id_domaine) . "'";
        $res = mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql) or die(hellopro_mysql_error($sql_count, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));

        $history = [];

        $searchType = [
            '1' => 'contains',
            '2' => 'not-contains'
        ];

        $typeFiltre = [
            '1' => 'url',
            '2' => 'regex',
            '3' => 'selector',
            '4' => 'content',
            '5' => 'sitemap',
            '6' => 'chatgpt'
        ];

        $modeQualif = [
            '1' => 'fiches-produits',
            '2' => 'autres-urls'
        ];

        $origine = [
            '1' => 'qualification urls',
            '2' => 'détection automatique',
            '3' => 'détection manuel'
        ];


        while ($row = mysqli_fetch_assoc($res)) {
            $infoModeQualif = $row['mode_qualification_fqdi'] == "2" ? "2" : "1"; // Si mode qualification est 2, alors c'est pour les fiches produits, sinon c'est pour les autres URLs
            $history[$row['id_filtre_qualification_domaine_ia']] = [
                'id' => $row['id_filtre_qualification_domaine_ia'],
                'searchType' => $searchType[$row['search_type_fqdi']] ?? 'contains',
                'searchValue' => $row['search_value_fqdi'],
                'regex' =>  $row['type_filtre_fqdi'] == 2,
                'selector' => $row['type_filtre_fqdi'] == 3,
                'content' => $row['type_filtre_fqdi'] == 4,
                'sitemap' => $row['type_filtre_fqdi'] == 5,
                'chatgpt' => $row['type_filtre_fqdi'] == 6,
                'modeQualif' => $infoModeQualif,
                'date' => date("d/m/Y H:i", strtotime($row['date_fqdi'])),
                'origine' => $origine[$row['origine_fqdi']] ?? 'qualification urls'
            ];
        }


        //recuperation des relations de filtres
        $sql_relations = "SELECT
            id_relation_filtre_domaine_ia,
            relation_filtre_rfdi
        FROM
            relation_filtre_domaine_ia RFDI
        WHERE
            id_domaine_rfdi = '" . hellopro_traitement_donnee_annuaire_bo($id_domaine) . "'";
        $res_relations = mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_relations) or die(hellopro_mysql_error($sql_relations, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));
        $relations = [];
        while ($lg_relation = mysqli_fetch_assoc($res_relations)) {
            $id_relation = $lg_relation['id_relation_filtre_domaine_ia'];
            $relations[$id_relation] = explode(',', $lg_relation['relation_filtre_rfdi']);
        }

        $finalHistory = [];
        $traited = [];
        foreach ($history as $id => $info) {
            $temp_history = [];
            if (in_array($id, $traited)) {
                continue; // Si déjà traité, on passe
            }

            $traited[] = $id;


            $has_relation = false;
            foreach ($relations as $relatedId => $relatedIdsFiltre) {
                if (in_array($id, $relatedIdsFiltre)) {
                    $info["idRelation"] = $relatedId;
                    $has_relation = true;
                    $temp_history[] = $info;

                    foreach ($relatedIdsFiltre as $relatedIdFiltre) {
                        if ($relatedIdFiltre != $id && isset($history[$relatedIdFiltre])) {
                            $history[$relatedIdFiltre]["idRelation"] = $relatedId;
                            $temp_history[] = $history[$relatedIdFiltre];
                            $traited[] = $relatedIdFiltre; // Marquer comme traité
                        }
                    }
                }
            }


            if (!$has_relation) {
                $temp_history[] = $info; // Si pas de relation, on ajoute l'info seule
            }

            $finalHistory[] = $temp_history;
        }

        echo json_encode(['success' => true, 'history' => $finalHistory]);
        break;

    case 'delete_qualif_params':
        $id_domaine = intval($_POST['id_domaine']);
        $id_filtre = intval($_POST['id_filtre']);
        if (!$id_domaine || !$id_filtre) {
            echo json_encode(['success' => false, 'message' => 'ID domaine ou filtre manquant']);
            break;
        }
        $sql = "DELETE FROM filtre_qualification_domaine_ia 
            WHERE 
            id_filtre_qualification_domaine_ia = '" . hellopro_traitement_donnee_annuaire_bo($id_filtre) . "' 
            AND id_domaine_fqdi = '" . hellopro_traitement_donnee_annuaire_bo($id_domaine) . "'";
        $res = mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql) or die(hellopro_mysql_error($sql, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));
        if ($res) {
            // Supprimer la relation si elle existe
            $sql_relations = "SELECT
                    id_relation_filtre_domaine_ia,
                    relation_filtre_rfdi
                FROM
                    relation_filtre_domaine_ia RFDI
                WHERE
                    id_domaine_rfdi = '" . hellopro_traitement_donnee_annuaire_bo($id_domaine) . "'
                    AND relation_filtre_rfdi LIKE '%" . hellopro_traitement_donnee_annuaire_bo($id_filtre) . "%'
                    ";
            $res_relations = mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_relations) or die(hellopro_mysql_error($sql_count, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));
            while ($lg_relation = mysqli_fetch_assoc($res_relations)) {
                $id_relation = $lg_relation['id_relation_filtre_domaine_ia'];
                $relation_filtre_rfdi = explode(',', $lg_relation['relation_filtre_rfdi']);
                $relation_filtre_rfdi = array_filter(array_map('trim', $relation_filtre_rfdi)); // Nettoyer les espaces

                $key = array_search($id_filtre, $relation_filtre_rfdi);
                if ($key !== false) {
                    unset($relation_filtre_rfdi[$key]);

                    if (count($relation_filtre_rfdi) <= 1) {
                        // Si la relation est vide, on supprime la ligne
                        $sql_delete = "DELETE FROM relation_filtre_domaine_ia 
                            WHERE id_relation_filtre_domaine_ia = '" . hellopro_traitement_donnee_annuaire_bo($id_relation) . "'";
                        $res_delete = mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_delete) or die(hellopro_mysql_error($sql_delete, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));
                    } else {
                        $relation_filtre_rfdi = implode(',', $relation_filtre_rfdi);

                        // Sinon, on met à jour la relation
                        $sql_update = "UPDATE relation_filtre_domaine_ia
                            SET relation_filtre_rfdi = '" . hellopro_traitement_donnee_annuaire_bo($relation_filtre_rfdi) . "'
                            WHERE id_relation_filtre_domaine_ia = '" . hellopro_traitement_donnee_annuaire_bo($id_relation) . "'";
                        $res_update = mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_update) or die(hellopro_mysql_error($sql_update, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));
                    }
                }
            }


            echo json_encode(['success' => true, 'message' => 'Paramètre de qualification supprimé avec succès']);
        } else {
            echo json_encode(['success' => false, 'message' => 'Erreur lors de la suppression du paramètre de qualification']);
        }
        break;
}