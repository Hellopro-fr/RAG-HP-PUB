<?php
ini_set('memory_limit','2048M'); 
ini_set('max_execution_time','161800'); 

/**
 * @author Fetra Fitahiana
 * @date   09/01/2025
 * @todo   Identifier les urls de fiches produit parmi les urls crawler d'un domaine défini
 */

// Définition de l'encodage par défaut
header('Content-Type: text/html; charset=UTF-8');

require_once($_SERVER['DOCUMENT_ROOT'] . '/include/connexion.php');
require_once($_SERVER['DOCUMENT_ROOT'] . "no_read_access/connexion_bdd_hellopro_ia.php");
require_once($_SERVER['DOCUMENT_ROOT'] . '/fonctions/fonctions_hellopro.php');
require_once($_SERVER['DOCUMENT_ROOT'] . '/fonctions/fonctions_generales.php');
require_once($_SERVER['DOCUMENT_ROOT'] . 'admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/fonctions/fonctions_scrapping.php');

function classifyUrls($otherUrlsContent, $cms_name, $results) 
{
    $classifiedUrls = [];
    switch($cms_name){
        case 'prestashop':
        case 'magento'   :
        case 'drupal'    :  
        case "wix website builder":  
        case "wordpress" : 
        case "shopify" : 
        
            // Classifier les URLs dans otherUrls.json
            foreach ($otherUrlsContent as $entry) {
                $url = $entry['url'] ?? '';
                $content = $entry['content'] ?? '';
                $uniqueCriteria = $results[0];
                // Vérifier si l'URL satisfait le critère unique
                if (checkUniqueCriteria($url, $content, $uniqueCriteria, $cms_name)) {
                    $classifiedUrls[] = ["url" => $url, "content" => $content];
                }
                
            }
        
                break;
        
        default :
            break;
    }

    return $classifiedUrls;
}

function insertDataResult($resultats, $id_domaine) {
    $insert_success_count = 0; // Initialiser un compteur pour les succès d'insertion

    foreach ($resultats as $ficheProduit) {
        $url = $ficheProduit["url"];
        $url = trim(trim($url), '/');
        $content = $ficheProduit["content"];

        $sql_select_sfpi =
            "SELECT
                id_scrapping_fiche_produit_ia,
                url_sfpi
            FROM 
                scrapping_fiche_produit_ia SFPI
            WHERE
                SFPI.url_sfpi = '" . hellopro_traitement_donnee_annuaire_bo($url) . "'
                AND est_dernier_sfpi = 1";

        $res_select_sfpi = mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_select_sfpi) 
            or die(hellopro_mysql_error($sql_select_sfpi, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));

        while ($ligne_sfpi = $res_select_sfpi->fetch_assoc()) {
            $sql_update_sfpi =
            "UPDATE 
                scrapping_fiche_produit_ia
            SET 
                est_dernier_sfpi = 0
            WHERE 
                id_scrapping_fiche_produit_ia = '{$ligne_sfpi['id_scrapping_fiche_produit_ia']}'
            LIMIT 1";

            mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_update_sfpi) 
                or die(hellopro_mysql_error($sql_update_sfpi, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));
        }
        
        $sql_insert_sfpi =
            "INSERT INTO 
                scrapping_fiche_produit_ia
            SET
                id_domaine_scrapping_produit_sfpi = '" . hellopro_traitement_donnee_annuaire_bo($id_domaine) . "',
                url_sfpi = '" . hellopro_traitement_donnee_annuaire_bo($url) . "',
                contenu_scrapping_sfpi = '" . hellopro_traitement_donnee_annuaire_bo($content) . "'";

        if (mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_insert_sfpi)) {
            $insert_success_count++; // Incrémenter si l'insertion est réussie
        } else {
            die(hellopro_mysql_error($sql_insert_sfpi, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));
        }
    }

    return $insert_success_count; // Retourner le nombre d'inserts réussis
}

function get_stats_crawling($id_domaine)
{
    $sql_nb_crawling = "SELECT
                    DSPI.urls_crawling_dspi,
                    DSPI.urls_erreur_crawling_dspi
                FROM 
                    domaine_scrapping_produit_ia DSPI
                WHERE DSPI.id_domaine_scrapping_produit_ia = '".hellopro_traitement_donnee_annuaire_bo($id_domaine)."'
                LIMIT 1";

    $res_cms_name = mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_nb_crawling) or die(hellopro_mysql_error($sql_nb_crawling, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));
    $lig_cms_name = mysqli_fetch_assoc($res_cms_name);
    $nb_crawling_old        = !empty($lig_cms_name['urls_crawling_dspi']) ? $lig_cms_name['urls_crawling_dspi'] : 0;
    $nb_erreur_crawling_old = !empty($lig_cms_name['urls_erreur_crawling_dspi']) ? $lig_cms_name['urls_erreur_crawling_dspi'] : 0;
    return [ "nb_crawling_old" => $nb_crawling_old, "nb_erreur_crawling_old" => $nb_erreur_crawling_old];
}

function get_allUrlCrawled($id_domaine)
{
    $sql_chemin_crawling = "SELECT
                    DSPI.chemin_crawling_dspi
                FROM 
                    domaine_scrapping_produit_ia DSPI
                WHERE DSPI.id_domaine_scrapping_produit_ia = '".hellopro_traitement_donnee_annuaire_bo($id_domaine)."'
                LIMIT 1";

    $res_chemin = mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_chemin_crawling) or die(hellopro_mysql_error($sql_chemin_crawling, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));
    $lig = mysqli_fetch_assoc($res_chemin);  
    return $lig['chemin_crawling_dspi'];
}


function isValidFP($content, $key) {
    return isset($content[$key]) && is_array($content[$key]) && !empty($content[$key]);
}

