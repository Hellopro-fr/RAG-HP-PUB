<?php

require_once($_SERVER["DOCUMENT_ROOT"] . "admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/lib/autoload.php"); # Autoload pour Librairie
require_once($_SERVER["DOCUMENT_ROOT"] . "admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/class/HtmlMin.php"); # HTML Minifier
require_once($_SERVER["DOCUMENT_ROOT"] . "admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/class/ImageComparator.php"); # Image Comparator
require_once($_SERVER["DOCUMENT_ROOT"] . "admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/class/TopFicheEvaluator.php"); # TopFicheEvaluator

// --- START: Crawler Service Migration Code ---

define('CRAWLER_API_BASE_URL', 'http://34.34.5.41:8500/crawling-service');
define('SYSTEM_LEGACY', 0);
define('SYSTEM_API', 1);

/**
 * Singleton class to interact with the new Crawler Microservice API.
 */
class CrawlerApiService {
    private static $instance = null;
    private $baseUrl;

    private function __construct() {
        $this->baseUrl = CRAWLER_API_BASE_URL;
    }

    public static function getInstance() {
        if (self::$instance == null) {
            self::$instance = new CrawlerApiService();
        }
        return self::$instance;
    }

    /**
     * Sends a request to the crawler API.
     * @param string $method HTTP method (GET, POST).
     * @param string $endpoint The API endpoint to call.
     * @param array $payload The data to send (for POST requests).
     * @param bool $isDownload Whether to expect a file download.
     * @return array|string The decoded JSON response or file content.
     */
    private function sendRequest($method, $endpoint, $payload = [], $isDownload = false) {
        $url = $this->baseUrl . $endpoint;
        $ch = curl_init();

        if ($method === 'GET' && !empty($payload)) {
            $url .= '?' . http_build_query($payload);
        }

        curl_setopt($ch, CURLOPT_URL, $url);
        curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
        curl_setopt($ch, CURLOPT_TIMEOUT, 300); // 5 minutes timeout for potentially long operations

        if ($method === 'POST') {
            curl_setopt($ch, CURLOPT_POST, true);
            curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($payload));
            curl_setopt($ch, CURLOPT_HTTPHEADER, ['Content-Type: application/json']);
        }

        $response = curl_exec($ch);
        $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);

        if (curl_errno($ch)) {
            // Log cURL error
            error_log("Crawler API cURL Error for {$url}: " . curl_error($ch));
            curl_close($ch);
            return ['success' => false, 'message' => 'Internal cURL error connecting to crawler service.'];
        }

        curl_close($ch);

        if ($isDownload) {
            if ($httpCode >= 200 && $httpCode < 300) {
                return $response;
            } else {
                error_log("Crawler API Download Error {$httpCode} for {$url}: " . $response);
                return false;
            }
        }

        $decodedResponse = json_decode($response, true);
        if ($httpCode >= 200 && $httpCode < 300) {
            return $decodedResponse;
        } else {
            $errorMessage = isset($decodedResponse['detail']) ? $decodedResponse['detail'] : 'Unknown API error.';
            error_log("Crawler API HTTP Error {$httpCode} for {$url}: " . $errorMessage);
            return ['success' => false, 'message' => $errorMessage, 'http_code' => $httpCode];
        }
    }

    public function startCrawl(array $params) {
        return $this->sendRequest('POST', '/crawler/start', $params);
    }

    public function stopCrawl(string $crawl_id) {
        return $this->sendRequest('POST', "/crawler/stop/{$crawl_id}");
    }

    /**
     * Downloads and extracts crawl results to a temporary directory.
     * The caller is responsible for cleaning up this directory.
     *
     * @param string $crawl_id The ID of the crawl job.
     * @param array $include A list of components to include in the archive.
     * @return string|false The path to the temporary directory, or false on failure.
     */
    public function getTemporaryResultsPath(string $crawl_id, array $include) {
        $tempDir = sys_get_temp_dir() . '/crawler_cache/' . uniqid($crawl_id . '_');
        if (!mkdir($tempDir, 0777, true)) {
            error_log("Failed to create temporary directory: {$tempDir}");
            return false;
        }

        $archiveContent = $this->sendRequest('GET', "/crawler/results/{$crawl_id}", ['include' => $include], true);

        if ($archiveContent === false) {
            $this->cleanupTemporaryPath($tempDir);
            return false;
        }

        $tempArchiveFile = $tempDir . '/results.tar.gz';
        file_put_contents($tempArchiveFile, $archiveContent);

        try {
            $phar = new PharData($tempArchiveFile);
            $phar->extractTo($tempDir);
            unlink($tempArchiveFile);
            return $tempDir; // Returns the path to the extracted contents
        } catch (Exception $e) {
            error_log("Failed to extract archive for crawl_id {$crawl_id}: " . $e->getMessage());
            $this->cleanupTemporaryPath($tempDir);
            return false;
        }
    }

    /**
     * Downloads final crawl results and syncs them to the permanent legacy filesystem location.
     *
     * @param string $crawl_id The ID of the crawl job.
     * @param string $domain_name The domain name, used for some sub-folder naming.
     * @return string|false The permanent local path to the results, or false on failure.
     */
    public function syncFinalResults(string $crawl_id, string $domain_name) {
        // Define the permanent storage path using the crawl_id for uniqueness
        $permanentPath = $_SERVER['DOCUMENT_ROOT'] . '/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/tools/crawler/storage/datasets/' . $crawl_id;

        if (is_dir($permanentPath)) {
            // Data is already synced, do nothing.
            return str_replace($_SERVER['DOCUMENT_ROOT'], '', $permanentPath);
        }

        $includeAll = ['dataset', 'dataset_nfr', 'dataset_error', 'request_queues', 'request_urls', 'miscellaneous'];
        $archiveContent = $this->sendRequest('GET', "/crawler/results/{$crawl_id}", ['include' => $includeAll], true);

        if ($archiveContent === false || empty($archiveContent)) {
            error_log("Failed to download final results for crawl_id {$crawl_id}.");
            return false;
        }

        $tempArchiveFile = sys_get_temp_dir() . '/' . $crawl_id . '.tar.gz';
        file_put_contents($tempArchiveFile, $archiveContent);

        try {
            $phar = new PharData($tempArchiveFile);
            // We extract into the permanent path. The archive internally has a 'storage' folder.
            $phar->extractTo($permanentPath);
            unlink($tempArchiveFile);
            
            // The final path used by other scripts is the 'datasets' folder inside the extracted content
            $finalPathForDb = str_replace($_SERVER['DOCUMENT_ROOT'], '', $permanentPath . '/storage/datasets/' . $domain_name);

            // Update database to point to this new permanent location
            sql_update_info(
                ["chemin_crawling_dspi" => $finalPathForDb],
                "domaine_scrapping_produit_ia",
                ["id_domaine_scrapping_produit_ia" => $crawl_id]
            );

            return $finalPathForDb;
        } catch (Exception $e) {
            error_log("Failed to extract final archive for crawl_id {$crawl_id}: " . $e->getMessage());
            @unlink($tempArchiveFile);
            $this->cleanupTemporaryPath($permanentPath); // Clean up partially extracted files
            return false;
        }
    }

    /**
     * Recursively deletes a temporary directory.
     *
     * @param string $path The path to the directory to clean up.
     */
    public function cleanupTemporaryPath(string $path) {
        if (empty($path) || strpos($path, sys_get_temp_dir()) !== 0) {
            // Safety check: only delete directories within the system's temp folder.
            return;
        }

        if (is_dir($path)) {
            $files = new RecursiveIteratorIterator(
                new RecursiveDirectoryIterator($path, RecursiveDirectoryIterator::SKIP_DOTS),
                RecursiveIteratorIterator::CHILD_FIRST
            );
            foreach ($files as $fileinfo) {
                $todo = ($fileinfo->isDir() ? 'rmdir' : 'unlink');
                $todo($fileinfo->getRealPath());
            }
            rmdir($path);
        }
    }
}

/**
 * Helper function to easily access the CrawlerApiService singleton.
 * @return CrawlerApiService
 */
function get_crawler_api_service() {
    return CrawlerApiService::getInstance();
}

// --- END: Crawler Service Migration Code ---


ini_set("memory_limit", -1);
set_time_limit(0);

/**
 * Initialisation des namespaces et des constructeurs
 */

use Abordage\HtmlMin\HtmlMin;
use ImageComparator\ImageComparator;
use Symfony\Component\CssSelector\CssSelectorConverter;

$htmlMinify = new HtmlMin();
$imageComparator = new ImageComparator();
$cssSelectorConverter = new CssSelectorConverter(true);

/**
 * Initialisation HTML Minifier
 */
$htmlMinify->findDoctypeInDocument(false);


/** FONCTION */
/**
 * Insère des informations dans une table de la base de données.
 *
 * @param array $array Un tableau associatif contenant les données à insérer. Les clés du tableau correspondent aux noms des colonnes de la table.
 * @param string $table Le nom de la table dans laquelle insérer les données.
 * @return int|false L'ID de la dernière ligne insérée, ou false si une erreur survient.
 * @global mysqli $LINK_MYSQLI_HELLOPRO_IA La connexion à la base de données.
 */
if (!function_exists('sql_insert_info')) {
    function sql_insert_info(array $array, string $table)
    {
        $fields = "";
        foreach ($array as $key => $value) {
            if ($value === "NOW()") {
                $fields .= " $key= NOW(),";
            } else {
                $fields .= " $key='" . hellopro_traitement_donnee_annuaire_bo($value) . "',";
            }
        }

        $fields = substr($fields, 0, -1);

        $sql_insert_info = "
            INSERT INTO 
                {$table} 
            SET 
                {$fields}
        ";

        $res_insert_info = mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_insert_info) or die(hellopro_mysql_error($sql_insert_info, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));
        return mysqli_insert_id($GLOBALS['LINK_MYSQLI_HELLOPRO_IA']);
    }
}

/**
 * Met à jour des informations dans une table de la base de données.
 *
 * @param array $array Un tableau associatif contenant les données à mettre à jour. Les clés du tableau correspondent aux noms des colonnes de la table.
 * @param string $table Le nom de la table dans laquelle mettre à jour les données.
 * @param array $champ_condition Un tableau associatif contenant les conditions de la clause WHERE. Les clés du tableau correspondent aux noms des colonnes de la table.
 * @return void
 * @global mysqli $LINK_MYSQLI_HELLOPRO_IA La connexion à la base de données.
 */
if (!function_exists('sql_update_info')) {
    function sql_update_info(array $array, string $table, array $champ_condition): void
    {
        $fields = "";
        foreach ($array as $key => $value) {
            if ($value === "NULL") {
                $fields .= " $key= NULL,";
            } 
            else
            {
                $fields .= " $key='" . hellopro_traitement_donnee_annuaire_bo($value) . "',";
            }
        }

        $conditions = "";
        foreach ($champ_condition as $key => $condition) {
            $conditions .= " $key='" . hellopro_traitement_donnee_annuaire_bo($condition) . "' AND";
        }

        $fields = substr($fields, 0, -1);
        $condition = substr($conditions, 0, -3);

        $sql_update_info = "
            UPDATE 
                {$table}
            SET
                {$fields}
            WHERE {$condition}
            LIMIT 1
        ";

        $res_update_info = mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_update_info) or die(hellopro_mysql_error($sql_update_info, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));
    }
}


function ping_bdd_ia() {
    $sql_ping_bdd_ia = "
        SELECT
            id_domaine_scrapping_produit_ia
        FROM
            domaine_scrapping_produit_ia DSPI
        LIMIT
            1
    ";
    $res_ping_bdd_ia = mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_ping_bdd_ia) or die(hellopro_mysql_error($sql_ping_bdd_ia, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));
}


/**
 * Vérifie si une chaîne de caractères ne contient aucun des mots d'une liste donnée.
 *
 * @param string $string La chaîne de caractères à vérifier.
 * @param array $wordList La liste des mots à rechercher.
 * @return bool True si la chaîne ne contient aucun des mots, False sinon.
 */
function stringContainsNoWords(string $string, array $wordList): bool
{
    foreach ($wordList as $word) {
        if (strpos($string, $word) !== false) {
            return false; // Le mot a été trouvé dans la chaîne
        }
    }
    return true; // Aucun mot n'a été trouvé dans la chaîne
}

/**
 * Vérifie si un mot est convertible en ISO-8859-1.
 *
 * @param string $mot Le mot à vérifier.
 * @return bool True si la conversion est possible, False sinon.
 */
function est_convertible_iso(string $mot): bool
{
    // Essayer de convertir le mot en ISO-8859-1
    $mot_converti = mb_convert_encoding($mot, 'ISO-8859-1', 'UTF-8');

    // Reconvertir en UTF-8 pour vérifier l'intégrité
    $mot_reconverti = mb_convert_encoding($mot_converti, 'UTF-8', 'ISO-8859-1');

    // Si le mot d'origine et le mot reconverti sont les mêmes, la conversion est correcte
    return $mot === $mot_reconverti;
}

/**
 * Convertit un texte en ISO-8859-1 s'il n'est pas en UTF-8 valide.
 *
 * @param string $texte Le texte à convertir.
 * @return string Le texte converti en ISO-8859-1 ou le texte d'origine s'il est déjà en UTF-8 valide.
 */
function traitement_d_utf8(string $texte): string
{
    if (!est_convertible_iso($texte)) {
        return $texte;
    }
    // Convertir le texte en UTF-8
    $temp_texte = mb_convert_encoding($texte, 'ISO-8859-1', 'UTF-8');
    if (preg_match('//u', $temp_texte)) {
        return $temp_texte;
    }
    return $texte;
}

/**
 * Extrait le nom de domaine d'une URL.
 *
 * @param string $input L'URL à partir de laquelle extraire le nom de domaine.
 * @return string Le nom de domaine extrait.
 */
function recupere_domaine(string $input): string
{
    $pieces = parse_url($input);
    $domain = isset($pieces['host']) ? $pieces['host'] : array_shift(explode('/', $pieces['path'], 2));
    $domain = preg_replace('/^www\./i', '', $domain);
    return $domain;
}

/**
 * Extrait le nom de domaine non_strict d'une URL.
 *
 * @param string $input L'URL à partir de laquelle extraire le nom de domaine.
 * @return string Le nom de domaine extrait.
 */
function recupere_domaine_n_strict($input )
{
    if(empty($input))
    {
        return "";
    }
    $pieces = parse_url($input);
    $domain = isset($pieces['host']) ? $pieces['host'] : array_shift(explode('/', $pieces['path'], 2));
   
    if(preg_match('/(?P<domain>[a-z0-9][a-z0-9\-]{1,63}\.[a-z\.]{2,6})$/i', $domain, $regs)){
        $domain = $regs['domain'];
    }
    elseif(preg_match('/(?P<domain>[a-z0-9][a-z0-9\-]{1,63}\.[a-z]{2,63})$/i', $domain, $regs))
    {
        $domain = $regs['domain'];
    }
         
    return $domain;
}

/**
 * Récupère le contenu HTML d'une page à l'aide de Crawlee.
 *
 * @param string $url L'URL de la page à scrapper.
 * @return string $content_html Le contenu HTML de la page scrappée.
 */
 function contenu_scrapping_crawlee( $url)
{
    //TODO
    $server_name = $GLOBALS['protocol_http_host_bo'] . "bo.hellopro.fr"; // PROD
    // $server_name = $GLOBALS['protocol_http_host_bo'] . "dev-bo.hellopro.fr"; // DEV

    $domaine = recupere_domaine($url);
    $domain_crawl = $domaine  . "-" . date("YmdHis");

    $test_temp = $_SERVER['DOCUMENT_ROOT'] . 'tmp/identification_prospects_ia_' . $domain_crawl . '.log';
    $command = "cd " . $_SERVER['DOCUMENT_ROOT'] . "tmp/; wget -t 1 '" . $server_name . "/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/tools/scraper/shell.php?domain=".$domain_crawl."&sites=" . $url . "' -a '" . $test_temp . "'";
    $b = shell_exec($command);

    $file_res = $_SERVER["DOCUMENT_ROOT"] . "admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/tools/scraper/storage/key_value_stores/" . $domain_crawl . "/$domain_crawl.json";

    $content = [];
    
    if (file_exists($file_res)) {
        $jsonData = file_get_contents($file_res);
        $tab_content = json_decode($jsonData, true);     
        $content = $tab_content[0];   
    }

    $content_html = isset($content['content']) ? $content['content'] : "";   

    return $content_html;
    
}

/**
 * Récupère les sélecteurs CSS pour un domaine donné.
 *
 * @param string $domaine Le nom de domaine pour lequel récupérer les sélecteurs.
 * @return array Un tableau contenant les sélecteurs CSS pour différents éléments du produit.
 * @global mysqli $LINK_MYSQLI_HELLOPRO_IA La connexion à la base de données.
 */
function get_selecteur_chatgpt(string $domaine): array
{
    $sql_selecteur = "
        SELECT
            id_domaine_scrapping_produit_ia,
            selecteur_titre_dspi,
            selecteur_description_dspi,
            selecteur_prix_dspi,
            selecteur_image_dspi,
            selecteur_categorie_dspi,
            selecteur_livraison_dspi,
            selecteur_stock_dspi,
            selecteur_nok_titre_dspi,
            selecteur_nok_description_dspi,
            selecteur_nok_prix_dspi,
            selecteur_nok_image_dspi,
            selecteur_nok_categorie_dspi,
            selecteur_nok_livraison_dspi,
            selecteur_stock_dspi
        FROM domaine_scrapping_produit_ia 
        WHERE domaine_dspi = '" . hellopro_traitement_donnee_annuaire_bo($domaine) . "'
        LIMIT 1
    ";
    $res_selecteur = mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_selecteur) or die(hellopro_mysql_error($sql_selecteur, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));
    $lig_selecteur = mysqli_fetch_assoc($res_selecteur);

    $titre       = !empty($lig_selecteur['selecteur_titre_dspi']) ? unserialize($lig_selecteur['selecteur_titre_dspi']) : [];
    $description = !empty($lig_selecteur['selecteur_description_dspi']) ? unserialize($lig_selecteur['selecteur_description_dspi']) : [];
    $prix        = !empty($lig_selecteur['selecteur_prix_dspi']) ? unserialize($lig_selecteur['selecteur_prix_dspi']) : [];
    $image       = !empty($lig_selecteur['selecteur_image_dspi']) ? unserialize($lig_selecteur['selecteur_image_dspi']) : [];
    $categorie   = !empty($lig_selecteur['selecteur_categorie_dspi']) ? unserialize($lig_selecteur['selecteur_categorie_dspi']) : [];
    $livraison   = !empty($lig_selecteur['selecteur_livraison_dspi']) ? unserialize($lig_selecteur['selecteur_livraison_dspi']) : [];
    $stock       = !empty($lig_selecteur['selecteur_stock_dspi']) ? unserialize($lig_selecteur['selecteur_stock_dspi']) : [];
    
    $titre_nok       = !empty($lig_selecteur['selecteur_nok_titre_dspi']) ? unserialize($lig_selecteur['selecteur_nok_titre_dspi']) : [];
    $description_nok = !empty($lig_selecteur['selecteur_nok_description_dspi']) ? unserialize($lig_selecteur['selecteur_nok_description_dspi']) : [];
    $prix_nok        = !empty($lig_selecteur['selecteur_nok_prix_dspi']) ? unserialize($lig_selecteur['selecteur_nok_prix_dspi']) : [];
    $image_nok       = !empty($lig_selecteur['selecteur_nok_image_dspi']) ? unserialize($lig_selecteur['selecteur_nok_image_dspi']) : [];
    $categorie_nok   = !empty($lig_selecteur['selecteur_nok_categorie_dspi']) ? unserialize($lig_selecteur['selecteur_nok_categorie_dspi']) : [];
    $livraison_nok   = !empty($lig_selecteur['selecteur_nok_livraison_dspi']) ? unserialize($lig_selecteur['selecteur_nok_livraison_dspi']) : [];
    $stock_nok       = !empty($lig_selecteur['selecteur_nok_stock_dspi']) ? unserialize($lig_selecteur['selecteur_nok_stock_dspi']) : [];


    return [
        "titre"       => $titre,
        "description" => $description,
        "prix"        => $prix,
        "image"       => $image,
        "categorie"   => $categorie,
        "livraison"   => $livraison,
        "stock"       => $stock,
        
        "titre_nok"       => $titre_nok,
        "description_nok" => $description_nok,
        "prix_nok"        => $prix_nok,
        "image_nok"       => $image_nok,
        "categorie_nok"   => $categorie_nok,
        "livraison_nok"   => $livraison_nok,
        "stock_nok"       => $stock_nok
    ];
}

/**
 * Fonction d'historisation des selecteur
 */
function historiser_selecteur($id_scrapping_fiche_produit, $id_domaine_scrapping_produit, $selecteurs)
{
    $champ_historique = [
        "titre"         => "selecteur_titre_hdspi",
        "description"   => "selecteur_description_hdspi",
        "prix"          => "selecteur_prix_hdspi",
        "image"         => "selecteur_image_hdspi",
        "livraison"     => "selecteur_livraison_hdspi",
        "stock"         => "selecteur_stock_hdspi",
        "categorie"     => "selecteur_categorie_hdspi"
    ];

    $info_insert = [];

    $info_insert[] = " id_domaine_scrapping_produit_hdspi = '" . hellopro_traitement_donnee_annuaire_bo($id_domaine_scrapping_produit) . "' ";
    $info_insert[] = " id_scrapping_fiche_produit_hdspi = '" . hellopro_traitement_donnee_annuaire_bo($id_scrapping_fiche_produit) . "' ";

    foreach ($selecteurs as $key_s => $val_s) {
        if (!empty($champ_historique[$key_s])) {
            $info_insert[] = " " . $champ_historique[$key_s] . " = '" . hellopro_traitement_donnee_annuaire_bo(serialize($val_s)) . "' ";
        }
    }

    $sql_historise = "
            INSERT INTO
            historique_domaine_scrapping_produit_ia
        SET
            " . implode(", ", $info_insert) . " ,
            date_creation_hdspi = NOW()
        ON DUPLICATE KEY UPDATE
            " . implode(", ", $info_insert) . " ,
            date_creation_hdspi = NOW()
        ";
    mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_historise) or die(hellopro_mysql_error($sql_historise, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));
}

/**
 * Convertit un sélecteur CSS en une expression XPath.
 *
 * @param string|array $cssSelector Le sélecteur CSS à convertir.
 * @return string L'expression XPath correspondante.
 */
function cssToXPath($cssSelector): string
{
    // Initialisation de la requête XPath
    $tab_xpathQuery = [];

    // Séparation des sélecteurs multiples par des virgules
    // $selectors = explode(',', $cssSelector);
    $selectors = preg_split('/(?<!\\\\)\s*,\s*(?![^[\]]*[\])])/u', $cssSelector);

    $replacements_general = [
        // Sélecteur de classe .className => [contains(concat(" ", normalize-space(@class), " "), " className ")]
        // '/\.([a-zA-Z0-9\-_]+)/' => '[contains(concat(" ", normalize-space(@class), " "), " $1 ")]',

        // Sélecteur d'identifiant #id => [@id="id"]
        // '/#([a-zA-Z0-9\-_]+)/' => '[@id="$1"]',

        // Sélecteur d'attribut [attr] => [@attr]
        '/\[([a-zA-Z0-9\-_]+)\]/' => '[@$1]',

        // Sélecteur d'attribut avec valeur exacte [attr="value"] => [@attr="value"]
        '/\[([a-zA-Z0-9\-_]+)="([^"]+)"\]/' => '[@$1="$2"]',

        // Sélecteur d'attribut avec préfixe [attr^="value"] => [starts-with(@attr, "value")]
        '/\[([a-zA-Z0-9\-_]+)\^="([^"]+)"\]/' => '[starts-with(@$1, "$2")]',

        // Sélecteur d'attribut avec suffixe [attr$="value"] => [ends-with(@attr, "value")] (XPath 2.0 uniquement, sinon via substring)
        '/\[([a-zA-Z0-9\-_]+)\$="([^"]+)"\]/' => '[substring(@$1, string-length(@$1) - string-length("$2") + 1) = "$2"]',

        // Sélecteur d'attribut contenant [attr*="value"] => [contains(@attr, "value")]
        '/\[([a-zA-Z0-9\-_]+)\*="([^"]+)"\]/' => '[contains(@$1, "$2")]',

        // Enfant direct : "parent > child" => "parent/child"
        // '/\s*>\s*/' => '/',

        // Frère suivant immédiat : "element + sibling" => "element/following-sibling::*[1]/self::sibling"
        '/\s*\+\s*/' => '/following-sibling::',

        // Frère suivant général : "element ~ sibling" => "element/following-sibling::sibling"
        '/\s*~\s*/' => '/following-sibling::',

        // Descendants : "ancestor descendant" => "ancestor//descendant"
        // '/\s+/' => '//',

        // Sélecteur universel (tous les éléments) : "*" => "*"
        // '/\*/' => '*',

        // Sélecteur d'élément (tag) : div, p, etc. (reste inchangé)
        // '/([a-zA-Z0-9\-_]+)/' => '$1',

        // Pseudo-classe : :first-child => [position()=1]
        '/:first-child/' => '[position()=1]',

        // Pseudo-classe : :last-child => [position()=last()]
        '/:last-child/' => '[position()=last()]',

        // Pseudo-classe : :nth-child(n) => [position()=n]
        // '/:nth-child\((\d+)\)/' => '[position()=$1]',

        // Pseudo-classe : :nth-of-type(n) => [position()=n] (par type d'élément)
        // '/:nth-of-type\((\d+)\)/' => '[position()=$1]',

        // Pseudo-classe : :not(selector) => ! (non supporté directement en XPath 1.0, complexité supplémentaire nécessaire)
        // '/:not\((.+)\)/' => '[not($1)]',

        // Sélecteur de groupe : sélecteur1, sélecteur2 => //sélecteur1 | //sélecteur2
        // '/,\s*/' => ' | //',
    ];

    // Boucle sur chaque sélecteur pour les convertir
    foreach ($selectors as $selector) {
        $selector = trim($selector);

        //traitement des cas exptionnelle xpath qui n'as pas de version css 
        // ceci ( "all selecteur ")[3]
        $debut_css = $fin_css = "";
        if (preg_match('/^(\()(.*)(\)\[\d+\])$/', $selector, $matches)) {
            $debut_css = $matches[1]; // Contient '('
            $selector = $matches[2];            // Contenu capturé entre parenthèses
            $fin_css = $matches[3]; // Contient ')[3]'

        }

        $sep = "+";
        if (preg_match('/~/', $selector)) $sep = "~";

        $tab_selector = explode($sep, $selector);
        $tab_res = array();

        foreach ($tab_selector as $k => $sel) {
            $sel = trim($sel);
            // Convertir les sélecteurs de ID ,  classes , attrinut [] et nth-child
            $sel = preg_replace_callback('/\s*>\s*/', function () {
                return '/';
            }, $sel);

            $sel = preg_replace('/(?<!\[.)\s+(?![^\[]*\])/', '//', $sel);


            $sel = preg_replace('/(?<!="|\'|:\s|:)\#([\w\-éèàâêîôûäëïöüùç]+(?:\\\.|\\:)*[\w\-éèàâêîôûäëïöüùç]*)/', '[@id="$1"]', $sel);
            $sel = preg_replace('/(?<!\\\)\.([\w\-éèàâêîôûäëïöüùç]+(?:\\\.|\\:)*(?!nth-child|nth-of-type|nth-last-of-type|nth-last-child|first-child|last-child)[\w\-éèàâêîôûäëïöüùç]*)/', '[contains(concat(" ", normalize-space(@class), " "), " $1 ")]', $sel);

            // Convert ID selectors, ignoring digits in id names
            // $selector = preg_replace('/\#([\w\-]+)/', '[translate(@id, "0123456789", "")="$1"]', $selector);

            // Convert class selectors, ignoring digits in class names            
            // $selector = preg_replace('/\.([\w\-]+)/', '[contains(concat(" ", normalize-space(translate(@class, "0123456789", "")), " "), " $1 ")]', $selector);

            // Appliquer les remplacements aux différents cas selon le tableau ci-dessus
            foreach ($replacements_general as $regex_g => $replacement_g) {
                $sel = preg_replace($regex_g, $replacement_g, $sel);
            }

            $sel = preg_replace_callback('/\[([^\]@]+)\]/', function ($matches) {
                $attribute = $matches[1];

                $matche_attr = [];
                if (preg_match('/(.*)\*\s*\=\s*(.*)/', $attribute, $matche_attr)) {
                    $matche_attr[2] = trim($matche_attr[2], "'\"");
                    return "[contains(normalize-space(@" . $matche_attr[1] . "), \"" . $matche_attr[2] . "\")]";
                }

                if (preg_match('/(.*)\^\s*\=\s*(.*)/', $attribute, $matche_attr)) {
                    $matche_attr[2] = trim($matche_attr[2], "'\"");
                    return "[starts-with(@" . $matche_attr[1] . ", \"" . $matche_attr[2] . "\")]";
                }

                if (preg_match('/(.*)\$\s*\=\s*(.*)/', $attribute, $matche_attr)) {
                    $matche_attr[2] = trim($matche_attr[2], "'\"");
                    return "[substring(@" . $matche_attr[1] . ", string-length(@" . $matche_attr[1] . ") - string-length('" . $matche_attr[2] . "') + 1) = '" . $matche_attr[2] . "']";
                } else if (preg_match('/([^\*\s\^\$]+)\s*=\s*(.*)/', $attribute, $matche_attr)) {
                    $matche_attr[2] = trim($matche_attr[2], "'\"");
                    return "[normalize-space(@" . $matche_attr[1] . ")=\"" . $matche_attr[2] . "\"]";
                }
                return '[@' . $attribute . ']';
            }, $sel);

            $sel = preg_replace_callback('/\:(nth-child|nth-of-type)\((\d+)\)/', function ($matches) {
                return '[' . $matches[2] . ']';
            }, $sel);

            $sel = preg_replace_callback('/:nth-last-of-type\((\d+)\)/', function ($matches) {
                $n = (int)$matches[1];
                return "[position() = last() - " . ($n - 1) . "]";
            }, $sel);

            $sel = preg_replace_callback('/:nth-last-child\((\d+)\)/', function ($matches) {

                $n = (int)$matches[1];
                return "[(count(following-sibling::*) = " . ($n - 1) . ")]";
            }, $sel);

            if ($k != 0) {
                if (preg_match('/^[^\w]/i', $sel)) {
                    $sel = "*" . $sel;
                }
            }
            $tab_res[] = $sel;
        }

        $selector = implode('/following-sibling::', $tab_res);
        $tab_xpathQuery[] = $debut_css . '//' . $selector . $fin_css;
    }

    $xpathQuery = implode(' | ', $tab_xpathQuery);

    $patterns = ['/\/\[contains/', '/\/\[@id/', '/\/\[/'];
    $replacements = ['/*[contains', '/*[@id', '/*['];

    // Utiliser preg_replace pour effectuer les substitutions
    $xpathQuery = preg_replace($patterns, $replacements, $xpathQuery);
    $xpathQuery = str_replace("\\", "", $xpathQuery);

    return $xpathQuery;
}

