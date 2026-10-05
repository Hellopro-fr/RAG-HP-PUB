# MCP HelloData — côté PHP (moteur BO + webhook FRONT) — 2026-10-05

Ce document **remplace** `MCP_HELLODATA_PHP_2026-10-04.md` (supprimé dans le
même commit). Le PHP a été réécrit dans le style du code de production
(`sftp-mcp/prod`, relevé le 2026-10-05) : la version du 2026-10-04 utilisait
des requêtes préparées, un fichier `config.php` et des inclusions par
`__DIR__`, ce que la production ne fait nulle part.

Déploiement manuel par SFTP/FTP, selon `site/CLAUDE.md` : les `.php` ne sont
**pas** dans git (`site/admin/` et `site/partenaires_externes/` sont ignorés),
seul ce document passe en PR.

- Wrapper Go qui appelle ce code : `apps-microservices/mcp-hellodata-service`
  (`internal/hellodata/client.go`, `types.go` : source de vérité du format).
- Specs : `docs/superpowers/specs/2026-09-21-mcp-hellodata-selection-design.md`
  (moteur, § 13 : tout plafonné à 2000 lignes, export = une page CSV),
  `docs/superpowers/specs/2026-09-28-mcp-hellodata-campagnes-design.md`
  (campagnes, amendement du 2026-10-04 qui fixe le contrat).

## Style de production suivi

Références lues : `admin/hellodata/lancer_comptage_combine.php`,
`recup_type_operation_ajax.php`, `traitement_export_fiche_acheteur.php`,
`fonctions/fonctions_hellopro.php` (BO) et
`partenaires_externes/openclaw/webhook_sync_bo.php` (FRONT, 2026).

- Inclusions `require_once($_SERVER['DOCUMENT_ROOT']."…")`, y compris pour les
  fichiers du moteur. Pas de `check_session.php` : points d'entrée machine,
  l'authentification est le Bearer.
- mysqli procédural sur les liens globaux : `$GLOBALS['LINK_MYSQLI_HELLOPRO_DATA']`
  pour `acheteur` (comme `lancer_comptage_combine.php`),
  `$GLOBALS['LINK_MYSQLI_ANNUAIRE_BO']` pour les 4 tables de campagne, toujours
  écrites `edgb2b.historique_campagne_…`. Jamais de jointure entre les deux
  liens : l'historique est lu par des requêtes séparées.
- Requêtes `$sql_x = "…"; $qry_x = mysqli_query($GLOBALS['LINK_…'], $sql_x) or mcp_hd_echec_sql($sql_x, $GLOBALS['LINK_…']);`
  puis `while ($ligne_x = mysqli_fetch_assoc($qry_x))`. Aucune requête
  préparée, aucun PDO.
- Échappement par les helpers prod : chaînes entre apostrophes via
  `hellopro_traitement_donnee_hellopro_data()` (hpdata) ou
  `hellopro_traitement_donnee_annuaire_bo()` (edgb2b) ; nombres par cast
  `(int)` / `(float)` ; colonnes et opérateurs uniquement depuis les listes
  blanches du code ; `LIKE` : jokers `\ % _` échappés avant le helper.
- Transactions comme openclaw : `mysqli_begin_transaction()`, `try { … mysqli_commit(); } catch (Throwable $e) { mysqli_rollback(); … }`.
- Secrets comme openclaw : constante définie dans un fichier hors web.
- Sortie `header('Content-Type: application/json; charset=UTF-8')`,
  `http_response_code()`, `json_encode(…, JSON_UNESCAPED_UNICODE)` avec garde
  UTF-8 ; CSV : BOM `\xEF\xBB\xBF` puis `fputcsv(…, ';')`, comme
  `traitement_export_fiche_acheteur.php`.
- Aucun fichier de log sous la racine web (openclaw en écrit un, téléchargeable) :
  `error_log('[mcp-hellodata] …')` seulement, sans numéro ni e-mail.

