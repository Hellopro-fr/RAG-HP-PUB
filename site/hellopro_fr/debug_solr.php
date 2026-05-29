<?php
/**
 * =============================================================================
 * debug_solr.php — Script TEMPORAIRE de diagnostic des scores Solr V2
 * -----------------------------------------------------------------------------
 * Usage :
 *   https://hellopro.fr/hellopro_fr/debug_solr.php?q=armoire+medicale&token=hp_debug_solr_2026_05_29
 *
 * Reproduit exactement la query de `recherche_produit_solr()` avec
 * `debugQuery=true` pour analyser les scores et les explanations.
 *
 * ⚠️ À SUPPRIMER après usage (ne pas laisser en prod long terme).
 * =============================================================================
 */

// =============================================================================
// SECURITE : token jetable
// =============================================================================
define('HP_DEBUG_TOKEN', 'hp_debug_solr_2026_05_29');
if (!isset($_GET['token']) || $_GET['token'] !== HP_DEBUG_TOKEN) {
    http_response_code(403);
    echo "Forbidden — token manquant ou invalide. Usage : ?q=...&token=hp_debug_solr_2026_05_29";
    exit;
}

// =============================================================================
// INCLUSIONS (memes que moteur_recherche.php)
// =============================================================================
require_once $_SERVER['DOCUMENT_ROOT'] . "no_read_access/moteur/connexion_mt_hellopro_pdt.php";
require_once $_SERVER['DOCUMENT_ROOT'] . "annuaire_hp/fonctions/fonctions_annuaire_hp.php";

// =============================================================================
// PARAMS
// =============================================================================
$mots_cles_raw = isset($_GET['q']) ? trim($_GET['q']) : 'armoire medicale';
$mots_cles_final = strtolower($mots_cles_raw);
$mots_cles_final = urldecode($mots_cles_final);

// =============================================================================
// CONSTRUCTION DU BQ (reproduit recherche_produit_solr)
// =============================================================================
$_relevance_tokens = preg_split('/\s+/', $mots_cles_final);
$_nom_clauses = array();
foreach ($_relevance_tokens as $_t) {
    $_t_clean = preg_replace('/[^a-z0-9-]/', '', $_t);
    if (strlen($_t_clean) >= 2 && !is_numeric($_t_clean)) {
        $_nom_clauses[] = "nom_produit:{$_t_clean}";
    }
}
$_nom_query = !empty($_nom_clauses) ? '(' . implode(' AND ', $_nom_clauses) . ')' : '';

$_bq_clauses = array();
$_bq_clauses[] = '(etat_societe:1)^500';
$_bq_clauses[] = '(etat_societe:2 AND visibilite_societe:1)^500';
$_bq_clauses[] = '(etat_societe:2)^20';
if ($_nom_query !== '') {
    $_bq_clauses[] = $_nom_query . '^500';
    $_cert_subquery = '(etat_societe:1 OR (etat_societe:2 AND visibilite_societe:1))';
    $_bq_clauses[] = '(' . $_cert_subquery . ' AND ' . $_nom_query . ')^8000';
}
$bq_param = implode(' ', $_bq_clauses);

// =============================================================================
// CONNEXION SOLR V2
// =============================================================================
$options = array(
    'hostname' => SOLR_SERVER_HOSTNAME,
    'login'    => SOLR_SERVER_USERNAME,
    'password' => SOLR_SERVER_PASSWORD,
    'path'     => function_exists('hp_get_solr_core_path') ? hp_get_solr_core_path() : 'solr/core0',
);

try {
    $client = new SolrClient($options);
} catch (Exception $e) {
    die("ERREUR connexion SolrClient : " . htmlspecialchars($e->getMessage()));
}

// =============================================================================
// QUERY SOLR avec debugQuery=true
// =============================================================================
$query = new SolrQuery();
$query->setQuery($mots_cles_final);
$query->addParam('defType', 'edismax');
$query->addParam('qf', 'nom_produit^50 categorie^25 sku^40');
$query->addFilterQuery('id_rubrique:[1 TO *]');
$query->setParam('bq', $bq_param);
$query->addField('id');
$query->addField('nom_produit');
$query->addField('etat_societe');
$query->addField('visibilite_societe');
$query->addField('id_categorie');
$query->addField('id_fournisseur');
$query->addField('categorie');
$query->addField('score');
$query->setRows(15);
$query->setStart(0);
$query->addParam('debugQuery', 'true');

try {
    $response = $client->query($query);
    $result = $response->getResponse();
} catch (Exception $e) {
    die("ERREUR query Solr : " . htmlspecialchars($e->getMessage()));
}

$docs = $result->response->docs ?? array();
$num_found = $result->response->numFound ?? 0;
$debug = isset($result->debug) ? $result->debug : null;