/**
 * Encode une URL complète en utilisant des expressions régulières pour remplacer les caractères spéciaux.
 *
 * @param string $url L'URL à encoder.
 * @return string L'URL encodée.
 */
function encodeFullUrlWithPreg(string $url): string
{
    // Liste des remplacements des caractères spéciaux avec leur encodage
    $patterns = [
        '/\s/',  // espace
        '/"/',  // "
        '/</',  // <
        '/>/',  // >
        '/\[/',  // [
        // '/\\/',  // \
        '/\]/',  // ]
        '/\^/',  // ^
        '/`/',  // `
        '/\{/',  // {
        '/\|/',  // |
        '/\}/',  // }
        '/~/'     // ~
    ];
    $replacements = [
        '%20',  // espace
        '%22',  // "
        '%3C',  // <
        '%3E',  // >
        '%5B',  // [
        // '%5C',  // \
        '%5D',  // ]
        '%5E',  // ^
        '%60',  // `
        '%7B',  // {
        '%7C',  // |
        '%7D',  // }
        '%7E'   // ~
    ];
    $url = preg_replace($patterns, $replacements, $url) ?: $url;

    return $url;
}

/**
 * Vérifie si une URL est accessible et correspond au type attendu (image ou page HTML).
 *
 * @param string|null $url L'URL à vérifier.
 * @param bool $returnContent Indique si le contenu de l'URL doit être retourné.
 * @param bool $pageProduit Indique si l'URL doit être vérifiée comme une page produit et non une image.
 * @return bool|array Retourne true si l'URL est accessible et correspond au type attendu, false sinon.
 *                     Si $returnContent est true, retourne un tableau contenant le status et le contenu.
 */
function isUrlAccessible(?string $url, bool $returnContent = false, bool $pageProduit = false)
{
    if (!empty($url)) {
        $maxRetryCount = 5;
        $retryCount = 0;
        $last_http_code = $last_error = "";
        $acceptEncoding = ($pageProduit) ? 'gzip, deflate, br, zstd' : 'gzip, deflate';

        if($pageProduit)
        {
            //verification si c'est déjà dans le global
            if (isset($GLOBALS["pageProduit"][$url])) {
                return $GLOBALS["pageProduit"][$url];
            }

            //verification si c'est direct un url image
            if( preg_match('/\.(jpg|jpeg|png|gif|webp)(\?.*)?$/i', $url)) {
                $GLOBALS["pageProduit"][$url] = false;
                return false;
            }
            //verification si c'est direct un url html avec paramètre ou seulement .php
            if (preg_match('/\.(html|htm)(\?.*)?$/i', $url) || preg_match('/\.php$/i', $url)) {
                $GLOBALS["pageProduit"][$url] = true;
                return true;
            }
        }

        if(!empty($GLOBALS["urlContent"][$url]) && !$pageProduit) {
            if ($returnContent) {
                return [
                    "status" => true,
                    "content" => $GLOBALS["urlContent"][$url]
                ];
            }
            return true;
        }

        while ($retryCount <= $maxRetryCount) {
            $retryCount++;
            $url_in_curl = $retryCount > 1 && $last_http_code == 0 ? encodeFullUrlWithPreg($url) : $url;
            $acceptEncoding = $retryCount > 1 ? 'gzip, deflate, br, zstd' : $acceptEncoding;
            $ch = curl_init();
            $options = [
                CURLOPT_URL            => $url_in_curl,
                CURLOPT_FOLLOWLOCATION => true,
                CURLOPT_RETURNTRANSFER => true,
                CURLOPT_CUSTOMREQUEST  => 'GET',
                CURLOPT_HTTP_VERSION   => CURL_HTTP_VERSION_1_1,
                CURLOPT_HTTPHEADER     => [
                    "Accept: */*",
                    "Accept-Encoding: {$acceptEncoding}",
                    "Cache-Control: no-cache",
                    "Connection: keep-alive",
                    "Sec-Fetch-Site: none",
                    "Sec-Fetch-User: ?1",
                    "Priority: u=0, i",
                    "Pragma: no-cache",
                    "user-agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
                ]
            ];

            if ($pageProduit) $options[CURLOPT_NOBODY] = true;

            if ($retryCount > 1 && stripos($last_error, "SSL certificate") !== false) {
                $options[CURLOPT_SSL_VERIFYPEER] = false;
                $options[CURLOPT_SSL_VERIFYHOST] = 0;
            }

            curl_setopt_array($ch, $options);
            $content = curl_exec($ch);

            $last_http_code = $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
            $contentType = curl_getinfo($ch, CURLINFO_CONTENT_TYPE);

            if (curl_errno($ch)) {
                $last_error =  curl_error($ch);
            }

            curl_close($ch);

            // Dans le cas $pageProduit = true, vérifier si l'URL est une page
            if ($pageProduit) {
                $isPageProduit = (strpos($contentType, 'text/html') === 0);
                $GLOBALS["pageProduit"][$url] = $isPageProduit;
                return $isPageProduit;
            }


            // Vérifier si le code HTTP est 200 (OK) et si le content type est application/octet-stream ou binary/octet-stream
            if ($httpCode == 200 && in_array($contentType, ['application/octet-stream', 'binary/octet-stream']) && !empty($content)) {
                $finfo = new finfo(FILEINFO_MIME_TYPE);
                $mime_type = $finfo->buffer($content);

                if (!preg_match("/(image|jpg|jpeg|png|gif|webp)/i", $mime_type)) {
                    return false;
                }

                $GLOBALS["urlContent"][$url] = $content;

                if ($returnContent) {
                    return [
                        "status" => true,
                        "content" => $content
                    ];
                }
                return true;
            }


            // Vérifier si le code HTTP est 200 (OK) et si le contenu est une image
            if ($httpCode == 200 && (strpos($contentType, 'image/') === 0 || (empty($contentType) && !empty($content)))) {
                $GLOBALS["urlContent"][$url] = $content;

                if ($returnContent) {
                    return [
                        "status"  => true,
                        "content" => $content
                    ];
                }

                return true;
            }

            if (!in_array($httpCode, [0, 429])) break;

            // Gestion des cas de Too Many Requests 429
            if ($httpCode == 429) {
                sleep(10);
            }
        }
    }

    // Retourne false si ce n'est pas une image ou si l'URL n'est pas accessible
    return false;
}

/**
 * Vérifie et récupère une version plus grande de l'image si parmi les patterns établis pour différents CMS.
 *
 * @param string $url L'URL de l'image.
 * @param array $allUrl Un tableau contenant tous les urls images
 * @param array $urlOk Un tableau contenant les URLs d'images déjà validées.
 * @param array $magentoDirectories Un tableau pour contenir les noms des dossiers pour Magento
 * @return string L'URL de l'image récupérée.
 */
function getLargerImages(string $url, array $allUrl, array $urlOk = [], array &$magentoDirectories = []): string
{
    global $imageComparator;
    $isPrestashop = $isWordpress = $isEpages = $isDrupal = $isSylius = $isShopify = $isMagento = $isWixBuilder = $isJoomla = false;

    $detectCmsType = detectCmsType($url);
    $cmsName = $detectCmsType['name'];
    $keywords = $detectCmsType['keywords'];
    $matches = $detectCmsType['matches'];

    if (!empty($cmsName)) {
        $variableName = "is{$cmsName}";
        $$variableName = true;
    }

    if ($isPrestashop) {
        $ID = $matches[1];
        $fullMatches = $matches[0];
        $urlBase = str_replace($fullMatches, $ID, $url);
        if (isUrlAccessible($urlBase)) return $urlBase;

        foreach ($keywords as $pattern => $replacement) {
            $replacementWord = "{$ID}{$matches[2]}{$matches[3]}{$replacement}{$matches[4]}";
            $newUrl = str_replace($fullMatches, $replacementWord, $url);

            if (in_array($newUrl, $urlOk) || isUrlAccessible($newUrl)) {
                return $newUrl;
            }
        }
    }

    if ($isSylius) {
        foreach ($keywords as $replacementWord) {
            $newUrl = str_replace($matches, $replacementWord, $url);

            if (in_array($newUrl, $urlOk) || isUrlAccessible($newUrl)) {
                return $newUrl;
            }
        }
    }

    if ($isWordpress) {
        if (!preg_match('/(.*)(-\d+x\d+)(\..*)/', $url, $matches)) {
            return $url;
        }
        $newUrl = $matches[1] . $matches[3];
        if (in_array($newUrl, $urlOk) || isUrlAccessible($newUrl)) {
            return $newUrl;
        }
    }

    if ($isEpages) {
        $pattern = '/(.*)_(\w{1,})(\..*)/';
        $urlBase = preg_replace($pattern, '$1$3', $url);
        if (isUrlAccessible($urlBase)) {
            return $urlBase;
        }

        $replacement = '$1_X$3';
        foreach ($keywords as $replacementWord) {
            $tempReplacement = str_replace('X', $replacementWord, $replacement);
            $newUrl = preg_replace($pattern, $tempReplacement, $url);
            if (in_array($newUrl, $urlOk) || isUrlAccessible($newUrl)) {
                return $newUrl;
            }
        }
    }

    if ($isDrupal) {
        $pattern = '/(\/sites\/.*\/files)(.*)(\/.*)(\..*)/';
        $urlBase = preg_replace($pattern, '$1$3$4', $url);
        if (isUrlAccessible($urlBase)) {
            return $urlBase;
        }

        $replacement = '$1/styles/X/public$3$4';
        foreach ($keywords as $replacementWord) {
            $tempReplacement = str_replace('X', $replacementWord, $replacement);
            $newUrl = preg_replace($pattern, $tempReplacement, $url);
            if (
                (
                    (
                        isset($GLOBALS['urlContent'][$newUrl])
                        && !empty($GLOBALS['urlContent'][$newUrl])
                    ) || isUrlAccessible($newUrl)
                ) && compareImageSizes($url, $newUrl) === $newUrl
            ) {
                return $newUrl;
            }
        }
    }

    if ($isShopify) {
        $newUrl = preg_replace('/(.*)(_.*)(\..*)/', '$1$3', $url);
        if (isUrlAccessible($newUrl)) {
            return $newUrl;
        }
    }

    if ($isMagento) {
        $pattern = '/(\/media\/)(import|catalog\/product)(\/.*)([a-f0-9]{32})/';
        $patternSize = '/(\d+x)/';
        $isMatched = preg_match($pattern, $url, $matches);

        if ($isMatched) {
            $urlBase = preg_replace($pattern, '$1$2$3$7', $url);

            if (isUrlAccessible($urlBase)) {
                if (isImagesSimilars($imageComparator, $url, $urlBase)) {
                    return $urlBase;
                }
            }

            $containSize = preg_match($patternSize, $matches[5], $matchesSize);
            $cacheFolder = $matches[6];

            if ($containSize) {
                $cacheFolder = "{$matchesSize[1]}/{$cacheFolder}";
            }

            if (empty($magentoDirectories)) {
                foreach ($allUrl as $currentUrl) {
                    $isMatchedCurrentURL = preg_match($pattern, $currentUrl, $matchesCurrentURL);

                    if ($isMatchedCurrentURL) {
                        $containSizeCurrentURL = preg_match($patternSize, $matchesCurrentURL[5], $matchesSizeCurrentURL);
                        $cacheFolderCurrentURL = $matchesCurrentURL[6];

                        if ($containSizeCurrentURL) {
                            $cacheFolderCurrentURL = "{$matchesSizeCurrentURL[1]}/{$cacheFolderCurrentURL}";
                        }

                        if (!in_array($cacheFolderCurrentURL, $magentoDirectories)) {
                            $urlContent = $GLOBALS['urlContent'][$currentUrl] ?? isUrlAccessible($currentUrl, true)['content'];

                            if ($urlContent !== false) {
                                $urlSize = getImageSizeWidthHeight($urlContent);
                                if ($urlSize !== false) $magentoDirectories[$cacheFolderCurrentURL] = $urlSize[0] * $urlSize[1];
                            }
                        }
                    }
                }

                array_multisort($magentoDirectories, SORT_DESC, SORT_NUMERIC);
            } else {
                foreach ($magentoDirectories as $directory) {
                    $newUrl = str_replace($cacheFolder, $directory, $url);

                    if (in_array($newUrl, $urlOk) || isUrlAccessible($newUrl)) {
                        return $newUrl;
                    }
                }
            }
        } else {
            // Voir si des paramètres sont contenus dans l'URL
            $query = parse_url($url, PHP_URL_QUERY);

            if (!empty($query)) {
                $urlBase = str_replace("?{$query}", '', $url);

                if (isUrlAccessible($urlBase)) {
                    return $urlBase;
                }
            }
        }
    }

    if ($isWixBuilder) {
        $fullMatches = $matches[0];
        $firstPart = $matches[1];
        $secondPart = $matches[2];

        $urlBase = str_replace($secondPart, '', $url);
        if (isUrlAccessible($urlBase)) {
            return $urlBase;
        }

        $secondPattern = [
            "width" => "/(v1\/fill\/.*)(w\_\d+)(.*mv2\..*)/",
            "height" => "/(v1\/fill\/.*)(h\_\d+)(.*mv2\..*)/"
        ];

        foreach ($keywords as $dimension) {
            $newUrl = $url;

            foreach ($dimension as $typeD => $valueD) {
                $Xreplacement = $typeD == "width" ? "w" : "h";
                $Xreplacement .= "_" . $valueD;
                $newUrl = preg_replace($secondPattern[$typeD], '$1' . $Xreplacement . '$3', $newUrl);
            }

            if (isUrlAccessible($newUrl)) {
                return $newUrl;
            }
        }
    }

    if ($isJoomla) {
        $urlBase = preg_replace($keywords['regex'], $keywords['original'], $url);
        if (isUrlAccessible($urlBase)) return $urlBase;

        foreach ($keywords['size'] as $size) {
            $tempLarge = $keywords['large'];
            $newUrl = $url;
            $tempReplacement = str_replace(['{WIDTH}', '{HEIGTH}'], $size, $tempLarge);
            $newUrl = preg_replace($keywords['regex'], $tempReplacement, $newUrl);
            if (in_array($newUrl, $urlOk) || isUrlAccessible($newUrl)) {
                return $newUrl;
            }
        }
    }

    $pattern = findMatchingPattern($url);

    if ($pattern) return processUrlWithPattern($url, $pattern, $urlOk);

    return $url;
}

/**
 * Détermine le type de CMS (Content Management System) utilisé par un site web en fonction de l'URL fournie.
 *
 * @param string $url L'URL du site web à analyser.
 * @return array Un tableau contenant les informations sur le CMS détecté, notamment son nom et les mots-clés associés.
 */
function detectCmsType($url): array
{
    // Définition des constantes pour les mots-clés et les modèles de recherche pour chaque CMS
    if (!defined('WORDPRESS_KEYWORD')) {
        define('WORDPRESS_KEYWORD', 'wp-content'); // Mot-clé pour détecter WordPress
    }
    if (!defined('SHOPIFY_KEYWORD')) {
        define('SHOPIFY_KEYWORD', 'cdn/shop/products'); // Mot-clé pour détecter Shopify
    }
    if (!defined('DRUPAL_KEYWORDS')) {
        define('DRUPAL_KEYWORDS', [
            'xl_1920w',
            'xl_1200w',
            'large',
            'medium',
            'thumbnail'
        ]); // Mots-clés associés à Drupal
    }

    if (!defined('PRESTASHOP_KEYWORDS')) {
        define('PRESTASHOP_KEYWORDS', [
            '/(\d+)(-)(.*)?thickbox(_default)?(?!$)(\d+[A-Za-z]{1,4})?/' => 'thickbox', // Modèle de recherche pour Prestashop
            '/(\d+)(-)(.*)?large(_default)?(?!$)(\d+[A-Za-z]{1,4})?/' => 'large',
            '/(\d+)(-)(.*)?pdt_540(?!$)(\d+[A-Za-z]{1,4})?/' => 'pdt_540',
            '/(\d+)(-)(.*)?medium(_default)?(?!$|Gallery)(\d+[A-Za-z]{1,4})?/' => 'medium',
            '/(\d+)(-)(.*)?pdt_360(?!$)(\d+[A-Za-z]{1,4})?/' => 'pdt_360',
            '/(\d+)(-)(.*)?pdt_300(?!$)(\d+[A-Za-z]{1,4})?/' => 'pdt_300',
            '/(\d+)(-)(.*)?home(_default)?(?!$)(\d+[A-Za-z]{1,4})?/' => 'home',
            '/(\d+)(-)(.*)?pdt_180(?!$)(\d+[A-Za-z]{1,4})?/' => 'pdt_180',
            '/(\d+)(-)(.*)?cart(_default)?(?!$)(\d+[A-Za-z]{1,4})?/' => 'cart',
            '/(\d+)(-)(.*)?small(_default)?(?!$)(\d+[A-Za-z]{1,4})?/' => 'small',
        ]);
    }

    if (!defined('SYLIUS_KEYWORDS')) {
        define('SYLIUS_KEYWORDS', [
            "sylius_shop_product_original", // Mots-clés associés à Sylius
            "sylius_shop_product_xlarge_thumbnail",
            "sylius_admin_product_original",
            "sylius_large",
            "sylius_shop_product_large_thumbnail",
            "sylius_admin_product_large_thumbnail",
            "sylius_product_large_thumbnail",
            "is_sylius_product_vertical_list",
            "sylius_medium",
            "sylius_shop_product_thumbnail",
            "sylius_admin_product_small_thumbnail",
            "is_sylius_shop_product_main_box",
            "is_sylius_shop_product_main_box_retina",
            "sylius_shop_product_small_thumbnail",
            "sylius_small",
            "sylius_admin_product_tiny_thumbnail",
            "sylius_shop_product_tiny_thumbnail",
            "sylius_admin_product_thumbnail",
            "sylius_admin_admin_user_avatar_thumbnail"
        ]);
    }

    if (!defined('EPAGES_PATTERN')) {
        define('EPAGES_PATTERN', '/\/WebRoot\/.*\/Shops\//'); // Modèle de recherche pour Epages
    }
    if (!defined('EPAGES_KEYWORDS')) {
        define('EPAGES_KEYWORDS', ['ml', 'm', 'ms']); // Mots-clés associés à Epages
    }

    if (!defined('MAGENTO_PATTERN')) {
        define('MAGENTO_PATTERN', '/media\/(import|catalog\/product)/'); // Modèle de recherche pour Magento
    }
    if (!defined('DRUPAL_PATTERN')) {
        define('DRUPAL_PATTERN', '/(\/sites\/.*\/files)(.*)(\/.*)(\..*)/'); // Modèle de recherche pour Drupal
    }

    if (!defined('WIX_BUILDER')) {
        define('WIX_BUILDER', '/(\/media\/(?:.+)mv2\.[A-Za-z]{3,4})(\/v1\/fill\/(?:.+)mv2\.[A-Za-z]{3,4}(?:.*))/'); // Modèle de recherche pour Wix Website Builder
    }

    // Modèle de recherche pour Joomla : HikaShop , VirtueMart, J2Store , Eshop ,  Phoca Cart , MijoShop
    if (!defined('JOOMLA')) {
        define('JOOMLA', [
            // HikaShop
            'hikashop' => [
                'regex' => '#/media/com_hikashop/upload/thumbnails/\d+x\d+f/(.+)$#',
                'original' => '/media/com_hikashop/upload/$1',
                'large' => '/media/com_hikashop/upload/thumbnails/{WIDTH}x{HEIGTH}f/$1'
            ],
            // VirtueMart
            'virtuemart' => [
                'regex' => '#/images/stories/virtuemart/product/resized/(.+)([\-\_])\d+x\d+(.+)$#',
                'original' => '/images/stories/virtuemart/product/$1$3',
                'large' => '/images/stories/virtuemart/product/resized/${1}${2}{WIDTH}x{HEIGTH}${3}'
            ],
            // J2Store
            'j2store' => [
                'regex' => '#/media/j2store/images/\d+/thumbs/(.+)([\-\_])\d+x\d+(.+)$#',
                'original' => '/media/j2store/images/$1$3',
                'large' => '/media/j2store/images/thumbs/${1}${2}{WIDTH}x{HEIGTH}${3}'
            ],
            // Eshop
            'eshop' => [
                'regex' => '#/media/com_eshop/products/thumbs/(.+)([\-\_])\d+x\d+(.+)$#',
                'original' => '/media/com_eshop/products/$1$3',
                'large' => '/media/com_eshop/products/thumbs/${1}${2}{WIDTH}x{HEIGTH}${3}'
            ],
            // Phoca Cart
            'phocacart' => [
                'regex' => '#/images/phocacart/thumbs/(?:small|medium|large)/(.+)$#',
                'original' => '/images/phocacart/$1',
                'large' => '/images/phocacart/thumbs/large/$1'
            ],
            // MijoShop
            'mijoshop' => [
                'regex' => '#/image/cache/catalog/(.+)([\-\_])\d+x\d+(.+)$#',
                'original' => '/image/catalog/$1$3',
                'large' => '/image/cache/catalog/${1}${2}{WIDTH}x{HEIGTH}${3}'
            ]
        ]);
    }

    // Recherche de mots-clés dans l'URL pour détecter le CMS
    if (strpos($url, WORDPRESS_KEYWORD) !== false) {
        // Si le mot-clé WordPress est trouvé, retourne un tableau avec le nom du CMS et un tableau vide de mots-clés
        return ['name' => 'WordPress', 'keywords' => []];
    }

    if (preg_match(DRUPAL_PATTERN, $url)) {
        // Si un modèle de recherche Drupal est trouvé, retourne un tableau avec le nom du CMS et les mots-clés associés
        return ['name' => 'Drupal', 'keywords' => DRUPAL_KEYWORDS];
    }

    if (strpos($url, SHOPIFY_KEYWORD) !== false) {
        // Si le mot-clé Shopify est trouvé, retourne un tableau avec le nom du CMS et un tableau vide de mots-clés
        return ['name' => 'Shopify', 'keywords' => []];
    }

    foreach (PRESTASHOP_KEYWORDS as $pattern => $replacement) {
        // Si un modèle de recherche Prestashop est trouvé, retourne un tableau avec le nom du CMS, un tableau des mots-clés associés et un tableau des données matchés
        if (preg_match($pattern, $url, $matches)) return ['name' => 'Prestashop', 'keywords' => PRESTASHOP_KEYWORDS, 'matches' => $matches];
    }

    foreach (SYLIUS_KEYWORDS as $keyword) {
        // Si un modèle de recherche Sylius est trouvé, retourne un tableau avec le nom du CMS, un tableau des mots-clés associés et le mot matché
        if (strpos($url, $keyword) !== false) return ['name' => 'Sylius', 'keywords' => SYLIUS_KEYWORDS, 'matches' => $keyword];
    }

    if (preg_match(EPAGES_PATTERN, $url)) {
        // Si un modèle de recherche Epages est trouvé, retourne un tableau avec le nom du CMS et les mots-clés associés
        return ['name' => 'Epages', 'keywords' => EPAGES_KEYWORDS];
    }

    if (preg_match(MAGENTO_PATTERN, $url)) {
        // Si un modèle de recherche Magento est trouvé, retourne un tableau avec le nom du CMS et un tableau vide de mots-clés
        return ['name' => 'Magento', 'keywords' => []];
    }

    if (preg_match(WIX_BUILDER, $url, $matches)) {
        // Si un modèle de recherche Wix Website Builder est trouvé, retourne un tableau avec le nom du CMS et un tableau vide de mots-clés
        //liste de dimension qu'on veut prendre, peut être alimenté à l'avenir
        $keyword = [
            ["width" => 980, "height" => 829],
            ["width" => 735, "height" => 551],
            ["width" => 569, "height" => 554]
        ];
        return ['name' => 'WixBuilder', 'keywords' => $keyword, 'matches' => $matches];
    }

    foreach (JOOMLA as  $shop => $config) {
        // Si un modèle de recherche Joomla est trouvé, retourne un tableau avec le nom du CMS, un tableau des mots-clés associés et un tableau des données matchés
        //liste de dimension qu'on veut prendre, peut être alimenté à l'avenir
        $config["size"] = [800, 600, 300, 200];
        if (preg_match($config['regex'], $url)) return ['name' => 'Joomla', 'keywords' => $config];
    }

    // Si aucun CMS n'est détecté, retourne un tableau vide
    return [];
}

/**
 * Vérifie si une chaîne est une URL valide ou un chemin relatif.
 *
 * @param string $string La chaîne à vérifier.
 * @return bool True si la chaîne est une URL valide ou un chemin relatif, false sinon.
 */
function isValidURLorRelativePath(string $string): bool
{
    // Vérifie si c'est une URL valide
    if (filter_var($string, FILTER_VALIDATE_URL)) {
        return true;
    }

    // Vérifie si c'est une URL valide : pour ceux qui ont des caracatére speciaux : exemple : é è à
    $reg_url = '/^(\/\/|www.|http:\/\/|https:\/\/|ftp:\/\/|){1}[^\x00-\x19\x22-\x27\x2A-\x2C\x2E-\x2F\x3A-\x40\x5B-\x5E\x60\x7B\x7D-\x7F]+(\.[^\x00-\x19\x22\x24-\x2C\x2E-\x2F\x3C\x3E\x40\x5B-\x5E\x60\x7B\x7D-\x7F]+)+(\/[^\x00-\x19\x22\x3C\x3E\x5E\x7B\x7D-\x7D\x7F]*)*$/';
    if (preg_match($reg_url, $string)) {
        return true;
    }

    // Expression régulière pour les chemins relatifs
    $relativePathPattern = '/^(?!https:\/\/|http:\/\/|ftp:\/\/|:\/\/|\/\/)(\.\.\/|\.\/|\/)*[\p{L}\p{N}\w\-\/%&=: \s]+(\/.[\p{L}\p{N}\w\-\/%&=: \s]+)(\.[\w]+)?(\?[^\s]*)?/';

    if (preg_match($relativePathPattern, $string)) {
        return true;
    }

    return false;
}

/**
 * Filtre les URLs d'images d'un produit en supprimant les logos et les images trop petites.
 *
 * @param array $array Un tableau contenant les URLs d'images à filtrer.
 * @param string $url L'URL de la page du produit.
 * @param bool $skipped Indique si le filtrage dedoublonnage doit être ignoré, defaut à false.
 * @return array Un tableau contenant les URLs d'images filtrées.
 * @global ImageComparator $imageComparator L'instance de la classe ImageComparator pour comparer les images.
 * @global resource $handle_trace Le handle du fichier de suivi.
 */