function detecter_fiche_produit_site($otherUrlsContent,$seuil_fiche_produit = 75) {
    global $handle_trace;
    global $id_domaine;
    global $method;

    $classifiedUrls = [];
    
    $nb_total_url = count($otherUrlsContent);
    $nb_url_fiche_produit = 0;

    $tab_url_no_identifier = [];

    $filter_qualif_other = [];

    foreach($otherUrlsContent as $entry) {
        $url = $entry['url'] ?? '';
        $content = $entry['content'] ?? '';

        $verifFP = est_fiche_produit_cas_non_gerer($url , $content);
        if($verifFP['statut']) {
            $classifiedUrls[] = ["url" => $url, "content" => $content];
            $nb_url_fiche_produit++;

            if(!in_array($verifFP['criteria'], $filter_qualif_other)) {
                $filter_qualif_other[] = $verifFP['criteria'];
            }
        } else {
            $tab_url_no_identifier[] = ["url" => $url , "content" => $content];
        }
    }

    fwrite($handle_trace, "filter_qualif_other :" . print_r($filter_qualif_other, true) . "\n");    
    foreach ($filter_qualif_other as $qualifManuel) {

        if($qualifManuel == "MTD")
        {
            $data = [
                        'searchType' => '1' , //contains
                        'searchValue' => 'meta[property="og:type"][content="product"]',
                        'typeFiltre' => 3, //selector
                        'modeQualif' => 1, //inclus         
                        'origine' => $method == "auto" ? '2' :'3', //detect manuel  ou auto    
            ];
            $id_filtre_qualif =  add_filtre_qualification($id_domaine , $data) ;
        }
        elseif($qualifManuel == "MCD")
        {
            $data = [
                        'searchType' => '1' , //contains
                        'searchValue' => '/"@type"\s*:\s*"Product"/',
                        'typeFiltre' => 4, //content
                        'modeQualif' => 1, //inclus        
                        'origine' => $method == "auto" ? '2' :'3', //detect manuel  ou auto
            ];
            $id_filtre_qualif =  add_filtre_qualification($id_domaine , $data) ;
        }

    }

    
    $tab_liste_fp_url = liste_fp_url($tab_url_no_identifier);
    $tab_fp_mehod_url = $tab_liste_fp_url['urls_final'] ?? [];    
    fwrite($handle_trace, "Nb fp identifié via URL\n");
    fwrite($handle_trace, count($tab_fp_mehod_url)."\n");
    

    $patterns_trouve = $tab_liste_fp_url['patterns_trouve'] ?? [];
    foreach ($patterns_trouve as $pattern) {
        $data = [
                    'searchType' => '1' , //contains
                    'searchValue' => '/\/' . $pattern .'\/.+/i',
                    'typeFiltre' => 2, //regex
                    'modeQualif' => 1, //inclus     
                    'origine' => $method == "auto" ? '2' :'3', //detect manuel  ou auto
        ];
        $id_filtre_qualif =  add_filtre_qualification($id_domaine , $data) ;

    }


    $classifiedUrls = array_merge($classifiedUrls,$tab_fp_mehod_url);


    fwrite($handle_trace, "Nb complet des FP identifiées\n");
    fwrite($handle_trace, count($classifiedUrls)."\n");

    $pourcentage_fp_detecter = ceil($nb_url_fiche_produit / $nb_total_url * 100);

    /**
     * Si on a moins de 75% de fiche produit parmi les urls crawlés
     * on ne prend pas en compte les fiches produits détectées pour éviter d'avoir beaucoup d'autres templates(catégorie,etc..)
     */
    // if($pourcentage_fp_detecter < $seuil_fiche_produit) {
    //     $classifiedUrls = [];
    // }

    fwrite($handle_trace, "Cas non géré\n");
    fwrite($handle_trace, "Total url crawlé : $nb_total_url \n");
    fwrite($handle_trace, "Total fiche produit identifiée : $nb_url_fiche_produit \n");
    fwrite($handle_trace, "Pourcentage fiche produit identifiée : $pourcentage_fp_detecter% \n");

    return $classifiedUrls;
}

function getRandomElements(array $array, int $maxCount): array {
    $shuffled = $array;
    shuffle($shuffled);
    return array_slice($shuffled, 0, min($maxCount, count($array)));
}

function getUniqueURLElements(array $urls): array {
    $uniqueParams = [];
    $uniqueHashes = [];
    $MAX_EXAMPLES = 4;

    foreach ($urls as $url) {
        try {
            $urlComponents = parse_url($url);
            
            // Get hash
            if (isset($urlComponents['fragment'])) {
                $hashValue = $urlComponents['fragment'];
                if (!isset($uniqueHashes[$hashValue])) {
                    $uniqueHashes[$hashValue] = [$url];
                } else {
                    $uniqueHashes[$hashValue][] = $url;
                }
            }
            
            // Get parameters
            if (isset($urlComponents['query'])) {
                parse_str($urlComponents['query'], $params);
                foreach ($params as $key => $value) {
                    if (!isset($uniqueParams[$key])) {
                        $uniqueParams[$key] = [];
                    }
                    if (!isset($uniqueParams[$key][$value])) {
                        $uniqueParams[$key][$value] = [$url];
                    } else {
                        $uniqueParams[$key][$value][] = $url;
                    }
                }
            }
        } catch (Exception $e) {
            error_log("Invalid URL: $url");
        }
    }

    // Randomly limit examples for hashes
    foreach ($uniqueHashes as $hash => $urls) {
        $uniqueHashes[$hash] = getRandomElements($urls, $MAX_EXAMPLES);
    }

    // Randomly limit examples for parameters
    foreach ($uniqueParams as $param => $values) {
        foreach ($values as $value => $urls) {
            $uniqueParams[$param][$value] = getRandomElements($urls, $MAX_EXAMPLES);
        }
    }

    return [
        'hashes' => $uniqueHashes,
        'parameters' => $uniqueParams
    ];
}

