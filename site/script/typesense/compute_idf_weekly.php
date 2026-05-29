<?php
/**
 * =============================================================================
 * compute_idf_weekly.php
 * -----------------------------------------------------------------------------
 * Script cron HEBDOMADAIRE : trigger la regeneration du dict IDF Typesense
 * sur le service GKE opti-moteur-front. Le service lance compute_idf.py en
 * background task (FastAPI) et recharge le cache idf_loader en RAM apres.
 *
 * Pattern : meme que sync_synonyms_daily.php (curl HTTP vers service GKE).
 *
 * URL appelee (cron Ecritel) :
 *   https://script.hellopro.fr/script/typesense/compute_idf_weekly.php?token=XXX
 *
 * Endpoint GKE appele :
 *   POST https://api.hellopro.eu/optimoteur-service/admin/compute-idf
 *   Header : X-Admin-Token: <ADMIN_TOKEN>
 *
 * Pourquoi un cron hebdomadaire :
 *   L'IDF (Inverse Document Frequency) varie lentement avec le catalogue.
 *   Le sync quotidien ajoute ~500-2000 produits/jour sur 2M docs = delta
 *   negligeable. Une regeneration hebdo garde le dict frais sans surcout.
 *   A declencher aussi manuellement apres toute ingestion massive de
 *   nouvelles categories (cf migrate_to_gke.sh).
 *
 * Comportement :
 *   - Verifie le token GET ?token=XXX (auth cron)
 *   - POST sur /admin/compute-idf avec X-Admin-Token (auth service)
 *   - Service GKE retourne {"status":"started"} immediatement
 *   - Cron PHP exit 0 sans attendre la fin (la regen tourne en background)
 *   - Logs : timestamp + status + duree (donnees observables via curl status apres)
 *
 * Cron suggere : dimanche 4h du matin (apres le sync quotidien synonymes qui
 * tourne a 3h30) :
 *   0 4 * * 0 wget -qO- "https://script.hellopro.fr/script/typesense/compute_idf_weekly.php?token=XXX"
 * =============================================================================
 */

header('Content-Type: text/plain; charset=UTF-8');

// =============================================================================
// SECURITE : token jetable (cron PHP)
// =============================================================================
define('HTTP_TOKEN', 'hp_idfcron_2026_05_22_xZ7q');

if (!isset($_GET['token']) || $_GET['token'] !== HTTP_TOKEN) {
    http_response_code(403);
    echo "FORBIDDEN - token manquant ou invalide\n";
    exit;
}

// =============================================================================
// CONFIG
// =============================================================================
// Token X-Admin-Token a passer au service GKE. DOIT matcher settings.ADMIN_TOKEN
// dans app/core/credentials.py cote service Python (defaut : hp_admin_2026_05_22_xZ7q).
define('GKE_ADMIN_TOKEN', 'hp_admin_2026_05_22_xZ7q');

$IDF_URL = 'https://api.hellopro.eu/optimoteur-service/admin/compute-idf';
$STATUS_URL = 'https://api.hellopro.eu/optimoteur-service/admin/compute-idf/status';
$TIMEOUT_SEC = 30;

$t0 = microtime(true);

function log_line($level, $msg)
{
    echo '[' . date('Y-m-d\TH:i:s') . "] [$level] $msg\n";
    @flush();
}

log_line('INFO', "POST $IDF_URL");

// =============================================================================
// CHECK STATUT AVANT (eviter double run si une regen est deja en cours)
// =============================================================================
$ch = curl_init($STATUS_URL);
curl_setopt_array($ch, [
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_TIMEOUT        => $TIMEOUT_SEC,
    CURLOPT_CONNECTTIMEOUT => 10,
    CURLOPT_SSL_VERIFYPEER => false,
    CURLOPT_SSL_VERIFYHOST => false,
]);
$rawStatus = curl_exec($ch);
curl_close($ch);

if ($rawStatus !== false) {
    $statusData = @json_decode($rawStatus, true);
    if (is_array($statusData) && isset($statusData['status']) && $statusData['status'] === 'running') {
        log_line('WARN', "Une regeneration est deja en cours (started_at=" .
                 ($statusData['started_at'] ?? '?') . "). Skip.");
        http_response_code(409);
        exit(0);
    }
}

