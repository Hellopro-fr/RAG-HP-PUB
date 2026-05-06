<?php
/**
 * =============================================================================
 * auto_generate_synonyms_weekly.php
 * -----------------------------------------------------------------------------
 * Script cron HEBDOMADAIRE : declenche la regeneration automatique des
 * synonymes Typesense a partir de TOUTES les categories de la collection.
 *
 * Pattern : Ecritel -> API VM (comme l'ingestion / le sync_typesense_daily).
 *
 * URL appelee :
 *   https://script.hellopro.fr/script/typesense/auto_generate_synonyms_weekly.php?token=XXX
 *
 * Endpoint VM appele :
 *   POST https://api.hellopro.eu/optimoteur-service/admin/synonyms/auto-generate
 *
 * Logique cote VM (synonyms_service.auto_generate_synonyms) :
 *   - Scan toutes les categories ingerees dans Typesense
 *   - Pour chaque categorie multi-tokens, genere les variantes :
 *     "Mini-pelles" -> minipelle, mini pelle, mini-pelle, minispelles, etc.
 *   - Push comme synonymes multi-way Typesense
 *
 * Apres ce script, lancer aussi sync_synonyms_daily.php pour pull le cache
 * local PHP front. Mais le cron quotidien le fera de toute facon.
 *
 * Frequence : HEBDO suffit (les categories ne changent pas tous les jours).
 * Cron suggere (lundi 4h, apres weekend tranquille) :
 *   0 4 * * 1 wget /script/typesense/auto_generate_synonyms_weekly.php?token=XXX
 *
 * Email de notification a la fin (succes ou erreur).
 * =============================================================================
 */

ini_set("memory_limit", "512M");
set_time_limit(0);

require_once($_SERVER['DOCUMENT_ROOT'] . "include/connexion.php");
require_once($_SERVER['DOCUMENT_ROOT'] . "include/functions.php");
require_once($_SERVER['DOCUMENT_ROOT'] . "fonctions/fonctions_hellopro.php");
require_once($_SERVER['DOCUMENT_ROOT'] . "fonctions/fonctions_generales.php");

// =============================================================================
// CONFIG
// =============================================================================
define('AUTO_GEN_API_URL', 'https://api.hellopro.eu/optimoteur-service/admin/synonyms/auto-generate');
define('NOTIFICATION_EMAIL', 'tandriatsiferantsoa@hellopro.fr');
define('HTTP_TOKEN', 'hp_syngen_2026_04_30_xZ7q');

// =============================================================================
// SECURITE : token jetable
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
$dry_run = isset($_GET['dry_run']) && $_GET['dry_run'] === '1';

// Headers HTTP
header('Content-Type: text/plain; charset=utf-8');
header('Cache-Control: no-store');
@ob_implicit_flush(true);
while (@ob_end_flush()) {}