function generateUrlAnalysisTables(array $urlElements): array {
    $MAX_EXAMPLES = 2;
    
    // Generate Hash Table
    $hashTable = '<table class="table">
        <thead>
            <tr>
                <th># trouvés</th>
                <th>Exemple d\'URL</th>
            </tr>
        </thead>
        <tbody>';
    
    foreach ($urlElements['hashes'] as $hash => $urls) {
        $randomUrls = getRandomElements($urls, $MAX_EXAMPLES);
        $urlList = implode('<br>', array_map('htmlspecialchars', $randomUrls));
        
        $hashTable .= "<tr>
            <td>" . htmlspecialchars($hash) . "</td>
            <td>{$urlList}</td>
        </tr>";
    }
    
    $hashTable .= '</tbody></table>';
    
    // Generate Parameters Table - grouped by parameter name only
    $parameterTable = '<table class="table">
        <thead>
            <tr>
                <th>? trouvés</th>
                <th>Exemple d\'URL</th>
            </tr>
        </thead>
        <tbody>';
    
    // Restructure parameters to group by parameter name only
    $groupedParams = [];
    foreach ($urlElements['parameters'] as $param => $values) {
        $groupedParams[$param] = [];
        foreach ($values as $urls) {
            $groupedParams[$param] = array_merge($groupedParams[$param], $urls);
        }
        // Remove duplicates
        $groupedParams[$param] = array_unique($groupedParams[$param]);
    }
    
    // Generate table rows
    foreach ($groupedParams as $param => $urls) {
        $randomUrls = getRandomElements($urls, $MAX_EXAMPLES);
        $urlList = implode('<br>', array_map('htmlspecialchars', $randomUrls));
        
        $parameterTable .= "<tr>
            <td>" . htmlspecialchars($param) . "</td>
            <td>{$urlList}</td>
        </tr>";
    }
    
    $parameterTable .= '</tbody></table>';
    
    return [
        'hash' => $hashTable,
        'parameters' => $parameterTable
    ];
}

function getInfoFPDomaine($id_domaine)
{
    global $handle_trace;
    // Configuration des fichiers 
    $repertoire = $_SERVER['DOCUMENT_ROOT'] ."script/fichiers/chatgpt/scrapping_produit/InfoFPDomaine/";

    $fileFP = $repertoire . "InfoFP-" . $id_domaine . ".json";

    $jsondataFP = file_get_contents($fileFP);

    $defaultDataDomaine = [
        "dataFP"        => [],
        "dataNFP"       => [],
        'FPinserted'    => 0
    ];
    $dataFP = $defaultDataDomaine;

    if(!empty($jsondataFP)) {
        $dataFP = json_decode($jsondataFP, true);
        if (json_last_error() !== JSON_ERROR_NONE) {
            fwrite($handle_trace, "Erreur de décodage JSON pour le fichier : {$fileFP}\n");
             $dataFP = $defaultDataDomaine;
        }
    } 

    return $dataFP;
}

function majInfoFPDomaine($id_domaine, $dataFP = [], $dataNFP = [] , $FPinserted = 0)
{
    // Configuration des fichiers 
    $repertoire = $_SERVER['DOCUMENT_ROOT'] ."script/fichiers/chatgpt/scrapping_produit/InfoFPDomaine/";

    $fileFP = $repertoire . "InfoFP-" . $id_domaine . ".json";

    $defaultDataDomaine = [
        "dataFP" => $dataFP,
        "dataNFP" => $dataNFP,
        'FPinserted'    => $FPinserted
    ];

    // Enregistrer les données dans le fichier JSON
    file_put_contents($fileFP, json_encode($defaultDataDomaine, JSON_PRETTY_PRINT));
}

function delInfoFPDomaine($id_domaine)
{
    // Configuration des fichiers 
    $repertoire = $_SERVER['DOCUMENT_ROOT'] ."script/fichiers/chatgpt/scrapping_produit/InfoFPDomaine/";

    $fileFP = $repertoire . "InfoFP-" . $id_domaine . ".json";

    if (file_exists($fileFP)) {
        unlink($fileFP);
    }
}

// Configuration des fichiers de suivi et d'erreurs
$repertoire = "script/fichiers/chatgpt/scrapping_produit/" . date("Y") . "/" . date("m") . "/";
if (!is_dir($_SERVER['DOCUMENT_ROOT'] . $repertoire)) {
    if (!mkdir($_SERVER['DOCUMENT_ROOT'] . $repertoire, 0777, true)) {
        return false;
    }
}
function recuperer_contenu_dossier($chemin_complet_dossier) {
    $tab_fichier = [];

    if ($handle = opendir($chemin_complet_dossier)) {
    
        while (false !== ($entry = readdir($handle))) {
            if ($entry != "." && $entry != "..") {
                $tab_fichier[] = $entry;
            }
        }
    
        closedir($handle);
    }

    return $tab_fichier;
}

$results      = [];
$id_domaine   = $_GET['id_domaine'];
$otherUrls    = $_GET['allUrlCrawled'];
$nb_crawling  = $_GET['success'];
$nb_erreur_crawling  = $_GET['failed'];
$method       = $_GET['method'];
$isFinished   = $_GET['isFinished'];
$results[0]   = $_GET['results'];
$origine      = $_GET['origine'];
$isError      = $_GET['isError'];

$fichier_tracking = date("Y-m-d-H-i") . "-tracking-detect-fiche-produit-" . $id_domaine . ".txt";
$handle_trace = fopen($_SERVER['DOCUMENT_ROOT'] . $repertoire . $fichier_tracking, "a+");

fwrite($handle_trace, "-----------------------------------------------\n");
fwrite($handle_trace, "Debut detection des fiches produits \n\n");
fwrite($handle_trace, "Id : {$id_domaine} \n");
fwrite($handle_trace, "otherUrls : {$otherUrls} \n");
fwrite($handle_trace, "nb_crawling : {$nb_crawling} \n");
fwrite($handle_trace, "isFinished : {$isFinished} \n");
fwrite($handle_trace, "nb_erreur_crawling : {$nb_erreur_crawling} \n\n");
fwrite($handle_trace, "origine : {$origine} \n");