### Écarts au style de production, et pourquoi

| Écart | Raison |
|---|---|
| `mcp_hd_echec_sql()` au lieu de `or die(hellopro_mysql_error(…))` | `hellopro_mysql_error()` est appelée (l'équipe reçoit toujours la requête et l'erreur MySQL par e-mail), mais `die()` enverrait un corps vide, ce qui casse le contrat JSON du wrapper. On répond `500 erreur_interne`, sans la requête ni le message MySQL. Dans une transaction, `mcp_hd_echec_sql_exception()` notifie puis lève une exception pour que le `catch` fasse le rollback. |
| `mysqli_report(MYSQLI_REPORT_OFF)` en tête des deux routeurs | Le motif `mysqli_query(…) or …` suppose que mysqli rende `false`. Depuis PHP 8.1, mysqli lève une exception par défaut : on fixe le comportement attendu quelle que soit la version du serveur. |
| `mysqli_set_charset(…, 'utf8mb4')` sur les liens utilisés | `json_encode` exige de l'UTF-8. Le réglage ne vaut que pour la requête HTTP en cours. Si les tables sont en latin1, MySQL convertit ; une garde `mcp_hd_utf8()` convertit en plus toute chaîne non UTF-8. |
| `setlocale(LC_NUMERIC, 'C')` (BO) | Sous PHP 7, un flottant concaténé suit la locale : « 1,5 » casserait le SQL. |
| `set_exception_handler()` | Toute exception imprévue rend un JSON 500, jamais une page HTML. |
| Garde `_MCP_HELLODATA_ROUTEUR_` en tête de chaque `actions/*.php` | Un appel direct à `…/actions/x.php` rend 404 vide au lieu de contourner le Bearer. |
| Fonctions préfixées `mcp_hd_…`, `$tab_sql_…` pour les fragments SQL | Convention vérifiable mécaniquement : une variable `$sql_*` / `$tab_sql_*` ou le retour d'une fonction `mcp_hd_sql_*()` ne contient que des littéraux, des valeurs échappées entre apostrophes, des casts ou d'autres `$sql_*`. |

## Fichiers à déposer

Ne **jamais** déposer de dossier `test/` ni de fichier `jeton_dev.php` en
production. Les fichiers marqués « copie identique » existent à l'octet près
des deux côtés.

### BO — `/admin/mcp/hellodata/`