function filter_images_produit(array $array, string $url , bool $skipped = false): array
{
    global $imageComparator;
    global $handle_trace;

    if (empty($array)) return $array;
    $array = array_unique($array);
    // Utiliser array_filter pour filtrer le tableau
    // $keywords = ['logo', 'vignette' , 'thumbnail'];
    $keywords = [ '/^data:image\//i'];
    $keywords_name = ['/[\W\_]logo[\W\_]/i'];
    $array = array_map('traitement_d_utf8', array_unique(array_filter($array)));

    $array_filtrer = array_filter($array, function ($item) use ($keywords , $keywords_name) {
        foreach ($keywords as $keyword) {  
            if (preg_match($keyword, $item)) { // Vérifie si le mot-clé est dans la chaîne (insensible à la casse)
                return false; // Retire l'élément s'il contient le mot-clé
            }
        }

        //test sur le nom du fichier
        $path = parse_url($item, PHP_URL_PATH);
        $basename = basename($path);
        foreach ($keywords_name as $keyword_name) {
            if (preg_match($keyword_name, $basename)) { // Vérifie si le mot-clé est dans le nim du fichier (insensible à la casse)
                return false; // Retire l'élément s'il contient le mot-clé
            }
        }
        
        return true; // Garde l'élément s'il ne contient aucun des mots-clés
    });

    $finalUrls = [];
    $relativePathPattern = '/^(?!https:\/\/|http:\/\/|ftp:\/\/|:\/\/|\/\/)(\.\.\/|\.\/|\/)*[\p{L}\p{N}\w\-\/%&=: \s]+(\/.[\p{L}\p{N}\w\-\/%&=: \s]+)(\.[\w]+)?(\?[^\s]*)?/';
    $info_url = parse_url($url);

    // Récupération de tous les URLs images
    $allUrls = [];
    foreach ($array_filtrer as $url_filtrer) {
        //toute les lien url relatif mais qui ne commence pas par // qui est un lien absolut sans https
        if (preg_match($relativePathPattern, $url_filtrer) && !preg_match("/^(\/\/)/", $url_filtrer) && !empty($info_url['host'])) {
            $before_url_filtrer = $url_filtrer;
            $url_filtrer = $info_url['scheme'] . "://" . $info_url['host'] . "/" . ltrim($before_url_filtrer, './');
            $allUrls[] = $url_filtrer;

            //pour les chemin relatif qui ne commence pas par un . ou /
            if (preg_match('/^[^\.\/]/', $before_url_filtrer)) {
                $directory = dirname($info_url['path']);
                $url_secondaire = $info_url['scheme'] . "://" . $info_url['host'] . $directory . "/" . ltrim($before_url_filtrer, './');
                $allUrls[] = $url_secondaire;
            } //pour les chemin relatif qui commence par ../
            elseif (preg_match('/^(\.\.\/)/', $before_url_filtrer)) {
                $directory = dirname($info_url['path']);
                $segments = explode('/', trim($directory, "/"));

                $matches_pa = [];
                preg_match_all('/^(?:\.\.\/)*/', $before_url_filtrer, $matches_pa);
                $count = substr_count($matches_pa[0][0], '../');

                $finalPath = array_slice($segments, 0, count($segments) - $count);
                $finalPathString = implode('/', $finalPath);
                if (!empty($finalPathString)) $finalPathString = "/" . $finalPathString;

                $url_tertiaire = $info_url['scheme'] . "://" . $info_url['host'] . $finalPathString . "/" . ltrim($before_url_filtrer, './');
                $allUrls[] = $url_tertiaire;
            }
        } elseif (!preg_match("/^(http:\/\/|https:\/\/|ftp:\/\/)/", $url_filtrer)) {
            $url_filtrer = $info_url['scheme'] . "://" . ltrim($url_filtrer, ':/');
            $allUrls[] = $url_filtrer;
        } else {
            $allUrls[] = $url_filtrer;
        }
    }

    $allUrls = array_unique($allUrls);

    // Dans le cas où on est sur du Magento
    $magentoDirectories = [];

    // Récupération des versions grandes des images
    if($skipped) {
        fwrite($handle_trace, "--- Pas de détéction des image grandes ---\n");
        $finalUrls = $allUrls;
    }
    else{
        foreach ($allUrls as $currentUrl) {
            $finalUrls[] = getLargerImages($currentUrl, $allUrls, $finalUrls, $magentoDirectories);
        }
    }       
    

    $finalUrls = array_unique($finalUrls);

    fwrite($handle_trace, "--- URLs Images apres nettoyage des chemins relatifs ---\n");
    fwrite($handle_trace, print_r($finalUrls, true) . "\n\n");

    // Faire une vérification des URLs uniques si est disponible
    foreach ($finalUrls as $key => $finalUrl) {
        if (!isset($GLOBALS['urlContent'][$finalUrl]) && !isUrlAccessible($finalUrl)) unset($finalUrls[$key]);
    }
    $finalUrls = array_values($finalUrls);

    fwrite($handle_trace, "--- URLs Images apres verification d'accessibilite ---\n");
    fwrite($handle_trace, print_r($finalUrls, true) . "\n\n");

    if($skipped) {
        fwrite($handle_trace, "--- Pas de dedoublonnage d'image par md5 et par pixel , pas de filtrage des images de dimension inferieur---\n");
    }
    else{

        $finalUrls = array_values(deduplicateImages($finalUrls));
        // $finalUrls = array_values(deduplicateImageUrls($finalUrls));
    
        fwrite($handle_trace, "--- URLs Images apres deduplication ---\n");
        fwrite($handle_trace, print_r($finalUrls, true) . "\n\n");
    
        for ($index = 0; $index < count($finalUrls); $index++) {
            if (!isset($finalUrls[$index])) continue;
            $currentUrl = $finalUrls[$index];
            $largestUrl = $currentUrl;
    
            for ($i = $index + 1; $i < count($finalUrls); $i++) {
                if (!isset($finalUrls[$i])) continue;
                $toCompare = $finalUrls[$i];
    
                # Pour éviter l'erreur "Mysql has gone away" s'il y a beaucoup d'images à traiter 
                ping_bdd_ia();
    
                $isSimilar = isImagesSimilars($imageComparator, $currentUrl, $toCompare);
    
                if ($isSimilar) {
                    $largerImage = compareImageSizes($largestUrl, $toCompare);
    
                    if ($largerImage === $toCompare) {
                        $largestUrl = $toCompare;
                    }
    
                    // Marquer l'URL à supprimer
                    $finalUrls[$i] = null;
                }
            }
    
            // Remplacer l'URL actuelle par la plus grande trouvée
            $finalUrls[$index] = $largestUrl;
        }

        // Supprimer les URLs nulles et réindexer
        $finalUrls = array_values(array_filter($finalUrls));

        fwrite($handle_trace, "--- URLs Images apres ImageComparator ---\n");
        fwrite($handle_trace, print_r($finalUrls, true) . "\n\n");

        //enlever les images de dimension inferieur à 200x200 ou 90x90
        if (count($finalUrls) > 0) {
            $finalUrls_temp = array_values(filterImagesBySize($finalUrls, 200, 200));

            // Si on n'a plus d'image après le filtrage par la dimension on réduit à 90x90
            if (count($finalUrls_temp) == 0) {
                $finalUrls = array_values(filterImagesBySize($finalUrls, 90, 90));
            } else {
                $finalUrls = $finalUrls_temp;
            }
        }

    }
    
    fwrite($handle_trace, "--- URLs Images finales ---\n");
    fwrite($handle_trace, print_r($finalUrls, true) . "\n\n");

    return $finalUrls;
}

/**
 * Comparer si l'image dans $url1 et $url2 sont similaires
 *
 * @param ImageComparator $imageComparator
 * @param string $url1
 * @param string $url2
 * @return boolean
 */
function isImagesSimilars($imageComparator, string $url1, string $url2, ?string $domaine = null): bool
{
    $content1 = $GLOBALS['urlContent'][$url1] ?? isUrlAccessible($url1, true)['content'];
    $content2 = $GLOBALS['urlContent'][$url2] ?? isUrlAccessible($url2, true)['content'];

    try {
        $imageComparator->setImagesSources($content1, $content2);
        $similarityArray = $imageComparator->compareImages();

        if (
            $similarityArray["basic"] === 100
            || $similarityArray['ssim'] === 1
            || $similarityArray['rmse'] === 0
            || $similarityArray['phash'] === 0
        ) {
            return true;
        } else {
            // Rattrapage en n'utilisant pas le removeBorder
            $imageComparator->setImagesSources($content1, $content2);
            $similarityArray = $imageComparator->compareImages('all', true, false);

            if (
                $similarityArray["basic"] === 100
                || $similarityArray['ssim'] === 1
                || $similarityArray['rmse'] === 0
                || $similarityArray['phash'] === 0
            ) {
                return true;
            }
        }
    } catch (\Throwable $th) {
        $trace = $th->getTrace()[0];
        $name_function = empty($trace["class"]) ? "::" . $th->getLine() : $trace["class"] . "::" . $trace["function"] . "()::" . $th->getLine();

        $pathError = '';
        if (!empty($domaine)) {
            $pathError = getErrorLogFile($domaine);
        }

        add_erreur([
            "-----------------------------------------------\n",
            $th->getCode() . " → " . $th->getMessage() . " :: " . $name_function . "\n",
            "URL 1: " . $url1 . "\n",
            "URL 2: " . $url2 . "\n\n"
        ], $pathError);
    }

    return false;
}

/**
 * Filtre un tableau d'URLs d'images en fonction de leurs dimensions minimales.
 *
 * @param array $urls Un tableau contenant les URLs d'images à filtrer.
 * @param int $minWidth La largeur minimale en pixels.
 * @param int $minHeight La hauteur minimale en pixels.
 * @return array Un tableau contenant les URLs d'images filtrées.
 */
function filterImagesBySize(array $urls, int $minWidth = 90, int $minHeight = 90): array
{
    $filteredUrls = [];

    foreach ($urls as $url) {
        $imageContent = $GLOBALS['urlContent'][$url] ?? isUrlAccessible($url, true)['content'];
        if ($imageContent === false) {
            $filteredUrls[] = $url;
        } else {
            $imageSize = getImageSizeWidthHeight($imageContent);
            $width = $imageSize[0];
            $height = $imageSize[1];

            if ($width >= $minWidth || $height >= $minHeight || $imageSize === false) {
                $filteredUrls[] = $url;
            }
        }
    }

    return $filteredUrls;
}

/**
 * Extrait les URLs d'images d'une chaîne CSS.
 *
 * @param string $string La chaîne CSS.
 * @return array Un tableau contenant les URLs d'images extraites.
 */
function extractImageUrls(string $string): array
{
    $string = html_entity_decode($string, ENT_QUOTES, 'UTF-8');

    // Expression régulière pour extraire les URLs à l'intérieur de url()
    $pattern = '/background(?:-image)?\s*:\s*url\((["\']?)(.*?)\1\)/i';

    preg_match_all($pattern, $string, $matches);

    // $matches[2] contiendra toutes les URL extraites
    $urls = array_map(function ($url) {
        return trim($url, " \"'"); // Trim des espaces et des guillemets doubles et simples
    }, $matches[2]);

    return $urls;
}

/**
 * Extrait les URLs d'images dans les attributs srcset ou data-srcset.
 *
 * @param string $string La chaîne contenu attribut.
 * @param array $list_image Un tableau contenant les URLs d'images déjà extraites.
 * @return array Un tableau contenant les URLs d'images extraites.
 */
function extractImageSrcsetBefore(string $string, array $list_image = []): array
{
    

    $srcsetParts = explode(',', $string);

    // Traiter chaque partie
    foreach ($srcsetParts as $part) {
        // Nettoyer l'URL en enlevant les espaces et les spécifications (480w, 2x, etc.)
        $url = trim(preg_replace('/\s+\d+[A-Za-z]{1,4}$/', '', trim($part)));

        // Ajouter l'URL nettoyée au tableau
        if (!in_array($url, $list_image)) $list_image[] = $url;
    }

    
    return array_unique($list_image);
}
function extractImageSrcset(string $string, array $list_image = []): ?array
{


    $srcsetParts = explode(',', $string);
    $largestImage = null;
    $maxValue = 0;
    $type = ''; // 'w' ou 'x'

    foreach ($srcsetParts as $part) {
        $part = trim($part);

        
        if (preg_match('/^(.*)\s+(\d+)([A-Za-z]{1,4})$/', $part, $matches)) {
            $url = trim($matches[1]);
            $value = (int)$matches[2];
            $uniteType = trim($matches[3]);

            if($type === '' && !empty($uniteType)) {
                $type = $uniteType; 
            }
            // Priorité aux 'w'
            if ($type == $uniteType && $value > $maxValue) {
                $maxValue = $value;
                $largestImage = $url;
            }
        }

        
    }

    if (!empty($largestImage)) {
        $list_image[] = $largestImage; // Ajouter l'image la plus grande à la liste
    }

    return array_unique($list_image);
}

/**
 * Vérifie si une URL est une URL d'image non traité.
 *
 * @param string $url L'URL à vérifier.
 * @return bool True si l'URL est une URL d'image, false sinon.
 */
function isImageUrl_NOK($url)
{
    // bmp , svg : extensions d'image suceptible d'être des icônes, logos  (à été enlevé)
    $pattern = '/\.(bmp|svg)([^\wA-Za-zÀ-ÿ]|$)+/i';

    return preg_match($pattern, $url) === 1;
}

/**
 * Vérifie si le contenu d'un élément est inclus dans celui d'un autre élément.
 *
 * @param string $smallElement Le contenu du petit élément.
 * @param string $largerElement Le contenu du grand élément.
 * @return bool True si le contenu du petit élément est inclus dans celui du grand élément, false sinon.
 */
function isIncludedInLargerElement(string $smallElement, string $largerElement): bool
{
    // On utilise strip_tags pour ignorer les balises HTML dans la comparaison de contenu
    $smallContent = preg_replace('/\s*/', ' ', strip_tags($smallElement));
    $largerContent = preg_replace('/\s*/', ' ', strip_tags($largerElement));

    // Si le contenu du petit élément est dans le plus grand, retourne true
    return strpos($largerContent, $smallContent) !== false;
}

/**
 * Dédoublonne les images en se basant sur leur hash MD5.
 *
 * @param array $imagesArray Un tableau contenant les URLs des images.
 * @return array Un tableau contenant les URLs des images dédoublonnées.
 */
function deduplicateImages(array $imagesArray): array
{
    $uniqueImages = [];
    $md5s = [];

    foreach ($imagesArray as $image) {
        $md5 = getRemoteMD5($image);
        if (!$md5) {
            $uniqueImages[] = $image;
        } elseif (!array_key_exists($md5, $md5s)) { // Use array_key_exists to check if the MD5 hash is already in the array
            $uniqueImages[] = $image;
            $md5s[$md5] = true; // Use a boolean value to avoid duplicates
        }
    }

    return $uniqueImages;
}

/**
 * Récupère le hash MD5 du contenu d'une URL distante.
 *
 * @param string $url L'URL du fichier distant.
 * @return string|false Le hash MD5 du contenu du fichier ou false si le fichier n'est pas accessible.
 */
function getRemoteMD5(string $url)
{
    if (isset($GLOBALS['urlContent'][$url])) return md5($GLOBALS['urlContent'][$url]);

    $maxRetryCount = 5;
    $retryCount = 0;

    while ($retryCount <= $maxRetryCount) {
        $retryCount++;
        $file_content = isUrlAccessible($url, true);

        if ($file_content === false) break;
    }

    if (!$file_content) return false;

    return md5($file_content["content"]);
}

/**
 * Trouve le pattern correspondant pour une URL donnée.
 *
 * @param string $url L'URL à analyser.
 * @return array|null Le pattern correspondant ou null si aucun pattern ne correspond.
 */
function findMatchingPattern(string $url): ?array
{
    $patterns = [
        '/(-500|-350)\.(.*)$/' => [
            'results' => ['-500', '-350'],
            'replacement' => 'X.$2'
        ],
        '/(\/imagecache\/\d+x\d+\/.*\/|\/Image\/)(.*)(\..*)/' => [
            'results' => ['/Image', '/imagecache/731x747/jpg'],
            'replacement' => 'X/${2}${3}'
        ],
        '/(-medium|-large)(\..*)/' => [
            'results' => ['-large', '-medium'],
            'replacement' => 'X${2}'
        ],
        '/\/cache\/(produit_detail|ekko_image)/' => [
            'results' => ['/ekko_image', '/produit_detail'],
            'replacement' => '/cacheX'
        ],
        '/\/images\/thumbs\/(.*)(_150|_625)(\..*)/' => [
            "results" => ['_625', '_150'],
            "indexMatches" => 2,
            'replacement' => '/images/thumbs/${1}X${3}'
        ],
        '/\/images\/produits\/(thumb_pdt|zoom)(.*)(\..*)/' => [
            'results' => ['/zoom', '/thumb_pdt'],
            'replacement' => '/images/produitsX${2}${3}'
        ],
        '/(\/expo\/medias\/\d+\/\d+\/\d+\/.+)\_(?:product|product_home|product_list|product_list_item)(\..*)/' => [
            'results' => ['_product', '_product_home', '_product_list', '_product_list_item'],
            'replacement' => '$1X$2'
        ],
        '/\/media\/(?:w-\d+(?:-h-\d+)?|h-\d+-w-\d+)(?:-zc-2)?-/' => [
            'results' => ['w-1080-', 'w-800-w-800-zc-2-'],
            'indexMatches' => 0,
            'replacement' => '/media/X'
        ],
        '/(\/images\/)(version\d+\/)?([\w\-]+\/image\/(?:produits|accueil)\/[^\?]*)(\?imgsize=\d+x\d+)?(.*)/' => [
            'results' => [],
            "indexMatches" => 0,
            'replacement' => '$1$3$5'
        ],
        '#(/contents/refim/)tn/(-[A-Za-z]{1,2}/)#' => [
            'results' => [],
            "indexMatches" => 0,
            'replacement' => '$1$2'
        ],
        // old '/\?(?:([a-z]*?Height=)(\d+)(\&[a-z]*?Width=)(\d+)|([a-z]*?Width=)(\d+)(\&[a-z]*?Height=)(\d+)|([a-z]*?Width=)(\d+)|([a-z]*?Height=)(\d+))(\&odnBg=[a-z0-9]{6})/i'
        // strick  '/\?([a-z]*?Width=)(\d+)(\&[a-z]*?Height=)(\d+)(\&odnBg=[a-z0-9]{6})?/i'
        '/\?(\w+=)(\d+)(\&\w+=)(\d+)(\&odnBg=[a-z0-9]{6})?/i' => [
            'results' => ["980", "612", "372"],
            "indexMatches" => 0,
            'replacement' => '?${1}X${3}X${5}',
            'urlBase' => true
        ],
        '/\/(large|mediumlarge|medium|mediumsmall|small)\//' => [
            'results' => ["large", "mediumlarge", "medium", "mediumsmall", "small"],
            "indexMatches" => 0,
            'replacement' => '/X/'
        ],
        '/\/(lg|md|sm|xs)\//' => [
            'results' => ["lg", "md"],
            "indexMatches" => 0,
            'replacement' => '/X/'
        ],
        '/(\?mw=\d{3,4}&rev=[0-9a-fA-F]{32}|\/mediumGallery|\/large|\/medium)$/' => [
            'results' => [],
            "indexMatches" => 0,
            'replacement' => ''
        ],
        //pattern enlever les urls image qui ont des pattern dimension apres \?
        // partern ? (alphabetique . ) = (alphanumerique ou nombre decimale ou entier ) 
        '/\?([\w\.]+=(?:\w|[\d\.])+)(\&[\w\.]+=(?:\w|[\d\.])+)*(\s+[\d\.]+[a-z]{1,4})?\s*$/i' => [
            'results' => [],
            "indexMatches" => 0,
            'replacement' => ''
        ],

        //Remplacement en dernier             
        '/[-_]*\d+x\d+[-_]*/' => [
            'results' => [],
            "indexMatches" => 0,
            'replacement' => ''
        ]
    ];

    foreach ($patterns as $pattern => $data) {
        $indexMatches = $data['indexMatches'] ?? 1;
        if (preg_match($pattern, $url, $matches) && strlen($matches[$indexMatches]) > 1) {
            return [
                "pattern" => $pattern,
                "data" => $data,
            ];
        }
    }
    return null;
}

/**
 * Traite une URL selon un pattern donné pour tenter de trouver une version plus grande de l'image.
 *
 * @param string $url L'URL à traiter.
 * @param array|null $patternArray Le pattern à appliquer.
 * @param array $validUrls Les URLs valides connues.
 * @return string L'URL traitée.
 */
function processUrlWithPattern(string $url, ?array $patternArray, array $validUrls): string
{
    global $imageComparator;

    if (empty($patternArray)) {
        return $url;
    }

    $pattern = $patternArray['pattern'];
    $data = $patternArray['data'];
    $resultsToCheck = $data['results'];
    $replacement = $data["replacement"];

    // Essayer d'abord avec avec l'urlBase
    if (isset($data["urlBase"]) && $data["urlBase"] === true) {
        $newUrl = preg_replace($pattern, '', $url);
        if (isUrlAccessible($newUrl) && isImagesSimilars($imageComparator, $url, $newUrl)) {
            return $newUrl;
        }
    }

    // Essayer d'abord avec un remplacement vide de X
    $emptyReplacement = str_replace('X', '', $replacement);
    $newUrl = preg_replace($pattern, $emptyReplacement, $url);
    $newUrl = preg_replace('/(?<!\:)\/\//', '/' , $newUrl);
    if (isUrlAccessible($newUrl) && isImagesSimilars($imageComparator, $url, $newUrl)) {
        return $newUrl;
    }

    foreach ($resultsToCheck as $result) {
        $tempReplacement = str_replace('X', $result, $replacement);
        $newUrl = preg_replace($pattern, $tempReplacement, $url);
        if (in_array($newUrl, $validUrls) || isUrlAccessible($newUrl)) {
            if( isImagesSimilars($imageComparator, $url, $newUrl))
            {
                return $newUrl;
            }
            
        }
    }

    return $url;
}

/**
 * Compare les dimensions de deux images àpartir de leurs URLs.
 *
 * @param string $url1 La première URL d'image.
 * @param string $url2 La deuxième URL d'image.
 * @return string|bool L'URL de l'image la plus grande ou true si les images ont la même taille. False si les deux images ne peuvent pas être lues.
 */
function compareImageSizes(string $url1, string $url2)
{
    $firstUrlContent = $GLOBALS['urlContent'][$url1] ?? isUrlAccessible($url1, true)['content'];
    $secondUrlContent = $GLOBALS['urlContent'][$url2] ?? isUrlAccessible($url2, true)['content'];

    $size1 = getImageSizeWidthHeight($firstUrlContent);
    $size2 = getImageSizeWidthHeight($secondUrlContent);

    if ($size1 === false && $size2 === false) {
        return false;
    }

    if ($size1 === false) {
        return $url2;
    }

    if ($size2 === false) {
        return $url1;
    }

    $area1 = $size1[0] * $size1[1];
    $area2 = $size2[0] * $size2[1];

    if ($area1 === $area2) return true;

    return $area1 >= $area2 ? $url1 : $url2;
}

/**
 * Obtient la largeur et la hauteur d'une image à partir de son contenu.
 *
 * @param string|false $content Le contenu de l'image.
 * @return array|false Un tableau contenant la largeur et la hauteur de l'image ou false si l'image ne peut pas être lue.
 */
function getImageSizeWidthHeight($content)
{
    if ($content === false) return false;

    $image = @imagecreatefromstring($content);

    if ($image === false) {
        $image = @imagecreatefromstring(gzdecode($content)) ?: @imagecreatefromstring(gzinflate($content));
    }

    if ($image === false) return false;

    $width = imagesx($image);
    $height = imagesy($image);
    imagedestroy($image);

    return [$width, $height];
}

/**
 * Dédoublonne les descriptions en supprimant les descriptions courtes qui sont incluses dans des descriptions plus longues.
 *
 * @param array $tab_description Un tableau contenant les descriptions à dédoublonner.
 * @return array Un tableau contenant les descriptions dédoublonnées.
 */
function dedoublonner_description($tab_description): array
{
    global $handle_trace;

    $uniqueArray = [];
    $tab_description = dedoublonner_tableau_html($tab_description);

    foreach ($tab_description as $key => $currentElement) {
        $isDuplicate = false;
        $currentElement = trim($currentElement);

        fwrite($handle_trace, "Traitement de l'élément à dédoublonner " . $key . ": \n" . var_export($currentElement, true) . "\n\n");

        // Comparer chaque élément avec les autres pour voir s'il est contenu dans un autre plus long
        foreach ($tab_description as $compareKey => $compareElement) {
            $compareElement = trim($compareElement);

            fwrite($handle_trace, "Comparaison avec l'élément " . $compareKey . ": \n" . var_export($compareElement, true) . "\n\n");

            if ($key !== $compareKey && isIncludedInLargerElement($currentElement, $compareElement) && strlen($currentElement) < strlen($compareElement)) {
                $isDuplicate = true;
                fwrite($handle_trace, "Element en doublon.\n\n");
                break;
            }
        }

        // Ajouter l'élément à la liste s'il n'est pas un doublon
        if (!$isDuplicate) {
            $uniqueArray[] = $currentElement;
        }
    }

    return $uniqueArray;
}

function dedoublonner_tableau_html($tableau_html)
{
    $html_uniques = []; // Contient les HTML uniques après normalisation
    $cles_uniques = []; // Contient les clefs de contrôle pour éviter les doublons

    foreach ($tableau_html as $html) {
        $html_normalise = normaliser_html($html);

        // Si le HTML n'existe pas déjà dans la liste des clefs uniques
        if (!in_array($html_normalise, $cles_uniques, true)) {
            $cles_uniques[] = $html_normalise;
            $html_uniques[] = $html; // Ajouter le HTML original
        }
    }

    return $html_uniques;
}

function normaliser_html($html)
{
    $dom = new DOMDocument();
    @$dom->loadHTML($html, LIBXML_HTML_NOIMPLIED | LIBXML_HTML_NODEFDTD);

    // Normaliser l'HTML en supprimant les espaces inutiles et en réorganisant
    $dom->preserveWhiteSpace = false;
    $dom->formatOutput = true;

    return $dom->saveHTML();
}

/**
 * Traite une description en supprimant
 *  les liens,
 *  les styles CSS masquant des éléments,
 *  les attributs JSON,
 *  les espaces s+1,
 *  les liens mais pas leurs contenus
 *  les images
 *  les balises avec contenu vide
 *  les boutons avec leurs contenus
 *  les balises br répétitives
 *  et tous les attributs sauf l'attribut style.
 *
 * @param string $description La description à traiter.
 * @return string La description traitée.
 */
function traitement_description(string $description): string
{
    $description = preg_replace('/\s+[a-z:\-_]+\s*=\s*(?:"\{(.*?)\}"|\'\{(.*?)\}\')/im', '', $description);

    $regex_remove_attribut = '/\s+(?!style\s*=)[a-z:\-_]+\s*=\s*("[^"]*"|\'[^\']*\'|[^\s>]+)/i';
    $description = preg_replace($regex_remove_attribut, '', $description);

    $description = preg_replace('/\s+/', ' ', $description);
    $description = preg_replace('/<\s*a.*>|<\s*\/\s*a>/Ui', '', $description);
    $description = preg_replace('/<\s*video.*>.*<\s*\/\s*video>/Uis', '', $description);
    $description = preg_replace('/<\s*form.*>.*<\s*\/\s*form>/Uis', '', $description);
    $description = preg_replace('/<\s*button.*>.*<\s*\/\s*button>/Uis', '', $description);
    $description = preg_replace('/<\s*select.*>.*<\s*\/\s*select>/Uis', '', $description);
    $description = preg_replace('/<\s*textarea.*>.*<\s*\/\s*textarea>/Uis', '', $description);
    $description = preg_replace('/<\s*img[^<]*\/?>/i', '', $description);
    $description = preg_replace('/<\s*input[^<]*\/?>/i', '', $description);

    $pattern = '/style=["\']([^"\']*)["\']/i';

    $description = preg_replace_callback($pattern, function ($matches) {
        $style = $matches[1]; // Contenu de l'attribut style
        $newStyle = array();

        // Expression régulière pour garder uniquement 'font-weight'
        preg_match_all('/\b(?:font|text)-(?:weight|style|transform|decoration)\s*:\s*[^;]+;?/i', $style, $styleMatches);

        // Concatène les propriétés 'font-weight' retrouvées
        foreach ($styleMatches as $s) {
            $newStyle[] = implode(' ', $s);
        }

        $newStyle = implode(';', $newStyle);

        // Si 'font-weight' existe, réintègre l'attribut style, sinon le supprime
        return $newStyle ? 'style="' . trim($newStyle) . '"' : '';
    }, $description);

    while (preg_match('/<([a-z]+)>\s*<\/\1>/i', $description)) {
        $description = preg_replace('/<([a-z]+)>\s*<\/\1>/i', '', $description);
    }

    $description = preg_replace('/<([a-z]+)>\s*<br\/?>\s*<\/\1>/i', '', $description);

    $description = nettoyer_email_tel_description($description);

    return $description;
}

function nettoyer_email_tel_description($description) {
    // Regex pour les emails
    $email_pattern = '/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/';
    
    // Regex pour les URLs
    $url_pattern = '/\b(?:https?:\/\/|www\.)\S+\b/i';
    
    // Regex pour les num tel FR
    $phone_pattern = '/(?:(?<=^|\s|\(|\[|>))(?:(?:\+33|0033|0)\s?(?:\s?\(0\)\s?)?[1-9])(?:[\s.\-]?\d{2}){4}(?=$|\s|\)|\]|<)/';
    
    
    // Nettoyage
    $description = preg_replace($email_pattern, '', $description);
    $description = preg_replace($phone_pattern, '', $description);
    $description = preg_replace($url_pattern, '', $description);
    
        
    return $description;
}

function simplifier_selecteur_id_desc($sel)
{
    if (preg_match('/([^\s]+)\s#/i', $sel)) {
        $tab_sel = explode('#', $sel);

        return '#' . end($tab_sel);
    }
    return $sel;
}

function normaliser_delai_livraison($livraison_content, $tab_selecteur)
{
    global $handle_trace;

    $go_to_nombre = [
        "un"     => 1,
        "deux"   => 2,
        "trois"  => 3,
        "quatre" => 4,
        "cinq"   => 5,
        "six"    => 6,
        "sept"   => 7,
        "huit"   => 8,
        "neuf"   => 9,
        "dix"    => 10
    ];

    $livraison_content = traitement_d_utf8($livraison_content);
    $livraison_content = preg_replace('/\bet\b/i', 'à', $livraison_content);
    $livraison_content = preg_replace('/(?:<br>|&nbsp;)/', ' ', $livraison_content);
    $livraison_content = str_ireplace(array_keys($go_to_nombre), array_values($go_to_nombre), $livraison_content);

    $unite             = trim($tab_selecteur['unite']);
    $label_unite       = str_replace('(', '\(', $tab_selecteur['label']);
    $label_unite       = str_replace(')', '\)', $label_unite);
    $label_unite       = str_replace('/', '\/', $label_unite);
    $tab_unite_jr      = ['jours', 'jour', 'jr'];
    $tab_unite = [
        "heures" => ["h", "heures?"],
        // "jours"  => ['jours','jour','jr'],
        "semaines"  => ['sem', 'semaines?'],
    ];

    if (preg_match('/' . $label_unite . '(?=\s*ouvrables?|ouvrés?)/', $livraison_content)) {
        $label_unite = $label_unite . "\s*ouvrables?";
    } elseif (preg_match('/' . $label_unite . '(?=\s*ouvrés?)/', $livraison_content)) {
        $label_unite = $label_unite . "\s*ouvrés?";
    }

    $label_rgx = $label_unite;

    if (!in_array($unite, $tab_unite_jr)) {
        $label_rgx = "(?:" . $label_unite . "|" . implode("|", $tab_unite[$unite]) . ")";
    }

    fwrite($handle_trace, "Contenu du livraison:". $livraison_content);

    $delai = "";
    if (empty($unite) && empty($label_unite)) {
        $delai = "";
    } else {
        if (preg_match('/([à\d\s\/\-]+)\s*' . $label_rgx . '(?=[^\d])?(?:\s*(?:ouvrables|ouvrés))?/i', $livraison_content, $matche)) {
            fwrite($handle_trace, "Regexp:([à\d\s\/\-]+)\s*$label_rgx(?=[^\d])?(?:\s*(?:ouvrables|ouvrés))?");
            fwrite($handle_trace, print_r($matche, true));
            $delai     = trim($matche[1]);
            preg_match('/([^\d]+)/', $delai, $match_sep);
            $sep = $match_sep[1];
            $tab_delai = !empty($sep) ? explode($sep, $delai) : [$delai];
            $tab_delai = array_filter($tab_delai);

            if (!in_array($unite, $tab_unite_jr)) {
                if ($unite == "heures") {
                    $tab_delai = array_map(function ($d) {
                        $d = trim($d);
                        return round($d / 24, 1);
                    }, $tab_delai);
                } elseif ($unite == "semaines") {
                    $tab_delai = array_map(function ($d) {
                        $d = trim($d);
                        return $d * 7;
                    }, $tab_delai);
                } elseif ($unite == "mois") {
                    $tab_delai = array_map(function ($d) {
                        $d = trim($d);
                        return $d * 30;
                    }, $tab_delai);
                }

                $delai = !empty($tab_delai) ? implode(" - ", $tab_delai) . " jour(s)" : "";
            } else {
                $delai = str_replace("ouvrés", "ouvrables", $matche[0]);
                $delai = str_replace($sep, " - ", $delai);
                $delai = preg_replace("/(?:jours?|JH|J|jr)\b/i", " jour(s)", $delai);
                $delai = preg_replace("/\s+/", " ", $delai);
            }
        }
        if (!preg_match('/\d+/', $delai)) $delai = '';
    }

    return $delai;
}

/**
 * Traite le contenu HTML d'une page web en minifiant le code, en décodant les entités HTML, 
 * en supprimant les balises inutiles et en nettoyant le code.
 *
 * @param string $contenu Le contenu HTML de la page web à traiter.
 * @return string Le contenu HTML traité.
 * @global HtmlMin $htmlMinify L'instance de la classe HtmlMin pour minifier le code HTML.
 */