if(!empty($origine) && $origine == "detectMethod")
{
    $otherUrls = get_allUrlCrawled($id_domaine);
}
else
{
    $data_maj = [];
    //mis à jour des nombre de urls crawler et les urls en erreur sur le crawling
    $stats_crawling = get_stats_crawling($id_domaine);
    $data_maj_domaine =  [
        "urls_crawling_dspi	" => $stats_crawling['nb_crawling_old'] + $nb_crawling,
        "urls_erreur_crawling_dspi	" => $stats_crawling['nb_erreur_crawling_old'] + $nb_erreur_crawling,
        "chemin_crawling_dspi" => ltrim($otherUrls, '\\')
    ];


    //maj statut enqueue => términé ou partielement términé
    //taitement des terminé partiels
    //maj erreur venant du crawlin : 7500 urls crawllé atteint
    if(!empty($isError) && in_array($isError , ['limitCrawl' , 'stoppedManually', "limitQuestionMark", "limitDiez"]))
    {
        $data_maj =[ 
            "statut_crawler_eci" => 4,
            "nb_retry_eci" => 0,
        ];
        $data_maj_domaine['statut_dspi'] = in_array($isError, ['stoppedManually', 'limitQuestionMark', 'limitDiez']) ? 12 : 10;

        //envoie de mail si le crawler est arrêté manuellement ou si le nombre de relance est atteint
        $mail_admin = getMailUserScraping($id_domaine);
        $mail_admin = !empty($mail_admin) ? "," . $mail_admin : "";
        $nom_domaine = getDomaine($id_domaine);

        $server_name_bo = $GLOBALS['protocol_http_host_bo'] . "bo.hellopro.fr"; // PROD
        $server_name_script = $GLOBALS['protocol_http_host_bo'] . "script.hellopro.fr"; // PROD

        $scraping_tool_base_link = $server_name_bo . "/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/index_V2.php";
        $shell_crawling_base_link = $server_name_script . "/script/chatgpt/script_relaunch_crawling.php";

        if ($isError == 'limitCrawl') {
            $objet = "[ERREUR][SCRAPPING] - Crawling de domaine arrêté : Nombre maximum d'URLs atteint";
            $message = 'Bonjour,';
            $message .= "<br><br>Le nombre maximum d'URLs crawlées de 5000 urls a été atteint pour le domaine <b><a href='{$scraping_tool_base_link}?domaine_dspi=contient|{$nom_domaine}'>{$id_domaine} - {$nom_domaine}</a></b>.<br>";
            $message .= "<br>Si vous souhaitez tout de même continuer le crawling, vous pouvez le relancer en cliquant sur le lien ci-dessous :";
            $message .= "<br><a href='{$shell_crawling_base_link}?id={$id_domaine}&breakLimit=1'>Continuer le crawling</a>";
            $message .= '<br><br>Cordialement';
        } elseif ($isError == 'stoppedManually') {
            $objet = "[SCRIPT][SCRAPPING] - Crawling de domaine arrêté manuellement";
            $message = 'Bonjour,';
            $message .= "<br><br> Le crawling du domaine <b><a href='{$scraping_tool_base_link}?domaine_dspi=contient|{$nom_domaine}'>{$id_domaine} - {$nom_domaine}</a></b> a été arrêté manuellement.<br>";
            $message .= '<br><br>Cordialement';
        } elseif ($isError == 'limitQuestionMark') {
            $otherUrls = $_SERVER['DOCUMENT_ROOT'] . ltrim($otherUrls, '\\');
            $otherUrlsContent = loadJsonFilesFromDirectory($otherUrls);

            $tableQuestionMark = [];
            if (!empty($otherUrlsContent)) {
                $urls = array_column($otherUrlsContent, 'url');
                $urlQuestionMark = getUniqueURLElements($urls);
                $tableQuestionMark = generateUrlAnalysisTables($urlQuestionMark);
            }
            $objet = "[SCRIPT][SCRAPPING] - Crawling de domaine arrêté : nombre maximum d'urls avec ? atteint";
            $message = 'Bonjour,';
            $message .= "<br><br>Le crawl pour le domaine suivant a été arrêté automatiquement car le nombre maximum d'urls avec ? a été atteint";
            $message .= "<br>Voici le domaine : <b><a href='{$scraping_tool_base_link}?domaine_dspi=contient|{$nom_domaine}'>{$id_domaine} - {$nom_domaine}</a></b>";
            if (!empty($tableQuestionMark['parameters'])) {
                $message .= "<br>Voici un tableau récapitulatif qui montre les paramètres trouvés ainsi que quelques exemples d'URLs associées :";
                $message .= "<br>{$tableQuestionMark['parameters']}";
                $message .= "<br><br>Vous pouvez également consulter la liste plus complète dans l'interface avec le bouton 'Historique' pour ce domaine.";
            }
            $message .= "<br><br>Merci de vérifier :";
            $message .= "<br><ul>";
            $message .= "<li>l'historique des URLs crawlés (Visible dans l'interface)</li>";
            $message .= "<li>sur le site s'il est nécessaire de garder les ? (Nécessaire dans pour les pagination, nécessaire pour avoir les fiches produits, ne génère pas de doublon d'URLs, etc)</li>";
            $message .= "<br></ul>";
            $message .= "<br>Après vérification, vous pouvez décider de relancer le crawl du domaine en cliquant sur le bouton <b>'Relancer le crawl'</b> et faire les modifications nécessaires pour la relance.";
            $message .= '<br><br>Cordialement';
        } elseif ($isError == 'limitDiez') {
            $otherUrls = $_SERVER['DOCUMENT_ROOT'] . ltrim($otherUrls, '\\');
            $otherUrlsContent = loadJsonFilesFromDirectory($otherUrls);

            $tableDiez = [];
            if (!empty($otherUrlsContent)) {
                $urls = array_column($otherUrlsContent, 'url');
                $urlDiez = getUniqueURLElements($urls);
                $tableDiez = generateUrlAnalysisTables($urlDiez);
            }
            $objet = "[SCRIPT][SCRAPPING] - Crawling de domaine arrêté : nombre maximum d'urls avec # atteint";
            $message = 'Bonjour,';
            $message .= "<br><br>Le crawl pour le domaine suivant a été arrêté automatiquement car le nombre maximum d'urls avec # a été atteint";
            $message .= "<br>Voici le domaine : <b><a href='{$scraping_tool_base_link}?domaine_dspi=contient|{$nom_domaine}'>{$id_domaine} - {$nom_domaine}</a></b>";
            if (!empty($tableDiez['hash'])) {
                $message .= "<br>Voici un tableau récapitulatif qui montre les paramètres trouvés ainsi que quelques exemples d'URLs associées :";
                $message .= "<br>{$tableDiez['hash']}";
                $message .= "<br><br>Vous pouvez également consulter la liste plus complète dans l'interface avec le bouton 'Historique' pour ce domaine.";
            }
            $message .= "<br><br>Merci de vérifier :";
            $message .= "<br><ul>";
            $message .= "<li>l'historique des URLs crawlés (Visible dans l'interface)</li>";
            $message .= "<li>sur le site s'il est nécessaire de garder les # (Nécessaire dans pour les pagination, nécessaire pour avoir les fiches produits variantes, ne génère pas de doublon d'URLs, etc)</li>";
            $message .= "<br></ul>";
            $message .= '<br><br>Cordialement';
        }

        envoyer_mail_scripts($objet, "", "script@hellopro.fr" . $mail_admin , $message, 1); //PROD
    }
    elseif($isFinished == 1){
        $data_maj =[ "statut_crawler_eci" => 2];
        $data_maj_domaine["date_fin_crawling_dspi"] = date("Y-m-d H:i:s");
    }
    else{    
        $data_maj =[ 
            "statut_crawler_eci" => 3,
            "date_continuation_eci" => date('Y-m-d H:i', strtotime('+4 hours'))
        ];
    }

    
    sql_update_info(
        $data_maj_domaine
       ,
        "domaine_scrapping_produit_ia",
        [
            "id_domaine_scrapping_produit_ia" => $id_domaine
        ]
    );

    sql_update_info(
        $data_maj,
        "enqueue_crawling_ia",
        [
            "id_domaine_scrapping_produit_ia" => $id_domaine
        ]
    );
}

