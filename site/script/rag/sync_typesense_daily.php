<?php
/**
 * sync_typesense_daily.php
 * =========================
 * Script cron quotidien sur Ecritel (cf moteur_solr.sh / crontab Linkbynet).
 *
 * Effectue 2 etapes en chaine :
 *   ETAPE 1 : POST /sync/incremental
 *     - Upserter dans Typesense les produits modifies en Milvus depuis 24h
 *       (couvre NEW + UPDATED via le champ date_maj)
 *     - Supprimer de Typesense les produits qui ne sont plus en Milvus
 *
 *   ETAPE 2 : POST /admin/synonyms/auto-generate (ajout 2026-05-06)
 *     - Regenere les synonymes pour les nouvelles categories ingerees a
 *       l'etape 1. Sans ca, les nouvelles categories n'ont pas leurs
 *       variantes (mini-pelle / minipelle / mini pelle).
 *     - Si l'etape 1 a echoue, on saute l'etape 2.
 *
 * Usage cron (dans moteur_solr.sh) :
 *   wget https://script.hellopro.fr/script/rag/sync_typesense_daily.php?token=XXX
 *
 * Effet attendu :
 *   - Duree totale : 5-35 min selon volume modifs
 *   - Email de notification a la fin (succes ou echec) avec stats des 2 etapes
 *
 * Inspire de nettoyage_produits_supprimes_milvus.php (meme pattern api_call cURL).
 */

// Memory + timeout
ini_set("memory_limit", "-1");
set_time_limit(0);

require_once($_SERVER['DOCUMENT_ROOT'] . "include/connexion.php");
require_once($_SERVER['DOCUMENT_ROOT'] . "include/functions.php");
require_once($_SERVER['DOCUMENT_ROOT'] . "fonctions/fonctions_hellopro.php");
require_once($_SERVER['DOCUMENT_ROOT'] . "fonctions/fonctions_generales.php");

// =============================================================================
// CONFIG
// =============================================================================

// URL de l'API VM (le service opti-moteur-front qui expose POST /sync/incremental)
define('SYNC_API_URL', 'https://api.hellopro.eu/optimoteur-service/sync/incremental');

// URL de l'API VM pour l'auto-generation des synonymes (etape 2)
define('AUTO_GEN_SYNONYMS_URL', 'https://api.hellopro.eu/optimoteur-service/admin/synonyms/auto-generate');

// Token d'auth (header X-Sync-Token). Doit matcher SYNC_TOKEN dans app/router/sync.py
// CHANGER avant de mettre en prod.
define('SYNC_TOKEN', 'hp_sync_2026_04_30_xZ7q');

// Mail destinataire pour la notification
define('NOTIFICATION_EMAIL', 'tandriatsiferantsoa@hellopro.fr');

// Securite : token d'access HTTP pour eviter les declenchements externes
// (different du SYNC_TOKEN utilise pour l'API VM)
define('HTTP_TOKEN', 'hp_cron_2026_04_30_xZ7q');

// =============================================================================
// SECURITE : verifier le token HTTP
// =============================================================================
if (!isset($_GET['token']) || $_GET['token'] !== HTTP_TOKEN) {
    http_response_code(403);
    header('Content-Type: text/plain');
    echo "FORBIDDEN - token manquant ou invalide\n";
    exit;
}

// =============================================================================
// PARAMS
// =============================================================================

// Filtrer date_maj depuis quand ? Default = hier (24h ago)
$since = isset($_GET['since']) ? trim($_GET['since']) : date('Y-m-d\TH:i:s', strtotime('-1 day'));

// Collection Typesense cible (default = produits_prod)
$ts_collection = isset($_GET['ts_collection']) ? trim($_GET['ts_collection']) : 'produits_prod';

// Activer la suppression d'orphelins ? (default true)
$delete_orphans = !(isset($_GET['no_delete']) && $_GET['no_delete'] === '1');

// Headers HTTP : flush au fur et a mesure pour suivi cron
header('Content-Type: text/plain; charset=utf-8');
header('Cache-Control: no-store');
header('X-Accel-Buffering: no');
@ob_implicit_flush(true);
while (@ob_end_flush()) {}