function traitement_contenu_web(string $contenu): string
{
    global $htmlMinify;

    if (preg_match('/\s+[a-zA-Z:\-_]+\s*=\s*(?:"\{(.*?)\}"|\'\{(.*?)\}\')/i', $contenu)) {
        $contenu = preg_replace('/\s+[a-zA-Z:\-_]+\s*=\s*(?:"\{(.*?)\}"|\'\{(.*?)\}\')/i', '', $contenu);
    }

    $contenu = $htmlMinify->minify($contenu);
    // $contenu = html_entity_decode($contenu, ENT_QUOTES, 'UTF-8');
    // Déjà dans plugin Minify
    // $contenu = preg_replace("~<!--(?!<!)[^\[>].*?-->~s", "", $contenu);


    // Supprime les balises et leur contenu
    $balise_ov = ["script", "svg", "noscript", "iframe", "style"];
    foreach ($balise_ov as $balise) {
        $contenu_tmp = preg_replace('#<' . $balise . '(.*?)>(.*?)</' . $balise . '>#is', '', $contenu);
        if (preg_last_error() !== PREG_NO_ERROR) {
            $contenu_tmp = preg_replace('#<' . $balise . '\b[^>]*>([^<]*)</' . $balise . '>#is', '', $contenu);
        }
        $contenu = $contenu_tmp;
    }
    // $contenu = preg_replace('#<script(.*?)>(.*?)</script>#is', '', $contenu);

    // $contenu = preg_replace('#<svg(.*?)>(.*?)</svg>#is', '', $contenu);
    // $contenu = preg_replace('#<noscript(.*?)>(.*?)</noscript>#is', '', $contenu);
    // $contenu = preg_replace('#<iframe(.*?)>(.*?)</iframe>#is', '', $contenu);

    // // Supprime les balises <style> et leur contenu
    // $contenu = preg_replace('#<style\b[^>]*>([^<]*)</style>#is', '', $contenu);

    $contenu = preg_replace('#<link(.*?)>#is', '', $contenu);

    $contenu = preg_replace('#<path(.*?)>#is', '', $contenu);

    $contenu = preg_replace("/\n+/", ' ', $contenu);

    return $contenu;
}

/**
 * Recherche un élément unique dans un tableau.
 *
 * @param array $array Le tableau à parcourir.
 * @return mixed|null L'élément unique trouvé ou null si aucun élément unique n'est trouvé.
 */
function findSingleItemInArray(array $array)
{
    foreach ($array as $item) {
        if (count($item) == 1) {
            return $item;
        }
    }
    return null;
}

/**
 * Construit l'URL complète d'une fiche produit à partir d'une URL de base et d'un chemin relatif ou absolu.
 *
 * Si `$autre_fiche_prod` est un chemin relatif, la fonction le combine avec le schéma, le domaine 
 * et le port de `$url_fiche_produit` pour former une URL absolue.
 *
 * @param string $autre_fiche_prod URL relative ou absolue de la fiche produit.
 * @param string $url_fiche_produit URL de base de la fiche produit.
 *
 * @return string L'URL complète de la fiche produit.
 */
function recupUrlFicheProduit($autre_fiche_prod, $url_fiche_produit)
{
    // Vérifie si $autre_fiche_prod est vide ou # ou n'est pas un url/relative url
    //si oui retourne vide
    $url_fiche_produit = trim($autre_fiche_prod);
    if (empty($autre_fiche_prod) || $autre_fiche_prod == "#" || preg_match("/^(javascript|#)/", $autre_fiche_prod)  || !isValidURLorRelativePath($autre_fiche_prod)) {
        return null;
    }
    // Vérifie si $autre_fiche_prod est une URL absolue 
    // (commence par "http://", "https://", "ftp://" , "://" ou "//" )
    if (!preg_match("/^(http:\/\/|https:\/\/|ftp:\/\/|:\/\/|\/\/)/", $autre_fiche_prod)) {
        // Si ce n'est pas une URL absolue, extraire les informations de l'URL de base
        $info_url = parse_url($url_fiche_produit);

        // Construire l'URL absolue en combinant les informations extraites 
        // avec le chemin relatif fourni en s'assurant qu'il n'y a pas de double "/" au début du chemin
        $autre_fiche_prod = $info_url['scheme'] . "://" . $info_url['host'] .  "/" . ltrim($autre_fiche_prod, ':/');
    }

    // Retourner l'URL complète de la fiche produit
    return $autre_fiche_prod;
}

/**
 * Fonction qui détécte automatique si c'est un fiches produits via aux critère absolu des cms géré
 *
 * 
 * @param string $content contenu HTML du page à téstée
 * @param string $url URL de base de la page à téstée
 * @param string $cms_name CMS de la page à tésté
 *
 * @return mixed|null false|null si c'est pas fiche produit ou method de détéction si c'est fiche produit
 */
function detectCriteriaAuto($content, $url, $cms_name) 
{

    $dom = new DOMDocument();
    libxml_use_internal_errors(true);
    $dom->loadHTML($content);
    libxml_clear_errors();

    $xpath = new DOMXPath($dom);

    $criteria = [];
    switch($cms_name){
        case 'Prestashop' :
        case 'prestashop' :                        
            // Vérification de l'ID du produit
            if ($xpath->query("//*[translate(@id, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')='product_page_product_id']")->length > 0) {
                $criteria['ID'] = true;
            }

            // Vérification du type de page produit dans la balise body
            if ($xpath->query("//body[contains(@class, 'product-page') or contains(@class, 'page-product')]")->length > 0) {
                $criteria['CLASS'] = true;
            }

            // Vérification de l'élément meta og:type product
            if ($xpath->query("//meta[@property='og:type' and @content='product']")->length > 0) {
                $criteria['META'] = true;
            }

            break;

        case 'Magento' :
        case 'magento' :
            // Vérification du formulaire d'ajout au panier
            if ($xpath->query("//*[translate(@id, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')='product_addtocart_form']")->length > 0) {
                $criteria['ID'] = true;
            }

            // Vérification de la structure catalog/product dans l'URL
            if (preg_match('/\/catalog\/product\/view/', $url)) {
                $criteria['URL'] = true;
            }

            // Vérification des microdonnées JSON-LD de type Product
            if (preg_match('/"@type"\s*:\s*"Product"/', $content)) {
                $criteria['JSON_LD'] = true;
            }

            break;

        case 'Drupal' :
        case 'drupal' : 
            // Vérification des classes body spécifiques aux produits
            if (checkClassBody($content)) {
                $criteria['CLASS'] = true;
            }     

            // Vérification des noeuds commerce spécifiques à Drupal Commerce
            if ($xpath->query("//article[contains(@class, 'commerce-product')]")->length > 0) {
                $criteria['COMMERCE'] = true;
            }

            // Vérification des attributs data-product spécifiques
            if ($xpath->query("//*[@data-product-id or @data-product-type]")->length > 0) {
                $criteria['DATA_ATTR'] = true;
            }

            break;

        case "WIX Website Builder" :
        case "wix website builder" :   
            // Vérification de l'attribut data-hook="product-page"
            if ($xpath->query("//*[normalize-space(@data-hook)='product-page']")->length > 0) {
                $criteria["ATTR"] = true;
            }

            // Vérification du préfixe /product-page/ dans l'URL 
            if (preg_match('/\/product-page\//', $url)) {
                $criteria["URL"] = true;
            }

            // Vérification des meta wix-product
            if ($xpath->query("//meta[contains(@property, 'wix:product')]")->length > 0) {
                $criteria["META"] = true;
            }

            break;

        case "Wordpress" :           
        case "wordpress" :         
            // Vérification du lien alternatif WP API
            $css_attr = '[rel="alternate"][type="application/json"]';
            $xpath_attr = '//*[normalize-space(@rel)="alternate"][normalize-space(@type)="application/json"]';
            $base_domaine = recupereBaseUrlDomaine($url);   
            $patternWP = "/^(https?:\/\/)?([^\/]*)" . $base_domaine . "\/wp-json\/wp\/v\d\/product\/\d+/";

            $elements = $xpath->query($xpath_attr);
            if($elements->length == 1) {
                $href = $elements->item(0)->getAttribute('href');
                if(preg_match($patternWP, $href)) {
                    $criteria["LA"] = true;
                }
            }            

            // Vérification des classes WooCommerce
            if ($xpath->query("//div[contains(@class, 'woocommerce-product-gallery')]")->length > 0) {
                $criteria["WOO"] = true;
            }

            // Vérification du HTML structuré WooCommerce
            if ($xpath->query("//div[@id='product-" . preg_replace('/[^0-9]/', '', $url) . "']")->length > 0) {
                $criteria["PROD_ID"] = true;
            }

            break;

        case "Shopify" :   
        case "shopify" :
            // Vérification des classes template et ID produit
            $css_attrs = ["body.template-product", "body.template_product", "[name='product_id']"];
            $i = 1;
            foreach($css_attrs as $css_attr) {        
                $xpath_attr = cssToXPath($css_attr);
                if($xpath->query($xpath_attr)->length > 0) {
                    $criteria["ATTR" . $i] = true;
                }
                $i++;
            }   

            // Vérification du chemin /products/ dans l'URL
            if (preg_match('/\/products\/[^\/]+$/', $url)) {
                $criteria["URL"] = true;
            }

            // Vérification des meta shopify-product
            if ($xpath->query("//meta[@property='og:type' and contains(@content,'product')]")->length > 0) {
                $criteria["META"] = true;
            }

            break;

        default :
            break;
    }

    return $criteria;
}

function libelleCriteriaCmsGere()
{

    /**
     * search_type_fqdi : 
     * 	1 -> contains 
     * 2 -> not-contains
     * 
     * type_filtre_fqdi 
     * 	1 -> url 
     * 2 -> regex 
     * 3 -> selector 
     * 4 -> content
     * 5 -> Sitemap
     * 6 -> Chatgpt 
     * 
     * mode_qualification_fqdi  : 
     * 	1 -> inclus 
     *  2 -> exclus
     * 
     * 	origine_fqdi : 
     * 0 -> sans origine 
     * 1 -> qualification urls 
     * 2 -> détection automatique 
     * 3 -
     */

    $libelle = 
    [
        "prestashop" => [
            "REGEX" => [
                    'searchType' => '1' , //contains
                    'searchValue' => '^(https?:\/\/)?(www\.)?[^\/]+\/([\/a-zA-Z0-9-]{2,}\/)?(?:(\d+(_\d+)?-).*|.*(-\d+(_\d+)?))\.htm(l)?$/',
                    'typeFiltre' => 2, //regex
                    'modeQualif' => 1, //inclus           
                ],
            "ID" => [
                    'searchType' => '1' , //contains
                    'searchValue' => '#product_page_product_id',
                    'typeFiltre' => 3, //selector
                    'modeQualif' => 1, //inclus           
                ],
            "CLASS" => [
                    'searchType' => '1' , //contains
                    'searchValue' => '.product-page , .page-product',
                    'typeFiltre' => 3, //selector
                    'modeQualif' => 1, //inclus           
                ],
            "META" => [
                    'searchType' => '1' , //contains
                    'searchValue' => 'meta[property="og:type"][content="product"]',
                    'typeFiltre' => 3, //selector
                    'modeQualif' => 1, //inclus           
                ],
            "MTD" => [
                    'searchType' => '1' , //contains
                    'searchValue' => 'meta[property="og:type"][content="product"]',
                    'typeFiltre' => 3, //selector
                    'modeQualif' => 1, //inclus           
                ],
            "MCD" => [
                    'searchType' => '1' , //contains
                    'searchValue' => '/"@type"\s*:\s*"Product"/',
                    'typeFiltre' => 4, //content
                    'modeQualif' => 1, //inclus           
                ],
        ],
        'magento' => [
            "REGEX" => [
                    'searchType' => '1' , //contains
                    'searchValue' => '^(https?:\/\/)?(www\.)?[^\/]+\/([\/a-zA-Z0-9-]+\/)?[a-zA-Z0-9-]+\.html$',
                    'typeFiltre' => 2, //regex
                    'modeQualif' => 1, //inclus           
                ],
            "ID" => [
                    'searchType' => '1' , //contains
                    'searchValue' => '#product_addtocart_form',
                    'typeFiltre' => 3, //selector
                    'modeQualif' => 1, //inclus           
                ],
            "URL" => [
                    'searchType' => '1' , //contains
                    'searchValue' => '/catalog/product/view',
                    'typeFiltre' => 2, //regex
                    'modeQualif' => 1, //inclus           
                ],
            "MTD" => [
                    'searchType' => '1' , //contains
                    'searchValue' => 'meta[property="og:type"][content="product"]',
                    'typeFiltre' => 3, //selector
                    'modeQualif' => 1, //inclus           
                ],
            "JSON_LD" => [
                    'searchType' => '1' , //contains
                    'searchValue' => '/"@type"\s*:\s*"Product"/',
                    'typeFiltre' => 4, //content
                    'modeQualif' => 1, //inclus           
                ],            
            "MTD" => [
                    'searchType' => '1' , //contains
                    'searchValue' => '/"@type"\s*:\s*"Product"/',
                    'typeFiltre' => 4, //content
                    'modeQualif' => 1, //inclus           
                ],
        ],

        'drupal' => [
            "CLASS" => [
                    'searchType' => '1' , //contains
                    'searchValue' => '.node-location-product , .node-type-location-product , .page-node-type-produit , .node-type-produit , .node-type-produits , .page-node-type-product .is-node-page--product , .page--product',
                    'typeFiltre' => 3, //selector
                    'modeQualif' => 1, //inclus           
                ],
            "COMMERCE" => [
                    'searchType' => '1' , //contains
                    'searchValue' => 'article.commerce-product',
                    'typeFiltre' => 3, //selector
                    'modeQualif' => 1, //inclus           
                ],
            "DATA_ATTR" => [
                    'searchType' => '1' , //contains
                    'searchValue' => '[data-product-id] , [data-product-type]',
                    'typeFiltre' => 3, //selector
                    'modeQualif' => 1, //inclus           
                ],
            "REGEX" => [
                    'searchType' => '1' , //contains
                    'searchValue' => '/(products?|produits?)\/.+',
                    'typeFiltre' => 2, //regex
                    'modeQualif' => 1, //inclus           
                ],
            "MTD" => [
                    'searchType' => '1' , //contains
                    'searchValue' => 'meta[property="og:type"][content="product"]',
                    'typeFiltre' => 3, //selector
                    'modeQualif' => 1, //inclus           
                ],
            "MCD" => [
                    'searchType' => '1' , //contains
                    'searchValue' => '/"@type"\s*:\s*"Product"/',
                    'typeFiltre' => 4, //content
                    'modeQualif' => 1, //inclus           
                ],

        ],
        "wix website builder" => [
            "ATTR" => [
                    'searchType' => '1' , //contains
                    'searchValue' => '[data-hook="product-page"]',
                    'typeFiltre' => 3, //selector
                    'modeQualif' => 1, //inclus           
                ],
            "URL" => [
                    'searchType' => '1' , //contains
                    'searchValue' => '/product-page/',
                    'typeFiltre' => 2, //regex
                    'modeQualif' => 1, //inclus           
                ],
            "META" => [
                    'searchType' => '1' , //contains
                    'searchValue' => 'meta[property^="wix:product"]',
                    'typeFiltre' => 3, //selector
                    'modeQualif' => 1, //inclus           
                ],
            "REGEX" => [
                    'searchType' => '1' , //contains
                    'searchValue' => '^(https?:\/\/)?(www\.)?[^\/]+\/product-page\/(.+)$',
                    'typeFiltre' => 2, //regex
                    'modeQualif' => 1, //inclus           
                ],
            "MTD" => [
                    'searchType' => '1' , //contains
                    'searchValue' => 'meta[property="og:type"][content="product"]',
                    'typeFiltre' => 3, //selector
                    'modeQualif' => 1, //inclus           
                ],
        ],
        "wordpress" => [
            "LA" => [
                    'searchType' => '1' , //contains
                    'searchValue' => '/(https?:\/\/)?([^\/]*)\/wp-json\/wp\/v\d\/product\/\d+/i',
                    'typeFiltre' => 4, //content
                    'modeQualif' => 1, //inclus           
                ],
            "WOO" => [
                    'searchType' => '1' , //contains
                    'searchValue' => 'div.woocommerce-product-gallery',
                    'typeFiltre' => 3, //selector
                    'modeQualif' => 1, //inclus           
                ],
            "PROD_ID" => [
                    'searchType' => '1' , //contains
                    'searchValue' => 'div[id^=product-]',
                    'typeFiltre' => 3, //selector
                    'modeQualif' => 1, //inclus           
                ],
            "REGEX" => [
                    'searchType' => '1' , //contains
                    'searchValue' => '(/boutique/|/shop/|/produit/|/p/)',
                    'typeFiltre' => 2, //regex
                    'modeQualif' => 1, //inclus           
                ],
        ],
        "shopify" => [
            "ATTR1" => [
                    'searchType' => '1' , //contains
                    'searchValue' => 'body.template-product',
                    'typeFiltre' => 3, //selector
                    'modeQualif' => 1, //inclus           
                ],
            "ATTR2" => [
                    'searchType' => '1' , //contains
                    'searchValue' => 'body.template_product',
                    'typeFiltre' => 3, //selector
                    'modeQualif' => 1, //inclus           
                ],
            "ATTR3" => [
                    'searchType' => '1' , //contains
                    'searchValue' => '[name="product_id"]',
                    'typeFiltre' => 3, //selector
                    'modeQualif' => 1, //inclus           
                ],
            "URL" => [
                    'searchType' => '1' , //contains
                    'searchValue' => '/products\/[^\/]+$',
                    'typeFiltre' => 2, //regex
                    'modeQualif' => 1, //inclus           
                ],
            "META" => [
                    'searchType' => '1' , //contains
                    'searchValue' => 'meta[property="og:type"][content^="product"]',
                    'typeFiltre' => 3, //selector
                    'modeQualif' => 1, //inclus           
                ],
            "REGEX" => [
                    'searchType' => '1' , //contains
                    'searchValue' => '/(products?|produits?)\/.+',
                    'typeFiltre' => 2, //regex
                    'modeQualif' => 1, //inclus           
                ],
            "MTD" => [
                    'searchType' => '1' , //contains
                    'searchValue' => 'meta[property="og:type"][content="product"]',
                    'typeFiltre' => 3, //selector
                    'modeQualif' => 1, //inclus           
                ],
            "MCD" => [
                    'searchType' => '1' , //contains
                    'searchValue' => '/"@type"\s*:\s*"Product"/',
                    'typeFiltre' => 4, //content
                    'modeQualif' => 1, //inclus           
                ],
        ]
    ];

    return $libelle;
}

/**
 * Fonction qui détécte automatiquement si c'est une fiche produit ou pas pour les cas non gérés
 *
 * @param string $url
 * @param text $contenu
 * @return bool
 * 
 */
function est_fiche_produit_cas_non_gerer($url,$contenu) {
    
    if(est_meta_og_type_produit_present($contenu)) {
        return [
            "statut" => true,
            "criteria" => "MTD"
        ];
    } elseif(est_microdonnee_produit_present($contenu)) {
        return [
            "statut" => true,
            "criteria" => "MCD"
        ];
    }

    return [
        "statut" => false,
        "criteria" => ""
    ];
}

function liste_fp_url($tab_url) {
    $tab_resultat = [];

    foreach($tab_url as $info_url) {
        $url = $info_url["url"];

        if(preg_match("/\/p\/.+/i",$url)) {
            $tab_resultat["p"][] = $info_url;        
        } elseif(preg_match("/\/prod\/.+/i",$url)) {
            $tab_resultat["prod"][] = $info_url;        
        } elseif(preg_match("/\/produit\/.+/i",$url)) {
            $tab_resultat["produit"][] = $info_url;        
        } elseif(preg_match("/\/produits\/.+/i",$url)) {
            $tab_resultat["produits"][] = $info_url;        
        } elseif(preg_match("/\/product\/.+/i",$url)) {
            $tab_resultat["product"][] = $info_url;        
        } elseif(preg_match("/\/products\/.+/i",$url)) {
            $tab_resultat["products"][] = $info_url;        
        } elseif(preg_match("/\/product-detail\/.+/i",$url)) {
            $tab_resultat["product-detail"][] = $info_url;        
        } elseif(preg_match("/\/products-detail\/.+/i",$url)) {
            $tab_resultat["products-detail"][] = $info_url;        
        }  
    }

    foreach($tab_resultat as $pattern => $resultat) {
        $tab_resultat_count[$pattern] = count($resultat);
    }

    $max_nb = max($tab_resultat_count);

    $patterns_trouve = array_keys($tab_resultat_count,$max_nb);

    $tab_final_url = [];
    foreach($patterns_trouve as $pattern) {
        $tab_final_url = array_merge($tab_final_url,$tab_resultat[$pattern]);
    }

    return [
        "urls_final" => $tab_final_url,
        "patterns_trouve" => $patterns_trouve,
    ];
}

function est_url_produit($url) {
    $tab_pattern_url = [
        "\/p\/",
        "\/prod\/",
        "\/produits?\/",
        "\/products?\/",
        "\/products?-detail\/",
    ];

    $pattern = implode("|",$tab_pattern_url);
    $pattern = "/(". $pattern .").+/i";

    if(preg_match($pattern,$url))
        return true;
    return false;
}

function est_meta_og_type_produit_present($contenu) {
    if(preg_match('/property="og:type"\s+content="product"/i',$contenu))
        return true;
    return false;
}

function est_microdonnee_produit_present($contenu) {
    if(preg_match('#"@type"\s*:\s*"Product".*</head>#is',$contenu))
        return true;
    return false;
}

function add_filtre_qualification($id_domaine, $data, $hasRelation = false)
{

    /**
     * search_type_fqdi : 
     * 	1 -> contains 
     * 2 -> not-contains
     * 
     * type_filtre_fqdi 
     * 	1 -> url 
     * 2 -> regex 
     * 3 -> selector 
     * 4 -> content
     * 
     * mode_qualification_fqdi  : 
     * 	1 -> inclus 
     *  2 -> exclus
     * 
     * 	origine_fqdi : 
     * 0 -> sans origine 
     * 1 -> qualification urls 
     * 2 -> détection automatique 
     * 3 -> détection manuel	
     */

    //Verification de doublon
    $searchtype = $data["searchType"] ?? "1";
    $typefiltre = $data["typeFiltre"] ?? "1";
    $modequalif = $data["modeQualif"] ?? "1";

    if (!$hasRelation) {
        $sql_doublon = "SELECT
                            id_filtre_qualification_domaine_ia
                        FROM
                            filtre_qualification_domaine_ia FQDI
                        WHERE
                            id_domaine_fqdi = '{$id_domaine}'
                            AND search_type_fqdi = '{$searchtype}'
                            AND search_value_fqdi = '" . hellopro_traitement_donnee_annuaire_bo($data["searchValue"]) . "'
                            AND type_filtre_fqdi = '{$typefiltre}'
                            AND mode_qualification_fqdi = '{$modequalif}'
                            AND origine_fqdi = '{$data["origine"]}' ";

        $res_doublon = mysqli_query($GLOBALS["LINK_MYSQLI_HELLOPRO_IA"], $sql_doublon) or die(hellopro_mysql_error($sql_doublon, $GLOBALS["LINK_MYSQLI_HELLOPRO_IA"]));
        $nb_doublon = mysqli_num_rows($res_doublon);

        if ($nb_doublon > 0) {
            return 0;
        }
    }

    $id_filtre_qualif = sql_insert_info(
        [
            "id_domaine_fqdi" =>  $id_domaine,
            "search_type_fqdi " =>  $data["searchType"] ?? "1",
            "search_value_fqdi" => $data["searchValue"],
            "type_filtre_fqdi " => $data["typeFiltre"] ?? "1",
            "mode_qualification_fqdi " => $data["modeQualif"] ?? "1",
            "date_fqdi" => "NOW()",
            "origine_fqdi " => $data["origine"] ?? "1",
        ],
        "filtre_qualification_domaine_ia"
    );

    return $id_filtre_qualif;
}

function add_filtre_qualif_relation($id_domaine, $ids_qualif = [])
{
    $ids_qualif = array_unique(array_filter($ids_qualif, function ($id) {
        return is_numeric($id) && $id > 0;
    }));
    if (empty($ids_qualif) || !is_array($ids_qualif)) {
        return 0;
    }
    $id_relation_filtre_qualif = sql_insert_info(
        [
            "id_domaine_rfdi" =>  $id_domaine,
            "relation_filtre_rfdi " =>  implode(",", $ids_qualif),
        ],
        "relation_filtre_domaine_ia"
    );

    return $id_relation_filtre_qualif;
}

function getCombinations($arrays) {
    $result = [[]];

    foreach ($arrays as $key => $values) {
        $temp = [];

        foreach ($result as $combination) {
            foreach ($values as $value) {
                $temp[] = array_merge($combination, [$value]);
            }
        }

        $result = $temp;
    }

    return $result;
}

