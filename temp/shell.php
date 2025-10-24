<?php
require_once($_SERVER['DOCUMENT_ROOT'] . "admin/secure/connexion.php");
require_once($_SERVER['DOCUMENT_ROOT'] . "no_read_access/connexion_bdd_hellopro_ia.php");
require_once($_SERVER["DOCUMENT_ROOT"] . "fonctions/fonctions_generales.php");
require_once($_SERVER["DOCUMENT_ROOT"] . "fonctions/fonctions_hellopro.php");
require_once($_SERVER['DOCUMENT_ROOT'] . 'no_read_access/apify/connexion_api_apify.php');
require_once($_SERVER['DOCUMENT_ROOT'] . 'admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/fonctions/fonctions_scrapping.php');

// --- START: Crawler Service Migration ---

/**
 * Handles the logic for when a LEGACY crawl fails.
 *
 * @param int $id_domaine The ID of the domain that failed.
 * @return void
 */
function handle_crawl_failure($id_domaine) {
    // This function is now only for the legacy system.
    error_log("Legacy crawl failure detected for domain ID: {$id_domaine}. Relaunching enqueue process.");
    launchEnqueueCrawler('crawler');
}


// --- Smart Crawl Launcher ---
$id_domaine = $_GET['id'];
$domaine = $_GET['domain'];
$startUrl = $_GET['site'];

if (empty($id_domaine)) {
    http_response_code(400);
    exit("Missing required parameter: id");
}

// Get domain info and determine which system to use
$sql_domaine = "
    SELECT
        id_domaine_scrapping_produit_ia,
        domaine_dspi,
        data_crawling_dspi,
        systeme_dspi
    FROM domaine_scrapping_produit_ia DSPI
    WHERE id_domaine_scrapping_produit_ia = '" . hellopro_traitement_donnee_annuaire_bo($id_domaine) . "'
";
$res_domaine = mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_domaine) or die(hellopro_mysql_error($sql_domaine, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));
$lig_domaine = mysqli_fetch_assoc($res_domaine);

if (!$lig_domaine) {
    http_response_code(404);
    exit("Domain with ID {$id_domaine} not found.");
}

$systeme = (int)$lig_domaine['systeme_dspi'];

if (empty($domaine) || empty($startUrl)) {
    $domaine    = $lig_domaine['domaine_dspi'];
    $data       = json_decode($lig_domaine['data_crawling_dspi'] , true);        
    $startUrl   = !empty($data['homepage']) ? $data['homepage'] : "https://".$domaine; 
}

// Fetch extra parameters from DB for BOTH systems
$sql_param = 
    "SELECT
        variable_crawler_pci,
        valeur_pci
    FROM parametre_crawler_ia PCI
    WHERE 
        variable_crawler_pci NOT IN ('parallelescraper')
";
$res_param = mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_param) or die(hellopro_mysql_error($sql_param, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));
$extraParams = [];
while ($lig_param = mysqli_fetch_assoc($res_param)) {
    $extraParams[$lig_param['variable_crawler_pci']] = $lig_param['valeur_pci'];
}