// =============================================================================
// FONCTION : appel API
// =============================================================================
function api_call($url, $method = 'POST', $data = null, $headers = []) {
    $ch = curl_init();

    $default_headers = ['Content-Type: application/json'];
    $all_headers = array_merge($default_headers, $headers);

    $options = [
        CURLOPT_URL            => $url,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT        => 1800, // 30 min max (sync long possible)
        CURLOPT_CONNECTTIMEOUT => 30,
        CURLOPT_HTTPHEADER     => $all_headers,
        CURLOPT_FOLLOWLOCATION => true,
        CURLOPT_MAXREDIRS      => 3,
        CURLOPT_SSL_VERIFYPEER => false,
        CURLOPT_SSL_VERIFYHOST => false,
    ];

    if ($method === 'POST') {
        $options[CURLOPT_POST] = true;
        if ($data !== null) {
            $options[CURLOPT_POSTFIELDS] = json_encode($data);
        }
    }

    curl_setopt_array($ch, $options);
    $response = curl_exec($ch);
    $http_code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    $curl_error = curl_error($ch);
    curl_close($ch);

    if ($response === false) {
        throw new Exception("Erreur cURL: " . $curl_error);
    }

    return ['http_code' => $http_code, 'body' => $response];
}

// =============================================================================
// LANCEMENT
// =============================================================================

$start_time = microtime(true);

echo "==========================================\n";
echo "Sync Typesense Daily - " . date('Y-m-d H:i:s') . "\n";
echo "==========================================\n";
echo "API URL       : " . SYNC_API_URL . "\n";
echo "Since         : $since\n";
echo "TS Collection : $ts_collection\n";
echo "Delete orphans: " . ($delete_orphans ? 'YES' : 'NO') . "\n";
echo "==========================================\n\n";

$payload = [
    'since'          => $since,
    'ts_collection'  => $ts_collection,
    'delete_orphans' => $delete_orphans,
    'batch_size'     => 1000,
];