//lancer crawler suivant
launchEnqueueCrawler("crawler");

//TODO DEV ONLY COMMENTAIRE
if( ( $isFinished != 1 && $origine != "detectMethod") || (!empty($isError) && in_array($isError , ['limitCrawl' , 'stoppedManually']))){
    fclose($handle_trace);
    exit;
}

$requiredParams = ['id_domaine' => $id_domaine, 'otherUrls' => $otherUrls];

$missingParams = array_keys(array_filter($requiredParams, fn($v) => empty($v)));

if (!empty($missingParams)) {
    http_response_code(400);
    echo "Missing parameters: " . implode(', ', $missingParams);
    exit;
}

//verification du chemin de crawling
if(strpos($otherUrls,$_SERVER["DOCUMENT_ROOT"]) !== false) {
    $parse_otherUrls = explode($_SERVER["DOCUMENT_ROOT"],$otherUrls);

    $otherUrls = end($parse_otherUrls);
}

$otherUrls = $_SERVER['DOCUMENT_ROOT'] . ltrim($otherUrls, '\\');

$count = 0;

while(empty($results[0]) && $count < 3){
    

    $cms_name_sql = "SELECT
                        DSPI.cms_dspi, 
                        DSPI.methode_fp_dspi,
                        DSPI.domaine_dspi,
                        DSPI.urls_crawling_dspi,
                        DSPI.urls_erreur_crawling_dspi,
                        DSPI.data_crawling_dspi
                    FROM 
                        domaine_scrapping_produit_ia DSPI
                    WHERE DSPI.id_domaine_scrapping_produit_ia = '".hellopro_traitement_donnee_annuaire_bo($id_domaine)."'
                    LIMIT 1";

    $res_cms_name = mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $cms_name_sql) or die(hellopro_mysql_error($cms_name_sql, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));
    $lig_cms_name = mysqli_fetch_assoc($res_cms_name);
    $domaine      = $lig_cms_name['domaine_dspi'];
    $info_cms     = json_decode($lig_cms_name['cms_dspi'], true);
    $cms_name     = $info_cms['cms_name'];
    $cms_name     = trim(strtolower($cms_name));
    $results[0]   = json_decode($lig_cms_name['methode_fp_dspi'] , true)['resultat'];

    $data         = json_decode($lig_cms_name['data_crawling_dspi'], true);
    $homepage     = !empty($data['homepage']) ? $data['homepage'] :( "https://" + $lig_cms_name['domaine_dspi'])  ;
    
	fwrite($handle_trace, "Homepage : {$homepage} \n");
    fwrite($handle_trace, "cms_name : {$cms_name} \n");
    if(!empty($method) && $method == "auto")
    {
        fwrite($handle_trace, "Méthode de détéction fiche produit : Automatique \n\n");
        $count = 3;
        break;
    }
    else
    {
        fwrite($handle_trace, "Méthode de détéction fiche produit : {$lig_cms_name['methode_fp_dspi']} \n\n");
        fwrite($handle_trace, print_r($results, true) . " \n\n");
    }
    

    sleep(10);
    $count++;
}

//patterns cms gérer 
$cms_gerer_auto = [
    "PrestaShop",
    "WIX Website Builder",
    "TYPO3 CMS",
    "Shopify",
    "Magento",
    "Drupal",
    "WordPress",
];

$pattern_cms = "/(" . preg_replace("/\s+/", "\s*", implode("|", $cms_gerer_auto)) . ")/i";

$emptyDataset = false;
$otherUrlsFile = $otherUrls;
$otherUrlsContent = loadJsonFilesFromDirectory($otherUrlsFile);
fwrite($handle_trace, "Nombre d'URLs à analyser : " . count($otherUrlsContent) . "\n\n");