function verif_doublon_relation_filtre($id_domaine, $dataParams)
{
    $existantFiltre = [];
    $index = 0;
    foreach ($dataParams as $data) {

        $searchtype = $data["searchType"] ?? "1";
        $typefiltre = $data["typeFiltre"] ?? "1";
        $modequalif = $data["modeQualif"] ?? "1";

        $sql_doublon = "SELECT
                            id_filtre_qualification_domaine_ia
                        FROM
                            filtre_qualification_domaine_ia FQDI
                        WHERE
                            id_domaine_fqdi = '{$id_domaine}'
                            AND search_type_fqdi = '{$searchtype}'
                            AND search_value_fqdi = '" . hellopro_traitement_donnee_annuaire_bo($data["searchValue"]) . "'
                            AND type_filtre_fqdi = '{$typefiltre}'
                            AND mode_qualification_fqdi = '{$modequalif}'
                            AND origine_fqdi = '{$data["origine"]}' ";

        $res_doublon = mysqli_query($GLOBALS["LINK_MYSQLI_HELLOPRO_IA"], $sql_doublon) or die(hellopro_mysql_error($sql_doublon, $GLOBALS["LINK_MYSQLI_HELLOPRO_IA"]));
        $nb_doublon = mysqli_num_rows($res_doublon);

        if ($nb_doublon == 0) {
            return false;
        }

        while ($ligne_doublon = mysqli_fetch_assoc($res_doublon)) {
            $existantFiltre[$index][] = $ligne_doublon['id_filtre_qualification_domaine_ia'];
        }
        $index++;
    }


    $combinations = getCombinations($existantFiltre);
    if (empty($combinations) || empty($combinations[0])) {
        return false;
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
    while ($lg_relation = mysqli_fetch_assoc($res_relations)) {
        $relations = explode(',', $lg_relation['relation_filtre_rfdi']);
        $relations = array_filter(array_map('trim', $relations));

        // Vérification si tous les filtres existent dans la relation
        foreach ($combinations as $combo) {
            if (count($combo) === count($relations) && count(array_intersect($relations, $combo)) === count($combo)) {
                // Si tous les filtres existent, on retourne l'ID de la relation
                return true;
            }
        }
    }

    return false;
}

function launchEnqueueCrawler($type = "")
{
    $server_name = $GLOBALS['protocol_http_host_bo'] . "script.hellopro.fr"; // PROD
    // $server_name = $GLOBALS['protocol_http_host_bo'] . "dev-script.hellopro.fr"; // DEV
    

    $test_temp = $_SERVER['DOCUMENT_ROOT'] . 'tmp/script_lancer_enqueue_crawling_' . date('Ymdhis') . '.log';
    $command = "cd " . $_SERVER['DOCUMENT_ROOT'] . "tmp/; wget -q -b -t 1 '" . $server_name . "/script/chatgpt/script_lancer_enqueue_crawling.php?launcher=shell&type=" . $type . "' -a '" . $test_temp . "'";
    $a = shell_exec($command);

}

function launchQualificationIa($params = [])
{
    $id_societe = $params['id_societe'] ?? [];
    $id_upload = $params['id_upload'] ?? null;
    $list_societe = !is_array($id_societe) ? [$id_societe] : $id_societe;
    //lancement qualification ia
    $server_name = $GLOBALS['protocol_http_host_bo'] . "script.hellopro.fr"; // PROD
    // $server_name = $GLOBALS['protocol_http_host_bo'] . "dev-script.hellopro.fr"; // DEV        

    $test_temp = $_SERVER['DOCUMENT_ROOT'] . 'tmp/script_lancer_enrichissemment_fournisseur_ia' . date('Ymdhis') . '.log';
    $command = "cd " . $_SERVER['DOCUMENT_ROOT'] . "tmp/; wget -q -b -t 1 '" . $server_name . "/script/chatgpt/variante_categorie/script_lancer_enrichissemment_fournisseur_ia.php?societes=" . implode(";" , $list_societe) . "&id_upload=" . $id_upload . "' -a '" . $test_temp . "'";
    $a = shell_exec($command);
}

//function de recuperation de fichier sitemape via url
function getSitemap($url) {
    $maxRetryCount = 5;
    $retryCount = 0;
    $last_http_code = $last_error = "";

    while ($retryCount <= $maxRetryCount) {
        $retryCount++;
        $url_in_curl = $retryCount > 1 && $last_http_code == 0 ? encodeFullUrlWithPreg($url) : $url ;
        $ch = curl_init();
        $options = [
            CURLOPT_URL => $url_in_curl,
            CURLOPT_FOLLOWLOCATION => true,
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_CUSTOMREQUEST => 'GET',
            CURLOPT_HTTP_VERSION => CURL_HTTP_VERSION_1_1,
            CURLOPT_HTTPHEADER => [
                "Accept: */*",
                "Accept-Encoding: gzip, deflate, br, zstd",
                "Cache-Control: no-cache",
                "Connection: keep-alive",
                "sec-fetch-dest: document",
                "Sec-Fetch-Site: none",
                "Sec-Fetch-User: ?1",
                "Priority: u=0, i",
                "Pragma: no-cache",
                "user-agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            ]
        ];

        if($retryCount > 1 && stripos($last_error, "SSL certificate") !== false)
        {
            $options[CURLOPT_SSL_VERIFYPEER] = false;
            $options[CURLOPT_SSL_VERIFYHOST] = 0;
        }

        curl_setopt_array($ch, $options);
        $content = curl_exec($ch);

        $last_http_code = $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
        $contentType = curl_getinfo($ch, CURLINFO_CONTENT_TYPE);

        if(curl_errno($ch)) {
            $last_error =  curl_error($ch);
        }

        curl_close($ch);

        // Vérifier si le code HTTP est 200 (OK) et si le contenu est une fichier xml
        if ($httpCode == 200 &&  strpos($contentType, 'text/xml') !== false )
        {
            return $content;            
        }

        if (!in_array($httpCode, [0, 429])) break;

        // Gestion des cas de Too Many Requests 429
        if ($httpCode == 429) {
            sleep(10);
        }
    }

    // Retourne false si ce n'est pas une image ou si l'URL n'est pas accessible
    return false;
}

//fonction de creation de l'objet xml du sitemap
function createXmlElement($content)
{
    // Liste des méthodes de décompression à essayer
    $decompressionMethods = [
        'raw' => function($content) { return $content; },
        'gzdecode' => function($content) { return gzdecode($content); },
        'gzinflate' => function($content) { return gzinflate($content); }
    ];

    // Supprime les espaces de noms XML qui pourraient causer des problèmes
    $cleanXml = function($content) {
        if (!is_string($content)) {
            return false;
        }
        return preg_replace("/(<\/?)(\w+):([^>]*>)/", "$1$2$3", $content);
    };

    // Essaie chaque méthode de décompression
    foreach ($decompressionMethods as $methodName => $decompress) {
        try {
            $decompressedContent = $decompress($content);
            if ($decompressedContent === false) {
                continue;
            }

            $xmlString = $cleanXml($decompressedContent);
            if ($xmlString === false) {
                continue;
            }

            $xml = new SimpleXMLElement($xmlString);
            if ($xml !== false) {
                return $xml;
            }
        } catch (Exception $e) {
            error_log("Échec de la méthode {$methodName}: " . $e->getMessage());
            continue;
        }
    }
    return [];
    
}

//focntion qui va verifier le sitemap du produit
function processSitemap($home)
{
    $list_url_sm = processSitemapByUrl($home);
    
    $fiche_produit = []; 
    if(is_array($list_url_sm) && $list_url_sm !== false && count($list_url_sm) > 0) 
    {
        foreach($list_url_sm AS $url_smp => $data_sm)
        {
            foreach($data_sm->url AS $data_url)
            {
                $temp_url = (string)$data_url->loc;
                $temp_url = trim($temp_url);
                $info_url = parse_url($temp_url);
                if( empty($temp_url) || preg_match("/^\/?[^\/]+\/?$/" , $info_url['path']))
                {
                    continue;
                } 
                return   $list_url_sm;        
            }
        }          
    }

    $pieces = parse_url($home);
    $homepage_strict = "https://" . $pieces['host'] . "/";
    return  processSitemapByUrl($homepage_strict);
}

function processSitemapByUrl($homepage)
{    
    $homepage = trim($homepage , '/') . "/";
    
    $default_sitemap_p = [ "product-sitemap.xml" , "produit-sitemap.xml"];

    foreach($default_sitemap_p as $sitemap_p)
    {
        $url_sitemap = $homepage . $sitemap_p;
        $content = getSitemap($url_sitemap);
        if($content !== false)
        {   
            return [createXmlElement($content)];
        }
    }

    $default_sitemap = $homepage . "sitemap.xml";
    $content = getSitemap($default_sitemap);
    if($content !== false)
    {
        $xmlString = preg_replace("/(<\/?)(\w+):([^>]*>)/", "$1$2$3", $content);
        $xml =  createXmlElement($xmlString);
        if (empty($xml) || $xml->getName() !== 'sitemapindex') {
            return false;
        }

        // Parcourt chaque sitemap pour récuperer l'url sitemap produit
        $url_sitemap_p = [];
        foreach ($xml->sitemap as $sitemap) {
            $loc = (string)$sitemap->loc;
            
            // Vérifie que le lien pointe vers un fichier XML
            if (!preg_match('/\.xml$/', $loc)) {
                continue;
            }

            // Vérifie la présence des mots "product" ou "produit"
            // mais pas "product_cat" ou "produit_cat"
            if ((stripos($loc, 'product') !== false || stripos($loc, 'produit') !== false) &&
                !preg_match("/(product_cat|produit_cat|product_tag|produit_tag|categorie?|category|[\-\_]cat[\-\_]|[\-\_]tag[\-\_])/" , $loc)) {
                    $url_sitemap_p[] = trim($loc);
            }
        }

        if(!empty( $url_sitemap_p ))
        {
            $final_sitemap =  [];
            foreach($url_sitemap_p as $url_sitemap)
            {
                $content = getSitemap($url_sitemap);
                if($content !== false)
                {
                    $sm_produit = createXmlElement($content);

                    //verification si sitemap produit n'est pas vide
                    if($sm_produit->url)
                    {
                        $final_sitemap[$url_sitemap] = $sm_produit;
                    }
                }
            }
            return $final_sitemap;
        }
    }

    return false;
}

function detectCriteria($content, $url, $cms_name) {

    
    $dom = new DOMDocument();
    libxml_use_internal_errors(true);
    $dom->loadHTML($content);
    libxml_clear_errors();

    $xpath = new DOMXPath($dom);

    $criteria = [];
    switch($cms_name){
        case 'Prestashop' :
        case 'prestashop' :
            
        
            $regex = '/^(https?:\/\/)?(www\.)?[^\/]+\/([\/a-zA-Z0-9-]{2,}\/)?(?:(\d+(_\d+)?-).*|.*(-\d+(_\d+)?))\.htm(l)?$/';
            if ($url && preg_match($regex, $url)) {
                $criteria['REGEX'] = true;
            }
        
            if ($xpath->query("//*[translate(@id, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')='product_page_product_id']")->length > 0) {
                $criteria['ID'] = true;
            }
        
            if ($xpath->query("//meta[translate(@property, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')='og:type' and translate(@content, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')='product']")->length > 0) {
                $criteria['MTD'] = true;
            }
        
            if (preg_match('/@type"\s*:\s*"product"/i', $dom->textContent)) {
                $criteria['MCD'] = true;
            }

            break;

        case 'Magento' :
        case 'magento' :
            

            $regex = '/^(https?:\/\/)?(www\.)?[^\/]+\/([\/a-zA-Z0-9-]+\/)?[a-zA-Z0-9-]+\.html$/';
            if ($url && preg_match($regex, $url)) {
                $criteria['REGEX'] = true;
            }

            if ($xpath->query("//*[translate(@id, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')='product_addtocart_form']")->length > 0) {
                $criteria['ID'] = true;
            }

            if ($xpath->query("//meta[translate(@property, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')='og:type' and translate(@content, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')='product']")->length > 0) {
                $criteria['MTD'] = true;
            }

            if (preg_match('/@type"\s*:\s*"product"/i', $dom->textContent)) {
                $criteria['MCD'] = true;
            }

            break;

        case 'Drupal' :
        case 'drupal' :    
        
            $regex = '/\/(products?|produits?)\/.+/';
            if ($url && preg_match($regex, $url)) {
                $criteria['REGEX'] = true;
            }
        
            if (checkClassBody($content)) {
                $criteria['CLASS'] = true;
            }
        
            if ($xpath->query("//meta[translate(@property, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')='og:type' and translate(@content, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')='product']")->length > 0) {
                $criteria['MTD'] = true;
            }
        
            if (preg_match('/@type"\s*:\s*"product"/i', $dom->textContent)) {
                $criteria['MCD'] = true;
            }
        
           break;
        case "WIX Website Builder" :
        case "wix website builder" :   
            
            // Étape 1 : Vérifier REGEX
            $regex = '/^(https?:\/\/)?(www\.)?[^\/]+\/product-page\/(.+)$/';    
            if ($url && preg_match($regex, $url)) {
                $criteria['REGEX'] = true;
            }

            //Etape 2- Vérifier attribut [data-hook="product-page"]
            $css_attr = '[data-hook="product-page"]';
            // $xpath_attr = cssToXPath($css_attr);
            $xpath_attr = '//*[normalize-space(@data-hook)="product-page"]';
            if($xpath->query($xpath_attr)->length > 0)
            {
                $criteria["ATTR"] = true;
            }

            // Étape 3 : Vérifier MTD avec flexibilité sur les guillemets et la casse
            if ($xpath->query("//meta[translate(@property, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')='og:type' and translate(@content, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')='product']")->length > 0) {
                $criteria['MTD'] = true;
            }
                    
           break;
        case "Wordpress" :           
        case "wordpress" :         
            // Étape 1 : verification sitemap produit
            //pas ici

            //Etape 2- Vérifier Lien Alternative worpress            

            $css_attr = '[rel="alternate"][type="application/json"]';
            // $xpath_attr = cssToXPath($css_attr);
            $xpath_attr = '//*[normalize-space(@rel)="alternate"][normalize-space(@type)="application/json"]';
            $laMatch = false;
            $base_domaine = recupereBaseUrlDomaine($url);   
            $patternWP = "/^(https?:\/\/)?([^\/]*)" . $base_domaine . "\/wp-json\/wp\/v\d\/product\/\d+/";

            $elements = $xpath->query($xpath_attr);
            if($elements->length == 1)
            {
                $href = $elements->item(0)->getAttribute('href');
                if(preg_match($patternWP, $href))
                {
                    $criteria["LA"] = true;
                }
            }

            // Étape 3 : Vérifier REGEX
            $regexs = [
                    '/^(https?:\/\/)?(www\.)?[^\/]+(\/[a-z]{2,4})?\/boutique\/(.+)/',
                    '/^(https?:\/\/)?(www\.)?[^\/]+(\/[a-z]{2,4})?\/produit\/(.+)/',
                    '/^(https?:\/\/)?(www\.)?[^\/]+(\/[a-z]{2,4})?\/shop\/(.+)/',
                    '/^(https?:\/\/)?(www\.)?[^\/]+(\/[a-z]{2,4})?\/p\/(.+)/',
                ];
            $i = 1;
            foreach($regexs as $regex)
            {
                if ($url && preg_match($regex, $url)) {
                    $criteria['REGEX' . $i] = true;
                }
                $i++;
            }
                    
           break;
        case "Shopify" :   
        case "shopify" :

            // Étape 1 : Vérifier REGEX
            $regex = '/\/(products?|produits?)\/.+/';    
            if ($url && preg_match($regex, $url)) {
                $criteria['REGEX'] = true;
            }

            //Etape 2- Vérifier class BODY body.template-product ou body.template_product ou produit id [name="product_id"]
            $css_attrs = ["body.template-product" , "body.template_product" , "[name='product_id']"];
            
            $i = 1;
            foreach($css_attrs as $css_attr)
            {        
                $xpath_attr = cssToXPath($css_attr);
                if($xpath->query($xpath_attr)->length > 0)
                {
                    $criteria["ATTR" . $i] = true;
                }
                $i++;
            }   

            // Étape 3 : Vérifier MTD avec flexibilité sur les guillemets et la casse            
            if ($xpath->query("//meta[translate(@property, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')='og:type' and translate(@content, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')='product']")->length > 0) {
                $criteria['MTD'] = true;
            }

            // Étape 4 : Vérifier MTC avec flexibilité sur les guillemets et la casse
            if (preg_match('/@type"\s*:\s*"product"/i', $dom->textContent)) {
                $criteria['MCD'] = true;
            }
           

            break;
        default :
            break;

    }
    return $criteria;
}

function checkClassBody($content) {
    $classBodyPatterns = [
        'node-location-product',
        'node-type-location-product',
        'page-node-type-produit',
        'node-type-produit',
        'node-type-produits',
        'page-node-type-product',
        'is-node-page--product',
        'page--product'
    ];

    foreach ($classBodyPatterns as $pattern) {
        if (stripos($content, $pattern) !== false) {
            return true;
        }
    }
    return false;
}

// Vérifier si le contenu satisfait le critère unique
function checkUniqueCriteria($url, $content, $uniqueCriteria, $cms_name) {
    $criteria = detectCriteria($content, $url, $cms_name);
    return $criteria[$uniqueCriteria] ?? false;
}

function loadJsonContents(string $file): array
{
    global $handle_trace;

    if (!file_exists($file)) {
        fwrite($handle_trace, "Le fichier JSON n'existe pas : $file\n");
        return [];
    }

    $jsonData = file_get_contents($file);
    $entries = json_decode($jsonData, true);

    if (json_last_error() !== JSON_ERROR_NONE) {
        fwrite($handle_trace, "Erreur de décodage JSON dans le fichier $file : " . json_last_error_msg() . "\n");
        return []; 
    }

    return is_array($entries) ? $entries : [];
}

function loadJsonFilesFromDirectory(string $directory): array
{
    global $handle_trace;
    if (!is_dir($directory)) {
        return []; 
    }

    $jsonFiles = glob($directory . DIRECTORY_SEPARATOR . '*.json'); // Trouve tous les fichiers JSON dans le répertoire
    $allData = [];

    fwrite($handle_trace, "tous les fichiers json : \n" . print_r($jsonFiles, true) . "\n");

    foreach ($jsonFiles as $jsonFile) {
        $data = loadJsonContents($jsonFile);
        if (!empty($data)) {
            $allData[] = $data; // Ajoute le contenu du fichier JSON au tableau
        }
    }

    return $allData;
}

/**
 * Extraire le nom de domaine d'une URL.
 *
 * @param string $input L'URL d'entrée.
 * @return string Le nom de domaine extrait.
 */
function recupereBaseUrlDomaine($input) 
{
        
    $pieces = parse_url($input);
    $domain = $pieces['host'] ?? array_shift(explode('/', $pieces['path'], 2));
    if(preg_match('/(?P<domain>[a-z0-9][a-z0-9\-]{1,63}\.[a-z\.]{2,6})$/i', $domain, $regs)){
        return $regs['domain'];
    }
    elseif(preg_match('/(?P<domain>[a-z0-9][a-z0-9\-]{1,63}\.[a-z]{2,63})$/i', $domain, $regs))
    {
        return $regs['domain'];
    }
    return "";
}


function normalizeText($text) {
    // 1. Décoder les entités HTML (&eacute; → é)
    $text = html_entity_decode($text, ENT_QUOTES | ENT_HTML5, 'UTF-8');

    // 2. Décoder les chaînes URL encodées (%C3%A9 → é)
    $text = urldecode($text);

    // 3. Essayer de réparer les caractères mal encodés (ÃƒÂ© → é)
    $text = traitement_d_utf8($text);

    // 4. Convertir en UTF-8 correctement
    $text = mb_convert_encoding($text, 'UTF-8', 'UTF-8');

    // 5. Supprimer les espaces multiples
    $text = preg_replace('/\s+/', ' ', $text);
    $text = trim($text);

    // 6. Mise en minuscules (unicode-safe)
    $text = mb_strtolower($text, 'UTF-8');

    return $text;
}


function alphaNumString($string)
{
    $string = preg_replace('/[^a-zA-Z0-9]/', '', $string);
    return strtolower($string);
}

/**
 * Récupère le contenu d'un sélecteur CSS en utilisant DOMDocument et DOMXPath.
 *
 * @param array $list_selecteur Un tableau contenant la liste des sélecteurs CSS.
 * @param string $key Le type de contenu à récupérer (titre, description, prix, image, categorie, livraison, stock).
 * @param string $url_fiche_produit L'URL de la fiche produit en cours de traitement.
 * @param string $contenu Le contenu HTML de la page.
 * @param array $other_param  Un tableau contenant contenant des autres paramètres.
 * @return array Un tableau contenant les résultats de la récupération du contenu.
 * @global resource $handle_trace Le handle du fichier de suivi.
 */
function recupere_contenu_selecteur(array $list_selecteur, string $key, string $url_fiche_produit, string $contenu, ?string $titre_produit = "" , ?array $other_param = []): array
{
    global $handle_trace;
    global $cssSelectorConverter;

    $domXPath = creerDOMEtXPath($contenu);
    $dom = $domXPath['dom'];
    $xpath = $domXPath['xpath'];

    if ($key == "description") {
        $contenu = preg_replace('#<head(.*?)>(.*?)</head>#is', '', $contenu);
        $contenu = preg_replace('#<footer(.*?)>(.*?)</footer>#is', '', $contenu);
        $contenu = preg_replace('/\s+[a-zA-Z:\-_]+\s*=\s*(?:"\{(.*?)\}"|\'\{(.*?)\}\')/i', '', $contenu);

        @$dom->loadHTML("<html>{$contenu}</html>");

        $xpath = new DOMXPath($dom);

        $root = $dom->saveHTML($xpath->query('//html')[0]);
    }

    // Partie 1 : Ajouter le contenu de <div class="tofixed">
    if ($key == "prix" || $key == "categorie") {
        $tofixed_match = [];
        // Partie 1 : Ajouter le contenu de <div class="tofixed">
        if (
            preg_match('#(<div class="tofixed">.*?</div>)#is', $contenu, $tofixed_match) &&
            (preg_match('#(<div class="pwnt">.*?</div>)#is', $contenu) || preg_match('#(<div class="pwt">.*?</div>)#is', $contenu))
        ) {
            if (!empty($tofixed_match)) {
                $tofixed_content = $tofixed_match[0];
                // Ajoute le contenu après <h1 class="h1">
                $contenu = preg_replace('#(<h1 class="h1">.*?</h1>)#is', "$1$tofixed_content", $contenu);
                // Charger le HTML une seule fois après toutes les modifications
                @$dom->loadHTML("<html>{$contenu}</html>");
                $xpath = new DOMXPath($dom);
            }
        }
        // Partie 2 : Supprimer toutes les occurrences de <div class="featured-products">
        $contenu = preg_replace('#<div\s+class="featured-products".*?>.*?</div>\s*</div>\s*</div>#is', '', $contenu); // supprime toutes les occurrences
        if ($contenu) {
            // Charger le HTML après la suppression
            @$dom->loadHTML("<html>{$contenu}</html>");
            $xpath = new DOMXPath($dom);
        }
        // Partie 3 : Supprimer toutes les occurrences de <div class="products-arrow">
        $elements = $xpath->query('//div[contains(@class, "products-arrow")]');
        foreach ($elements as $element) {
            $element->parentNode->removeChild($element); // Supprime chaque occurrence trouvée
        }
        // Requête XPath pour tous les éléments avec style="display: none"
        $elements = $xpath->query('//*[@style and contains(normalize-space(@style), "display: none")]');
        // Supprimer les éléments trouvés
        foreach ($elements as $element) {
            $element->parentNode->removeChild($element);
        }
        // Recharger le HTML modifié dans $contenu
        $contenu = $dom->saveHTML();
    }

    fwrite($handle_trace, "list_selecteur_nok : " . print_r($list_selecteur_nok, true) . "\n\n");


    $est_selecteur_nok_existe = false;
    $list_selecteur_nok = $other_param["selecteur_nok"];
    
    foreach ($list_selecteur_nok[$key] as $index => $list_cssSelector) 
    {
        if (!is_array($list_cssSelector['selecteur'])) {
            $selecteurs[$key][$index]['selecteur'] = $list_cssSelector['selecteur'] = [$list_cssSelector['selecteur']];
        }

        foreach ($list_cssSelector['selecteur'] as $cssSelector) {
    
            $tab_selecteur = [];
            if ($key == "prix" || $key == "categorie" || $key == 'livraison') {
                $tab_selecteur = $cssSelector;
                $cssSelector = $tab_selecteur['selecteur'];
            
            }

            if (empty($cssSelector)) {
                continue;
            }
            

            $cssSelector = preg_replace('/(\[.*)(\.)(.*\])/', "$1\\.$3", $cssSelector);

            if ($key == "description") {
                $cssSelector = simplifier_selecteur_id_desc($cssSelector);
            }

            // Convertir le sélecteur CSS "div > span" en expression XPath "div/span"
            $cssSelector  = trim($cssSelector);
            $xpathQuery = cssToXPath($cssSelector);


            // Exécuter la requête XPath
            $elements = $xpath->query($xpathQuery);

            if ($elements->length == 0) {
                //traitement des cas exptionnelle xpath qui n'as pas de version css 
                // ceci ( "all selecteur ")[3]
                $debut_css = $fin_css = "";
                $selector_temp = $cssSelector;
                if (preg_match('/^(\()(.*)(\)\[\d+\])$/', $cssSelector, $matches)) {
                    $debut_css = $matches[1]; // Contient '('
                    $selector_temp = $matches[2];            // Contenu capturé entre parenthèses
                    $fin_css = $matches[3]; // Contient ')[3]'

                }
                
                try {
                    $xpathQuery = $debut_css . $cssSelectorConverter->toXPath($selector_temp) . $fin_css;
                    $elements = $xpath->query($xpathQuery);
                } catch(Exception $e) {
                    fwrite($handle_trace, "Erreur cssSelectorConverter: {$e->getMessage()}\n");
                    fwrite($handle_trace, "Selecteur css: {$selector_temp}\n");
                }
            }

            //si on a aucun resultat on réessaye avec le contenu decode de utf_8
            if ($elements->length == 0) 
            {
                $cssSelector_utf8 = mb_convert_encoding($cssSelector,  'UTF-8');
                $xpathQuery = cssToXPath($cssSelector_utf8);
                $elements = $xpath->query($xpathQuery);
            }
            
            foreach ($elements as $element) {
                $element->parentNode->removeChild($element);
                $est_selecteur_nok_existe = $est_selecteur_nok_existe || true;
            }
        }
    }

    if($est_selecteur_nok_existe) {
        $contenu = utf8_decode($dom->saveHTML($dom->documentElement));

        $dom = new DOMDocument('1.0', 'UTF-8');
        @$dom->loadHTML($contenu);
        
        $xpath = new DOMXPath($dom);
    }

    

    $restart = true;
    $index_start = 0;
    $limit_skip_image = [
        1 => "8",
        2 => "3",
        3 => "1",
        4 => 0
    ];
    $max_restart = count($limit_skip_image);
    while ($restart && $index_start < $max_restart) {
        $restart = false;
        $index_start++;
        $has_image_skipped = false;


        $has_selecteur = $get_h1_titre = $has_categ_skipped = false;
        $used_selecteur = [];
        $all_info_titre = $all_info_titre_h1 = $all_info_titre_css = $all_info_titre_h1_css = [];

        foreach ($list_selecteur as $index => $list_cssSelector) {
            if (!is_array($list_cssSelector['selecteur'])) {
                $selecteurs[$key][$index]['selecteur'] = $list_cssSelector['selecteur'] = [$list_cssSelector['selecteur']];
            }

            $new_contenu_produit = $new_contenu_image = $pos_contenu_produit = [];

            // Pour stocker les prix uniques
            $prix_uniques = [];

            // Pour stocker le fil d'ariane
            $fil_d_ariane_complet = [];
            $index_acceuil = $last_fil_ariane = -1;
            $is_fil_ariane = false;

            foreach ($list_cssSelector['selecteur'] as $cssSelector) {
               
               
                fwrite($handle_trace, "Trace selecteur livraison : " . print_r($list_cssSelector, true) . "\n\n");
                

                $tab_selecteur = [];
                if ($key == "prix" || $key == "categorie" || $key == 'livraison') {
                    $tab_selecteur = $cssSelector;
                    $cssSelector = $tab_selecteur['selecteur'];
                    //print_r($cssSelector);
                    if ($key == "prix") {
                        if (!empty($tab_selecteur['type']) && preg_match('/.*cach[eé].*/i', $tab_selecteur['type'])) {
                            if (!empty($cssSelector)) {
                                $prix_contenu_produit = [];
                                $prix_contenu_produit[] =  "Prix caché";
                                // break;
                                continue;
                            } else {
                                continue;
                            }
                        }

                        if (!empty($tab_selecteur['type']) && preg_match('/.*sur.*demande.*/i', $tab_selecteur['type'])) {
                            if (!empty($cssSelector)) {
                                $prix_contenu_produit = [];
                                $prix_contenu_produit[] =  "Prix sur demande";
                                // break;
                                continue;
                            } else {
                                continue;
                            }
                        }
                    }
                }

                if (empty($cssSelector)) {
                    continue;
                }
                $has_selecteur = true;

                $t = false;
                if (preg_match('/\\\\.|\\:/', $cssSelector)) {
                    fwrite($handle_trace, "Selecteur spec : {$cssSelector}\n");
                    $t = true;
                };

                $cssSelector = preg_replace('/(\[.*)(\.)(.*\])/', "$1\\.$3", $cssSelector);

                if ($key == "description") {
                    $cssSelector = simplifier_selecteur_id_desc($cssSelector);
                }

                //trimer le selecteur css
                $cssSelector  = trim($cssSelector);

               

                /*
                * 1. si le getContentCss.ts ne fonctionne pas, utiliser le convertisseur CSS vers XPath
                */
                // Convertir le sélecteur CSS "div > span" en expression XPath "div/span"
                
                    $xpathQuery = cssToXPath($cssSelector);

                    if ($t) {
                        fwrite($handle_trace, "Selecteur param special : {$cssSelector}\n");
                        fwrite($handle_trace, " Selecteur Xpath special : {$xpathQuery}\n");
                    }

                    // Exécuter la requête XPath
                    $elements = $xpath->query($xpathQuery);

                    if ($elements->length == 0) {
                        //traitement des cas exptionnelle xpath qui n'as pas de version css 
                        // ceci ( "all selecteur ")[3]
                        $debut_css = $fin_css = "";
                        $selector_temp = $cssSelector;
                        if (preg_match('/^(\()(.*)(\)\[\d+\])$/', $cssSelector, $matches)) {
                            $debut_css = $matches[1]; // Contient '('
                            $selector_temp = $matches[2];            // Contenu capturé entre parenthèses
                            $fin_css = $matches[3]; // Contient ')[3]'

                        }
                        
                        try {
                        $xpathQuery = $debut_css . $cssSelectorConverter->toXPath($selector_temp) . $fin_css;
                        $elements = $xpath->query($xpathQuery);
                        } catch(Exception $e) {
                            fwrite($handle_trace, "Erreur cssSelectorConverter: {$e->getMessage()}\n");
                            fwrite($handle_trace, "Selecteur css: {$selector_temp}\n");
                        }
                    }

                    //si on a aucun resultat on réessaye avec le contenu decode de utf_8
                    if ($elements->length == 0) 
                    {
                        $cssSelector_utf8 = mb_convert_encoding($cssSelector,  'UTF-8');
                        $xpathQuery = cssToXPath($cssSelector_utf8);
                        $elements = $xpath->query($xpathQuery);
                    }

                    //Pour image , si le nombre d'element du query est 0 et que le selecteur css contient un picture > img 
                    //possibilité des cas des ancien version de html
                    if ($key == "image" && $elements->length == 0 && preg_match('/\b(picture)\s*>\s*(.+)$/', $cssSelector)) {
                        $cssSelector = preg_replace('/\b(picture)\s*>\s*(.+)$/', "$1 $2", $cssSelector);
                        $xpathQuery = cssToXPath($cssSelector);
                        $elements = $xpath->query($xpathQuery);
                    } elseif ($key == "description" && preg_match('/#[^\s]+\s+\.[^\s]+/', $cssSelector) && $elements->length == 0) {
                        $cssSelector = preg_replace('/(#[^\s]+)(\s+)(\.[^\s]+)/', "$1$3", $cssSelector);
                        $xpathQuery = cssToXPath($cssSelector);
                        $elements = $xpath->query($xpathQuery);
                    }
                
                /*
                * 2. Utiliser d'abord le getContentCss.ts pour récuperer le contenu
                */
                // ajouter le selecteur css dans le fichier json
                $get_content_via_js = false;
                if ($elements->length == 0 && isNonXPathCompatibleSelector($cssSelector)) 
                {
                    $old_elements = $elements;

                    //créer un fichier {date(ymdhis)}_contenu_{domaine}.txt qui va contenir le contenu de la page
                    // et un fichie {date(ymdhis)}_selecteur_{domaine}.json qui va contenir les sélecteurs
                    $domaineFile = recupereBaseUrlDomaine($url_fiche_produit);
                    $fileContent =  date('YmdHis') . "_contenu_" . $domaineFile . ".txt";
                    $jsonSelecteur =  date('YmdHis') . "_selecteur_" . $domaineFile . ".json";
                    $repertoireFileContent = $_SERVER['DOCUMENT_ROOT'] . "admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/tools/scraper/files/";

                    $handleFileContent = fopen($repertoireFileContent . $fileContent, 'w');
                    fwrite($handleFileContent, $contenu);    
                    fclose($handleFileContent);

                   
                    
                    $contentElements = [];
                    
                    $arraySelecteur = [$cssSelector];
                    file_put_contents($repertoireFileContent . $jsonSelecteur , json_encode($arraySelecteur, JSON_PRETTY_PRINT));
                    $contentElements = GetContent_via_Css($fileContent, $jsonSelecteur);
                    
                    $has_elements = false;
                    if(!empty($contentElements))
                    {
                        //créer un DOMDocument et un DOMXPath pour le contenu récupéré 
                        $get_content_via_js = true;
                        $content_result = implode("",$contentElements);
                        // $content_result =  utf8_decode($content_result);
                        $content_result =  mb_convert_encoding($content_result, 'ISO-8859-1', 'UTF-8');
                        $domXPath_temp = creerDOMEtXPath("<html><body>" . $content_result . "</body></html>");
                        $dom_temp = $domXPath_temp['dom'];
                        $xpath_temp = $domXPath_temp['xpath'];

                        $elements = $xpath_temp->query("/html/body/*");
                        fwrite($handle_trace, "xpath_temp\n" .  $dom_temp->saveHTML($xpath_temp->query('//html')[0]));

                        if($elements->length > 0) {
                            $has_elements = true;
                        } 

                        if($key == "image" ) {
                            $node_image = $elements;
                            $elements_final = [];
                            foreach ($node_image as $node_image) {
                                $expectedHtml = $dom_temp->saveHTML($node_image);
                                $tagName = $node_image->nodeName;
                                $xpathParts = ["//$tagName"];

                                fwrite($handle_trace, "\n\nexpectedHtml\n" .  $expectedHtml . "\n"); 

                                if ($node_image->hasAttribute('id')) {
                                    $id = $node_image->getAttribute('id');
                                    $xpathParts[] = "[@id='" . $id . "']";
                                }

                                if ($node_image->hasAttribute('class')) {
                                    $class = $node_image->getAttribute('class');
                                    $xpathParts[] = "[contains(concat(' ', normalize-space(@class), ' '), ' " . $class . " ')]";
                                }

                                $query = implode('', $xpathParts);
                                fwrite($handle_trace, "query\n" .  $query . "\n");

                                $nodes = $xpath->query($query);
                                foreach ($nodes as $n) {
                                    $html = $dom->saveHTML($n);
                                    $expected =  $expectedHtml;

                                    fwrite($handle_trace, "html\n" .  $html . "\n");
                                    if (normalizeText($expected) == normalizeText($html) ) {
                                        fwrite($handle_trace, "\nfound\n");
                                        $elements_final[] = $n;
                                        $has_elements = true;
                                    }
                                }
                            }
                            if(!empty($elements_final))
                            {
                                $elements = $elements_final;
                            }
                        }
                    }

                    //supprimer le fichier qui a le contenu de la page
                    unlink($repertoireFileContent . $fileContent);
                    unlink($repertoireFileContent . $jsonSelecteur);


                    if(!$has_elements) {
                       $elements = $old_elements;
                       fwrite($handle_trace, "Aucun élément trouvé avec le getContent_via_Css\n");
                    } 
                }
                 

                // Parcourir les résultats et les afficher
                foreach ($elements as $index_element => $element) {
                    if ($key == "image") {
                        $balise_image = trim($element->nodeName);
                        if ($balise_image == "img") {
                            //verifier si c'est un lien vers autres fiches grace jusqu'au 3eme parent

                            if ($index_start < array_key_last($limit_skip_image)) {
                                $list_fiche_prod = [];
                                $parent_3eme = $element->parentNode;
                                $max_parent = $limit_skip_image[$index_start];
                                $index_parent = 1;
                                while ($index_parent <= $max_parent && $parent_3eme->parentNode && empty($list_fiche_prod)) {

                                    //verifier si le 3eme parent est un <a>
                                    if ($parent_3eme->nodeName === 'a') {
                                        $autre_fiche_prod = trim($parent_3eme->getAttribute('href'));

                                        $list_fiche_prod[] = recupUrlFicheProduit($autre_fiche_prod,  $url_fiche_produit);
                                    }

                                    // Requête XPath pour récupérer tous les éléments <a> descendants (fils et petits-fils)
                                    $anchors = $xpath->query('.//a', $parent_3eme);
                                    foreach ($anchors as $anchor) {
                                        $autre_fiche_prod = trim($anchor->getAttribute('href'));
                                        $list_fiche_prod[] = recupUrlFicheProduit($autre_fiche_prod,  $url_fiche_produit);
                                    }

                                    $parent_3eme = $parent_3eme->parentNode;
                                    $index_parent++;

                                    if ($index_start == 1 && !empty($list_fiche_prod)) {
                                        break;
                                    }
                                }

                                //verifier si le 4eme parent est un <a> est qu'on a pas encore eu des url fiche produit similaire
                                if (empty($list_fiche_prod) && $parent_3eme->nodeName === 'a') {
                                    $autre_fiche_prod = trim($parent_3eme->getAttribute('href'));
                                    $list_fiche_prod[] = recupUrlFicheProduit($autre_fiche_prod,  $url_fiche_produit);
                                }

                                $list_fiche_prod = array_unique(array_filter($list_fiche_prod));

                                if (count($list_fiche_prod) > 0) {
                                    fwrite($handle_trace, "--- Selecteur image : " . $cssSelector . " ---\nImage avant skipped " . $index_start . "\nurl autre fiche produit : " . print_r($list_fiche_prod, true) . "\n\n");
                                    $all_fiche_produit = array_reduce(
                                        $list_fiche_prod,
                                        function ($carry, $url_fiche_prod) {
                                            return $carry && isUrlAccessible($url_fiche_prod, false, true);
                                        },
                                        true
                                    );
                                    if ($all_fiche_produit) {
                                        fwrite($handle_trace, "Image skipped\n\n");
                                        $has_image_skipped = true;
                                        continue;
                                    }
                                }
                            }

                            //extracter les autres urls images dans les attributs 
                            foreach ($element->attributes as $attr) {
                                $src_image_2 = trim($attr->nodeValue);
                                $node_image = trim($attr->nodeName);

                                if ((stripos($node_image, "srcset") !== false)) {
                                    $new_contenu_image = extractImageSrcset($src_image_2, $new_contenu_image);
                                } elseif ($node_image == "src" && isValidURLorRelativePath($src_image_2) && !isImageUrl_NOK($src_image_2)) {
                                    $new_contenu_image[] =  $src_image_2;
                                } elseif (!in_array($node_image, ['id', 'class', 'style', 'src' , 'alt' , 'title'])) {
                                    if (isValidURLorRelativePath($src_image_2)) {
                                        $new_contenu_image[] = $src_image_2;
                                    }
                                }
                            }

                            $background_image = trim($element->getAttribute('style'));
                            $others_images = extractImageUrls($background_image);
                            foreach ($others_images as $other_image) {
                                if (isValidURLorRelativePath($other_image)) {
                                    $new_contenu_image[] = $other_image;
                                }
                            }


                            //recuperation des liens des parents <a> et <source>
                            $parent = $element->parentNode;
                            $max_parent = 3;
                            $max_parent_source = 2;
                            $found_source = $found_link = false;
                            $index_parent = 1;
                            while ($parent && $index_parent <= $max_parent) {

                                //pour les lien a
                                if ($parent->nodeName === 'a' && !$found_link) {
                                    // $href_image = trim($parent->getAttribute('href'));

                                    //si la valeur de href est le lien de la grande image
                                    // avec verification d'autre attribut
                                    foreach ($parent->attributes as $attr) {
                                        $src_image_a_2 = trim($attr->nodeValue);
                                        $node_image = trim($attr->nodeName);
                                        if (!in_array($node_image, ['id', 'class', 'style'])  && isValidURLorRelativePath($src_image_a_2)) {
                                            $new_contenu_image[] =  $src_image_a_2;
                                            $found_link  = true;
                                        }
                                    }
                                }

                                //pour les balises sources
                                if ($index_parent <= $max_parent_source && !$found_source) {
                                    $siblings = $parent->childNodes;
                                    //recuperation des siblings <source>
                                    foreach ($siblings as $sibling) {
                                        if ($sibling->nodeType === XML_ELEMENT_NODE && $sibling->nodeName === 'source') {
                                            $found_source = true;
                                            foreach ($sibling->attributes as $attr) {
                                                $src_image_2 = trim($attr->nodeValue);
                                                $node_image = trim($attr->nodeName);

                                                if ((stripos($node_image, "srcset") !== false)) {
                                                    $new_contenu_image = extractImageSrcset($src_image_2, $new_contenu_image);
                                                }
                                            }
                                        }
                                    }
                                }

                                //si trouver source et a
                                if ($found_source && $found_link) {
                                    break;
                                }

                                // Remonter d'un niveau dans l'arbre DOM
                                $parent = $parent->parentNode;

                                //ne pas considérér les balises <source> comme parent
                                if ($parent->nodeName !== 'source') {
                                    $index_parent++;
                                }
                            }
                        } else {
                            $background_image = trim($element->getAttribute('style'));
                            $others_images = extractImageUrls($background_image);

                            //extracter les autres urls images pas dans attribut style
                            foreach ($element->attributes as $attr) {
                                $attribut_image = trim($attr->nodeValue);
                                if (!in_array(trim($attr->nodeName), ['id', 'class', 'style' , 'alt' , 'title'])) {
                                    $others_images[] = trim($attr->nodeValue);
                                }
                            }

                            foreach ($others_images as $other_image) {
                                if (isValidURLorRelativePath($other_image)) {
                                    $new_contenu_image[] = $other_image;
                                }
                            }
                        }
                    } else if (in_array($key, ["description", "titre", "stock"])) {
                        if (!empty($element->textContent)) {
                            if ($key == "description") {
                                // Sauvegarder le contenu HTML jusqu'à cet élément
                                $partialHtml = $get_content_via_js ? $dom_temp->saveHTML($element) : $dom->saveHTML($element);

                                // Trouver l'index dans le contenu HTML original
                                $position = strpos(preg_replace('/\s+/', ' ', $root), preg_replace('/\s+/', ' ', $partialHtml));
                                $pos_contenu_produit[] =  $position;
                                $new_contenu_produit[] =  traitement_d_utf8($partialHtml);
                            } else {
                                $newText = '';
                                foreach ($element->childNodes as $child) {
                                    if ($child->nodeType === XML_TEXT_NODE) {
                                        // Ajouter le texte normal
                                        $newText .= trim($child->textContent) . ' '; // Ajout d'un espace après chaque texte
                                    } elseif ($child->nodeType === XML_ELEMENT_NODE) {
                                        if ($child->hasAttribute('class') && strpos($child->getAttribute('class'), 'material-icons') !== false) {
                                            // Ignorer l'icône
                                            continue;
                                        }
                                        // Traiter les balises comme <br> et <span>
                                        $newText .= ' ' . $child->textContent; // Ajouter un espace avant le texte de l'élément
                                    }
                                }
                                $newText = trim($newText);
                                if (!empty($newText)) {
                                    $new_contenu_produit[] = traitement_d_utf8($newText);
                                }
                            }
                        } else {
                            $value_balise = trim($element->getAttribute('value'));
                            $content_balise = trim($element->getAttribute('content'));

                            $autre_contenu_produit = !empty($value_balise) ? $value_balise : $content_balise;

                            if (!empty($autre_contenu_produit)) {
                                $new_contenu_produit[] = traitement_d_utf8($autre_contenu_produit);
                            }
                        }
                    } elseif ($key == 'livraison') {
                        if (!empty($element->textContent)) {
                            $new_contenu_produit[] = normaliser_delai_livraison($element->textContent, $tab_selecteur);
                        }
                    } elseif ($key == "prix") {
                        $content_prix = "";

                        if (!empty($element->textContent)) {
                            $content_prix = $element->textContent;
                            $content_prix = traitement_d_utf8($content_prix);
                            
                            // ÉTAPE 1: Nettoyage ciblé qui préserve la structure
                            fwrite($handle_trace, "DEBUG: Avant nettoyage : {$content_prix}\n");
                            fwrite($handle_trace, "DEBUG: Codes ASCII: ");
                            for ($i = 0; $i < strlen($content_prix); $i++) {
                                fwrite($handle_trace, ord($content_prix[$i]) . " ");
                            }
                            fwrite($handle_trace, "\n");
                                                        
                            // Nettoyage qui préserve la structure des prix
                            $content_prix_clean = $content_prix;
                            // Remplacer les espaces insécables par des espaces normaux
                            $content_prix_clean = str_replace(["\xC2\xA0", "\xE2\x80\xAF"], " ", $content_prix_clean);
                            // Remplacer les tirets UTF-8 par tiret simple
                            $content_prix_clean = str_replace(["\xE2\x80\x93", "\xE2\x80\x94"], "-", $content_prix_clean);
                            // Normaliser les espaces multiples
                            $content_prix_clean = preg_replace('/\s+/', ' ', $content_prix_clean);
                            $content_prix_clean = trim($content_prix_clean);

                            fwrite($handle_trace, "DEBUG: Après nettoyage préservant structure: '" . $content_prix_clean . "'\n");

                            // ÉTAPE 2: Test de détection de fourchette sur le texte préservé
                            $is_fourchette = false;
                            
                            // Pattern 1: Détecter prix avec € puis tiret puis prix avec €
                            if (preg_match('/(\d+(?:\s+\d+)*)\s*€\s*-\s*(\d+(?:\s+\d+)*)\s*€/', $content_prix_clean, $matches)) {
                                fwrite($handle_trace, "DEBUG: FOURCHETTE Pattern € - € détectée!\n");
                                $is_fourchette = true;
                            }
                            // Pattern 2: Version plus flexible
                            elseif (preg_match('/(\d+(?:\s+\d+)*)[^-]*-[^-]*(\d+(?:\s+\d+)*)/', $content_prix_clean, $matches)) {
                                fwrite($handle_trace, "DEBUG: FOURCHETTE Pattern flexible détectée!\n");
                                $is_fourchette = true;
                            }
                            
                            if ($is_fourchette) {
                                fwrite($handle_trace, "DEBUG: Match 1 (min): '" . $matches[1] . "'\n");
                                fwrite($handle_trace, "DEBUG: Match 2 (max): '" . $matches[2] . "'\n");

                                $prix_min = trim($matches[1]);
                                $prix_max = trim($matches[2]);

                                // Nettoyage des prix min/max
                                $prix_min = preg_replace('/[^\d.,]/', '', $prix_min);
                                $prix_max = preg_replace('/[^\d.,]/', '', $prix_max);

                                fwrite($handle_trace, "DEBUG: Prix min nettoyé: '$prix_min'\n");
                                fwrite($handle_trace, "DEBUG: Prix max nettoyé: '$prix_max'\n");

                                // Vérifier que les prix sont valides
                                if (!empty($prix_min) && !empty($prix_max) && is_numeric($prix_min) && is_numeric($prix_max)) {
                                    // Construction du prix fourchette final
                                    $devise = !empty($tab_selecteur['devise']) ? htmlspecialchars($tab_selecteur['devise'], ENT_QUOTES, 'UTF-8') : "€";
                                    $content_prix = $prix_min . " " . $devise . " - " . $prix_max . " " . $devise;

                                    fwrite($handle_trace, "DEBUG: Prix fourchette final: '$content_prix'\n");
                                } else {
                                    fwrite($handle_trace, "DEBUG: Prix invalides, traitement normal\n");
                                    $is_fourchette = false;
                                }
                            } else {
                                fwrite($handle_trace, "DEBUG: Aucune fourchette détectée\n");
                            }
                            
                            if (!$is_fourchette) {
                                fwrite($handle_trace, "DEBUG: Traitement prix simple\n");

                                // Nettoyages normaux pour prix simple
                                $content_prix = preg_replace('/[()]/', '', $content_prix);
                                $content_prix = preg_replace('/\d+\s*\'/', '', $content_prix);
                                $content_prix = preg_replace('/\d+\s*%/', '', $content_prix);

                                // Traitement pour prix simple
                                if (!empty($tab_selecteur['devise'])) {
                                    $content_prix = preg_replace('/[a-zA-Z]+/', '', $content_prix);
                                    $content_prix = preg_replace("/(?<!\d)[';,.:*\/+\-](?!\d)/", '', $content_prix);
                                    if (preg_match('/^0([,.]00)?$/', trim($content_prix))) {
                                        break;
                                    }
                                    $content_prix = trim(str_replace($tab_selecteur['devise'], "", $content_prix));
                                    $content_prix .= " " . htmlspecialchars($tab_selecteur['devise'], ENT_QUOTES, 'UTF-8');
                                }
                                
                                // Regex pour gérer les différents formats de prix
                                $montant_sans_euro = preg_replace_callback(
                                    '/(.*)[$€]\s*(\d{0,})/u',
                                    function ($matches) {
                                        if (floatval($matches[1]) == 0) {
                                            return $matches[0];
                                        }
                                        $partie_entiere = $matches[1];
                                        $decimales = !empty($matches[2]) && intval($matches[2]) > 0 ? ',' . $matches[2] : "";
                                        return $partie_entiere . $decimales;
                                    },
                                    $content_prix
                                );
                                $content_prix = $montant_sans_euro;
                            }
                            
                        } else {
                            // Traitement des attributs si pas de textContent
                            $value_balise = trim($element->getAttribute('value'));
                            $content_balise = trim($element->getAttribute('content'));
                            $content_prix = !empty($value_balise) ? $value_balise : $content_balise;

                            if (empty($content_prix)) {
                                foreach ($element->attributes as $attr) {
                                    $data_price = trim($attr->nodeValue);
                                    if ((stripos(trim($attr->nodeName), "price") !== false) && !empty($data_price)) {
                                        $content_prix = $data_price;
                                        break;
                                    }
                                }
                            }
                            $is_fourchette = false;
                        }

                        if (!empty($content_prix)) {
                            
                            // Traitement final SEULEMENT pour les prix non-fourchette
                            if (!$is_fourchette) {
                                if (!empty($tab_selecteur['devise'])) {
                                    $content_prix = preg_replace('/[a-zA-Z]+/', '', $content_prix);
                                    $content_prix = preg_replace("/(?<!\d)[';,.:*\/+\-](?!\d)/", '', $content_prix);
                                    if (preg_match('/^0([,.]00)?$/', trim($content_prix))) {
                                        break;
                                    }
                                    $content_prix = trim(str_replace($tab_selecteur['devise'], "", $content_prix));
                                    $content_prix .= " " . htmlspecialchars($tab_selecteur['devise'], ENT_QUOTES, 'UTF-8');
                                }
                            }
                            
                            // Ajout des indicatifs (TTC/HT)
                            $content_prix .= !empty($tab_selecteur['indicatif'])
                                ? " " . htmlspecialchars($tab_selecteur['indicatif'], ENT_QUOTES, 'UTF-8')
                                : " TTC";
                            
                            // Ajout des mentions
                            if (!empty($tab_selecteur['mention'])) {
                                if ($tab_selecteur['mention'] != "fixe" && $tab_selecteur['mention'] != "fourchette") {
                                    $content_prix = htmlspecialchars($tab_selecteur['mention'], ENT_QUOTES, 'UTF-8') . " " . $content_prix;
                                }
                            }
                            
                            // Ajout du type de prix
                            if (!empty($tab_selecteur['type']) && $tab_selecteur['type'] != "normal") {
                                $content_prix = "Prix " . htmlspecialchars($tab_selecteur['type'], ENT_QUOTES, 'UTF-8') . " " . $content_prix;
                            }
                            
                            // Ajout à la liste des prix uniques
                            if (!in_array($content_prix, $prix_uniques)) {
                                $new_contenu_produit[] = $content_prix;
                                $prix_uniques[] = $content_prix;
                            }
                            break;
                        }
                    } else if ($key == "categorie") {
                        $categ_node = $element->nodeName;
                        $categ_link = recupUrlFicheProduit($element->getAttribute('href'),  $url_fiche_produit);
                        if ($tab_selecteur["type"] != "mention_categorie" && $elements->length > 1) {
                            $is_fil_ariane = true;
                            $last_fil_ariane = $index_element;

                            $nom_categorie = trim($element->textContent, " >");

                            //les mots reguliere à skipper dans les catégorie 
                            if (preg_match('/^(back|pr[eé]cedent|retour)([^\w]|s)*?$/i', $nom_categorie)) {
                                $has_categ_skipped = true;
                                continue;
                            }

                            //skippé si le nom catégorie est le nom du produit et que ce n'est pas un <a>
                            //ne pas skippé si <a> est que 
                            if (
                                ((alphaNumString($titre_produit) == alphaNumString($nom_categorie) || stripos($nom_categorie, trim($titre_produit)) !== false) && ($categ_node !== 'a' || empty($categ_link)))
                                || ($categ_node === 'a' && trim($url_fiche_produit) == trim($categ_link))
                            ) {
                                continue;
                                $has_categ_skipped = true;
                            }

                            // Repérer l'index de l'acceuil
                            if (preg_match('/\b(home|accueil|acceuil)s?\b/i', $nom_categorie)) {
                                //skipper tout autre catégorie si on a déja l'acceuil
                                if ($index_acceuil != -1) {
                                    continue;
                                }
                                $index_acceuil =  $index_element;
                            }

                            // Ignorer les éléments non pertinents (Accueil, Home, etc.)
                            if (!empty($nom_categorie) && !in_array($nom_categorie, $fil_d_ariane_complet)) {
                                // Ajouter l'élément à la liste du fil d'Ariane
                                $fil_d_ariane_complet[] = $nom_categorie;
                            }
                        } else {
                            $nom_categorie = trim($element->textContent);
                            // Convertir la liste de nœuds DOMNodeList en un tableau
                            $elementsArray = iterator_to_array($elements);
                            fwrite($handle_trace, "Contenu categorie (nom_categorie) : " . print_r($elementsArray, true));
                            // Ajouter la catégorie au résultat
                            if (!empty($nom_categorie)) {
                                if (
                                    ((alphaNumString($titre_produit) == alphaNumString($nom_categorie) || stripos($nom_categorie, trim($titre_produit)) !== false) && ($categ_node !== 'a' || empty($categ_link)))
                                    || ($categ_node === 'a' && trim($url_fiche_produit) == trim($categ_link))
                                ) {
                                    continue;
                                    $has_categ_skipped = true;
                                }
                                $new_contenu_produit[] =  traitement_d_utf8($nom_categorie);
                            }
                        }
                    }
                }
            }

            // traitement des liste catégoirie fil d'ariane
            if ($key == "categorie" && $is_fil_ariane) {

                if ($last_fil_ariane != -1 && $last_fil_ariane == $index_acceuil) {
                    $fil_d_ariane_complet = array_reverse($fil_d_ariane_complet);
                }
                // Créer la chaîne du fil d'Ariane avec le séparateur '>'
                $fil_d_ariane_chaine = implode(' > ', $fil_d_ariane_complet);

                // Ajouter le fil d'Ariane final au contenu produit
                if (!empty($fil_d_ariane_chaine)) {
                    $new_contenu_produit[] = traitement_d_utf8($fil_d_ariane_chaine);
                }
            }

            if ($key == "image") {
                fwrite($handle_trace, "--- Liste images avant traitement ---\n");
                fwrite($handle_trace, print_r($new_contenu_image, true) . "\n\n");
            }

            $skip_ddblng = isset($other_param['skip_ddblng']) && $other_param['skip_ddblng'] === true ? true : false;
            $new_contenu_image = filter_images_produit($new_contenu_image, $url_fiche_produit , $skip_ddblng);
            if ($key == "image" && !empty($new_contenu_image)) {
                $new_contenu_produit = $new_contenu_image;
            } else {
                $new_contenu_produit = array_unique(array_filter($new_contenu_produit));
            }

            if (!empty($new_contenu_produit)) {
                $used_selecteur = $list_cssSelector;
                $new_contenu_produit = array_unique($new_contenu_produit);
                if (($key == "titre" && count($new_contenu_produit) > 1) || $get_h1_titre) {
                    if (preg_match('/(h1|h2|h3)/i', $cssSelector)) {
                        $all_info_titre_h1[] = $new_contenu_produit;
                        $all_info_titre_h1_css[] = $list_cssSelector;
                    }
                    $all_info_titre[] = $new_contenu_produit;
                    $all_info_titre_css[] = $list_cssSelector;

                    $get_h1_titre = true;
                } else {
                    break;
                }
            }
        }

        if ($key == "image" && empty($new_contenu_image) && $has_image_skipped) {
            $restart = true;
        }
    }

    



    if ($get_h1_titre) {
        $new_contenu_produit = $all_info_titre[0];
        unset($all_info_titre[0]);

        $new_contenu_produit = findSingleItemInArray($all_info_titre_h1) ?? $new_contenu_produit;

        if (count($new_contenu_produit) > 1) {
            $new_contenu_produit = findSingleItemInArray($all_info_titre) ?? $new_contenu_produit;
        }

        $key_css_titre = array_search($new_contenu_produit, $all_info_titre);

        if ($key_css_titre !== false) {
            $used_selecteur =  $all_info_titre_css[$key_css_titre];
        }
    }

    if ($key == "description") {
        fwrite($handle_trace, "Position description : " . print_r($pos_contenu_produit, true));
        $pos_contenu_produit = array_unique($pos_contenu_produit);
        array_filter($pos_contenu_produit);
        if (count($pos_contenu_produit) == count($new_contenu_produit)) {
            $new_contenu_produit = array_combine($pos_contenu_produit, $new_contenu_produit);
            ksort($new_contenu_produit);
        }
        fwrite($handle_trace, "Contenu description : " . print_r($new_contenu_produit, true));
    } elseif ($key == "livraison" || $key == "stock") {
        if ($key == "stock") {
            if (!empty($new_contenu_produit)) {
                $has_selecteur = false;
            }
            $new_contenu_produit = array_map('traitementContenuStock', $new_contenu_produit);
        }
        $new_contenu_produit = array_unique($new_contenu_produit);
        $new_contenu_produit = array_filter($new_contenu_produit);
    } elseif ($key == "categorie") {
        if ($has_categ_skipped) {
            $has_selecteur = false;
        }

        if (count($new_contenu_produit) == 1 && preg_match('/^\s*(home|accueil|acceuil|produit|retour|mat[eé]riel)s?\s*$/i', $new_contenu_produit[0])) {
            $has_selecteur = false;
            $new_contenu_produit = [];
        }
    }

    if($key == "prix" && empty($new_contenu_produit) && !empty($prix_contenu_produit)) {
        $new_contenu_produit = $prix_contenu_produit;
    } 
    return [
        "new_contenu_produit" => $new_contenu_produit,
        "has_selecteur" => $has_selecteur,
        "used_selecteur" => $used_selecteur,
        "selecteur_nok" => $list_selecteur_nok,
    ];
}

/**
 * fonction qui verifié si le sélecteur a un selecteur css qui n'est pas compatible avec xpath
 *
 * @param string $selector le sélecteur css à vérifier
 * @return bool true si le sélecteur n'est pas compatible avec xpath, false sinon
 */

function isNonXPathCompatibleSelector(string $selector): bool
{
    $patterns = [
        // :has pseudo-class , :not(...) 
        '/:(has|not)\s*\(/i',

        // Pseudo-éléments
        '/::(before|after|first-letter|marker)/i',

        // Pseudo-classes dynamiques
        '/:(hover|active|focus|visited|link)\b/i',

        // :nth-child(2n+1), :nth-last-child(3n-1) , nth-of-type(2n+1), nth-last-of-type(3n-1)
        '/:(nth-child|nth-last-child|nth-of-type|nth-last-of-type)\(\s*[\d]*n\s*[\+\-]\s*\d+\s*\)/i',
    ];

    foreach ($patterns as $pattern) {
        if (preg_match($pattern, $selector)) {
            return true; // Found a non-XPath-compatible feature
        }
    }

    return false; // Safe: only uses basic XPath-compatible selectors
}


/**
 * fonction qui va lancé un shell commande qui va récupere le contenu d'une page avec getContentCss.ts
 *
 * @param string $domaineFile le fichier contenant le contenu html de la page
 * @param string $jsonSelecteur le fichier json contenant le selecteur css
 * @return array  List de html résultat 
 */

 function GetContent_via_Css($fileContent, $jsonSelecteur)
{
    global $handle_trace;
    $result = [];
    
    fwrite($handle_trace, "GetContent_via_Css : {$fileContent} {$jsonSelecteur}\n");
    if(empty($fileContent) || empty($jsonSelecteur)) {
        return $result;
    }
   
    $file = '"--content=' . $fileContent . '"';
    $selecteur = '"--selecteur=' . $jsonSelecteur . '"';

    $repertoireScraper = $_SERVER['DOCUMENT_ROOT'] . "admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/tools/scraper/";

    $params = <<<PARAMETERS
        $file $selecteur "--root={$_SERVER['DOCUMENT_ROOT']}"
    PARAMETERS;

    $commandExportPath = 'export PATH=$PATH:/usr/local/bin;';

    // To Run
    $commandSystem = <<<COMMAND
        cd {$repertoireScraper} && $commandExportPath npm run --silent start:getcontent $params 2>&1
    COMMAND;

    $output = shell_exec($commandSystem);
    fwrite($handle_trace, "output : {$output}\n");

    $result = json_decode($output , true);
    fwrite($handle_trace, print_r($result , true) . "\n");

    return $result;
}


/**
 * Traite une chaîne de caractères représentant l'état du stock d'un produit.
 *
 * Cette fonction analyse le texte d'entrée pour déterminer l'état du stock 
 * d'un produit (par exemple, "En rupture", "En réassort", "En stock") 
 * en utilisant des expressions régulières. Elle peut également extraire 
 * la quantité de produits disponibles lorsque cela est possible.
 *
 * @param string $stock La chaîne de caractères à analyser, représentant l'état du stock.
 *
 * @return string L'état du stock traité. Cela peut être "En rupture", "En réassort", 
 *                "En stock" suivi éventuellement de la quantité entre parenthèses. 
 *                Si aucun état ne correspond, une chaîne vide est retournée.
 *
 * Exemple d'utilisation :
 * $resultat = traitementContenuStock("Il reste 5 produits en stock");
 * // $resultat serait "En stock (5)"
 *
 * Liste des états possibles :
 * - "En rupture" : lorsque le stock est épuisé ou non disponible.
 * - "En réassort" : lorsque le produit est en cours de réapprovisionnement.
 * - "En stock" : lorsque le produit est disponible avec une quantité spécifiée.
 */
function traitementContenuStock($stock)
{
    $final = [];
    // Liste des mentions de stock avec des options pour "en" et "épuisé", et des accents optionnels
    $mentionsStock = [
        "En rupture" => [
            '(?:non|plus\s*en|pas\s+de|(?:en)?\s*ruptures?\s*(?:de)?)\s*stock',
            'stock\s*([eé]puis[eé](s)?)',
            '(?:(non|pas|plus)\s*|in)disponible',
            '(?:article|produit)?\s*[eé]puis[eé](s)?',
            'not\s+in\s*stock|unavailable|articles?\s*vendus?'

        ],
        "En réassort" => [
            '(?:en|de)?\s*(?:r[eé]approvisionnement|r[eé]assort)s?'
        ],
        "En stock" => [
            '(\d+)?\s*(?:produits?)?\s*(?:en)?\s*stock\s*(\d+)?\s*(?:produits?)?',
            'disponib[^\s]+\s+(?:de\s+)?stock',
            '(?:en)?\s*disponible',
            '(?<!\w)(\d+)\s+(?:produits?|restants?|unit[ée]s?)(?!\s+similaires?|\w)',
            'in\s*stock|available',
            '(?:quantit[eéÉ]s?|articles?)?\s+disponibles?[\s\W]*\d+',
            '^(\d+)$'
        ],
    ];
    $traite_stock = "";
    $stock = trim($stock);
    foreach ($mentionsStock as $etat => $patterns) {
        foreach ($patterns as $pattern) {
            $patternStock = '/\b' . $pattern . '\b/iu';
            if (preg_match($patternStock, $stock, $matches)) {
                $traite_stock =  $etat;
                if (!empty($matches[1]) && is_numeric($matches[1])) {
                    $traite_stock .= " (" . $matches[1] . ")";
                } elseif (!empty($matches[2])  && is_numeric($matches[2])) {
                    $traite_stock .= " (" . $matches[2] . ")";
                }
                break 2;
            }
        }
    }
    return $traite_stock;
}

/**
 * Récupère les informations du CMS d'un domaine en utilisant cmseek.
 *
 * @param string $domaine Le domaine à analyser.
 * @param int $id_domaine_ia L'ID du domaine dans la table domaine_scrapping_produit_ia.
 * @return void
 * @global mysqli $LINK_MYSQLI_HELLOPRO_IA La connexion à la base de données.
 */
function get_cms_domaine(string $domaine, int $id_domaine_ia): void
{
    $verif_cms = "SELECT
                        cms_dspi
                    FROM
                        domaine_scrapping_produit_ia DSPI
                    WHERE
                        id_domaine_scrapping_produit_ia = '" . hellopro_traitement_donnee_annuaire_bo($id_domaine_ia) . "'
                        AND (  cms_dspi IS NULL
                            OR cms_dspi = '' )";
    $res_verif_cms = mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $verif_cms) or die(hellopro_mysql_error($verif_cms, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));

    if (mysqli_num_rows($res_verif_cms) > 0) {
        $repertoire_cmseek = $_SERVER['DOCUMENT_ROOT']  . "admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/tools/cmseek/";
        shell_exec('cd ' . $repertoire_cmseek . ' && yes | python3 cmseek.py -u ' . $domaine);
        $path = $repertoire_cmseek . 'Result/' . $domaine . '/cms.json';
        $info_cms = file_get_contents($path);

        sql_update_info(
            [
                "cms_dspi" => $info_cms
            ],
            "domaine_scrapping_produit_ia",
            [
                "id_domaine_scrapping_produit_ia" => $id_domaine_ia
            ]
        );
    }
}

function supprimer_attr_id_lass($contenu)
{
    $contenu = preg_replace('/id\s*=\s*(?:"|\')[^"\']*(?:"|\')/Ui', '', $contenu);
    $contenu = preg_replace('/class\s*=\s*(?:"|\')[^"\']*(?:"|\')/Ui', '', $contenu);

    return $contenu;
}

/**
 * Recherche des occurrences de mots-clés dans le contenu HTML et les attributs ID/classe.
 *
 * Cette fonction analyse un contenu HTML donné et une liste d'ID/classes pour trouver
 * des correspondances avec des mots-clés prédéfinis. Elle est particulièrement utile
 * pour identifier des éléments liés aux éléments dans une page web.
 *
 * @param string $contenu     Le contenu HTML à analyser.
 * @param array  $listIDClass Liste des ID et classes à vérifier.
 * @param int  $idDomaine
 * @return array              Un tableau associatif contenant les résultats de la recherche.
 */
function cherche_occurence(string $contenu, array $listIDClass, $idDomaine): array
{
    global $ComparateurSelecteur;

    // Définition des mots-clés et patterns pour la recherche
    $mots_cles = buildTabKeyword($idDomaine);

    $resultats = [
        'contenu' => [],
        'idClass' => []
    ];

    // Recherche des mots-clés dans le contenu
    $contenu_modifie = supprimer_attr_id_lass($contenu);
    foreach ($mots_cles['contenu'] as $type => $mots) {
        $resultats['contenu'][$type] = [];
        foreach ($mots as $key => $pattern) {
            $count = preg_match_all("/$pattern/iu", $contenu_modifie, $matches);
            $resultats['contenu'][$type][$key] = $count;
        }
    }

    // Recherche des mots-clés dans les ID/classes
    foreach ($listIDClass as $IDClass) {
        foreach ($mots_cles['idClass'] as $type => $mots) {
            $resultats['idClass'][$type] = [];
            foreach ($mots as $key => $pattern) {
                if (preg_match("/$pattern/i", $IDClass)) {
                    $checkIdsInSelector = $ComparateurSelecteur->checkIdsInCssSelector($IDClass);

                    if (!empty($checkIdsInSelector['id'])) {
                        $ID = str_replace($checkIdsInSelector['id'], '', $IDClass);
                        $resultats['idClass'][$type][] = $ID;
                    } else {
                        $resultats['idClass'][$type][] = $IDClass;
                    }
                    break 2; // Sort des deux boucles dès qu'une correspondance est trouvée
                }
            }
        }
    }

    return $resultats;
}

/**
 * Traite un tableau d'éléments de données, en comparant les éléments par catégories.
 * Chaque catégorie est traitée indépendamment, et les ID scraping des URLs éligibles sont collectées pour chaque catégorie.
 * 
 * @param array $data Le tableau d'entrée des éléments de données à traiter.
 * @param array $ignoreData Le tableau contenant la liste des IDs à ne pas prendre en compte dans le traitement (Cas max token ChatGPT)
 * @return array Un tableau associatif où les clés sont les catégories et les valeurs sont des tableaux des ID scraping des URLs éligibles.
 */
function processDataElementsByCategory(array $data, array $ignoreData): array
{
    $result = [];
    $categories = [];

    // Identifier toutes les catégories uniques à travers tous les éléments
    foreach ($data as $element) {
        if (isset($element['domData']['idClass'])) {
            $categories = array_merge($categories, array_keys($element['domData']['idClass']));
        }
        if (isset($element['domData']['contenu'])) {
            $categories = array_merge($categories, array_keys($element['domData']['contenu']));
        }
    }
    $categories = array_unique($categories);

    // Traiter chaque catégorie indépendamment
    foreach ($categories as $category) {
        $ignoreDataCategory = array_key_exists($category, $ignoreData) ? $ignoreData[$category] : [];
        $eligibleUrlsId = processCategory($data, $category, $ignoreDataCategory);
        if (!empty($eligibleUrlsId)) {
            $result[$category] = $eligibleUrlsId;
        }
    }

    return $result;
}

/**
 * Traite une catégorie spécifique à travers tous les éléments de données.
 *
 * @param array $data Le tableau d'entrée des éléments de données à traiter.
 * @param string $category La catégorie à traiter.
 * @param array $ignoreData Le tableau contenant la liste des IDs à ne pas prendre en compte dans le traitement (Cas max token ChatGPT)
 * @param StringComparisonConfig|null $config La configuration par défaut pour la comparaison de texte
 * @return array Le tableau traité des éléments de données pour la catégorie donnée.
 */
function processCategory(array $data, string $category, array $ignoreData, $config = null): array
{
    $firstId = [];
    if (is_null($config)) {
        $config = new StringComparisonConfig();
    }

    for ($index = 0; $index < count($data); $index++) {
        if (!isset($data[$index])) continue;

        $selectedElement = $data[$index];

        if (in_array($selectedElement['id'], $ignoreData)) {
            $data[$index] = null;
            continue;
        }

        //ajouter le premier id produit par défaut
        if(empty($firstId))
        {
            $firstId[] = $selectedElement['id'];
        }

        $selectedCategoryArray = $selectedElement['domData'];
        $selectedCategoryIdClass = $selectedCategoryArray['idClass'][$category] ?? [];
        $selectedCategoryContenu = $selectedCategoryArray['contenu'][$category] ?? [];

        for ($compareIndex = $index + 1; $compareIndex < count($data); $compareIndex++) {
            if (!isset($data[$compareIndex])) continue;

            $compareElement = $data[$compareIndex];

            if (in_array($compareElement['id'], $ignoreData)) {
                $data[$compareIndex] = null;
                continue;
            }

            $compareCategoryArray = $compareElement['domData'];
            $compareCategoryIdClass = $compareCategoryArray['idClass'][$category] ?? [];
            $compareCategoryContenu = $compareCategoryArray['contenu'][$category] ?? [];

            $uniqueToSelected = array_diff($selectedCategoryIdClass, $compareCategoryIdClass);
            $uniqueToCompare = array_diff($compareCategoryIdClass, $selectedCategoryIdClass);

            $action = determineAction($uniqueToSelected, $uniqueToCompare, $selectedCategoryContenu, $compareCategoryContenu, $config);

            switch ($action) {
                case 'keep_selected':
                    $data[$compareIndex] = null;
                    break;
                case 'keep_compare':
                    $selectedElement = $compareElement;
                    $data[$compareIndex] = null;
                    break;
                case 'keep_both':
                    // Ne rien faire, garder les deux éléments
                    break;
            }
        }

        $data[$index] = $selectedElement;
    }

    $data = array_values(array_filter($data));

    $resProcess = array_column($data, 'id');
    
    if(empty($resProcess))
    {
        $resProcess = $firstId;
    }

    return $resProcess;
}

/**
 * Détermine l'action à prendre en fonction de la comparaison des idClass et contenu.
 *
 * @param array $uniqueToSelected Valeurs idClass uniques dans l'élément sélectionné.
 * @param array $uniqueToCompare Valeurs idClass uniques dans l'élément de comparaison.
 * @param array $selectedContenu Valeurs de contenu de l'élément sélectionné.
 * @param array $compareContenu Valeurs de contenu de l'élément de comparaison.
 * @param StringComparisonConfig|null $config La configuration par défaut pour la comparaison de texte
 * @return string L'action à prendre : 'keep_selected', 'keep_compare', ou 'keep_both'.
 */
function determineAction(array $uniqueToSelected, array $uniqueToCompare, array $selectedContenu, array $compareContenu, $config = null): string
{
    if (is_null($config)) {
        $config = new StringComparisonConfig();
    }
    $analyzer = new StringDifferenceAnalyzer($config);

    // Compte les différences significatives
    $significantDifferences = 0;
    foreach ($uniqueToSelected as $selected) {
        foreach ($uniqueToCompare as $compare) {
            $analysis = $analyzer->analyze($selected, $compare);
            if (!$analysis['negligible']) {
                $significantDifferences++;
            }
        }
    }

    // Si peu de différences significatives, traiter comme similaire
    if ($significantDifferences <= $config->getMaxDifferences()) {
        if (!empty($selectedContenu)) {
            $contenuComparison = compareArrays($selectedContenu, $compareContenu);
            if ($contenuComparison === 'array1_superior' || $contenuComparison === 'equal') {
                return 'keep_selected';
            } elseif ($contenuComparison === 'array2_superior') {
                return 'keep_compare';
            }

            return 'keep_both';
        }
        return 'keep_selected';
    }

    if (empty($uniqueToSelected) && empty($uniqueToCompare)) {
        // Les valeurs idClass sont identiques, comparer le contenu
        if (!empty($selectedContenu)) {
            $contenuComparison = compareArrays($selectedContenu, $compareContenu);
            if ($contenuComparison === 'array1_superior' || $contenuComparison === 'equal') {
                return 'keep_selected';
            } elseif ($contenuComparison === 'array2_superior') {
                return 'keep_compare';
            }

            return 'keep_both';
        }
        return 'keep_compare'; // Par défaut, garder l'élément de comparaison si le contenu est vide
    } elseif (empty($uniqueToSelected)) {
        // L'élément de comparaison a plus de valeurs idClass
        if (!empty($selectedContenu)) {
            $contenuComparison = compareArrays($selectedContenu, $compareContenu);
            if ($contenuComparison === 'array1_superior' || $contenuComparison === 'alternating') {
                return 'keep_both';
            }
        }
        return 'keep_compare';
    } elseif (!empty($uniqueToSelected) && !empty($uniqueToCompare)) {
        // Les deux éléments ont des valeurs idClass uniques
        return 'keep_both';
    } else {
        // L'élément sélectionné a plus de valeurs idClass
        if (!empty($selectedContenu)) {
            $contenuComparison = compareArrays($selectedContenu, $compareContenu);
            if ($contenuComparison === 'array2_superior' || $contenuComparison === 'alternating') {
                return 'keep_both';
            }
        }
        return 'keep_selected';
    }
}

/**
 * Compare deux tableaux associatifs et détermine la relation entre leurs valeurs.
 *
 * @param array $array1 Le premier tableau à comparer
 * @param array $array2 Le second tableau à comparer
 * @return string Le résultat de la comparaison :
 *                - "array1_superior" si toutes les valeurs de $array1 sont supérieures à celles de $array2
 *                - "array2_superior" si toutes les valeurs de $array2 sont supérieures à celles de $array1
 *                - "equal" si toutes les valeurs des deux tableaux sont exactement les mêmes
 *                - "alternating" si aucune des conditions ci-dessus n'est remplie
 * @throws InvalidArgumentException si les tableaux ont des clés différentes ou sont vides
 */
function compareArrays(array $array1, array $array2): string
{
    if (empty($array1) || empty($array2) || array_keys($array1) !== array_keys($array2)) {
        throw new InvalidArgumentException("Les tableaux doivent être non vides et avoir les mêmes clés");
    }

    $array1Superior = true;
    $array2Superior = true;
    $equal = true;

    foreach ($array1 as $key => $value1) {
        $value2 = $array2[$key];

        if ($value1 < $value2) {
            $array1Superior = false;
            $equal = false;
        } elseif ($value1 > $value2) {
            $array2Superior = false;
            $equal = false;
        }

        if (!$array1Superior && !$array2Superior && !$equal) {
            return "alternating";
        }
    }

    if ($equal) {
        return "equal";
    } elseif ($array1Superior) {
        return "array1_superior";
    } elseif ($array2Superior) {
        return "array2_superior";
    } else {
        return "alternating";
    }
}

/**
 * Crée un objet DOMDocument à partir d'une chaîne HTML et initialise un objet DOMXPath.
 *
 * Cette fonction crée un nouveau document DOM, charge le contenu HTML fourni,
 * et prépare un objet XPath pour des requêtes ultérieures sur le document.
 *
 * @param string $contenu Le contenu HTML à charger dans le document DOM.
 * 
 * @return array Un tableau associatif contenant les objets DOMDocument et DOMXPath.
 *
 * @throws \Exception Si une erreur survient lors du chargement du HTML.
 */
function creerDOMEtXPath($contenu)
{
    $dom = new DOMDocument('1.0', 'utf-8');
    @$dom->loadHTML("<html>{$contenu}</html>");
    $xpath = new DOMXPath($dom);

    return ['dom' => $dom, 'xpath' => $xpath];
}

/**
 * Récupère les informations d'un prompt ChatGPT à partir de son ID.
 *
 * @param int $id_prompt L'ID du prompt à récupérer.
 * @return array Un tableau contenant les informations du prompt (contenu et température).
 * @global mysqli $LINK_MYSQLI_HELLOPRO_IA La connexion à la base de données.
 */
function get_prompt(int $id_prompt): array
{
    $sql_prompt = "
        SELECT
            id_action_prompt_chatgpt,
            temperature_apc,
            contenu_prompt_apc
        FROM action_prompt_chatgpt APC
        WHERE id_action_prompt_chatgpt = '" . hellopro_traitement_donnee_annuaire_bo($id_prompt) . "'
    ";
    $res_prompt = mysqli_query($GLOBALS['LINK_MYSQLI_ANNUAIRE_BO'], $sql_prompt) or die(hellopro_mysql_error($sql_prompt, $GLOBALS['LINK_MYSQLI_ANNUAIRE_BO']));
    $lig_prompt = mysqli_fetch_assoc($res_prompt);
    return [
        "prompt" => $lig_prompt['contenu_prompt_apc'],
        "temperature" => $lig_prompt['temperature_apc'],
    ];
}

function getPromptTemperature(string $type): array
{
    //PROD
    $typesData = [
        'titre' => 25,
        'description' => 26,
        'prix' => 28,
        'image' => 27,
        'categorie' => 33,
        'livraison' => 34,
        'stock' => 35,
    ];

    return get_prompt($typesData[$type]);
}

/**
 * Récupère le sélecteur CSS pour un type de contenu donné en utilisant ChatGPT.
 *
 * @param Gpt $gpt L'instance de la classe Gpt pour interagir avec l'API ChatGPT.
 * @param string $contenu Le contenu HTML de la page à partir de laquelle extraire le sélecteur.
 * @param string $type Le type de sélecteur (titre, description, prix, image, categorie, livraison, stock).
 * @param array $all_prompt Un tableau contenant tous les prompts ChatGPT.
 * @param string $domaine Le nom de domaine de la page en cours de scrapping.
 * @param string|null $titre_produit Le titre du produit (facultatif).
 * @param string $url_produit L'URL du produit (facultatif)
 * @return array Un tableau contenant les résultats de la récupération du sélecteur.
 * @global resource $handle_trace Le handle du fichier de suivi.
 * @global array $all_temperature Un tableau contenant les températures pour chaque type de prompt.
 */
function recupere_selecteur($gpt, $contenu, $type, $all_prompt, $domaine, $titre_produit = "", $url_produit = ""): array
{
    global $handle_trace;
    global $all_temperature;

    $result = [];
    $result['success'] = false;

    $prompt = processPrompt($domaine, $contenu, $type, $titre_produit, $url_produit);

    fwrite($handle_trace, "Lancement Prompt :" . print_r([
        "url"   => $domaine,
        "type"  => $type,
        "titre" => $titre_produit,
    ], true) . "\n\n");

    if (isset($all_temperature[$type])) {
        $gpt->set_temperature($all_temperature[$type]);
        fwrite($handle_trace, "Temperature ({$type}): " . $all_temperature[$type] . "\n\n");
    } else {
        $gpt->set_temperature(0.1); // Valeur par défaut si aucune température n'est spécifiée
    }

    //attendre une seconde par prompt chagpt
    sleep(1);

    $data_array = [
        "prompt" => check_encodage($prompt)
    ];
    $resultat = $gpt->post($data_array);


    fwrite($handle_trace, "Reponse ChatGPT ({$type}): \n" . print_r($resultat, true) . "\n\n");

    //relancer l'appel api chatgpt une fois si c'est timeout apres 10s
    // if (!empty($resultat["response"]["error"]) && $resultat["response"]["error"]['code'] == "TIMEOUT") { #gemini 
    if (!empty($resultat["response"]["error"]) && $resultat["response"]["error"]['code'] == "request_timeout") {
        sleep(10);
        $resultat = $gpt->post($data_array);
        fwrite($handle_trace, "Relance chatgpt :\n" . print_r($resultat, true));
    }


    if (isset($resultat["response"]["error"]) && !empty($resultat["response"]["error"])) {
        $result['erreur'] = var_export($resultat["response"]["error"], true);
        $erreur_chatgpt = "Erreur ChatGPT";
        // if ($resultat["response"]["error"]['code'] == "MAX_TOKENS_EXCEEDED") { # gemini
        if ($resultat["response"]["error"]['code'] == "context_length_exceeded") {
            add_erreur_max_prompt(check_encodage($prompt), $domaine);
            $erreur_chatgpt .= " : Maximum token ChatGPT atteint";
        } elseif ($resultat["response"]["error"]['code'] == "string_above_max_length") {
            $erreur_chatgpt .= ": Maximum longueur input atteint";
        }
    } else {
        // $selecteur = $resultat["response"]['candidates'][0]['content']['parts'][0]['text']; #gemini
        $selecteur = $resultat["response"]['choices'][0]['message']['content'];

        $selecteur   = preg_replace('#\s+#', ' ', $selecteur);
        $tab_content = json_decode($selecteur, true);

        if (json_last_error() !== JSON_ERROR_NONE) {
            // Initialiser un tableau pour stocker les valeurs trouvées
            $matches_2 = array();

            if (preg_match('/\{(.*)\}/m', $selecteur, $matches_2)) {

                $matched_string = $matches_2[0];
                $tab_content = json_decode($matched_string, true);
            } else {
                // $trimmed = trim($selecteur, "`json");
                $trimmed = preg_replace('/^[^{]*|[^}]*$/', '', $selecteur);
                $tab_content = json_decode($trimmed, true);
            }
        }

        $list_selecteur = [];
        if ($type == "titre") {
            foreach ($tab_content[$type] as $res_selecteur) {
                $input_s = is_array($res_selecteur['selecteur']) ? $res_selecteur['selecteur'] : [$res_selecteur['selecteur']];
                $list_selecteur[] = [
                    "selecteur" => $input_s
                ];
            }
        } elseif ($type == "prix" || $type == "categorie") {
            $selecteur_prix = [];
            foreach ($tab_content[$type] as $res_selecteur) {
                $selecteur_prix[] = $res_selecteur;
            }

            $list_selecteur[] = [
                "selecteur" => $selecteur_prix
            ];
        } else {
            $input_s2 = is_array($tab_content[$type]['selecteur']) ? $tab_content[$type]['selecteur'] : [$tab_content[$type]['selecteur']];

            if ($type == "description") {
                $tab_sel_carac         = is_array($tab_content['caracteristique']['selecteur']) ? $tab_content['caracteristique']['selecteur'] : [$tab_content['caracteristique']['selecteur']];
                $tab_sel_utilisation   = is_array($tab_content['utilisation']['selecteur']) ? $tab_content['utilisation']['selecteur'] : [$tab_content['utilisation']['selecteur']];
                $tab_sel_avantage      = is_array($tab_content['avantage']['selecteur']) ? $tab_content['avantage']['selecteur'] : [$tab_content['avantage']['selecteur']];
                $tab_sel_pt_fort       = is_array($tab_content['point-fort']['selecteur']) ? $tab_content['point-fort']['selecteur'] : [$tab_content['point-fort']['selecteur']];
                $tab_sel_application   = is_array($tab_content['application']['selecteur']) ? $tab_content['application']['selecteur'] : [$tab_content['application']['selecteur']];
                $tab_sel_option        = is_array($tab_content['option']['selecteur']) ? $tab_content['option']['selecteur'] : [$tab_content['option']['selecteur']];
                $tab_sel_titre_section = is_array($tab_content['titre-section']['selecteur']) ? $tab_content['titre-section']['selecteur'] : [$tab_content['titre-section']['selecteur']];
                $input_s2 = array_merge(
                    $input_s2,
                    $tab_sel_carac,
                    $tab_sel_utilisation,
                    $tab_sel_avantage,
                    $tab_sel_pt_fort,
                    $tab_sel_application,
                    $tab_sel_option,
                    $tab_sel_titre_section
                );
                $input_s2 = array_unique($input_s2);
            }

            if ($type == 'livraison') {
                $selecteur_livraison = array();
                $selecteur_livraison[] = [
                    "selecteur" => $tab_content[$type]['selecteur'],
                    "unite"     => $tab_content[$type]['unite'],
                    "label"     => $tab_content[$type]['label'],
                ];

                $list_selecteur[] = 
                [
                    "selecteur" => $selecteur_livraison
                ];
            } else {
                $list_selecteur[] = [
                    "selecteur" => $input_s2
                ];
            }
        }

        $new_list_selecteur = [];
        if (!empty($list_selecteur)) {
            $new_list_selecteur = $list_selecteur;
            $result['success'] = true;
        } else {
            $result['success'] = false;
            $result['erreur'] = "Retour vide par CHATGPT \n" . json_encode($resultat);
        }

        $result['res'] = $new_list_selecteur;
        $result['last_selecteur'] = $list_selecteur;
    }

    return $result;
}

function processPrompt($domaine, $contenu, $type, $titreProduit = '', $urlProduit = '', $selecteur = [], $reverifierSelecteur = false, $checkTokenLimit = false)
{
    /**
     * Limite de token pour ChatGPT, on enlève ensuite les valeurs ci-dessous par rapport au plafond
     * Plafond : 128000
     * 
     * Cas titre : {
     *  "titre": 60
     *  "url" : 150
     *  "output" : 80
     * }
     * 
     * Cas description : {
     *  "titre": 60
     *  "output": 300
     * }
     * 
     * Cas prix : {
     *  "titre": 60
     *  "output": 250
     * }
     * 
     * Cas image : {
     *  "titre": 60
     *  "output": 320
     * }
     * 
     * Cas stock : {
     *  "titre": 60
     *  "output": 80
     * }
     * 
     * Cas livraison : {
     *  "titre": 60
     *  "output": 80
     * }
     * 
     * Cas categorie : {
     *  "titre": 60
     *  "output": 50
     * }
     * 
     * Cas description2 : {
     *  "titre": 60
     *  "selecteur": ? → On a mis à 200
     *  "output": 300
     * }
     */
    $tokenLimits = [
        'titre' => 127710,
        'description' => 127640,
        'prix' => 127690,
        'image' => 127620,
        'livraison' => 127860,
        'stock' => 127860,
        'categorie' => 127890,
        'description2' => 127440,
    ];

    global $all_prompt;
    global $id_upload;
    global $id_domaine;

    // Préparer le contenu HTML en fonction du type de sélecteur
    if ($type == "description" || $type == "prix") {
        $contenu = preg_replace('#<head(.*?)>(.*?)</head>#is', '', $contenu);
        $contenu = preg_replace('#<footer(.*?)>(.*?)</footer>#is', '', $contenu);
        if ($type == "description") {
            $contenu = preg_replace('/\s+[a-zA-Z:\-_]+\s*=\s*(?:"\{(.*?)\}"|\'\{(.*?)\}\')/i', '', $contenu);
        }

        if ($type == "prix") {
            $contenu = preg_replace('/\s\w+\s*=\s*"data:[^"]+;base64,[^"]+"/i', '', $contenu);
            $contenu = preg_replace('#<select(.*?)>(.*?)</select>#is', '', $contenu);
        }
    } else if ($type == "image") {
        $contenu = preg_replace('/\s\w+\s*=\s*"data:[^"]+;base64,[^"]+"/i', '', $contenu);
    }

    $prompt = $all_prompt[$type];

    if ($reverifierSelecteur) {
        $prompts = [
            "description" => get_prompt(32),
            // "titre" => get_prompt(/*@todo*/),
            // "prix"  => get_prompt(/*@todo*/),
            // "image" => get_prompt(/*@todo*/),
        ];

        $prompt = $prompts[$type]['prompt'];
    }

    $pattern = '/\{(.*?)\}/';

    // Initialiser un tableau pour stocker les valeurs trouvées
    $matches = array();

    // Utiliser preg_match_all pour trouver toutes les correspondances
    preg_match_all($pattern, $prompt, $matches);


    foreach ($matches[1] as $key) {
        if (preg_match("/.*CONTENU_PAGE_PRODUIT.*/", $key)) {
            $prompt = str_replace("{" . $key . "}", $contenu, $prompt);
        } elseif (preg_match("/.*TITRE_PRODUIT.*/", $key)) {
            $prompt = str_replace("{" . $key . "}", $titreProduit, $prompt);
        } else if (preg_match("/.*URL_PAGE_PRODUIT.*/", $key)) {
            $prompt = str_replace("{" . $key . "}", $urlProduit, $prompt);
        } elseif (preg_match("/.*SELECTEUR.*/", $key)) {
            $prompt = str_replace("{" . $key . "}", implode(' , ', $selecteur['selecteur']), $prompt);
        }
    }

    if ($checkTokenLimit) {
        try {
            $counter = TokenCounter::getInstance();

            if ($reverifierSelecteur) {
                $type = 'description2';
            }

            $tokenLimit = $tokenLimits[$type];

            // INFO: N'oubliez pas de correspondre la version du modèle ChatGPT utilisé et celle passée en paramètre ici
            $ID = $id_upload;
            if (!empty($id_domaine)) $ID = $id_domaine;
            $count = $counter->count($prompt, $ID, $domaine, 'gpt-4o');

            if ($count > $tokenLimit) {
                return true;
            }

            return false;
        } catch (\Throwable $th) {
            $trace = $th->getTrace()[0];
            $name_function = empty($trace["class"]) ? "::" . $th->getLine() : $trace["class"] . "::" . $trace["function"] . "()::" . $th->getLine();
            add_erreur([
                "-----------------------------------------------\n",
                $th->getCode() . " → " . $th->getMessage() . " :: " . $name_function . "\n",
                "ID: " . $ID . "\n",
                "domaine: " . $domaine . "\n",
                "type: " . $type . "\n",
                "reverifierSelecteur: " . ($reverifierSelecteur) ? 'true' : 'false' . "\n\n",
            ]);
        }
    }

    return $prompt;
}


/**
 * Ajoute une erreur au fichier d'erreurs.
 *
 * @param array $erreurs Un tableau contenant les messages d'erreurs à ajouter.
 * @return void
 * @global string $repertoire Le répertoire du fichier d'erreurs.
 * @global string $fichier_erreur Le nom du fichier d'erreurs.
 * @global int $count_erreur Le compteur d'erreurs.
 */
function add_erreur(array $erreurs, ?string $pathError = null): void
{
    global $repertoire;
    global $fichier_erreur;
    global $count_erreur;

    $filePathError = $repertoire . $fichier_erreur;
    if (!empty($pathError)) {
        $filePathError = $pathError;
    }

    $handle_erreur = fopen($_SERVER['DOCUMENT_ROOT'] . $filePathError, "a+");
    foreach ($erreurs as $erreur) {
        fwrite($handle_erreur, $erreur);
    }
    fclose($handle_erreur);
    $count_erreur++;
}

function createLogFolder(): string
{
    $path = 'admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/tracking/' . date('Y') . '/' . date('m') . '/';

    if (!is_dir($_SERVER['DOCUMENT_ROOT'] . $path)) {
        if (!mkdir($_SERVER['DOCUMENT_ROOT'] . $path, 0777, true)) {
            return false;
        }
    }

    return $path;
}

function getErrorLogFile(string $domaine): string
{
    $folder = createLogFolder();

    if (!$folder) {
        return false;
    }

    $pathFile = "erreur-{$domaine}.txt";

    return $folder . $pathFile;
}

function getDomaine($id_domaine)
{
    $sql_get_domaine =
        "SELECT domaine_dspi AS domaine
        FROM domaine_scrapping_produit_ia DSPI
        WHERE id_domaine_scrapping_produit_ia = '" . hellopro_traitement_donnee_annuaire_bo($id_domaine) . "'
    ";
    $res_get_domaine = mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_get_domaine) or die(hellopro_mysql_error($sql_get_domaine, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));

    return $res_get_domaine->fetch_assoc()['domaine'];
}