try {
    echo "[INFO] Appel API VM...\n";
    $response = api_call(
        SYNC_API_URL,
        'POST',
        $payload,
        ['X-Sync-Token: ' . SYNC_TOKEN]
    );

    $http_code = $response['http_code'];
    $body = $response['body'];
    $result = json_decode($body, true);

    $elapsed = round(microtime(true) - $start_time, 2);

    if ($http_code !== 200 || !$result) {
        // ECHEC
        echo "\n[ERREUR] HTTP $http_code\n";
        echo "Body: $body\n";

        $subject = "[Script][Sync] ECHEC sync Typesense quotidien";
        $message = "<h2>Echec du sync Typesense</h2>";
        $message .= "<p><strong>HTTP code:</strong> $http_code</p>";
        $message .= "<p><strong>Duree:</strong> {$elapsed}s</p>";
        $message .= "<p><strong>Body:</strong></p><pre>" . htmlspecialchars($body) . "</pre>";
        $message .= "<p><strong>Payload:</strong></p><pre>" . json_encode($payload, JSON_PRETTY_PRINT) . "</pre>";

        envoyer_mail_scripts($subject, '', NOTIFICATION_EMAIL, $message, 0);
        exit(1);
    }

    // SUCCES ETAPE 1
    echo "\n[SUCCES ETAPE 1] Sync termine\n";
    echo "  TS Collection      : " . ($result['ts_collection'] ?? '?') . "\n";
    echo "  Since              : " . ($result['since_iso'] ?? '?') . "\n";
    echo "  Milvus recent rows : " . ($result['milvus_recent_rows'] ?? 0) . "\n";
    echo "  TS upserted        : " . ($result['ts_upserted'] ?? 0) . "\n";
    echo "  TS upsert errors   : " . ($result['ts_upsert_errors'] ?? 0) . "\n";
    echo "  TS orphans deleted : " . ($result['ts_orphans_deleted'] ?? 0) . "\n";
    echo "  Duration (API)     : " . ($result['duration_s'] ?? 0) . "s\n";
    echo "  TS docs before     : " . ($result['ts_docs_before'] ?? 0) . "\n";
    echo "  TS docs after      : " . ($result['ts_docs_after'] ?? 0) . "\n";

    // =========================================================================
    // ETAPE 2 : Auto-generate synonymes (apres ingestion reussie)
    // =========================================================================
    $synonyms_result = null;
    $synonyms_error = null;

    echo "\n==========================================\n";
    echo "ETAPE 2 : Auto-generate synonymes\n";
    echo "==========================================\n";
    echo "[INFO] Appel API VM /admin/synonyms/auto-generate...\n";

    try {
        $syn_response = api_call(
            AUTO_GEN_SYNONYMS_URL,
            'POST',
            null  // pas de body (les params sont en query string si besoin)
        );
        $syn_http = $syn_response['http_code'];
        $syn_body = $syn_response['body'];
        $synonyms_result = json_decode($syn_body, true);

        if ($syn_http !== 200 || !$synonyms_result) {
            $synonyms_error = "HTTP $syn_http : $syn_body";
            echo "[WARN ETAPE 2] $synonyms_error\n";
        } else {
            echo "[SUCCES ETAPE 2]\n";
            echo "  Categories scannees    : " . ($synonyms_result['nb_categories'] ?? 0) . "\n";
            echo "  Synonymes generes      : " . ($synonyms_result['nb_synonyms_generated'] ?? 0) . "\n";
            echo "  Synonymes pushes       : " . ($synonyms_result['nb_synonyms_pushed'] ?? 0) . "\n";
            echo "  Erreurs                : " . ($synonyms_result['nb_errors'] ?? 0) . "\n";
        }
    } catch (Exception $e) {
        $synonyms_error = $e->getMessage();
        echo "[EXCEPTION ETAPE 2] $synonyms_error\n";
    }

    $elapsed = round(microtime(true) - $start_time, 2);
    echo "\n  Duration (total)   : {$elapsed}s\n";

    // =========================================================================
    // EMAIL DE NOTIFICATION (succes etape 1 + status etape 2)
    // =========================================================================
    $syn_status = $synonyms_error
        ? "<span style='color:red'>WARN: $synonyms_error</span>"
        : sprintf("OK (%d pushes)", $synonyms_result['nb_synonyms_pushed'] ?? 0);

    $subject = sprintf(
        "[Script][Sync] OK Typesense - %d upserted, %d deleted, syn:%s",
        $result['ts_upserted'] ?? 0,
        $result['ts_orphans_deleted'] ?? 0,
        $synonyms_error ? "ERR" : "OK"
    );

    $message = "<h2>Sync Typesense quotidien - SUCCES ETAPE 1</h2>";
    $message .= "<h3>Etape 1 : Sync incremental</h3>";
    $message .= "<table border='1' cellpadding='5' cellspacing='0'>";
    foreach ($result as $k => $v) {
        $message .= "<tr><td><strong>$k</strong></td><td>$v</td></tr>";
    }
    $message .= "</table>";

    $message .= "<h3>Etape 2 : Auto-generate synonymes</h3>";
    if ($synonyms_error) {
        $message .= "<p style='color:red'><strong>ECHEC :</strong> "
                  . htmlspecialchars($synonyms_error) . "</p>";
    } elseif ($synonyms_result) {
        $message .= "<table border='1' cellpadding='5' cellspacing='0'>";
        foreach (['nb_categories', 'nb_synonyms_generated', 'nb_synonyms_pushed', 'nb_errors'] as $k) {
            $v = $synonyms_result[$k] ?? 0;
            $message .= "<tr><td><strong>$k</strong></td><td>$v</td></tr>";
        }
        $message .= "</table>";
    } else {
        $message .= "<p>Aucune donnee.</p>";
    }

    $message .= "<p><strong>Total elapsed:</strong> {$elapsed}s</p>";
    envoyer_mail_scripts($subject, '', NOTIFICATION_EMAIL, $message, 0);

} catch (Exception $e) {
    $elapsed = round(microtime(true) - $start_time, 2);
    echo "\n[EXCEPTION] " . $e->getMessage() . "\n";

    $subject = "[Script][Sync] EXCEPTION sync Typesense";
    $message = "<h2>Exception lors du sync Typesense</h2>";
    $message .= "<p><strong>Erreur:</strong> " . htmlspecialchars($e->getMessage()) . "</p>";
    $message .= "<p><strong>Duree:</strong> {$elapsed}s</p>";
    envoyer_mail_scripts($subject, '', NOTIFICATION_EMAIL, $message, 0);
    exit(2);
}

echo "\n==========================================\n";
echo "Done in " . round(microtime(true) - $start_time, 2) . "s\n";
echo "==========================================\n";