$libelleCriteria = libelleCriteriaCmsGere();
$classifiedUrls = [];
$unClassifiedUrls = [];
$oneBYone = false;
if($method == "auto" )
{
    //ajout tracking si la méthode de détéction des fiche produit est automatique , mais c'est pas un cms géré
    fwrite($handle_trace, "Debut détéction auto des URL fiche produit:  \n\n");
    

    if(count($otherUrlsContent) <= 1)
    {
        fwrite($handle_trace, "reverification des urls crawler  \n\n");
        $tempOtherUrlsContent = [];

        $tab_fichier_crawling = recuperer_contenu_dossier($otherUrls);

        fwrite($handle_trace, "Nombre de fichiers à analyser : " . count($tab_fichier_crawling) . "\n\n");
        
        foreach($tab_fichier_crawling as $fichier) {
            try{
                $json_content = file_get_contents($otherUrls."/".$fichier);
                $tab_json     = json_decode($json_content,true);
                $tempOtherUrlsContent[] = $tab_json;
            } catch(Exception $e) {
                fwrite($handle_trace, "Erreur json : " . $e->getMessage() . " \n\n");
            }
        }

        if(count($tempOtherUrlsContent) > 1)
        {
            fwrite($handle_trace, "Nombre d'URLs à analyser après re-vérification : \n\n");
            fwrite($handle_trace, "Avant : " . count($otherUrlsContent) . " - " . print_r($otherUrlsContent) . "\n\n");
            fwrite($handle_trace, "Après : " . count($tempOtherUrlsContent) . " - " . print_r($tempOtherUrlsContent) . "\n\n");
            $otherUrlsContent = $tempOtherUrlsContent;
           
        }
    }
    

    if(empty($otherUrlsContent) || count($otherUrlsContent) <= 1)
    {
        $emptyDataset = true;
        fwrite($handle_trace, "Aucun url crawlé \n\n");
        fwrite($handle_trace, "otherUrlsContent : " . print_r($otherUrlsContent , true) . "\n\n");
    }
    else if(!preg_match($pattern_cms , $cms_name))
    {
        $classifiedUrls = detecter_fiche_produit_site($otherUrlsContent);
    }
    else
    {
        
        $filtre_qualif_auto = [];
        fwrite($handle_trace, "CMS géré\n");
    
        foreach ($otherUrlsContent as $entry) {
            $url = $entry['url'] ?? '';
            $content = $entry['content'] ?? '';
            $uniqueCriteria = $results[0];
            // Vérifier si l'URL satisfait aux critère de détéction automatique des fiche produits
            $criteria = detectCriteriaAuto($content, $url, $cms_name);
            if (!empty($criteria)) {
                $classifiedUrls[] = ["url" => $url, "content" => $content];

                foreach ($criteria as $key => $value) {
                    if (!in_array($key, $filtre_qualif_auto) && $value ) {
                        $filtre_qualif_auto[] = $key;
                    }
                }
            }        
        }

        //enregistrement des filtres qualification
        fwrite($handle_trace, "Critère de détection automatique : " . print_r($filtre_qualif_auto, true) . "\n\n");
        if(!empty($filtre_qualif_auto)) {
           foreach($libelleCriteria as $keyCms => $critereCms) {
                if(strtolower($cms_name) == strtolower($keyCms)) {
                    foreach($filtre_qualif_auto as $keyQualif => $valueQualif) {

                        if(empty($critereCms[$valueQualif])) {
                            fwrite($handle_trace, "Critère {$valueQualif} non trouvé pour le CMS {$cms_name} \n\n");
                            continue;
                        }

                        $data = $critereCms[$valueQualif];
                        $data['origine'] = 2;
                        $id_filtre_qualif =  add_filtre_qualification($id_domaine , $data) ;
                    }
                    
                }
            }
        }
        
    
        if(empty($classifiedUrls) && preg_match("/WordPress/i" , $cms_name))
        {
            fwrite($handle_trace, "Détéction des URL fiche produit via sitemap:  \n\n");
            $list_url_sm = processSitemap($homepage);  
            $fiche_produit = []; 
            foreach($list_url_sm AS $url_smp => $data_sm)
            {
                fwrite($handle_trace, "Sitemap produit: " . var_export($data_sm , true) ."  \n\n");
                foreach($data_sm->url AS $data_url)
                {
                    $temp_url = (string)$data_url->loc;
                    $temp_url = trim($temp_url);
                    $info_url = parse_url($temp_url);
                    if( empty($temp_url) || preg_match("/^\/?[^\/]+\/?$/" , $info_url['path']))
                    {
                        continue;
                    }
                    
                    $fiche_produit[] = $temp_url;
                }
            }

            fwrite($handle_trace, "Fiche produit sitemap : " . print_r($fiche_produit , true) . "\n\n");
            
            if(!empty($fiche_produit))
            {
                foreach ($otherUrlsContent as $entry) {
                    $url = $entry['url'] ?? '';
                    $content = $entry['content'] ?? '';
                    
                    fwrite($handle_trace, "URL à verifie : " . $url . "\n");
                    if (in_array($url , $fiche_produit)) {
                        fwrite($handle_trace, "URL produit\n\n");
                        $classifiedUrls[] = ["url" => $url, "content" => $content];
                    }        
                }

                if(!empty($classifiedUrls)) {
                    fwrite($handle_trace, "URL produit trouvée dans le sitemap \n\n");
                    $data = [
                        'searchType' =>  '0',
                        'searchValue' => "",
                        'typeFiltre' => 5,
                        'modeQualif' => 0,
                        'origine' => 2 //qualification urls            
                    ];        

                    $id_filtre_qualif =  add_filtre_qualification($id_domaine , $data) ;
                }
            }
            
        }


        if(empty($classifiedUrls)) {
            fwrite($handle_trace, "detecter_fiche_produit_site \n\n");
            $classifiedUrls = detecter_fiche_produit_site($otherUrlsContent);
        }
    }   

}
else
{   
    fwrite($handle_trace, "Debut détéction manuel des URL fiche produit:  \n\n");
    if(is_array($results) && array_key_exists('GPT', $results[0])) {
        fwrite($handle_trace, "Méthode GPT détectée\n");
        $res_synthese = $results[0]['GPT'];
        fwrite($handle_trace, "Résultats GPT : " . print_r($res_synthese, true) . "\n\n");
        
        $oneBYone   = true; // On insert les URLs FPs une par une pour la méthode GPT
        $InfoFPNFP  = getInfoFPDomaine($id_domaine);
        $dataFP     = $InfoFPNFP['dataFP'];
        $dataNFP    = $InfoFPNFP['dataNFP'];
        $FPinserted = $InfoFPNFP['FPinserted'] ?? 0;
        fwrite($handle_trace, "URLs déjà classifiée comme fiche produit : \n" . print_r($dataFP, true) . "\n");
        fwrite($handle_trace, "URLs déjà classifiée comme non fiche produit : \n" . print_r($dataNFP, true) . "\n");
        fwrite($handle_trace, "Nombre de fiche produit déjà inséré : " . $FPinserted . "\n\n");

        foreach($otherUrlsContent as $entry) {
            $url = $entry['url'] ?? '';
            fwrite($handle_trace, "Analyse de l'URL : $url\n");
            
            $content = $entry['content'] ?? '';
            $content_minified = traitement_contenu_web($content);

            if(in_array($url, $dataFP)) {
                fwrite($handle_trace, "URL déjà classifiée comme fiche produit.\n");
                
                continue;
            }
            elseif(in_array($url, $dataNFP)) {
                fwrite($handle_trace, "URL déjà classifiée comme non fiche produit.\n");
                
                continue;
            }

            if(!isset($res_synthese[$id_domaine]['titre'], $res_synthese[$id_domaine]['description'], $res_synthese[$id_domaine]['image'])){
                fwrite($handle_trace, "Sélecteurs manquants pour l'ID domaine $id_domaine\n");
                continue;
            }
    
            $selecteur_titre[0]['selecteur'] = $res_synthese[$id_domaine]['titre'];
            $selecteur_description[0]['selecteur'] = $res_synthese[$id_domaine]['description'];
            $selecteur_image[0]['selecteur'] = $res_synthese[$id_domaine]['image'];
            
            // fwrite($handle_trace, "Sélecteurs utilisés:\n");
            // fwrite($handle_trace, "- Titre: " . $selecteur_titre[0]['selecteur'] . "\n");
            // fwrite($handle_trace, "- Description: " . $selecteur_description[0]['selecteur'] . "\n");
            // fwrite($handle_trace, "- Image: " . $selecteur_image[0]['selecteur'] . "\n");
            
            $res_content_titre = recupere_contenu_selecteur($selecteur_titre, "titre", $url, $content_minified, "");
            $res_content_description = recupere_contenu_selecteur($selecteur_description, "description", $url, $content_minified, "");
            $res_content_image = recupere_contenu_selecteur($selecteur_image , "image", $url, $content_minified, "",  ["skip_ddblng" => true]);
    
            fwrite($handle_trace, "Résultats extraction:\n");
            fwrite($handle_trace, "- Titre valide: " . (isValidFP($res_content_titre, "new_contenu_produit") ? "Oui" : "Non") . "\n");
            fwrite($handle_trace, "- Description valide: " . (isValidFP($res_content_description, "new_contenu_produit") ? "Oui" : "Non") . "\n");
            fwrite($handle_trace, "- Image valide: " . (isValidFP($res_content_image, "new_contenu_produit") ? "Oui" : "Non") . "\n\n");
    
            if (isValidFP($res_content_titre, "new_contenu_produit") &&
                isValidFP($res_content_description, "new_contenu_produit") &&
                isValidFP($res_content_image, "new_contenu_produit")) {
                fwrite($handle_trace, "✓ URL CLASSIFIÉE COMME FICHE PRODUIT\n");
                // fwrite($handle_trace, "============================================\n");
                fwrite($handle_trace, "URL: " . $url . "\n");
                // fwrite($handle_trace, "Titre extrait: " . print_r($res_content_titre['new_contenu_produit'], true) . "\n");
                // fwrite($handle_trace, "Description extraite: " . print_r($res_content_description['new_contenu_produit'], true) . "\n");
                // fwrite($handle_trace, "Image extraite: " . print_r($res_content_image['new_contenu_produit'], true) . "\n");
                // fwrite($handle_trace, "============================================\n\n");
                $classifiedUrls[] = ["url" => $url, "content" => $content];
                
                $nb_inserted = insertDataResult($classifiedUrls, $id_domaine);
                $FPinserted += $nb_inserted;
                $classifiedUrls = []; // Réinitialiser pour éviter les doublons

                $dataFP[] = $url; // Ajouter l'URL à la liste des fiches produits
            }
            else {
                fwrite($handle_trace, "✗ URL NON CLASSIFIÉE\n");
                fwrite($handle_trace, "--------------------------------------------\n");
                fwrite($handle_trace, "URL: " . $url . "\n");
                fwrite($handle_trace, "Raison: \n");
                if (!isValidFP($res_content_titre, "new_contenu_produit")) fwrite($handle_trace, "- Titre invalide\n");
                if (!isValidFP($res_content_description, "new_contenu_produit")) fwrite($handle_trace, "- Description invalide\n");
                if (!isValidFP($res_content_image, "new_contenu_produit")) fwrite($handle_trace, "- Image invalide\n");
                fwrite($handle_trace, "--------------------------------------------\n\n");
                $unClassifiedUrls[] = ["url" => $url, "content" => $content];
                $dataNFP[] = $url; // Ajouter l'URL à la liste des non-fiches produits
            }

            majInfoFPDomaine($id_domaine, $dataFP, $dataNFP , $FPinserted);
        }

        delInfoFPDomaine($id_domaine);

        $data = [
            'searchType' =>  '0',
            'searchValue' => "",
            'typeFiltre' => 6,
            'modeQualif' => 0,
            'origine' => 2 //qualification urls            
        ];        

        $id_filtre_qualif =  add_filtre_qualification($id_domaine , $data) ;
    }
    elseif($results[0] == "SITEMAP" && preg_match("/WordPress/i" , $cms_name))
    {
        fwrite($handle_trace, "Détéction des URL fiche produit via sitemap:  \n\n");
        $list_url_sm = processSitemap($homepage);  
        $fiche_produit = []; 
        foreach($list_url_sm AS $url_smp => $data_sm)
        {
            fwrite($handle_trace, "Sitemap produit: " . var_export($data_sm , true) ."  \n\n");
            foreach($data_sm->url AS $data_url)
            {
                $temp_url = (string)$data_url->loc;
                $temp_url = trim($temp_url);
                $info_url = parse_url($temp_url);
                if( empty($temp_url) || preg_match("/^\/?[^\/]+\/?$/" , $info_url['path']))
                {
                    continue;
                }
                
                $fiche_produit[] = $temp_url;
            }
        }

        fwrite($handle_trace, "Fiche produit sitemap : "  . print_r($fiche_produit , true) . "\n\n");
        
        if(!empty($fiche_produit))
        {
            foreach ($otherUrlsContent as $entry) {
                $url = $entry['url'] ?? '';
                $content = $entry['content'] ?? '';
                 
                fwrite($handle_trace, "URL à verifie : " . $url . "\n");
                if (in_array($url , $fiche_produit)) {
                    fwrite($handle_trace, "URL produit\n\n");
                    $classifiedUrls[] = ["url" => $url, "content" => $content];
                }        
            }
        }
        
    } else {
        fwrite($handle_trace, "Méthode CMS détectée pour : $cms_name\n");
        switch($cms_name){
            case 'prestashop':
            case 'magento'   :
            case 'drupal'    :  
            case "wix website builder":  
            case "wordpress" : 
            case "shopify" : 
                fwrite($handle_trace, "CMS géré détecté\n");
               
                // Classifier les URLs
                fwrite($handle_trace, "URLs classifiées :\n");
                $classifiedUrls = classifyUrls($otherUrlsContent, $cms_name, $results);
                fwrite($handle_trace, print_r($classifiedUrls, true) . "\n\n");
                break;
            default :
                fwrite($handle_trace, "CMS non géré\n");
                break;
        }
    }

    
}
fwrite($handle_trace, "Finale :\n\n");
foreach ($classifiedUrls as $item) {
    fwrite($handle_trace, "-" . $item['url'] . "\n");
}