function getUrlByUploadOrDomain($idUploadTraitement = '', $idDomaineTraitement = ''): array
{
    $dataArray = $dataToProcess = [];

    $conditionSqlUrl = <<<SQL
        AND id_upload_scrapping_produit_sfpi = {$idUploadTraitement}
    SQL;

    if (!empty($idDomaineTraitement)) {
        $conditionSqlUrl = <<<SQL
            AND id_domaine_scrapping_produit_sfpi = {$idDomaineTraitement}
            AND (
                id_upload_scrapping_produit_sfpi IS NULL
                OR id_upload_scrapping_produit_sfpi = ''
            )
        SQL;
    }

    $sql_get_url =
        "SELECT
            id_scrapping_fiche_produit_ia,
            id_domaine_scrapping_produit_sfpi,
            url_sfpi
        FROM scrapping_fiche_produit_ia SFPI
        WHERE
            has_content = 1 AND est_dernier_sfpi = 1
            {$conditionSqlUrl}
    ";
    $res_get_url = mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_get_url) or die(hellopro_mysql_error($sql_get_url, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));

    $tab_pattern_url = [
        "\/p\/?",
        "\/prod\/?",
        "\/produits?\/?",
        "\/products?\/?",
        "\/products?-detail\/?",
    ];
    $pattern = implode("|",$tab_pattern_url);
    $pattern = "/(". $pattern .")$/i";

    while ($ligne_url = $res_get_url->fetch_assoc()) {
        $currentUrl = trim($ligne_url['url_sfpi']);
        
        if(preg_match($pattern,$currentUrl)) {
            continue;
        }

        $idScraping = $ligne_url['id_scrapping_fiche_produit_ia'];
        $idDomaine = $ligne_url['id_domaine_scrapping_produit_sfpi'];
        if (!empty($idDomaineTraitement)) {
            $domaine = getDomaine($idDomaine);
        } else {
            $domaine = recupere_domaine($currentUrl);
        }

        if (empty($domaine)) {
            add_erreur(
                [
                    "-----------------------------------------------\n",
                    "Erreur recuperation domaine : " . $currentUrl . "\n\n"
                ]
            );
            continue;
        }

        $arrayContenu = getContenuHTML($idScraping);
        $contenu = $arrayContenu['contenu'];
        $xpath = $arrayContenu['xpath'];

        /**
         * @todo {
         *  - Compter le nombre de DOM
         *  - Récupération de tous les éléments avec un attribut class / ID
         * }
         */
        // Balise à ne pas compter
        $balise_not_compted = ["br", "hr", "footer", "header", "meta", "strong", "em", "picture", "source"];
        $where_not = implode(' or ', array_map(function ($tag) {
            return 'self::' . $tag;
        }, $balise_not_compted));

        // Parcourir les éléments et compter les balises
        // $bodyElements = $xpath->query('//body//*[not('.$where_not.')]');
        // $tagsCount = [];
        // foreach ($bodyElements as $element) {
        //     $tagName = $element->nodeName;
        //     if (isset($tagsCount[$tagName])) {
        //         $tagsCount[$tagName]++;
        //     } else {
        //         $tagsCount[$tagName] = 1;
        //     }
        // }
        // $tagsCount['total'] = array_sum($tagsCount);

        /**
         * Lister les classes et ID dans le contenu
         */
        // Récupération de tous les éléments avec un attribut class
        $classElements = $xpath->query('//*[@class]');
        $classes = [];

        foreach ($classElements as $element) {
            $elementClasses = preg_replace('/\s+/', ' ', $element->getAttribute('class'));
            $classes[] = $elementClasses;
        }

        // Suppression des doublons
        $classes = array_filter(array_unique($classes));

        // Récupération de tous les éléments avec un attribut id
        $idElements = $xpath->query('//*[@id]');
        $ids = [];

        foreach ($idElements as $element) {
            $ids[] = $element->getAttribute('id');
        }

        // Suppression des doublons
        $ids = array_filter(array_unique($ids));

        // Combinaison des listes
        $ListClassID = array_unique(array_merge($ids, $classes));
        sort($ListClassID);

        // Rechercher le nombre d'occurence des mots-clés établis ainsi que la liste des ID/Class contenant la liste de ces mots-clés
        $domData = cherche_occurence($contenu, $ListClassID, $idDomaine);

        // Mise à jour des informations sur le DOM
        sql_update_info(
            ['nombre_dom_sfpi' => json_encode($domData, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT)],
            'scrapping_fiche_produit_ia',
            ['id_scrapping_fiche_produit_ia' => $idScraping]
        );

        if (!array_key_exists($idDomaine, $dataArray)) {
            $dataArray[$idDomaine] = [
                "domaine" => $domaine,
                "fiches" => [
                    [
                        "id" => $idScraping,
                        "url" => $currentUrl,
                        'listIDClass' => $ListClassID,
                        'domData' => $domData
                    ]
                ]
            ];
        } else {
            $dataArray[$idDomaine]["fiches"][] = [
                "id" => $idScraping,
                "url" => $currentUrl,
                'listIDClass' => $ListClassID,
                'domData' => $domData
            ];
        }

        $dataToProcess[$idDomaine][] = [
            'id' => $idScraping,
            'domData' => $domData
        ];

        // Get CMS of domaine
        get_cms_domaine($domaine, $idDomaine);
    }

    return [
        'dataArray' => $dataArray,
        'dataToProcess' => $dataToProcess,
    ];
}