// =============================================================================
// FONCTION : appel API
// =============================================================================
function api_call($url, $method = 'POST', $data = null) {
    $ch = curl_init();
    $options = [
        CURLOPT_URL            => $url,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT        => 600, // 10 min max (auto-generate sur 4500+ cat)
        CURLOPT_CONNECTTIMEOUT => 30,
        CURLOPT_HTTPHEADER     => ['Content-Type: application/json'],
        CURLOPT_FOLLOWLOCATION => true,
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
echo "Auto-generate synonyms weekly - " . date('Y-m-d H:i:s') . "\n";
echo "==========================================\n";
echo "API URL : " . AUTO_GEN_API_URL . "\n";
echo "Dry run : " . ($dry_run ? 'YES' : 'NO') . "\n";
echo "==========================================\n\n";

$url = AUTO_GEN_API_URL;
if ($dry_run) {
    $url .= '?dry_run=true';
}

try {
    echo "[INFO] Appel API VM (peut prendre quelques minutes)...\n";
    $response = api_call($url, 'POST');
    $http_code = $response['http_code'];
    $body = $response['body'];
    $result = json_decode($body, true);

    $elapsed = round(microtime(true) - $start_time, 2);

    if ($http_code !== 200 || !$result) {
        // ECHEC
        echo "\n[ERREUR] HTTP $http_code\n";
        echo "Body: $body\n";

        $subject = "[Script][Synonyms] ECHEC auto-generate hebdo";
        $message = "<h2>Echec auto-generate synonymes</h2>";
        $message .= "<p><strong>HTTP code:</strong> $http_code</p>";
        $message .= "<p><strong>Duree:</strong> {$elapsed}s</p>";
        $message .= "<p><strong>Body:</strong></p><pre>" . htmlspecialchars($body) . "</pre>";
        envoyer_mail_scripts($subject, '', NOTIFICATION_EMAIL, $message, 0);
        exit(1);
    }

    // SUCCES
    echo "\n[SUCCES] Auto-generate termine\n";
    echo "  Categories scannees      : " . ($result['nb_categories'] ?? 0) . "\n";
    echo "  Synonymes generes        : " . ($result['nb_synonyms_generated'] ?? 0) . "\n";
    echo "  Synonymes pushes Typesense: " . ($result['nb_synonyms_pushed'] ?? 0) . "\n";
    echo "  Erreurs                  : " . ($result['nb_errors'] ?? 0) . "\n";
    echo "  Dry run                  : " . (($result['dry_run'] ?? false) ? 'YES' : 'NO') . "\n";
    echo "  Duree                    : {$elapsed}s\n";

    if (!empty($result['examples'])) {
        echo "\n  Exemples (10 premiers) :\n";
        foreach (array_slice($result['examples'], 0, 5) as $ex) {
            echo "    - " . substr($ex['cat'], 0, 40) . " -> " . count($ex['variants']) . " variantes\n";
        }
    }

    // Email de notification
    $subject = sprintf(
        "[Script][Synonyms] OK auto-generate - %d synonymes pushes",
        $result['nb_synonyms_pushed'] ?? 0
    );
    $message = "<h2>Auto-generate synonymes hebdo - SUCCES</h2>";
    $message .= "<table border='1' cellpadding='5' cellspacing='0'>";
    $message .= "<tr><td><strong>Categories scannees</strong></td><td>" . ($result['nb_categories'] ?? 0) . "</td></tr>";
    $message .= "<tr><td><strong>Synonymes generes</strong></td><td>" . ($result['nb_synonyms_generated'] ?? 0) . "</td></tr>";
    $message .= "<tr><td><strong>Synonymes pushes Typesense</strong></td><td>" . ($result['nb_synonyms_pushed'] ?? 0) . "</td></tr>";
    $message .= "<tr><td><strong>Erreurs</strong></td><td>" . ($result['nb_errors'] ?? 0) . "</td></tr>";
    $message .= "<tr><td><strong>Duree</strong></td><td>{$elapsed}s</td></tr>";
    $message .= "</table>";

    if (!empty($result['examples'])) {
        $message .= "<h3>Exemples</h3><ul>";
        foreach (array_slice($result['examples'], 0, 10) as $ex) {
            $message .= "<li><strong>" . htmlspecialchars($ex['cat']) . "</strong> : "
                     . count($ex['variants']) . " variantes ("
                     . htmlspecialchars(implode(", ", array_slice($ex['variants'], 0, 5)))
                     . "...)</li>";
        }
        $message .= "</ul>";
    }

    envoyer_mail_scripts($subject, '', NOTIFICATION_EMAIL, $message, 0);

} catch (Exception $e) {
    $elapsed = round(microtime(true) - $start_time, 2);
    echo "\n[EXCEPTION] " . $e->getMessage() . "\n";

    $subject = "[Script][Synonyms] EXCEPTION auto-generate";
    $message = "<h2>Exception lors de auto-generate synonymes</h2>";
    $message .= "<p><strong>Erreur:</strong> " . htmlspecialchars($e->getMessage()) . "</p>";
    $message .= "<p><strong>Duree:</strong> {$elapsed}s</p>";
    envoyer_mail_scripts($subject, '', NOTIFICATION_EMAIL, $message, 0);
    exit(2);
}

echo "\n==========================================\n";
echo "Done in " . round(microtime(true) - $start_time, 2) . "s\n";
echo "==========================================\n";