if ($systeme === SYSTEM_API) {
    // --- API System Launch ---
    error_log("Launching crawl for domain ID {$id_domaine} via API Service.");
    header('Content-Type: application/json');

    $api_service = get_crawler_api_service();
    
    // Construct callback URLs
    $server_name = $GLOBALS['protocol_http_host_bo'] . "script.hellopro.fr";
    $callback_script = $server_name . "/script/chatgpt/script_process_detect_fiche_produit.php";

    // Both success and failure point to the same script. The script will check parameters to know the context.
    $success_callback = $callback_script;
    $failure_callback = $callback_script;

    // Map GET parameters to the API payload
    $payload = [
        'id' => $id_domaine,
        'domain' => $domaine,
        'start_url' => $startUrl,
        'callback_url' => $success_callback,
        'failure_callback_url' => $failure_callback,
        'type_crawling' => $_GET['typecrawling'] ?? null,
        'method' => $_GET['method'] ?? null,
        'drop_data' => isset($_GET['dropdata']) ? (bool)$_GET['dropdata'] : false,
        'skip_question_mark' => isset($_GET['skipquestionmark']) ? (bool)$_GET['skipquestionmark'] : false,
        'skip_diez' => isset($_GET['skipdiez']) ? (bool)$_GET['skipdiez'] : false,
        'bypass_question_mark' => isset($_GET['bypassquestionmark']) ? (bool)$_GET['bypassquestionmark'] : false,
        'bypass_diez' => isset($_GET['bypassdiez']) ? (bool)$_GET['bypassdiez'] : false,
        'break_limit' => isset($_GET['breaklimit']) ? (bool)$_GET['breaklimit'] : false,
        'to_keep' => isset($_GET['tokeep']) ? explode(';', $_GET['tokeep']) : [],
        'to_remove' => isset($_GET['toremove']) ? explode(';', $_GET['toremove']) : [],
        'proxy_apify' => APIFY_PROXY ?? null,
        // Add DB parameters
        'per_crawl' => isset($extraParams['percrawl']) ? (int)$extraParams['percrawl'] : 0,
        'per_minute' => isset($extraParams['perminute']) ? (int)$extraParams['perminute'] : 100,
    ];
    
    $api_response = $api_service->startCrawl($payload);

    // Echo the API response back to the caller (e.g., script_lancer_enqueue_crawling)
    echo json_encode($api_response);
    exit();

} else {
    // --- Legacy System Launch ---
    error_log("Launching crawl for domain ID {$id_domaine} via Legacy System. This is deprecated.");
    
    $typeCrawling = ($_GET['typecrawling']) ? '"--typecrawling=' . $_GET['typecrawling'] . '"' : '';
    $keyApifyProxy = !empty(APIFY_PROXY) ? '"--proxyApify=' . APIFY_PROXY . '"' : '';
    $method = ($_GET['method']) ? '"--method=' . $_GET['method'] . '"' : '';
    $dropData = ($_GET['dropdata']) ? '"--dropdata=' . $_GET['dropdata'] . '"' : '';
    $skipquestionmark = ($_GET['skipquestionmark']) ? '"--skipquestionmark=' . $_GET['skipquestionmark'] . '"' : '';
    $skipdiez = ($_GET['skipdiez']) ? '"--skipdiez=' . $_GET['skipdiez'] . '"' : '';
    $bypassQuestionMark = ($_GET['bypassquestionmark']) ? '"--bypassquestionmark=' . $_GET['bypassquestionmark'] . '"' : '';
    $bypassDiez = ($_GET['bypassdiez']) ? '"--bypassdiez=' . $_GET['bypassdiez'] . '"' : '';
    $breakLimit = ($_GET['breaklimit']) ? '"--breaklimit=' . $_GET['breaklimit'] . '"' : '';
    $toKeep = ($_GET['tokeep']) ? '"--tokeep=' . $_GET['tokeep'] . '"' : '';
    $toRemove = ($_GET['toremove']) ? '"--toremove=' . $_GET['toremove'] . '"' : '';

    $extraParam = '';
    foreach ($extraParams as $key => $value) {
        $extraParam .= ' "--' . $key . '=' . $value . '" ';
    }

    $params = <<<PARAMETERS
        "--id={$id_domaine}" "--domain={$domaine}" "--site={$startUrl}" {$typeCrawling} $keyApifyProxy {$method} {$dropData} {$skipquestionmark} {$skipdiez} {$bypassQuestionMark} {$bypassDiez} {$breakLimit} {$toKeep} {$toRemove} "--root={$_SERVER['DOCUMENT_ROOT']}" {$extraParam}
    PARAMETERS;

    $commandExportPath = 'export PATH=$PATH:/usr/local/bin;';

    // To Run
    $commandSystem = <<<COMMAND
        $commandExportPath npm run release:prod $params 2>&1 & echo "pid: $!##id_domaine: {$id_domaine}" > processus/pid_{$domaine}.txt
    COMMAND;

    $repertoire_shell =  $_SERVER['DOCUMENT_ROOT'] . '/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/tools/crawler/retour_shell/'. date('Y/m') . "/";
    if (!is_dir($repertoire_shell)) {
        if (!mkdir($repertoire_shell, 0777, true)) {
            return false;
        }
    }
    $log_npm = $repertoire_shell . 'content_shell_' . $domaine . '_.txt';

    exec($commandSystem, $output, $result_code);

    $ancien = file_exists($log_npm) ? file_get_contents($log_npm) : '';
    $now = "Date : " . date('Y-m-d H:i:s') . "\n";
    $now .= "Commande : " . $commandSystem . "\n";
    $now .= "Output : " . implode('<br>', $output) . "\n";
    $now .= "Result code : " . $result_code . "\n";
    file_put_contents($log_npm, $ancien . "\n\n" . $now);

    echo '<pre>'; echo('<b><u>Command :</b></u><br>' . $commandSystem); echo '</pre>';
    echo '<pre>'; echo('<b><u>Output :</b></u><br>' . implode('<br>', $output)); echo '</pre>';
    echo '<pre>'; echo('<b><u>Result code :</b></u>' . ' ' . $result_code); echo '</pre>';

    if ($result_code !== 2) {
        echo '<pre>'; echo('<b><u>Erreur result code :</b></u>' . ' ' . $result_code); echo '</pre>';
        handle_crawl_failure($id_domaine);
    }
}
// --- END: Crawler Service Migration ---
?>