function getContenuHTML($idScraping): array
{
    $sql_get_content =
        "SELECT contenu_scrapping_sfpi
        FROM scrapping_fiche_produit_ia SFPI
        WHERE id_scrapping_fiche_produit_ia = {$idScraping}
    ";
    $res_get_content = mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_get_content) or die(hellopro_mysql_error($sql_get_content, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));
    $ligne_content = $res_get_content->fetch_assoc()['contenu_scrapping_sfpi'];

    $contenu = traitement_contenu_web($ligne_content);

    $domXPath = creerDOMEtXPath($contenu);

    return [
        'contenu' => $contenu,
        'dom' => $domXPath['dom'],
        'xpath' => $domXPath['xpath']
    ];
}

function getTopsFiches(array $dataToProcess, array $dataArray, bool $getNew = true, $idDomaine = null): array {
    $evaluationGlobal = [];
    if (!$getNew) {
        $dataToGetSelector = [];
        $sql_get_tops_fiches = 
            "SELECT tops_fiches_dspi AS tops_fiches
             FROM domaine_scrapping_produit_ia
             WHERE id_domaine_scrapping_produit_ia = '" . hellopro_traitement_donnee_annuaire_bo($idDomaine) . "'
             LIMIT 1";
        $res_get_tops_fiches = mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_get_tops_fiches)
            or die(hellopro_mysql_error($sql_get_tops_fiches, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));
        $tops_fiches_json = $res_get_tops_fiches->fetch_assoc()['tops_fiches'] ?? null;
        if (empty($tops_fiches_json)) {
            return [];
        }
        $tops_fiches = json_decode($tops_fiches_json, true);

        if (json_last_error() != JSON_ERROR_NONE) {
            return [];
        }

        $dataToGetSelector[$idDomaine] = $tops_fiches;
    } else {
        $ignoreData = [];
    
        do {
            $allOK = true;
            $dataToGetSelector = [];
            foreach ($dataToProcess as $idDomaine => $domDataToProcess) {
                if (empty($domDataToProcess)) {
                    continue;
                }
                $ignoreDataDomain = array_key_exists($idDomaine, $ignoreData) ? $ignoreData[$idDomaine] : [];
                $dataToGetSelector[$idDomaine] = processDataElementsByCategory($domDataToProcess, $ignoreDataDomain);
            }
        
            foreach ($dataToGetSelector as $idDomaine => $typesData) {
                $domaine = $dataArray[$idDomaine]['domaine'];
                foreach ($typesData as $typeData => $idsScraping) {
                    if (empty($idsScraping) || !is_array($idsScraping)) {
                        continue;
                    }
                    foreach ($idsScraping as $idScraping) {
                        $contenu = getContenuHTML($idScraping)['contenu'];
                        if (empty($contenu)) {
                            continue;
                        }
                        $isTokenLimit = processPrompt($domaine, $contenu, $typeData, '', '', [], false, true);
    
                        if ($isTokenLimit) {
                            $ignoreData[$idDomaine][$typeData][] = $idScraping;
                            $allOK = false;
                            continue;
                        }
    
                        if ($typeData === 'description') {
                            $isTokenLimit = processPrompt($domaine, $contenu, $typeData, '', '', [], true, true);
    
                            if ($isTokenLimit) {
                                $ignoreData[$idDomaine][$typeData][] = $idScraping;
                                $allOK = false;
                            }
                        }
                    }
                }
            }
            if (!$allOK) {
                foreach ($dataToProcess as $idDom => $domData) {
                    $ignoreDataDomain = array_key_exists($idDom, $ignoreData) ? $ignoreData[$idDom] : [];
                    $dataToGetSelector[$idDom] = processDataElementsByCategory($domData, $ignoreDataDomain);
                }
            }
        } while (!$allOK);

        $globalOccurrences = [];
        foreach ($dataToGetSelector as $idDom => $typesData) {
            foreach ($typesData as $typeData => $idsScraping) {
                if (empty($idsScraping) || !is_array($idsScraping)) {
                    continue;
                }
                foreach ($idsScraping as $idScraping) {
                    $contenu = getContenuHTML($idScraping)['contenu'];
                    if (empty($contenu)) {
                        continue;
                    }
                    // Extraire la signature (combinaison id et classes)
                    $dom = new DOMDocument();
                    @$dom->loadHTML("<html>{$contenu}</html>");
                    foreach ($dom->getElementsByTagName('div') as $div) {
                        if ($div->hasAttribute('class')) {
                            $classes = explode(' ', trim($div->getAttribute('class')));
                            $classes = array_filter($classes);
                            sort($classes);
                            $signature = implode('-', $classes);
                            if ($div->hasAttribute('id')) {
                                $signature = trim($div->getAttribute('id')) . "|" . $signature;
                            }
                            if (!isset($globalOccurrences[$signature])) {
                                $globalOccurrences[$signature] = 1;
                            } else {
                                $globalOccurrences[$signature]++;
                            }
                        }
                    }
                }
            }
        }

        $evaluator = new TopFicheEvaluator();
        foreach ($dataToGetSelector as $idDom => $typesData) {
            $finalSelector = [];
            foreach ($typesData as $typeData => $idsScraping) {
                if (empty($idsScraping) || !is_array($idsScraping)) {
                    continue;
                }
                $finalSelector[$typeData] = [];
                $maxScore = -INF;
                $maxScrapingId = null;
                foreach ($idsScraping as $idScraping) {
                    $contenu = getContenuHTML($idScraping)['contenu'];
                    if (empty($contenu)) {
                        continue;
                    }
                    // Passage de globalOccurrences à evaluateFiche
                    $evaluation = $evaluator->evaluateFiche($contenu, $dataArray[$idDom]['domaine'], $globalOccurrences);
                    $evaluationGlobal[$idDom][$idScraping] = $evaluation;
                    if ($evaluation['isTopFiche']) {
                        $finalSelector[$typeData][] = $idScraping;
                    }
                    if (isset($evaluation['score']) && $evaluation['score'] > $maxScore) {
                        $maxScore = $evaluation['score'];
                        $maxScrapingId = $idScraping;
                    }
                }
                if (empty($finalSelector[$typeData]) && $maxScrapingId !== null) {
                    $finalSelector[$typeData][] = $maxScrapingId;
                }
            }
            $dataToGetSelector[$idDom] = $finalSelector;
            
            // Mise à jour en base
            $valuesJson = json_encode($finalSelector);
            $sql_update_tops_fiches = 
                "UPDATE domaine_scrapping_produit_ia
                SET tops_fiches_dspi = '" . hellopro_traitement_donnee_annuaire_bo($valuesJson) . "'
                WHERE id_domaine_scrapping_produit_ia = '" . hellopro_traitement_donnee_annuaire_bo($idDomaine) . "'
                LIMIT 1
            ";
            mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_update_tops_fiches) or die(hellopro_mysql_error($sql_update_tops_fiches, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));
        }
    }


    $listTypesData = [
        'titre',
        'description',
        'prix',
        'image',
        'categorie',
        'livraison',
        'stock',
    ];    
    foreach ($dataToGetSelector as $idDomaine => $datas) {
        foreach ($datas as $typeData => $data) {    
            if(!in_array($typeData, $listTypesData)) 
            {                
                unset($dataToGetSelector[$idDomaine][$typeData]);
            }
        }
    }
    $dataToGetSelector["evaluation"] = $evaluationGlobal;
    return $dataToGetSelector;
}