// =============================================================================
// RENDU HTML
// =============================================================================
header('Content-Type: text/html; charset=UTF-8');
?><!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>Debug Solr — <?= htmlspecialchars($mots_cles_raw) ?></title>
<style>
body { font-family: -apple-system, Arial, sans-serif; margin: 20px; line-height: 1.4; }
h1 { color: #1F4E79; }
h2 { color: #2E75B6; border-bottom: 2px solid #2E75B6; padding-bottom: 5px; margin-top: 30px; }
table { border-collapse: collapse; width: 100%; margin-bottom: 20px; font-size: 14px; }
th, td { border: 1px solid #ccc; padding: 6px 10px; text-align: left; vertical-align: top; }
th { background: #D9E1F2; color: #1F4E79; }
.cert { background: #d4edda; }
.noncert { background: #f8d7da; }
.score { font-weight: bold; text-align: right; font-family: Consolas, monospace; }
pre { background: #f5f5f5; padding: 10px; overflow-x: auto; font-size: 12px; max-height: 400px; }
.muted { color: #888; font-size: 12px; }
.summary { background: #fff3cd; padding: 10px; border-radius: 4px; margin: 15px 0; }
</style>
</head>
<body>

<h1>Debug Solr V2 — "<?= htmlspecialchars($mots_cles_raw) ?>"</h1>

<div class="summary">
<strong>Total docs trouvés :</strong> <?= number_format($num_found, 0, ',', ' ') ?><br>
<strong>Tokens nettoyés (pour bq):</strong> <code><?= htmlspecialchars(implode(', ', $_nom_clauses)) ?></code><br>
<strong>Bq complet :</strong><br>
<code style="display:block; padding:5px; background:#fff; margin-top:5px;">
<?= htmlspecialchars($bq_param) ?>
</code>
</div>

<h2>Top 15 résultats (les ✅ devraient être en HAUT)</h2>
<table>
<tr>
    <th>#</th>
    <th>nom_produit</th>
    <th>etat</th>
    <th>vis</th>
    <th>cert ?</th>
    <th>id_fournisseur</th>
    <th class="score">score</th>
</tr>
<?php
$i = 0;
foreach ($docs as $doc):
    $i++;
    $etat = $doc->etat_societe ?? '';
    $vis = $doc->visibilite_societe ?? '';
    $is_cert = ($etat == 1) || ($etat == 2 && $vis == 1);
    $cls = $is_cert ? 'cert' : 'noncert';
    $nom_short = substr($doc->nom_produit ?? '', 0, 120);
?>
<tr class="<?= $cls ?>">
    <td><?= $i ?></td>
    <td><?= htmlspecialchars($nom_short) ?></td>
    <td><?= htmlspecialchars($etat) ?></td>
    <td><?= htmlspecialchars($vis) ?></td>
    <td><?= $is_cert ? '✅ CERT' : '❌ non' ?></td>
    <td><?= htmlspecialchars($doc->id_fournisseur ?? '') ?></td>
    <td class="score"><?= number_format(round($doc->score ?? 0, 1), 1, ',', ' ') ?></td>
</tr>
<?php endforeach; ?>
</table>

<h2>Explanations détaillées (top 5)</h2>
<?php
if ($debug && isset($debug->explain)):
    $shown = 0;
    foreach ($debug->explain as $id => $exp):
        if ($shown >= 5) break;
        $shown++;

        // Retrouver le doc correspondant pour avoir le nom
        $doc_match = null;
        foreach ($docs as $d) {
            if (($d->id ?? '') === $id) { $doc_match = $d; break; }
        }
        $nom = $doc_match->nom_produit ?? '(inconnu)';
        $etat = $doc_match->etat_societe ?? '';
        $vis = $doc_match->visibilite_societe ?? '';
        $is_cert = ($etat == 1) || ($etat == 2 && $vis == 1);
        $badge = $is_cert ? '✅ CERT' : '❌ non-cert';
?>
<h3>#<?= $shown ?> — <?= htmlspecialchars(substr($nom, 0, 100)) ?> [<?= $badge ?>]</h3>
<p class="muted">id Solr : <code><?= htmlspecialchars($id) ?></code></p>
<pre><?= htmlspecialchars(is_string($exp) ? $exp : print_r($exp, true)) ?></pre>
<?php
    endforeach;
else: ?>
<p class="muted">Pas d'explain disponible (debugQuery non actif ?).</p>
<?php endif; ?>

<h2>Query Solr envoyée</h2>
<pre>q       : <?= htmlspecialchars($mots_cles_final) ?>

defType : edismax
qf      : nom_produit^50 categorie^25 sku^40
fq      : id_rubrique:[1 TO *]
rows    : 15
bq      : <?= htmlspecialchars(implode("\n          ", $_bq_clauses)) ?>

</pre>

<p class="muted" style="margin-top: 40px; border-top: 1px solid #ccc; padding-top: 15px;">
⚠️ Fichier de debug temporaire — à supprimer après usage.
Token : hp_debug_solr_2026_05_29.
</p>

</body>
</html>