| Fichier | Rôle |
|---|---|
| `admin/mcp/hellodata/index.php` | Routeur : includes prod, jeton, Bearer, POST, corps ≤ 256 Ko, dispatch des 5 actions |
| `admin/mcp/hellodata/fonctions_mcp_hellodata.php` | Réponse `{code, response}`, erreurs à code stable, `mcp_hd_echec_sql()`, Bearer, garde UTF-8, listes `IN (…)` échappées (copie identique côté FRONT) |
| `admin/mcp/hellodata/arbre.php` | Forme et bornes de l'arbre : profondeur 5, 50 feuilles, 1 à 20 enfants, `NON` unaire, noeud ambigu refusé |
| `admin/mcp/hellodata/criteres.php` | Liste blanche des 23 critères `acheteur` et validation des feuilles |
| `admin/mcp/hellodata/compilateur.php` | Arbre → `WHERE` échappé (chaque feuille est une expression autonome, d'où ET / OU / NON libres) |
| `admin/mcp/hellodata/requete.php` | Projection (email / mobile seulement avec le droit), dédoublonnage `ROW_NUMBER()` SIREN (2, 3) / SIRET (4, 5, 7, 8), curseur, page ≤ 2000 + ligne de sonde, comptages |
| `admin/mcp/hellodata/cache.php` | Cache de comptage 5 min sous `sys_get_temp_dir()` (entiers seulement) |
| `admin/mcp/hellodata/historique.php` | Feuilles `hist_*` : séparation de l'arbre, validation, faits lus dans `edgb2b`, évaluation |
| `admin/mcp/hellodata/telephone.php` | `telephone_normaliser()` → `0XXXXXXXXX` ou `null`, `telephone_est_mobile()` (copie identique côté FRONT) |
| `admin/mcp/hellodata/campagne.php` | Validation de `campagne` et de `n`, production du CSV |
| `admin/mcp/hellodata/actions/comptage.php` | Comptage approché (plafond 10 001 → `{count: 10000, plafonne: true}`) ou exact, cache |
| `admin/mcp/hellodata/actions/echantillon.php` | Une page de lignes par curseur (`taille` 1..2000, défaut 50) |
| `admin/mcp/hellodata/actions/export.php` | La même page en CSV brut, sentinelle finale `# fin-export;<lignes>;<curseur ou vide>` |
| `admin/mcp/hellodata/actions/recup_acheteur.php` | Sélection et inscription de `n` acheteurs dans une campagne |
| `admin/mcp/hellodata/actions/bilan_campagnes.php` | Campagnes et compteurs de réponses |
| `admin/mcp/hellodata/download.php` | Téléchargement du CSV par lien signé (GET, sans session ni Bearer), CSV régénéré |
| `admin/mcp/hellodata/telechargement.php` | Tickets signés (création, vérification, URL absolue) et écriture CSV commune à `export` et `download.php` |

### FRONT — `/partenaires_externes/mcp/hellodata/`

| Fichier | Rôle |
|---|---|
| `partenaires_externes/mcp/hellodata/index.php` | Routeur du webhook : includes FRONT, jeton propre, Bearer, POST, corps ≤ 256 Ko |
| `partenaires_externes/mcp/hellodata/fonctions_mcp_hellodata.php` | Copie identique du BO |
| `partenaires_externes/mcp/hellodata/telephone.php` | Copie identique du BO |
| `partenaires_externes/mcp/hellodata/reponses.php` | Validation des réponses, troncature à 2000 caractères, filet `STOP` |
| `partenaires_externes/mcp/hellodata/actions/enregistrer_reponses.php` | Rapprochement et écriture, une transaction par appel |

## Configuration : les jetons (étape manuelle)

Le compte SFTP ne peut pas écrire dans `no_read_access/` : ces deux fichiers
sont déposés **à la main** par quelqu'un qui a l'accès. Chacun ne fait que
définir une constante ; appelé en HTTP, un tel `.php` ne renvoie rien.

| Serveur | Fichier (relatif à `DOCUMENT_ROOT`) | Constante | Même valeur que |
|---|---|---|---|
| BO | `no_read_access/mcp_hellodata/jeton_bo.php` | `_MCP_HELLODATA_TOKEN_` | `HELLODATA_TOKEN` du wrapper |
| FRONT | `no_read_access/mcp_hellodata/jeton_webhook.php` | `_MCP_HELLODATA_WEBHOOK_TOKEN_` | `HELLODATA_WEBHOOK_TOKEN` du wrapper |

Modèle (remplacer la valeur entre chevrons, ne jamais la versionner) :

```php
<?php
define('_MCP_HELLODATA_TOKEN_', '<valeur de HELLODATA_TOKEN>');
```

Sur un serveur de dev où `no_read_access/` reste inaccessible, le routeur lit
à défaut un fichier `jeton_dev.php` posé à côté de `index.php`, au même format
(c'est le repli d'openclaw). Fichier absent ou constante vide : toutes les
requêtes rendent `500 jeton_absent`.

## Liens et bases utilisés

| Côté | Inclusions | Lien | Usage |
|---|---|---|---|
| BO | `admin/secure/connexion.php`, `no_read_access/connexion_bdd_hellopro_data.php`, `fonctions/fonctions_hellopro.php` | `LINK_MYSQLI_HELLOPRO_DATA` | lecture de `acheteur` (sans préfixe de base, comme la prod) |
| BO | idem | `LINK_MYSQLI_ANNUAIRE_BO` | lecture / écriture `edgb2b.historique_campagne_ia`, `…_acheteur_ia`, `…_acheteur_doublon_ia`, `…_suivi_ia` |
| FRONT | `include/connexion.php`, `fonctions/fonctions_generales.php`, `fonctions/fonctions_hellopro.php` | `LINK_MYSQLI_ANNUAIRE_BO` | écriture `edgb2b.historique_campagne_suivi_ia` et `…_acheteur_ia` (comme openclaw) |

## À vérifier sur le serveur avant le premier test

Points que l'agent n'a pas pu vérifier (lecture SFTP seule, `no_read_access/` illisible) :

1. **Version de PHP** des deux serveurs. Le code est vérifié (`php -l` et tests unitaires) sur PHP 7.0 et 8.2 ; il exige 7.0 au minimum (`Throwable`, tableau dans `define()`).
2. **Propagation de `Authorization`** : **constaté en prod le 2026-10-05** — même jeton des deux côtés (SHA-256 identiques) et `401 non_autorise` systématique : Ecritel (PHP-FPM) ne transmet pas `Authorization` au PHP, comme le montre déjà le webhook openclaw qui passe par ses propres en-têtes `X-LF-*`. Correctif, sans toucher au `.htaccess` : le wrapper envoie aussi le jeton dans **`X-Hellodata-Token`**, que `mcp_hd_verifier_jeton()` (BO et FRONT, copie identique) lit en second recours, toujours avec `hash_equals`. `Authorization: Bearer` reste lu en premier et suffit ailleurs (dev, tests).

   ```diff
   -	if (strpos($entete, 'Bearer ') !== 0) {
   -		return false;
   -	}
   -	$fourni = substr($entete, 7);
   -	if ($fourni === '' || $fourni === false) {
   +	$fourni = '';
   +	if (strpos($entete, 'Bearer ') === 0) {
   +		$fourni = (string)substr($entete, 7);
   +	} elseif (!empty($_SERVER['HTTP_X_HELLODATA_TOKEN'])) {
   +		$fourni = (string)$_SERVER['HTTP_X_HELLODATA_TOKEN'];
   +	}
   +	if ($fourni === '') {
    		return false;
    	}
    	return hash_equals($attendu, $fourni);
   ```

   Fichiers à redéposer : `admin/mcp/hellodata/fonctions_mcp_hellodata.php` et `partenaires_externes/mcp/hellodata/fonctions_mcp_hellodata.php`. Test : le gate `entete` du harnais (jeton seul dans `X-Hellodata-Token` → 200 ; mauvais, vide ou jeton de l'autre côté → 401).
3. **mysqli disponible sur les deux liens** : `admin/secure/connexion.php` doit bien créer `LINK_MYSQLI_ANNUAIRE_BO` sur le BO sans passer par `check_session.php`, et `include/connexion.php` le même lien sur le FRONT. Sinon : `500 erreur_interne`, journal `lien mysqli absent`.
4. **Droits d'écriture sur `edgb2b`** du compte annuaire BO, sur le BO **et** sur le FRONT : `SELECT`, `INSERT`, `UPDATE`, `DELETE` (le `DELETE` sert à détacher une fiche dont le numéro est devenu invalide).
5. **Tables en InnoDB** : les transactions par lot (BO) et par appel (FRONT) en dépendent ; en MyISAM le rollback ne fait rien.
6. **`max_execution_time`** : `recup_acheteur` s'arrête de lui-même à 100 s et appelle `set_time_limit(120)` ; si l'hébergeur l'interdit, la borne réelle sera plus courte (le wrapper attend 120 s).
7. **Jeu de caractères des tables** `acheteur` et `edgb2b` (utf8mb4 forcé côté client, voir les écarts).
8. **`mbstring`** : utilisée si présente, avec repli en `preg` sinon.

### Questions ouvertes

- **Colonne de téléphone** : seul `telephone_mobile_a` est lu (spec § 7). `telephone_standard_a` et `telephone_ligne_direct_a` existent sur `acheteur` : faut-il s'en servir en repli pour les campagnes `appel` ?
- **Droit au téléphone** : le CSV de `recup_acheteur` porte le numéro pour tout appelant autorisé, alors que `echantillon` / `export` réservent `mobile` à l'admin (précondition 5 non tranchée).
- **Numéros factices** : `TELEPHONES_FACTICES` (dans `telephone.php`) est à compléter à la recette ; le format réel des numéros n'a pas pu être audité.
- **`bilan_campagnes`** rend les 1000 campagnes les plus récentes au plus (pas de pagination dans le contrat).

- **`max_allowed_packet` de la base `hpdata`** : la liste d'exclusion de `recup_acheteur` peut atteindre 200 000 entiers (environ 1,5 Mo de SQL), renvoyée à chaque lot de 500. Vérifier qu'elle dépasse 2 Mo.
- **Limite connue du parcours** : les fiches qui ne donnent jamais de réservation (numéro invalide, `ne_plus_contacter`, exclusion par une feuille `hist_*`) ne sont pas mémorisées ; elles sont relues à chaque appel et comptent dans la borne de 100 000 fiches. Une campagne qui en a plus de 100 000 devant toute fiche sélectionnable rend `epuise = false` sans progresser : réduire le filtre plutôt que rappeler.

## Téléchargement du CSV (download.php)

Ajouté le 2026-10-05 (amendement « bis » de la spec campagnes) : le
`/download/{jeton}` du wrapper n'a pas de route publique, ses liens étaient
morts. Le BO sert désormais le fichier lui-même.

- **URL** : `https://<hôte BO>/admin/mcp/hellodata/download.php?t=<ticket>`, bâtie comme les exports existants du BO : `$GLOBALS['protocol_http_host_bo'] . $_SERVER['HTTP_HOST'] . "/admin/mcp/hellodata/download.php?t=…"`.
- **Ticket** : `base64url(gzdeflate(JSON)) . '.' . base64url(HMAC-SHA256)`, clé dérivée du jeton existant (`hash_hmac('sha256', 'mcp-hellodata-download', _MCP_HELLODATA_TOKEN_, true)`) : aucun nouveau secret ni fichier à déposer. Validité 15 minutes (`exp`). Tous les paramètres sont dans le ticket signé, le droit aux colonnes restreintes compris : le porteur du lien ne peut pas l'élever.
- **Réponses** : 200 CSV en pièce jointe (`text/csv`, BOM, `;`) ; ticket absent, malformé ou altéré → 403 `lien invalide` ; expiré → 410 ; GET seulement (405 sinon). Le contenu du ticket n'est jamais renvoyé.
- **`export`** : corps et sentinelle inchangés, en-tête `X-Hellodata-Lien: <url>` en plus ; le téléchargement rend la même page à l'octet près, **sans** la ligne sentinelle (la page est recalculée : si la base a changé entre-temps, le contenu suit la base).
- **`recup_acheteur`** : nouveau champ `url_csv` (vide si `selectionnes` = 0). Le ticket porte `id_campagne` et la plage `id_suivi` des réservations de l'appel ; le CSV est refait depuis `edgb2b` (suivi + identité) puis `acheteur` (requête séparée), mêmes colonnes. Limite connue : si une autre conversation réserve dans la **même** campagne au même instant, ses lignes peuvent tomber dans la plage.
- **Limite de 6000 caractères** : un ticket plus long n'est pas émis (`400 lien_trop_long` sur `export`, filtre à réduire) : Apache coupe la ligne de requête vers 8190 octets (`LimitRequestLine`). Le ticket `recup` fait une centaine de caractères.
- **Wrapper** : il rend ce lien au LLM (branche `features/mcp-hellodata-download`) et ne retombe sur son `/download` que si le moteur ne fournit pas de lien. Une fois `download.php` déployé, `HELLODATA_PUBLIC_URL` n'est plus nécessaire.
- **Le ticket est une capacité porteuse de 15 minutes** : quiconque détient le lien télécharge le fichier, autant de fois qu'il veut tant que le ticket n'a pas expiré (pas d'usage unique, rien n'est mémorisé côté serveur). Le ticket figure dans l'URL, donc dans les **journaux d'accès Apache du BO** : en restreindre la lecture aux personnes habilitées (ils donnent accès, pendant 15 minutes, à des listes de téléphones).
- **Durcissement** : le ticket est vérifié **avant** toute connexion MySQL (un appel non autorisé n'ouvre aucun lien) ; toutes les réponses portent `Cache-Control: no-store, private`, `Pragma: no-cache`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`.
- **Injection de formule** : dans tous les CSV du moteur (`export`, `recup_acheteur`, `download.php`), une cellule texte qui commence par `=`, `+`, `-`, `@`, tabulation ou retour chariot est préfixée d'une apostrophe ; un nombre pur (identifiant, téléphone) reste intact.
- **Wrapper** : il n'accepte le lien que si son schéma et son hôte sont ceux de `HELLODATA_BASE_URL` (https exigé), sinon repli `/download`.
- **À vérifier sur le serveur** : extension `zlib` (`gzdeflate` / `gzinflate`) disponible.

## Comportement et contrat

> **Amendement du 2026-10-05** (décisions de l'utilisateur, reportées dans la spec campagnes) : `recup_acheteur` continue chaque campagne en excluant du parcours toutes les fiches rattachées à un numéro déjà réservé dans cette campagne (reprise par exclusion, quel que soit le filtre ; au-delà de 200 000 fiches couvertes : `campagne_trop_volumineuse`), et STOP l'emporte quelle que soit la campagne dans `enregistrer_reponses`. Le contrat `ResultatReponses` ne change pas. Les deux routeurs posent aussi `ini_set('display_errors', '0')` : aucune erreur PHP ne s'affiche dans une réponse JSON.

- **Transport** : `POST {base}/index.php?action=<nom>`, `Authorization: Bearer <jeton>` et le même jeton dans `X-Hellodata-Token` (voir § vérifications, point 2), corps JSON. Succès `{"code":200,"response":{…}}` ; erreur : statut non 2xx et `{"code":<statut>,"response":{"erreur":"<code_stable>","message":"…"}}`. Le code stable est la tête du message (`groupe_vide: …`) et remonte tel quel au LLM.
- **Sélection** (`comptage`, `echantillon`, `export`) : arbre validé puis compilé en SQL échappé ; `id_acheteur <> 0 AND bloquage_a = 0` toujours posés ; dédoublonnage par `ROW_NUMBER()` dont le `CASE` donne sa propre partition à chaque fiche sans SIRET ; page lue avec une ligne de sonde pour `has_more` ; `export` = la même page en CSV (BOM + en-tête + lignes + sentinelle, sélection vide = BOM + sentinelle). Une feuille `hist_*` y est refusée (`critere_historique_hors_campagne`).
- **`recup_acheteur`** : validation (`campagne_invalide`, `n_hors_bornes`), campagne créée si son code est inconnu (`cree_par` lu au premier niveau du corps), sinon réutilisée ; canal ou date différents → `409 campagne_incoherente`. Feuilles `hist_*` admises seulement à la racine, en enfant direct du `ET` racine ou dans un sous-groupe purement `hist_*` enfant du `ET` racine (sinon `hist_hors_et_racine`). Parcours de `acheteur` par id décroissant, toujours depuis la fiche la plus récente ; pour une campagne existante il exclut (`AND A.id_acheteur NOT IN (…)`, entiers castés) toutes les fiches rattachées à un numéro déjà réservé dans cette campagne, lues par une requête séparée sur `edgb2b` — amendement du 2026-10-05 ; plus de 200 000 fiches couvertes → `campagne_trop_volumineuse`, lots de 500, au plus 100 000 fiches et 100 s ; une transaction par lot : identité du numéro, rattachement des fiches et `est_actif` (fiche de plus grand `id_acheteur`), exclusions (`ne_plus_contacter`, déjà dans la campagne, numéro invalide ou non mobile en `sms`), feuilles `hist_*`, puis réservation `INSERT IGNORE` jusqu'à `n`. `epuise = false` seulement si la borne ou une erreur a arrêté l'appel avant `n` : rappeler avec la même campagne. Sortie : `id_campagne`, `campagne_creee`, `selectionnes`, `exclus` (`ne_plus_contacter`, `critere_historique`, `deja_dans_campagne`, `telephone_invalide`), `fiches_parcourues`, `epuise`, `csv` (BOM + `telephone_normalise;id_acheteur;civilite;nom;prenom;raison_sociale;cp;ville`, sur la fiche active du numéro).
- **`bilan_campagnes`** : `{}` ou `{"code": "…"}` → `{"campagnes": [{code, nom, canal, date_campagne, cree_par, envoyes, positive, negative_contactable, negative_stop, sans_reponse}]}`.
- **`enregistrer_reponses`** (FRONT) : refus avant écriture (`corps_trop_gros`, `trop_de_reponses` > 500, `code_campagne_invalide`, `telephone_manquant`, `categorie_invalide`) ; campagne inconnue → `404 campagne_inconnue` ; numéro inconnu → `inconnus`, rien écrit ; hors campagne → `hors_campagne`, aucun suivi écrit, mais STOP l'emporte quelle que soit la campagne : si la catégorie effective est `negative_stop`, le numéro connu passe quand même en `ne_plus_contacter` (amendement du 2026-10-05, `mis_a_jour` ne compte que les suivis ; `stop_force` compte aussi un STOP forcé appliqué hors campagne) ; sinon `reponse_brute` (tronquée à 2000 caractères), `categorie`, `date_historique = NOW()` ; `^\s*STOP` force `negative_stop` (compté dans `stop_force`) ; `negative_stop` → `statut_contact = ne_plus_contacter`, jamais levé automatiquement ; un renvoi identique rend le même résultat ; une transaction par appel.
- **Erreur SQL** : `hellopro_mysql_error()` envoie la requête et l'erreur MySQL à l'équipe ; le client reçoit `500 erreur_interne` sans détail.

## Tests locaux (passés le 2026-10-05)

Pile Docker locale persistante, données synthétiques (adresses `@example.test`,
faux numéros) : MySQL 8.0 avec `hpdata.acheteur` et les 4 tables de la spec
dans `edgb2b`, deux comptes MySQL distincts (le lien hpdata en lecture seule,
le lien annuaire BO sans accès à hpdata et avec une base par défaut qui n'est
**pas** `edgb2b`), `php -S` sur PHP 8.2 avec le vrai `fonctions/fonctions_hellopro.php`
de production (seul l'envoi de mail est capturé dans un fichier). Le harnais
n'est pas versionné (hors du dépôt public). Il a vérifié :

- `php -l` de chaque fichier sur PHP 8.2 et 7.0 ;
- le style : aucune requête préparée, chaque `mysqli_query` sur un lien `$GLOBALS` et vérifié, inclusions `DOCUMENT_ROOT`, tables `edgb2b.` qualifiées, aucune valeur concaténée sans échappement ni cast (avec un contrôle positif par règle) ;
- 161 assertions unitaires (arbre, critères, compilateur avec valeurs hostiles, requête, cache, historique, CSV, filet STOP) sur 7.0 et 8.2, et le même fichier de cas de téléphone sur les deux copies ;
- 104 assertions HTTP contre MySQL : auth, chaque action, pagination sans décalage, deux `recup_acheteur` successifs sans numéro commun, reprise par exclusion (autre filtre sur la même campagne, campagne dont le haut est réservé, filet `deja_dans_campagne`) et campagne neuve repartant du haut, STOP hors campagne, doublons et `est_actif`, changement de numéro, feuilles `hist_*`, webhook (STOP, hors campagne, renvoi), `ne_plus_contacter` jamais levé, erreur SQL notifiée et rendue en JSON ;
- le contrat : le client Go du wrapper (`internal/hellodata`) décode chacune des 6 méthodes servies par ce PHP.

## Tests post-déploiement (sur dev)

Avec `BO=https://<hôte BO dev>/admin/mcp/hellodata/index.php`,
`FRONT=https://<hôte FRONT dev>/partenaires_externes/mcp/hellodata/index.php`,
`T` et `W` les deux jetons :

```bash
# 1. Auth : 401 sans jeton et avec un mauvais jeton
curl -s -o /dev/null -w '%{http_code}\n' -X POST "$BO?action=comptage" -d '{}'
curl -s -o /dev/null -w '%{http_code}\n' -X POST -H 'Authorization: Bearer mauvais' "$BO?action=comptage" -d '{}'

# 2. Comptage
curl -s -X POST -H "Authorization: Bearer $T" "$BO?action=comptage" \
  -d '{"filtre":{"critere":"region","comparateur":"dans","valeur":[6]}}'

# 3. Accès direct à une action : 404, corps vide
curl -s -o /dev/null -w '%{http_code}\n' -X POST "${BO%index.php}actions/bilan_campagnes.php"

# 4. Échantillon page 1 puis page 2 (cursor = next_cursor de la page 1)
curl -s -X POST -H "Authorization: Bearer $T" "$BO?action=echantillon" \
  -d '{"filtre":{"critere":"region","comparateur":"dans","valeur":[6]},"taille":5}'

# 5. Export : dernière ligne « # fin-export;5;<id> »
curl -s -X POST -H "Authorization: Bearer $T" "$BO?action=export" \
  -d '{"filtre":{"critere":"region","comparateur":"dans","valeur":[6]},"taille":5}' | tail -n 1

# 6. Campagne de recette, 20 numéros, puis un second appel identique
curl -s -X POST -H "Authorization: Bearer $T" "$BO?action=recup_acheteur" \
  -d '{"campagne":{"code":"recette-2026-10","nom":"Recette","canal":"sms","date_campagne":"2026-10-05"},
       "n":20,"cree_par":"recette@example.test","filtre":{"critere":"region","comparateur":"dans","valeur":[6]}}'

# 7. Webhook : une réponse STOP sur un numéro du CSV, puis le bilan
curl -s -X POST -H "Authorization: Bearer $W" "$FRONT?action=enregistrer_reponses" \
  -d '{"code_campagne":"recette-2026-10","reponses":[{"telephone":"<numéro du CSV>","reponse_brute":"STOP","categorie":"positive"}]}'
curl -s -X POST -H "Authorization: Bearer $T" "$BO?action=bilan_campagnes" -d '{"code":"recette-2026-10"}'
```

Attendus :
1. `401`, `401`.
2. `{"code":200,"response":{"count":…,"exact":false,"plafonne":…}}`.
3. `404`.
4. Aucun `id_acheteur` commun entre les deux pages.
5. `# fin-export;5;<id>`.
6. `selectionnes` = 20 et `csv` non vide ; au second appel, aucun des 20 premiers numéros, comptés dans `exclus.deja_dans_campagne`.
7. `mis_a_jour` = 1, `stop_force` = 1 ; au bilan, `negative_stop` = 1.

Après la recette, supprimer les lignes de la campagne `recette-2026-10` dans
`edgb2b.historique_campagne_suivi_ia` et `edgb2b.historique_campagne_ia`. Le
numéro passé en `ne_plus_contacter` doit être remis à la main en
`contactable` dans `edgb2b.historique_campagne_acheteur_ia` s'il s'agissait
d'un vrai prospect. Les identités et rattachements créés restent valables :
ils sont alimentés au fil de l'eau, par conception.