// =============================================================================
// TRIGGER /admin/compute-idf
// =============================================================================
$ch = curl_init($IDF_URL);
curl_setopt_array($ch, [
    CURLOPT_POST           => true,
    CURLOPT_POSTFIELDS     => '{}',  // body vide, ts_collection prise dans settings
    CURLOPT_HTTPHEADER     => [
        'Content-Type: application/json',
        'X-Admin-Token: ' . GKE_ADMIN_TOKEN,
    ],
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

log_line('INFO', sprintf("trigger OK en %.2fs (http=%d, response=%s)", $total_t, $http, $raw));

// =============================================================================
// PARSE RESPONSE (200 = started, 429 = already running)
// =============================================================================
$data = @json_decode($raw, true);
if (!is_array($data)) {
    log_line('ERROR', "Reponse non-JSON : $raw");
    http_response_code(502);
    exit(1);
}

$status = $data['status'] ?? 'unknown';
$coll   = $data['collection'] ?? '?';
$dt     = microtime(true) - $t0;

if ($status !== 'started') {
    log_line('WARN', "Statut inattendu : $status (response: $raw)");
    exit(1);
}

log_line('INFO', sprintf("Regen IDF declenchee pour collection=%s en %.2fs", $coll, $dt));

// =============================================================================
// POLLING jusqu'a fin de la regeneration (timeout 15 min)
// =============================================================================
$RELOAD_URL    = 'https://api.hellopro.eu/optimoteur-service/admin/reload-idf';
$POLL_TIMEOUT  = 900;   // 15 min max
$POLL_INTERVAL = 15;    // 15s entre les polls
$elapsed = 0;

log_line('INFO', "Polling status (max {$POLL_TIMEOUT}s)...");
while ($elapsed < $POLL_TIMEOUT) {
    sleep($POLL_INTERVAL);
    $elapsed += $POLL_INTERVAL;

    $ch = curl_init($STATUS_URL);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT        => 10,
        CURLOPT_SSL_VERIFYPEER => false,
        CURLOPT_SSL_VERIFYHOST => false,
    ]);
    $sRaw = curl_exec($ch);
    curl_close($ch);

    $sData = @json_decode($sRaw, true);
    $sStatus = is_array($sData) ? ($sData['status'] ?? '?') : '?';

    if ($sStatus === 'ok') {
        $duration = $sData['duration_s'] ?? '?';
        $gcs_ok   = $sData['gcs_uploaded'] ?? null;
        log_line('OK', "compute-idf termine apres {$duration}s (gcs_uploaded=" .
                       json_encode($gcs_ok) . ")");
        break;
    }
    if ($sStatus === 'error' || $sStatus === 'exception') {
        $stderr_tail = is_array($sData) ? ($sData['stderr_tail'] ?? '') : '';
        log_line('ERROR', "compute-idf en erreur : $stderr_tail");
        exit(1);
    }
    if ($elapsed % 60 === 0) {
        log_line('INFO', "Toujours running apres {$elapsed}s...");
    }
}

if ($elapsed >= $POLL_TIMEOUT) {
    log_line('ERROR', "Timeout polling apres {$POLL_TIMEOUT}s");
    exit(1);
}

// =============================================================================
// PROPAGATION : appeler /admin/reload-idf plusieurs fois pour que les
// differents pods (derriere le LoadBalancer) downloadent le nouvel IDF
// depuis GCS. 5 appels = ~95% de chance que les 2 pods soient touches.
// =============================================================================
log_line('INFO', "Propagation aux autres pods via $RELOAD_URL...");
$pods_reloaded = 0;
for ($i = 1; $i <= 5; $i++) {
    $ch = curl_init($RELOAD_URL);
    curl_setopt_array($ch, [
        CURLOPT_POST           => true,
        CURLOPT_POSTFIELDS     => '',
        CURLOPT_HTTPHEADER     => ['X-Admin-Token: ' . GKE_ADMIN_TOKEN],
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT        => 30,
        CURLOPT_SSL_VERIFYPEER => false,
        CURLOPT_SSL_VERIFYHOST => false,
    ]);
    $rRaw = curl_exec($ch);
    $rHttp = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);

    $rData = @json_decode($rRaw, true);
    $rStatus = is_array($rData) ? ($rData['status'] ?? '?') : '?';
    log_line('INFO', "  reload #$i : http=$rHttp status=$rStatus");
    if ($rStatus === 'ok') $pods_reloaded++;
    sleep(1);
}

$total = microtime(true) - $t0;
log_line('OK', sprintf("Cron termine en %.2fs (compute + propagation %d/5 pods)",
                       $total, $pods_reloaded));
exit(0);