function isFonctionalUrl(?string $url): bool
{
    if (filter_var($url, FILTER_VALIDATE_URL)) {
        return true;
    }

    $reg_url = '/^(\/\/|www.|http:\/\/|https:\/\/|ftp:\/\/|){1}[^\x00-\x19\x22-\x27\x2A-\x2C\x2E-\x2F\x3A-\x40\x5B-\x5E\x60\x7B\x7D-\x7F]+(\.[^\x00-\x19\x22\x24-\x2C\x2E-\x2F\x3C\x3E\x40\x5B-\x5E\x60\x7B\x7D-\x7F]+)+(\/[^\x00-\x19\x22\x3C\x3E\x5E\x7B\x7D-\x7D\x7F]*)*$/';
    if (preg_match($reg_url, $url)) {
        return true;
    }
    return false;
}

function getKeywordsOfTopFiche($idDomaine) {
    $sql_get_keywords = "
        SELECT
            id_keyword_top_fiche_produit_ia,
            type_info_ktfpi,
            keyword_ktfpi,
            statut_ktfpi,
            est_tout_domaine_ktfpi,
            type_keyword_ktfpi
        FROM
            keyword_top_fiche_produit_ia KTFPI
        WHERE
            id_domaine_scrapping_produit_ia = '". hellopro_traitement_donnee_annuaire_bo($idDomaine) ."' 
        OR id_domaine_scrapping_produit_ia IS NULL
    ";
    $res_get_keywords = mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_get_keywords) or die(hellopro_mysql_error($sql_get_keywords, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));

    $tab_keywords = array();

    while($lig_get_keywords = mysqli_fetch_assoc($res_get_keywords)) {
        $type_info  = $lig_get_keywords['type_info_ktfpi'];
        $id_keyword = $lig_get_keywords['id_keyword_top_fiche_produit_ia'];
        $keyword    = $lig_get_keywords['keyword_ktfpi'];
        $est_actif  = $lig_get_keywords['statut_ktfpi']; 
        $est_pour_tt_domaine = $lig_get_keywords['est_tout_domaine_ktfpi'];
        $type_keyword = $lig_get_keywords['type_keyword_ktfpi'] ? "contenu" : "idclass";


        $tab_keyword = explode('_##_',$keyword);

        $tab_keywords[$type_info][$type_keyword][] = [
            "id"           => $id_keyword,
            "keyword"      => $tab_keyword[1],
            "est_actif"    => $est_actif,
            "est_pour_tt_domaine" => $est_pour_tt_domaine
        ];
    }

    return $tab_keywords;
}

function getDetailTopFiche($idDomaine) {
    $tab_detail_top_fp = array();
    $tab_top_fp = getTopsFiches([], [], false, $idDomaine);

    foreach($tab_top_fp[$idDomaine] as $type => $tab_id_scrapping) {
        foreach($tab_id_scrapping as $id_scrapping) {
            $sql_info_top_fp = "
                SELECT
                    url_sfpi
                FROM scrapping_fiche_produit_ia SFPI
                WHERE id_scrapping_fiche_produit_ia =  '". hellopro_traitement_donnee_annuaire_bo($id_scrapping) ."'
            ";
            $res_info_top_fp = mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_info_top_fp) or die(hellopro_mysql_error($sql_info_top_fp, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));
            
            if($lig_info_top_fp = mysqli_fetch_assoc($res_info_top_fp)) {
                $url_top_fp = $lig_info_top_fp['url_sfpi'];

                $tab_detail_top_fp[$type][] = [
                    "url" => $url_top_fp,
                    "id"  => $id_scrapping
                ];
            }
        }
    }

    return $tab_detail_top_fp;
}

function buildTabKeyword($idDomaine) {
    $sql_get_keywords = "
        SELECT
            id_keyword_top_fiche_produit_ia,
            type_info_ktfpi,
            keyword_ktfpi,
            type_keyword_ktfpi
        FROM
            keyword_top_fiche_produit_ia KTFPI
        WHERE
            ( 
                id_domaine_scrapping_produit_ia = '". hellopro_traitement_donnee_annuaire_bo($idDomaine) ."' 
                OR 
                id_domaine_scrapping_produit_ia IS NULL 
            )
        AND statut_ktfpi = 1

    ";
    $res_get_keywords = mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_get_keywords) or die(hellopro_mysql_error($sql_get_keywords, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));

    $tab_keywords = array();
    $tab_cle = ['idClass','contenu'];

    while($lig_get_keywords = mysqli_fetch_assoc($res_get_keywords)) {
        $type_info    = $lig_get_keywords['type_info_ktfpi'];
        $keyword      = explode('_##_',$lig_get_keywords['keyword_ktfpi']);
        $type_keyword = $lig_get_keywords['type_keyword_ktfpi']; #0: idClass , 1: contenu

        $cle_tab = $tab_cle[$type_keyword];

         /**
             * Forme du tab
             * $mots_cles = [
                'idClass' => [
                    'description' => [
                        'description' => 'description',
                    ],
                    'prix' => [
                        'barre'         => 'barr[eé]',
                        'old'           => '^(?=.*price)(?=.*old)(?:(?:price[-_]{1,2}old)|(?:old[-_]{1,2}price))$'
                    ],
                    'image' => [
                        'img'      => 'img',
                        'picture'  => 'picture',
                    ],
                    'categorie' => [
                        'navigation' => 'navigation',
                        'fil_ariane' => 'fil[_-]ariane'
                    ],
                    'livraison' => [
                        'delivery'  => 'delivery',
                    ],
                    'stock' => [
                        'availability' => 'availability',
                    ]
                ],
                'contenu' => [
                    'livraison' => [
                        'expedition' => 'exp[eé]dition|exp[eé]dié',
                    ],
                    'stock' => [
                        'reassort'   => 'r[eé]assort',
                    ],
                    'description' => [
                        'description'     => 'description(?:\s*du\s*produit)?',
                    ],
                    'prix' => [
                        '$'                => '\$',
                        '€'                => '€',
                    ],
                    'titre' => [
                        'h1' => '<h1(.*?)>',
                        'h2' => '<h2(.*?)>'
                    ],
                    'categorie' => [
                        'categorie' => 'categorie',
                        'category'  => 'category'
                    ],
                    'image' => [
                        'picture' => '<picture(.*?)>',
                        'img'     => '<img(.*?)>'
                    ]
                ]
            ];
         */
        $tab_keywords[$cle_tab][$type_info][$keyword[0]] = $keyword[1];
    }

    return $tab_keywords;
}

function getMailUserScraping($idDomaine): string
{
    $sql_get_mail_user_scraping =
        "SELECT DSPI.utilisateur_dspi
        FROM
            domaine_scrapping_produit_ia DSPI
        WHERE DSPI.id_domaine_scrapping_produit_ia = '{$idDomaine}'
        LIMIT 1
    ";
    $res_get_mail_user_scraping = mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_get_mail_user_scraping) or die(hellopro_mysql_error($sql_get_mail_user_scraping, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));
    $lig_user = mysqli_fetch_assoc($res_get_mail_user_scraping);
    $id_admin = $lig_user['utilisateur_dspi'];
    $email = "";

    if(!empty($id_admin)) {
        $sql_email = "SELECT
                        A.email_administrateur
                    FROM administrateur A 
                    WHERE A.id_administrateur = '". hellopro_traitement_donnee_annuaire_bo($id_admin) ."' 
                    ";
        $res_email = mysqli_query($GLOBALS['LINK_MYSQLI_ANNUAIRE_BO'], $sql_email) ;
        
        if ($lig_email = mysqli_fetch_assoc($res_email)) {
            $email = $lig_email['email_administrateur'];
        }
    }
    

    return $email;
}

/**
 * Fonction de verification si un url existe dans la base BO
 *
 * @param string $input L'URL à verifié
 * @return array  Liste de sociétés ayant l'url
 */

function est_deja_existe_bo($url, $siret = null, $is_prospect = false)
{
    $list_id = [];
    if (!empty($url)) {
        $domaine_non_strict = recupere_domaine_n_strict($url);
        $sql_verif_url_bo = "
                        SELECT  
                            S.site_web_commercial, 
                            SU.url_su, 
                            S.id_societe, 
                            S.etat_societe,  
                            S.id_type_societe_contrat, 
                            S.nom_commercial
                        FROM  societe S
                        INNER JOIN societe_fournisseur SF ON SF.id_societe_sf = S.id_societe
                        LEFT JOIN societe_url SU ON S.id_societe = SU.id_societe_su
                        WHERE (
                                SU.url_su LIKE '%".hellopro_traitement_donnee_annuaire_bo($domaine_non_strict)."%'
                                OR S.site_web_commercial LIKE '%".hellopro_traitement_donnee_annuaire_bo($domaine_non_strict)."%'
                                )
                        AND S.id_societe NOT IN (SELECT id_succursale FROM societe_succursale)
                        AND SF.business_model_sf = 1
                        AND SF.est_supprime = 0
                        ";
        $qry_verif_url_bo = mysqli_query($GLOBALS["LINK_MYSQLI_ANNUAIRE_BO"], $sql_verif_url_bo) 
        OR DIE (hellopro_mysql_error($sql_verif_url_bo,$GLOBALS["LINK_MYSQLI_ANNUAIRE_BO"]));                 
        while ($lig_verif_url = mysqli_fetch_assoc($qry_verif_url_bo))
        {
            $domaine_temp = recupere_domaine_n_strict( $lig_verif_url['site_web_commercial']);
            $domaine_temp_2 = recupere_domaine_n_strict( $lig_verif_url['url_su']);

            if(!$is_prospect) {
                if( ( $domaine_temp == $domaine_non_strict || $domaine_temp_2 == $domaine_non_strict) && ($lig_verif_url['etat_societe'] != 3 ) )
                {
                    $list_id[$lig_verif_url['id_societe']] = $lig_verif_url;
                }
            } else {
                if($domaine_temp == $domaine_non_strict || $domaine_temp_2 == $domaine_non_strict)
                {
                    $list_id[$lig_verif_url['id_societe']] = $lig_verif_url;
                }
            }
        }
    }

    // Si rien trouvé et siret fourni, on tente par siret
    if (empty($list_id) && !empty($siret)) {
        $sql_siret = "
            SELECT  
                S.site_web_commercial, 
                SU.url_su, 
                S.id_societe, 
                S.etat_societe,  
                S.id_type_societe_contrat, 
                S.nom_commercial
            FROM societe S
            INNER JOIN societe_fournisseur SF ON SF.id_societe_sf = S.id_societe
            LEFT JOIN societe_url SU ON S.id_societe = SU.id_societe_su
            LEFT JOIN siret_societe SS ON SS.id_societe = S.id_societe
            WHERE SS.siret = '".hellopro_traitement_donnee_annuaire_bo($siret)."' 
            AND S.id_societe NOT IN (SELECT id_succursale FROM societe_succursale)
            AND SF.business_model_sf = 1
            AND SF.est_supprime = 0
        ";
        $qry_siret = mysqli_query($GLOBALS["LINK_MYSQLI_ANNUAIRE_BO"], $sql_siret)
            OR DIE (hellopro_mysql_error($sql_siret, $GLOBALS["LINK_MYSQLI_ANNUAIRE_BO"]));
        while ($lig_siret = mysqli_fetch_assoc($qry_siret)) 
        {

            $domaine_temp = recupere_domaine_n_strict( $lig_siret['site_web_commercial']);
            $domaine_temp_2 = recupere_domaine_n_strict( $lig_siret['url_su']);

            if (!$is_prospect) {
                if( ( $domaine_temp == $domaine_non_strict || $domaine_temp_2 == $domaine_non_strict) && ($lig_siret['etat_societe'] != 3 ) )
                {
                    $list_id[$lig_siret['id_societe']] = $lig_siret;
                }
            } else {
                if($domaine_temp == $domaine_non_strict || $domaine_temp_2 == $domaine_non_strict)
                {
                    $list_id[$lig_siret['id_societe']] = $lig_siret;
                }
            }
        }
    }
    
    return $list_id;
}

function get_statut_crawling() {
    return [
        // 0 => "Non commencé",
        1 => "En cours crawling",
        2 => "Vérification crawling et top fiche",
        3 => "En cours selecteurs top fiche",
        4 => "Vérification selecteurs",
        5 => "En cours récuperation information",
        6 => "Terminé",
        7 => "Erreur détéction fiches produits automatiques",
        8 => "Erreur détéction fiches produits manuelles",
        9 => "Erreur crawling",
        10 => "Erreur limit crawling atteint",
        11 => "En cours de détéction fiches produits manuelles",
        12 => "Erreur arrêt manuel du crawl",
        13 => "Terminé - Contrôle fait",
        14 => "Domaine sans fiche produits"
    ];
}

function recuperer_fichier_log_crawling($nom_domaine) {
    $repertoire = "script/fichiers/chatgpt/scrapping_produit/" . date("Y") . "/" . date("m") . "/";
    $liste_fichier_logs = glob($_SERVER["DOCUMENT_ROOT"] . $repertoire . "*-tracking-scrapping-produit-ia-". $nom_domaine .".txt");

    $tab_logs = array();

    foreach($liste_fichier_logs as $fichier_log) {
        $dernier_modif_log = filemtime($fichier_log);
        $tab_logs[$dernier_modif_log] = $fichier_log;
    }

    krsort($tab_logs);
    return $tab_logs;
}

function historique_action_utilisateur($user_bo, $id_domaine, $domaine = "", $action) {

    if(empty($user_bo)) {
        $user_bo = $_SESSION['user_bo'];
    }

    $sql_historique = "INSERT INTO
                            historique_action_utilisateur_scrapping_ia
                        SET
                            id_admin_hausi = {$user_bo},
                            id_domaine_hausi = {$id_domaine},
                            date_action_hausi = NOW(),
                            id_action_hausi = {$action}";
    $res_historique = mysqli_query($GLOBALS["LINK_MYSQLI_HELLOPRO_IA"], $sql_historique) or die(hellopro_mysql_error($sql_historique, $GLOBALS["LINK_MYSQLI_HELLOPRO_IA"]));
}
/**
 * Récupère le contenu d'un sélecteur CSS en utilisant DOMDocument et DOMXPath.
 *
 * @param array  $list_selecteur Un tableau  contenant la liste des sélecteurs CSS.
 * @param string $contenu Le contenu HTML de la page.
 *  @return booleen true si le contenu du sélecteur est trouvé, sinon false.
 */
function has_contenu_selecteur( array $list_selecteur  , string $contenu  )
{
    global $cssSelectorConverter;
    $found_content = false;

    $domXPath = creerDOMEtXPath($contenu);
    $dom = $domXPath['dom'];
    $xpath = $domXPath['xpath'];

    $hasNonComaptibleXpath = false;

    foreach ($list_selecteur as  $cssSelector) {

        $cssSelector = preg_replace('/(\[.*)(\.)(.*\])/', "$1\\.$3", $cssSelector);
        $cssSelector  = trim($cssSelector);

        $xpathQuery = cssToXPath($cssSelector);
        $elements = $xpath->query($xpathQuery);

        if ($elements->length > 0) {
            $found_content = true;
            break;
        } else {
            $debut_css = $fin_css = "";
            $selector_temp = $cssSelector;
            if (preg_match('/^(\()(.*)(\)\[\d+\])$/', $cssSelector, $matches)) {
                $debut_css = $matches[1]; // Contient '('
                $selector_temp = $matches[2];            // Contenu capturé entre parenthèses
                $fin_css = $matches[3]; // Contient ')[3]'

            }

            try {
                $xpathQuery = $debut_css . $cssSelectorConverter->toXPath($selector_temp) . $fin_css;
                $elements = $xpath->query($xpathQuery);
                if ($elements->length > 0) {
                    $found_content = true;
                    break;
                }
            } catch (Exception $e) {
            }
        }

        if (isNonXPathCompatibleSelector($cssSelector)) {
            $hasNonComaptibleXpath = true;
        }
    }

    if (!$found_content && $hasNonComaptibleXpath) {

        $domaineFile = "hcs" . rand(1, 20);
        $fileContent =  date('YmdHis') . "_contenu_" . $domaineFile . ".txt";
        $jsonSelecteur =  date('YmdHis') . "_selecteur_" . $domaineFile . ".json";
        $repertoireFileContent = $_SERVER['DOCUMENT_ROOT'] . "admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/tools/scraper/files/";

        $handleFileContent = fopen($repertoireFileContent . $fileContent, 'w');
        fwrite($handleFileContent, $contenu);
        fclose($handleFileContent);


        file_put_contents($repertoireFileContent . $jsonSelecteur, json_encode($list_selecteur, JSON_PRETTY_PRINT));
        $contentElements = GetContent_via_Css($fileContent, $jsonSelecteur);
        if (!empty($contentElements)) {
            $found_content = true;
        }

        fclose($handleFileContent);
        unlink($repertoireFileContent . $fileContent);
        unlink($repertoireFileContent . $jsonSelecteur);
    }



    return $found_content;
}

function info_admin($id_user_bo) {
    $sql_info_admin = "
        SELECT
            id_administrateur,
            nom_administrateur,
            prenom_administrateur,
            email_administrateur,
            login_administrateur,
            photo
        FROM
            administrateur A
        WHERE
            id_administrateur = '". hellopro_traitement_donnee_annuaire_bo($id_user_bo) ."'
    ";
    $res_info_admin = mysqli_query($GLOBALS['LINK_MYSQLI_ANNUAIRE_BO'], $sql_info_admin) or die(hellopro_mysql_error($sql_info_admin, $GLOBALS['LINK_MYSQLI_ANNUAIRE_BO']));
    $lig_info_admin = mysqli_fetch_assoc($res_info_admin);

    return [
        "nom"    => $lig_info_admin["nom_administrateur"],
        "prenom" => $lig_info_admin["prenom_administrateur"],
        "email"  => $lig_info_admin["email_administrateur"],
        "login"  => $lig_info_admin["login_administrateur"],
        "photo"  => $lig_info_admin["photo"],
    ];
}

function maj_utilisateur_dspi($id_domaine, $id_user_bo) {

    if (empty($id_domaine) || empty($id_user_bo)) {
        return false;
    }

    $sql_get_utilisateur = "
        SELECT utilisateur_dspi
        FROM domaine_scrapping_produit_ia
        WHERE id_domaine_scrapping_produit_ia = '". hellopro_traitement_donnee_annuaire_bo($id_domaine) ."'
    ";
    $res_get_utilisateur = mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_get_utilisateur) or die(hellopro_mysql_error($sql_get_utilisateur, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA'])); 
    $lig_get_utilisateur = mysqli_fetch_assoc($res_get_utilisateur);
    $utilisateur_dspi = $lig_get_utilisateur['utilisateur_dspi'];
    
    if ($utilisateur_dspi == $id_user_bo) {
        return false; // Pas de changement
    }   

    $sql_update_utilisateur = "
        UPDATE domaine_scrapping_produit_ia
        SET utilisateur_dspi = '". hellopro_traitement_donnee_annuaire_bo($id_user_bo) ."'
        WHERE id_domaine_scrapping_produit_ia = '". hellopro_traitement_donnee_annuaire_bo($id_domaine) ."'
    ";
    $res_update_utilisateur = mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_update_utilisateur) or die(hellopro_mysql_error($sql_update_utilisateur, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));
}

function get_url_fp_domaine($id_domaine) {
    $sql_fp = "SELECT
                    id_scrapping_fiche_produit_ia,
                    url_sfpi AS url
                FROM
                    scrapping_fiche_produit_ia SFPI
                WHERE
                    id_domaine_scrapping_produit_sfpi = '" . hellopro_traitement_donnee_annuaire_bo($id_domaine) . "'
                    AND SFPI.est_dernier_sfpi = 1";
    $res_fp = mysqli_query($GLOBALS["LINK_MYSQLI_HELLOPRO_IA"], $sql_fp) or die(hellopro_mysql_error($sql_fp, $GLOBALS["LINK_MYSQLI_HELLOPRO_IA"]));
    $tab_url = [];
    while($lig = mysqli_fetch_assoc($res_fp)) {
        $tab_url[$lig['id_scrapping_fiche_produit_ia']] = $lig['url'];
    }

    return $tab_url;
}
/** FONCTION */
