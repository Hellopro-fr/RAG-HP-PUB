<?php
/**
 * =============================================================================
 * sync_synonyms_daily.php
 * -----------------------------------------------------------------------------
 * Script cron QUOTIDIEN : pull les synonymes Typesense (auto + manual deja
 * pushed) depuis l'API VM et les stocke localement dans le cache PHP front.
 *
 * Pattern : Ecritel -> API VM (comme l'ingestion).
 *
 * Origine : etait dans site/annuaire_hp/fonctions/sync_synonyms.php (mauvais
 * dossier = repertoire du front PHP). Deplace 2026-05-06 V4.
 *
 * URL appelee :
 *   https://script.hellopro.fr/script/typesense/sync_synonyms_daily.php?token=XXX
 *
 * Endpoint VM appele :
 *   GET https://api.hellopro.eu/optimoteur-service/admin/synonyms
 *
 * Ecrit dans :
 *   $_SERVER['DOCUMENT_ROOT']/fichiers_communs_bo_front/hellopro_fr/typesense_synonyms.json
 *
 * Utilise par :
 *   site/annuaire_hp/fonctions/fonctions_annuaire_hp.php :: load_synonyms_index()
 *
 * Comportement en cas d'erreur :
 *   - curl echoue -> output ERROR + exit 1 (garde l'ancien fichier)
 *   - JSON invalide -> output ERROR + exit 1 (garde l'ancien fichier)
 *   - moins de 10 synonymes recus -> output ERROR (suspect de corruption)
 *   - fichier ecrit atomiquement (mv final) -> 0 risque de lecture partielle
 *
 * Cron suggere (1x / jour a 3h30 du matin, apres l'ingestion) :
 *   0 3 * * * /script/annuaire/moteur_solr.sh
 *   30 3 * * * wget /script/typesense/sync_synonyms_daily.php?token=XXX
 * =============================================================================
 */

header('Content-Type: text/plain; charset=UTF-8');

// =============================================================================
// SECURITE : token jetable
// =============================================================================
define('HTTP_TOKEN', 'hp_synsync_2026_04_30_xZ7q');

if (!isset($_GET['token']) || $_GET['token'] !== HTTP_TOKEN) {
    http_response_code(403);
    echo "FORBIDDEN - token manquant ou invalide\n";
    exit;
}

// =============================================================================
// CONFIG
// =============================================================================
$SYNONYMS_URL = 'https://api.hellopro.eu/optimoteur-service/admin/synonyms';
$CACHE_FILE   = $_SERVER['DOCUMENT_ROOT'] . 'fichiers_communs_bo_front/hellopro_fr/typesense_synonyms.json';
$CACHE_DIR    = dirname($CACHE_FILE);
$CACHE_TMP    = $CACHE_FILE . '.tmp.' . getmypid();
$TIMEOUT_SEC  = 30;

$t0 = microtime(true);

function log_line($level, $msg)
{
    echo '[' . date('Y-m-d\TH:i:s') . "] [$level] $msg\n";
    @flush();
}

log_line('INFO', "GET $SYNONYMS_URL");
log_line('INFO', "Target: $CACHE_FILE");

// =============================================================================
// PREREQUIS DOSSIER
// =============================================================================
if (!is_dir($CACHE_DIR)) {
    if (!@mkdir($CACHE_DIR, 0755, true)) {
        log_line('ERROR', "Dossier inexistant et mkdir echoue : $CACHE_DIR");
        http_response_code(500);
        exit(1);
    }
}

// =============================================================================
// DOWNLOAD via curl
// =============================================================================
$ch = curl_init($SYNONYMS_URL);
curl_setopt_array($ch, [
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_TIMEOUT        => $TIMEOUT_SEC,
    CURLOPT_CONNECTTIMEOUT => 10,
    CURLOPT_FAILONERROR    => true,
    CURLOPT_SSL_VERIFYPEER => false,
    CURLOPT_SSL_VERIFYHOST => false,
]);
$raw     = curl_exec($ch);
$errno   = curl_errno($ch);
$errstr  = curl_error($ch);
$http    = curl_getinfo($ch, CURLINFO_HTTP_CODE);
$total_t = curl_getinfo($ch, CURLINFO_TOTAL_TIME);
curl_close($ch);

if ($errno !== 0 || $raw === false) {
    log_line('ERROR', "curl echoue (errno=$errno, http=$http) : $errstr");
    http_response_code(502);
    exit(1);
}

log_line('INFO', sprintf("download OK en %.2fs (%d bytes, http=%d)", $total_t, strlen($raw), $http));

// =============================================================================
// VALIDATION JSON
// =============================================================================
$data = @json_decode($raw, true);
if (!is_array($data) || !isset($data['synonyms']) || !is_array($data['synonyms'])) {
    log_line('ERROR', "JSON invalide ou structure inattendue (pas de cle 'synonyms')");
    http_response_code(502);
    exit(1);
}

$nb = count($data['synonyms']);
if ($nb < 10) {
    log_line('ERROR', "Seulement $nb synonymes recus (sanity check : attendu >= 10)");
    http_response_code(502);
    exit(1);
}

log_line('INFO', "JSON valide : $nb entrees synonymes");

// =============================================================================
// ECRITURE ATOMIQUE
// =============================================================================
if (file_put_contents($CACHE_TMP, $raw) === false) {
    log_line('ERROR', "echec ecriture tmp : $CACHE_TMP");
    http_response_code(500);
    exit(1);
}

if (!@rename($CACHE_TMP, $CACHE_FILE)) {
    log_line('ERROR', "echec rename $CACHE_TMP -> $CACHE_FILE");
    @unlink($CACHE_TMP);
    http_response_code(500);
    exit(1);
}

@chmod($CACHE_FILE, 0644);

$size = filesize($CACHE_FILE);
$dt   = microtime(true) - $t0;
log_line('OK', sprintf("synonymes synchronises : $nb entrees, %d bytes, total=%.2fs", $size, $dt));
exit(0);