$data_update = [  "urls_fiches_produits_dspi" => 0 ];

if($emptyDataset) {
    $data_update["statut_dspi"] = 9; // Pas de données à traiter
    fwrite($handle_trace, "Aucune URL à traiter, statut mis à jour à 9 (Pas de données)\n");

    $objet = "[SCRIPT][SCRAPPING] - ERREUR de crawl du domaine";
    $messages = 'Bonjour,';
    $messages .= "<br><br>On a " . count($otherUrlsContent) . " URLs crawlé pour le domaine <b>{$id_domaine} - {$domaine}</b>.<br>";
    $messages .= "Page d'accueil : <b><a href='{$homepage}' target='_blank'>{$homepage}</a></b><br>";
    $messages .= '<br><br>Cordialement';        
    envoyer_mail_scripts($objet, "", "script@hellopro.fr", $messages, 1); //PROD

} else if(!empty($classifiedUrls) || ($oneBYone && !empty($dataFP)) ){
    $nb_inserted = $oneBYone ? $FPinserted : insertDataResult($classifiedUrls, $id_domaine);
    // echo 'OK : '.$nb_inserted;

    fwrite($handle_trace, 'OK : '.$nb_inserted . " \n");
    $data_update["urls_fiches_produits_dspi"] = $nb_inserted;
    

    $server_name = $GLOBALS['protocol_http_host_bo'] . "script.hellopro.fr"; // PROD
    // $server_name = $GLOBALS['protocol_http_host_bo'] . "dev-script.hellopro.fr"; // DEV
    
    fwrite($handle_trace, 'Début détection top fiche : ' . date('Y-m-d H:i:s') . " \n");

    $test_temp = $_SERVER['DOCUMENT_ROOT'] . 'tmp/script_scrapping_produit_ia_DOCUMENTE_' . date('Ymdhis') . '.log';
    $command = "cd " . $_SERVER['DOCUMENT_ROOT'] . "tmp/; wget -q -b -t 1 '" . $server_name . "/script/chatgpt/script_scrapping_produit_ia_V2.php?id_domaine=" . $id_domaine . "&checkIdeal=1' -a '" . $test_temp . "'";
    $a = shell_exec($command);
}
else{
    $server_name = $GLOBALS['protocol_http_host_bo'] . "script.hellopro.fr"; // PROD
    //$server_name = $GLOBALS['protocol_http_host_bo'] . "dev-script.hellopro.fr"; // DEV
    $method_detection = $method == "auto" ? "automatique" : "fpnfp";
    $data_update["statut_dspi"] = $method == "auto" ? 7 : 8;
    fwrite($handle_trace, 'KO : détéction ' . $method_detection. ' des fiches produits' . " \n");

    if ($method == "auto") {
        $objet = "[SCRIPT][SCRAPPING] - Aucune fiche produit détectée automatiquement";
        $messages .= "<hr>Impossible d'identifier automatiquement les fiches produits pour l'id_domaine : " . $id_domaine . " .<br><br>";
        $messages .= "Fichier de log : <br>";
        $messages .= '<a href="' . $server_name . '/' . $repertoire . $fichier_tracking . '" target="_blank">' . $fichier_tracking . '</a><br>';

        envoyer_mail_scripts($objet, "", "script@hellopro.fr", $messages, 1); //PROD
    }
    

    
}
// echo "<pre>".print_r($classifiedUrls, true)."</pre><br>";


 //enregister le nombre de url fiche produits
 sql_update_info(
    $data_update,
    "domaine_scrapping_produit_ia",
    [
        "id_domaine_scrapping_produit_ia" => $id_domaine
    ]
);

fclose($handle_trace);