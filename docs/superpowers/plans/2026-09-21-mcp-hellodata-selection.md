# MCP HelloData — sélection paginée et export CSV — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Exposer au LLM le moteur de ciblage acheteurs du BO sous forme de données paginées et d'exports CSV, au lieu d'un simple comptage.

**Architecture:** Un moteur PHP neuf sur Ecritel (`/admin/mcp/hellodata/`) traduit un arbre de filtres métier en SQL et exécute à côté de la base ; un wrapper Go dans le monorepo (`mcp-hellodata-service`, port 8597) porte le contrat MCP, décide seul de l'autorisation à partir de l'identité injectée par le gateway, et proxifie le téléchargement des CSV pour qu'aucune URL du BO ne circule.

**Tech Stack:** PHP (Ecritel, mysqli, aucune dépendance) · Go 1.24 stdlib seule · MySQL 8.0.36 · MCP JSON-RPC 2.0 · Docker

**Spec:** `docs/superpowers/specs/2026-09-21-mcp-hellodata-selection-design.md`

## Global Constraints

Ces contraintes s'appliquent à **toutes** les tâches. Valeurs reprises telles quelles de la spec.

- **Go 1.24, bibliothèque standard uniquement.** Aucune dépendance externe — c'est la règle de `mcp-leexi-service`, que ce service suit.
- **PHP sans dépendance.** Pas de composer, pas de PHPUnit : le code est déployé par FTP sur Ecritel, où rien ne peut être installé. Les tests sont des scripts PHP nus.
- **Port du service : 8597.** 8590–8596, 8599–8601, 8610, 8625 et 8665 sont déjà pris dans `docker-compose.yml`.
- **`expose:` et jamais `ports:`** dans `docker-compose.yml` pour ce service. Contrairement à `mcp-leexi-service` qui publie `8589:8589`, ce service ne doit être joignable que depuis le réseau Docker interne : l'autorisation repose sur des en-têtes non signés (§ 7.1 de la spec).
- **Aucune adresse e-mail dans un fichier tracké.** `Hellopro-fr/RAG-HP-PUB` est un dépôt **public** ; une adresse commitée survit dans l'historique. Ni dans le code, ni dans un `.env.example`, ni dans un test — les tests utilisent des adresses fictives en `@example.test`.
- **Enveloppe HTTP du moteur : `{"code": 200, "response": {...}}`.** Identique à celle de `mcp-gateway-service/internal/bddcatalog/client.go`.
- **Plafonds de l'arbre de filtres :** profondeur ≤ 5, ≤ 50 feuilles au total, 1 à 20 enfants par groupe, `NON` strictement unaire.
- **Plafond d'échantillon : 2000 lignes**, défaut 50.
- **Comptage approché plafonné à 10 001**, cache TTL 5 minutes, purge des exports à 24 h.
- **Le PHP n'est pas tracké** (`site/CLAUDE.md`) : il vit localement sous `site/admin/mcp/hellodata/`, est déployé par upload FTP manuel, et ne part en PR que sous forme d'un `.md` de déploiement.
- **Commits : Conventional Commits, corps bilingue EN + FR** (`CLAUDE.md` racine). Le hook `conventional-commits.py` vérifie le préfixe de la première ligne.
- **Aucun SQL fourni par l'appelant.** Le moteur n'accepte qu'un arbre structuré ; toute valeur passe en requête préparée.

## Outillage local

**Ni `go` ni `php` ne sont installés sur cette machine.** Seul Docker l'est (`docker compose` 2.40.3). Toutes les commandes de test du plan passent donc par un conteneur jetable. Définis ces deux alias au début de chaque session d'exécution :

```bash
# Depuis la racine du repo
alias gotest='docker run --rm -v "$PWD":/src -w /src golang:1.24-alpine go'
alias phprun='docker run --rm -v "$PWD":/src -w /src php:8.2-cli php'
```

Si `go` ou `php` sont disponibles nativement, utilise-les directement — les commandes du plan sont écrites avec les alias, remplace `gotest` par `go` et `phprun` par `php`.

---

## Structure des fichiers

### Phase A — Moteur PHP (non tracké, local sous `site/admin/mcp/hellodata/`)

| Fichier | Responsabilité |
|---|---|
| `index.php` | Routeur unique : auth → dispatch d'action → enveloppe JSON. Aucune logique métier |
| `auth.php` | Vérification du Bearer. Rien d'autre |
| `reponse.php` | `repondre()` / `echouer()` : enveloppe `{code, response}` et codes d'erreur stables |
| `criteres.php` | Liste blanche : pour chaque critère, son type, ses comparateurs, sa table source, son fragment SQL |
| `arbre.php` | Parsing de l'arbre JSON + application des bornes structurelles. Pur |
| `compilateur.php` | Arbre validé → `(sql, params[])`. Applique la règle EXISTS / INNER JOIN. Pur |
| `requete.php` | Assemblage complet : SELECT, jointures, fenêtre de dédoublonnage, curseur, LIMIT. Pur |
| `cache.php` | Cache de comptage sur fichier, clé = hash de la forme canonique |
| `actions/comptage.php` | Comptage approché ou exact |
| `actions/echantillon.php` | Lecture paginée par curseur |
| `actions/export_start.php` | Inscrit un job, rend la main |
| `actions/export_worker.php` | Écrit le CSV en flux. Invoqué en tâche de fond |
| `actions/export_statut.php` | État d'un job |
| `actions/export_fetch.php` | Streame le CSV derrière le Bearer |
| `test/*.test.php` | Scripts de test nus, un par unité pure |

Répertoire d'état **hors racine web**, chemin confirmé en tâche 0 : `jobs/`, `exports/`, `cache/`.

### Phase B — Wrapper Go (`apps-microservices/mcp-hellodata-service/`)

| Fichier | Responsabilité |
|---|---|
| `cmd/server/main.go` | Câblage et démarrage |
| `internal/config/config.go` | Lecture de l'environnement |
| `internal/acces/autorise.go` | `Autorise(email, role)` : admin OU liste. Le cœur du contrôle d'accès |
| `internal/acces/liste.go` | Chargement et normalisation de la liste |
| `internal/filtre/arbre.go` | Types de l'arbre + décodage JSON |
| `internal/filtre/valide.go` | Bornes structurelles |
| `internal/hellodata/client.go` | Client HTTP du moteur : Bearer, déballage d'enveloppe, budget par endpoint |
| `internal/hellodata/types.go` | DTO de requête et de réponse |
| `internal/mcp/types.go` | Types JSON-RPC 2.0 et MCP |
| `internal/tools/registry.go` | Définition des 4 outils |
| `internal/tools/handler.go` | `initialize`, `tools/list` variable, `tools/call` |
| `internal/tools/selection.go` | Implémentation des 4 outils |
| `internal/download/proxy.go` | `GET /download/{handle}` |
| `internal/transport/streamable_http.go` | Transport HTTP |
| `Dockerfile`, `CLAUDE.md` | Build et documentation de service |

### Phase C — Gateway (`apps-microservices/mcp-gateway-service/`)

| Fichier | Modification |
|---|---|
| `internal/gateway/scoped_gateway.go` | Un `case` d'injection d'identité dans `requestHeadersFor` ; un cas de live-fetch dans le chemin `tools/list` |

`internal/gateway/access_gate.go` **n'est pas modifié.**

---

## Phase 0 — Préconditions bloquantes

### Task 0: Vérifier les neuf préconditions

Aucune ligne de code n'est écrite avant que cette tâche soit close. Chaque point est une **question à laquelle on répond par une observation**, pas par une hypothèse. Un point qui ne peut pas être vérifié est un point qui **bloque** : il remonte à l'utilisateur, il ne se contourne pas.

**Files:**
- Create: `docs/superpowers/plans/2026-09-21-mcp-hellodata-preconditions.md` (le compte rendu)

**Interfaces:**
- Consumes: rien
- Produces: les valeurs que les tâches suivantes citent — chemin d'état hors racine web, version PHP d'Ecritel, URL de base du moteur, nom du réseau Docker

- [ ] **Step 1: Chemin accessible en écriture hors racine web (spec § 4.1)**

Le moteur doit écrire `jobs/`, `exports/` et `cache/` en dehors de `DOCUMENT_ROOT`, sinon les CSV redeviennent téléchargeables par URL directe comme ceux de `/admin/hellodata/fichiers_exports/`.

Le MCP `sftp-reader` n'est pas attaché à ce projet ; pilote-le en JSON-RPC sur stdio :

```bash
cat > /tmp/sftp-drive.mjs <<'JS'
import { spawn } from "node:child_process";
const srv = spawn("node", ["/home/hellopro/ftp-reader/dist/index.js"], { stdio: ["pipe","pipe","inherit"] });
let buf = ""; const pending = new Map(); let id = 0;
srv.stdout.on("data", d => { buf += d; let i;
  while ((i = buf.indexOf("\n")) >= 0) { const l = buf.slice(0,i).trim(); buf = buf.slice(i+1);
    if (!l) continue; let m; try { m = JSON.parse(l); } catch { continue; }
    if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); } } });
const send = (method, params) => new Promise(r => { const n = ++id; pending.set(n, r);
  srv.stdin.write(JSON.stringify({ jsonrpc:"2.0", id:n, method, params }) + "\n"); });
await send("initialize", { protocolVersion:"2024-11-05", capabilities:{}, clientInfo:{name:"drive",version:"1"} });
srv.stdin.write(JSON.stringify({ jsonrpc:"2.0", method:"notifications/initialized" }) + "\n");
console.log(JSON.stringify((await send("tools/call", { name: process.argv[2], arguments: JSON.parse(process.argv[3]) })).result, null, 2));
srv.kill();
JS
node /tmp/sftp-drive.mjs sftp_list_dir '{"server":"prod","path":"/"}'
```

Attendu : la liste de la racine du compte. Compte **~40 s par opération** — le bastion Wallix est lent, et un `Timed out while waiting for handshake` est transitoire, pas une absence de fichier : réessaie.

Cherche un répertoire frère de la racine web, en écriture. **Si aucun n'existe**, le repli est un répertoire sous `/admin/mcp/hellodata/var/` protégé par un `.htaccess` `Deny from all` — et il faudra **prouver** que la protection fonctionne en tentant un `curl` sur un fichier témoin, pas la supposer.

Note le chemin retenu dans le compte rendu.

- [ ] **Step 2: Version de PHP sur Ecritel**

Le moteur tourne sur Ecritel, pas ici. La syntaxe autorisée en dépend.

Dépose un fichier témoin et lis-le, ou demande la valeur à l'administrateur. Le code existant (`lancer_comptage_combine.php`) utilise `mysqli_*` et `list(...) = explode(...)` sans opérateur de coalescence, ce qui ne prouve qu'un plancher très bas.

**Décision à consigner** : le plan écrit du PHP compatible **7.0+** (pas de types de propriété, pas d'`?->`, pas d'arguments nommés). Si Ecritel est en 5.x, remonte-le : plusieurs constructions du plan devront changer.

- [ ] **Step 3: Pas de `.htaccess` imposant une session sur `/admin/`**

```bash
node /tmp/sftp-drive.mjs sftp_list_dir '{"server":"prod","path":"/admin"}'
```

Cherche un `.htaccess`. S'il existe, lis-le : s'il impose une authentification HTTP ou une redirection de session sur tout `/admin/`, le moteur ne pourra pas répondre à un simple Bearer, et l'emplacement du moteur doit être rediscuté.

- [ ] **Step 4: Joignabilité réseau RAG → BO en HTTPS**

Depuis l'hôte qui exécutera `mcp-hellodata-service` :

```bash
curl -s -o /dev/null -w '%{http_code}\n' --max-time 10 https://<hôte-bo-ecritel>/admin/
```

Attendu : un code HTTP, quel qu'il soit. Un timeout ou un échec DNS **bloque tout le projet** — sans ce chemin réseau, l'architecture entière ne tient pas.

- [ ] **Step 5: Droit aux colonnes téléphone et e-mail pour un non-admin**

Question métier, pas technique : un utilisateur admis **par la liste statique** (donc non `admin`) a-t-il droit aux colonnes `email`, `telephone`, `telephone_md5`, `fax` ?

Tant que ce n'est pas tranché, le plan applique le défaut prudent de la spec : **seul un `admin` les obtient**. Consigne la réponse.

- [ ] **Step 6: Coût réel des sous-requêtes corrélées**

C'est la précondition la plus susceptible de changer le design. Mesure sur la vraie base, via le MCP `bdd` (`bdd_query_readonly`) ou un client MySQL, un `OU` entre deux critères portant sur des tables liées :

```sql
SELECT COUNT(*) FROM (
  SELECT A.id_acheteur
  FROM acheteur A
  WHERE A.bloquage_a = 0
    AND (
      (SELECT COUNT(*) FROM demande_information DI WHERE DI.id_societe = A.id_source_a) >= 3
      OR A.effectif_a >= 10
    )
  LIMIT 10001
) t;
```

Attendu : une réponse en quelques secondes. **Si la requête dépasse largement une minute**, la règle de composition de la spec (§ 4.3.3) n'est pas tenable telle quelle : le repli documenté est de restreindre les critères sur tables liées à la chaîne `ET` de premier niveau, et de le dire au LLM dans le message de refus. Consigne la mesure, pas une impression.

- [ ] **Step 7: Isolation réseau réelle du service en production**

C'est **la** garantie du modèle d'accès : si autre chose que le gateway peut joindre le port 8597, l'en-tête `X-End-User-Role: admin` est forgeable et la liste d'autorisés ne protège rien.

Vérifie sur le déploiement réel, pas seulement dans `docker-compose.yml`. Note que `mcp-leexi-service` publie `8589:8589` — la convention existante **ne convient pas** ici, et la divergence est délibérée.

- [ ] **Step 8: Où injecter les variables d'environnement en production**

`HELLODATA_ALLOWED_EMAILS` contient des adresses d'employés et le dépôt est **public**. Identifie le mécanisme d'injection (fichier `.env` hors git, secret d'orchestrateur, variable CI) **avant** la première mise en service.

- [ ] **Step 9: Budget du live-fetch `tools/list`**

Le gateway interrogera le backend à chaque `tools/list` (§ 7.2). Relis `scoped_gateway.go:363` et le budget appliqué au live-fetch Zoho. Confirme qu'un backend lent ne pénalise pas le `tools/list` des autres backends agrégés dans la même réponse.

- [ ] **Step 10: Écrire le compte rendu et commiter**

Une ligne par précondition : la question, l'observation, la valeur retenue. Les points non résolus sont listés en tête comme **bloquants**.

```bash
git add docs/superpowers/plans/2026-09-21-mcp-hellodata-preconditions.md
git commit -m "docs(mcp-hellodata): record precondition checks before implementation

EN: Records the nine precondition observations gathered before any code:
writable path outside the web root, Ecritel PHP version, /admin htaccess,
RAG to BO reachability, phone and email column rights for non-admins,
measured cost of correlated subqueries, production network isolation, where
environment variables are injected, and the tools/list live-fetch budget.

FR: Consigne les neuf observations de precondition recueillies avant tout
code : chemin en ecriture hors racine web, version PHP d'Ecritel, htaccess
sur /admin, joignabilite RAG vers BO, droits aux colonnes telephone et email
pour un non-admin, cout mesure des sous-requetes correlees, isolation reseau
en production, lieu d'injection des variables d'environnement, et budget du
live-fetch tools/list."
```

- [ ] **Step 11: Obtenir le schéma réel de `acheteur` — BLOQUANT pour la Task A2**

Découverte faite pendant la rédaction de ce plan, et elle invalide une hypothèse implicite de la spec : **`bdd_describe_table` ne renvoie pas le schéma réel**, mais le registre curé `bdd_used_fields`. Il liste 29 colonnes, alors que la table en a davantage.

Preuves obtenues le 2026-09-21 via `bdd_query_readonly` :

| Colonne | Dans `bdd_describe_table` | Existe réellement |
|---|---|---|
| `bloquage_a` | non | **oui** — `SELECT COUNT(*) FROM acheteur WHERE bloquage_a = 0` rend 5 615 366 |
| `email_a` | non | **oui** — `SELECT email_a … WHERE id_acheteur = 0` rend 0 ligne, sans erreur |
| `mail_a` | non | **non** — erreur base de données |
| `telephone_a` ou `effectif_a` | non | **au moins un des deux n'existe pas** — la requête combinée échoue alors que `email_a` seul passe |

La spec § 4.4 liste des colonnes restituables (`fax`, `validite_email`, `chiffre_affaires`, `forme_juridique`, `code_insee`, `secteur_activite`) tirées de l'écran d'extraction du BO. **Rien ne prouve qu'elles sont sur `acheteur`** ; elles viennent probablement de tables jointes.

Obtiens un `DESCRIBE acheteur` **authentique**, par la voie la plus directe disponible :

1. demande-le à quelqu'un ayant un accès MySQL direct ; ou
2. une fois le squelette du moteur déployé (Task A5), expose une action `schema` temporaire, protégée par le Bearer, qui exécute `SHOW COLUMNS FROM acheteur` et la supprime ensuite ; ou
3. à défaut, sonde colonne par colonne avec le motif validé ci-dessus — une colonne inexistante produit une erreur, une colonne valide rend zéro ligne :

```sql
SELECT <colonne_candidate> FROM acheteur WHERE id_acheteur = 0 LIMIT 1
```

Fais de même pour les tables jointes dont dépendent les critères DI et emailing (`demande_information` au minimum, dont la clé de jointure vue dans `lancer_comptage_combine.php` est `DI.id_societe = A.id_source_a`).

Consigne le schéma obtenu dans le compte rendu : **la Task A2 le recopie**, elle ne le devine pas.

**Colonnes déjà confirmées** utilisables sans nouvelle vérification :

`id_acheteur`, `id_source_a`, `source_a`, `date_creation_a`, `raison_sociale_a`, `nom_commercial_a`, `cp_a`, `ville_a`, `adresse_a`, `site_web_a`, `civilite_a`, `nom_a`, `prenom_a`, `code_fonction_a`, `code_service_a`, `statut_a`, `telephone_mobile_a`, `siret_a`, `siren_a`, `code_effectif_a`, `code_naf_a`, `naf_niv2_a`, `naf_niv3_a`, `naf_niv4_a`, `id_pays_a`, `departement_a`, `region_a`, `annee_creat_a`, `mois_creat_a`, `bloquage_a`, `email_a`

**Gate de sortie de la Phase 0 :** les steps 1, 4 et 11 sont bloquants pour toute la suite. Les steps 6 et 7 sont bloquants respectivement pour la Task A4 et la mise en production. Les autres sont des valeurs à consigner.

---

## Phase A — Moteur PHP

> Tout le code de cette phase vit sous `site/admin/mcp/hellodata/`, **non tracké** (`site/CLAUDE.md`). Les commits de la phase ne portent donc que sur les fichiers `docs/`. Le `.php` part sur Ecritel par upload FTP manuel, accompagné d'un `.md` de déploiement (Task A9).

### Task A1: Harnais de test et validation structurelle de l'arbre

`arbre.php` est la première brique parce qu'elle est **pure et sans dépendance** : elle ne connaît pas la liste des critères, seulement la forme d'un arbre. On peut donc la tester avant que quoi que ce soit d'autre existe.

**Files:**
- Create: `site/admin/mcp/hellodata/arbre.php`
- Create: `site/admin/mcp/hellodata/test/_assert.php`
- Test: `site/admin/mcp/hellodata/test/arbre.test.php`

**Interfaces:**
- Consumes: rien
- Produces: `arbre_valider(array $noeud): int` — rend le nombre de feuilles, lève `ArbreErreur` au premier problème. Constantes `ARBRE_PROFONDEUR_MAX = 5`, `ARBRE_FEUILLES_MAX = 50`, `ARBRE_ENFANTS_MAX = 20`. `arbre_est_feuille(array $noeud): bool`.

- [ ] **Step 1: Écrire le harnais de test**

Aucune dépendance : le moteur est déployé par FTP sur un hôte où rien ne s'installe.

```php
<?php
// test/_assert.php — mini-harnais sans dependance. Sort en 1 au premier echec.

$GLOBALS['assertions'] = 0;

function ok($condition, $nom) {
    if ($condition) { $GLOBALS['assertions']++; echo "  ok   $nom\n"; return; }
    echo "  FAIL $nom\n";
    exit(1);
}

/** Verifie qu'un appel leve une exception dont le message contient $fragment. */
function leve(callable $fn, $fragment, $nom) {
    try {
        $fn();
    } catch (Exception $e) {
        if (strpos($e->getMessage(), $fragment) !== false) {
            $GLOBALS['assertions']++; echo "  ok   $nom\n"; return;
        }
        echo "  FAIL $nom : message inattendu << " . $e->getMessage() . " >>\n";
        exit(1);
    }
    echo "  FAIL $nom : aucune exception levee\n";
    exit(1);
}

function bilan() { echo "OK - {$GLOBALS['assertions']} assertions\n"; }
```

- [ ] **Step 2: Écrire les tests qui échouent**

```php
<?php
// test/arbre.test.php
require_once __DIR__ . '/_assert.php';
require_once __DIR__ . '/../arbre.php';

$feuille = array('critere' => 'region', 'comparateur' => 'dans', 'valeur' => array(1));

// --- controle positif : sans lui, les tests de refus ne prouvent rien ---
ok(arbre_valider($feuille) === 1, 'une feuille seule vaut 1 feuille');

$plat = array('operateur' => 'ET', 'conditions' => array($feuille, $feuille));
ok(arbre_valider($plat) === 2, 'un ET de deux feuilles vaut 2 feuilles');

$imbrique = array('operateur' => 'ET', 'conditions' => array(
    $feuille,
    array('operateur' => 'OU', 'conditions' => array($feuille, $feuille)),
));
ok(arbre_valider($imbrique) === 3, 'imbrication comptee correctement');

// profondeur 5 exactement : doit passer
$n = $feuille;
for ($i = 0; $i < 4; $i++) { $n = array('operateur' => 'ET', 'conditions' => array($n)); }
ok(arbre_valider($n) === 1, 'profondeur 5 acceptee');

// profondeur 6 : doit echouer
$trop = array('operateur' => 'ET', 'conditions' => array($n));
leve(function () use ($trop) { arbre_valider($trop); },
     'arbre_trop_complexe', 'profondeur 6 refusee');

// 51 feuilles : doit echouer
$large = array('operateur' => 'ET', 'conditions' => array());
for ($i = 0; $i < 20; $i++) { $large['conditions'][] = $feuille; }
$racine = array('operateur' => 'ET', 'conditions' => array($large, $large, $large));
leve(function () use ($racine) { arbre_valider($racine); },
     'arbre_trop_complexe', '60 feuilles refusees');

// groupe vide
leve(function () { arbre_valider(array('operateur' => 'ET', 'conditions' => array())); },
     'groupe_vide', 'groupe sans condition refuse');

// NON binaire
leve(function () use ($feuille) {
        arbre_valider(array('operateur' => 'NON', 'conditions' => array($feuille, $feuille)));
     }, 'non_unaire', 'NON a deux enfants refuse');

// NON unaire : doit passer
ok(arbre_valider(array('operateur' => 'NON', 'conditions' => array($feuille))) === 1,
   'NON unaire accepte');

// 21 enfants
$vingtetun = array('operateur' => 'OU', 'conditions' => array());
for ($i = 0; $i < 21; $i++) { $vingtetun['conditions'][] = $feuille; }
leve(function () use ($vingtetun) { arbre_valider($vingtetun); },
     'arbre_trop_complexe', '21 enfants refuses');

// operateur inconnu
leve(function () use ($feuille) {
        arbre_valider(array('operateur' => 'XOR', 'conditions' => array($feuille)));
     }, 'operateur_inconnu', 'operateur XOR refuse');

// noeud ni feuille ni groupe
leve(function () { arbre_valider(array('truc' => 1)); },
     'noeud_invalide', 'noeud sans critere ni operateur refuse');

bilan();
```

- [ ] **Step 3: Lancer les tests et vérifier qu'ils échouent**

```bash
cd /home/hellopro/RAG-HP-PUB
docker run --rm -v "$PWD":/src -w /src php:8.2-cli \
  php site/admin/mcp/hellodata/test/arbre.test.php
```

Attendu : échec, `Failed to open stream: ... arbre.php`.

- [ ] **Step 4: Écrire l'implémentation minimale**

```php
<?php
// arbre.php — forme et bornes de l'arbre de filtres. Pur : aucune I/O,
// aucune connaissance de la liste blanche des criteres (voir criteres.php).

define('ARBRE_PROFONDEUR_MAX', 5);
define('ARBRE_FEUILLES_MAX', 50);
define('ARBRE_ENFANTS_MAX', 20);

class ArbreErreur extends Exception {}

function arbre_est_feuille($noeud) {
    return is_array($noeud) && isset($noeud['critere']);
}

/**
 * Valide la forme de l'arbre et rend son nombre de feuilles.
 * Leve ArbreErreur au premier probleme, avec la limite franchie nommee.
 */
function arbre_valider($noeud) {
    $feuilles = 0;
    arbre_parcourir($noeud, 1, $feuilles);
    return $feuilles;
}

/**
 * Le compteur de feuilles est passe par reference et verifie a CHAQUE
 * feuille, pas a la fin : avec 20 enfants et 5 niveaux, un arbre peut
 * porter 3,2 millions de feuilles, et le parcourir entierement avant de
 * le refuser serait exactement le deni de service qu'on veut eviter.
 */
function arbre_parcourir($noeud, $profondeur, &$feuilles) {
    if (!is_array($noeud)) {
        throw new ArbreErreur('noeud_invalide: un noeud doit etre un objet');
    }
    if (arbre_est_feuille($noeud)) {
        $feuilles++;
        if ($feuilles > ARBRE_FEUILLES_MAX) {
            throw new ArbreErreur('arbre_trop_complexe: plus de ' . ARBRE_FEUILLES_MAX . ' feuilles');
        }
        return;
    }
    if (!isset($noeud['operateur'])) {
        throw new ArbreErreur("noeud_invalide: ni 'critere' ni 'operateur'");
    }
    $op = $noeud['operateur'];
    if ($op !== 'ET' && $op !== 'OU' && $op !== 'NON') {
        throw new ArbreErreur("operateur_inconnu: '$op' (attendus: ET, OU, NON)");
    }
    if ($profondeur > ARBRE_PROFONDEUR_MAX) {
        throw new ArbreErreur('arbre_trop_complexe: profondeur superieure a ' . ARBRE_PROFONDEUR_MAX);
    }
    $enfants = isset($noeud['conditions']) ? $noeud['conditions'] : null;
    if (!is_array($enfants) || count($enfants) === 0) {
        throw new ArbreErreur("groupe_vide: '$op' doit porter au moins une condition");
    }
    if ($op === 'NON' && count($enfants) !== 1) {
        throw new ArbreErreur('non_unaire: NON prend exactement 1 condition, ' . count($enfants) . ' fournies');
    }
    if (count($enfants) > ARBRE_ENFANTS_MAX) {
        throw new ArbreErreur('arbre_trop_complexe: ' . count($enfants) . ' enfants, maximum ' . ARBRE_ENFANTS_MAX);
    }
    foreach ($enfants as $enfant) {
        arbre_parcourir($enfant, $profondeur + 1, $feuilles);
    }
}
```

- [ ] **Step 5: Lancer les tests et vérifier qu'ils passent**

```bash
docker run --rm -v "$PWD":/src -w /src php:8.2-cli \
  php site/admin/mcp/hellodata/test/arbre.test.php
```

Attendu : `OK - 12 assertions`.

- [ ] **Step 6: Commiter la note de suivi**

Le `.php` n'est pas tracké. Ce qui se commite, c'est l'avancement.

```bash
git add docs/superpowers/plans/2026-09-21-mcp-hellodata-selection.md
git commit -m "docs(mcp-hellodata): mark A1 tree validation done

EN: Structural tree validation implemented and tested locally. Leaf counter
is checked per leaf rather than at the end, so an oversized tree is rejected
before it is fully walked.

FR: Validation structurelle de l'arbre implementee et testee en local. Le
compteur de feuilles est verifie a chaque feuille plutot qu'a la fin, pour
qu'un arbre surdimensionne soit refuse avant d'etre entierement parcouru."
```

---

### Task A2: Liste blanche des critères

Le catalogue est la **seule** porte d'entrée : ce qui n'y figure pas ne peut pas être exprimé en SQL. C'est ce qui rend l'absence de SQL utilisateur structurelle plutôt que déclarative.

Chaque critère porte une **expression SQL autonome**. C'est ce qui fait tomber le piège des jointures de la spec § 4.3.3 sans code dédié : une feuille compilable seule se compose librement sous `ET`, `OU` et `NON`. L'optimisation « `INNER JOIN` pour la chaîne `ET` de premier niveau » de la spec est **volontairement non implémentée en v1** — la spec l'écrit comme une exception facultative, et elle ne se justifie qu'à la lumière de la mesure de la Task 0 step 6.

**Files:**
- Create: `site/admin/mcp/hellodata/criteres.php`
- Test: `site/admin/mcp/hellodata/test/criteres.test.php`

**Interfaces:**
- Consumes: rien
- Produces:
  - `criteres_catalogue(): array` — clé = nom du critère, valeur = `array('type' => string, 'expr' => string)`
  - `criteres_comparateurs(string $type): array`
  - `criteres_valider_feuille(string $critere, string $comparateur, $valeur): array` — rend `array($type, $valeur_normalisee)`, lève `CritereErreur`
  - Constante `CRITERE_VALEURS_MAX = 500`

- [ ] **Step 1: Écrire les tests qui échouent**

```php
<?php
// test/criteres.test.php
require_once __DIR__ . '/_assert.php';
require_once __DIR__ . '/../criteres.php';

$cat = criteres_catalogue();
ok(count($cat) >= 20, 'le catalogue porte au moins 20 criteres');
ok(isset($cat['region']['expr']), 'region a une expression SQL');

// --- controles positifs, un par type ---
list($t, $v) = criteres_valider_feuille('region', 'dans', array(6, 11));
ok($t === 'liste' && $v === array(6, 11), 'liste: dans accepte');

list($t, $v) = criteres_valider_feuille('annee_creation', '>=', 2015);
ok($t === 'numerique' && $v === 2015, 'numerique: >= accepte');

list($t, $v) = criteres_valider_feuille('fiche_creation', 'entre',
    array('2025-01-01', '2025-12-31'));
ok($t === 'date' && count($v) === 2, 'date: entre accepte deux bornes');

list($t, $v) = criteres_valider_feuille('a_siret', '=', true);
ok($t === 'booleen' && $v === true, 'booleen: = accepte');

list($t, $v) = criteres_valider_feuille('ville', 'contient', 'Rennes');
ok($t === 'texte' && $v === 'Rennes', 'texte: contient accepte');

// --- refus ---
leve(function () { criteres_valider_feuille('couleur_preferee', 'dans', array(1)); },
     'critere_inconnu', 'critere inexistant refuse');

// le message doit enseigner le vocabulaire, pas seulement refuser
try { criteres_valider_feuille('couleur_preferee', 'dans', array(1)); }
catch (Exception $e) {
    ok(strpos($e->getMessage(), 'region') !== false,
       'le refus enumere les criteres connus');
}

leve(function () { criteres_valider_feuille('region', 'contient', 'x'); },
     'comparateur_invalide', 'comparateur incompatible avec le type refuse');

leve(function () { criteres_valider_feuille('region', 'dans', array()); },
     'valeur_invalide', 'liste vide refusee');

leve(function () { criteres_valider_feuille('region', 'dans', 'Bretagne'); },
     'valeur_invalide', 'dans exige un tableau');

$trop = range(1, CRITERE_VALEURS_MAX + 1);
leve(function () use ($trop) { criteres_valider_feuille('region', 'dans', $trop); },
     'valeur_invalide', 'liste au-dela du plafond refusee');

leve(function () { criteres_valider_feuille('annee_creation', '>=', 'mille'); },
     'valeur_invalide', 'numerique non numerique refuse');

leve(function () { criteres_valider_feuille('fiche_creation', 'entre', array('2025-01-01')); },
     'valeur_invalide', 'entre exige exactement deux bornes');

leve(function () { criteres_valider_feuille('fiche_creation', 'apres', '01/01/2025'); },
     'valeur_invalide', 'date hors format ISO refusee');

// aucune expression du catalogue ne doit contenir de point d'interrogation :
// les valeurs sont liees par le compilateur, jamais par le catalogue
foreach (criteres_catalogue() as $nom => $def) {
    ok(strpos($def['expr'], '?') === false, "expr de '$nom' sans placeholder");
}

bilan();
```

- [ ] **Step 2: Lancer les tests et vérifier qu'ils échouent**

```bash
docker run --rm -v "$PWD":/src -w /src php:8.2-cli \
  php site/admin/mcp/hellodata/test/criteres.test.php
```

Attendu : échec, `criteres.php` absent.

- [ ] **Step 3: Écrire le catalogue**

Toutes les colonnes ci-dessous sont **confirmées existantes** sur `hpdata.acheteur` (Task 0 step 11). N'en ajoute aucune autre sans l'avoir sondée.

```php
<?php
// criteres.php — liste blanche des criteres exposables.
// Chaque critere porte une EXPRESSION SQL AUTONOME : elle se suffit a
// elle-meme dans un WHERE, sans jointure a ajouter. C'est ce qui permet
// de composer librement sous ET, OU et NON sans qu'une INNER JOIN
// n'elimine a tort des lignes que l'autre branche devait retenir.
//
// Aucune expression ne contient de placeholder : les valeurs sont liees
// par le compilateur (compilateur.php), jamais concatenees ici.

define('CRITERE_VALEURS_MAX', 500);

class CritereErreur extends Exception {}

function criteres_catalogue() {
    return array(
        // --- geographie ---
        'region'            => array('type' => 'liste',     'expr' => 'A.region_a'),
        'departement'       => array('type' => 'liste',     'expr' => 'A.departement_a'),
        'code_postal'       => array('type' => 'liste',     'expr' => 'A.cp_a'),
        'ville'             => array('type' => 'texte',     'expr' => 'A.ville_a'),
        'pays'              => array('type' => 'liste',     'expr' => 'A.id_pays_a'),

        // --- entreprise ---
        'naf'               => array('type' => 'liste',     'expr' => 'A.code_naf_a'),
        'naf_niveau2'       => array('type' => 'liste',     'expr' => 'A.naf_niv2_a'),
        'naf_niveau3'       => array('type' => 'liste',     'expr' => 'A.naf_niv3_a'),
        'naf_niveau4'       => array('type' => 'liste',     'expr' => 'A.naf_niv4_a'),
        'effectif'          => array('type' => 'liste',     'expr' => 'A.code_effectif_a'),
        'annee_creation'    => array('type' => 'numerique', 'expr' => 'A.annee_creat_a'),
        'statut_entreprise' => array('type' => 'liste',     'expr' => 'A.statut_a'),
        'raison_sociale'    => array('type' => 'texte',     'expr' => 'A.raison_sociale_a'),
        'nom_commercial'    => array('type' => 'texte',     'expr' => 'A.nom_commercial_a'),
        'a_siret'           => array('type' => 'booleen',   'expr' => "(A.siret_a <> '')"),
        'a_site_web'        => array('type' => 'booleen',   'expr' => "(A.site_web_a <> '')"),

        // --- contact ---
        'civilite'          => array('type' => 'liste',     'expr' => 'A.civilite_a'),
        'fonction'          => array('type' => 'liste',     'expr' => 'A.code_fonction_a'),
        'service'           => array('type' => 'liste',     'expr' => 'A.code_service_a'),
        'a_mobile'          => array('type' => 'booleen',   'expr' => "(A.telephone_mobile_a <> '')"),
        'a_email'           => array('type' => 'booleen',   'expr' => "(A.email_a <> '')"),

        // --- fiche ---
        'fiche_creation'    => array('type' => 'date',      'expr' => 'A.date_creation_a'),
        'source'            => array('type' => 'liste',     'expr' => 'A.source_a'),
    );
}

function criteres_comparateurs($type) {
    switch ($type) {
        case 'liste':     return array('dans', 'pas_dans');
        case 'numerique': return array('=', '!=', '<', '<=', '>', '>=', 'entre');
        case 'date':      return array('avant', 'apres', 'entre');
        case 'booleen':   return array('=');
        case 'texte':     return array('contient', 'ne_contient_pas', 'commence_par');
        default:          return array();
    }
}

/** Rend array($type, $valeur_normalisee). Leve CritereErreur sinon. */
function criteres_valider_feuille($critere, $comparateur, $valeur) {
    $cat = criteres_catalogue();
    if (!isset($cat[$critere])) {
        throw new CritereErreur(
            "critere_inconnu: '$critere'. Criteres connus: " . implode(', ', array_keys($cat))
        );
    }
    $type = $cat[$critere]['type'];
    $autorises = criteres_comparateurs($type);
    if (!in_array($comparateur, $autorises, true)) {
        throw new CritereErreur(
            "comparateur_invalide: '$comparateur' sur '$critere' (type $type). " .
            'Comparateurs valides: ' . implode(', ', $autorises)
        );
    }
    return array($type, criteres_normaliser($critere, $type, $comparateur, $valeur));
}

function criteres_normaliser($critere, $type, $comparateur, $valeur) {
    if ($comparateur === 'dans' || $comparateur === 'pas_dans') {
        if (!is_array($valeur) || count($valeur) === 0) {
            throw new CritereErreur("valeur_invalide: '$critere' attend un tableau non vide");
        }
        if (count($valeur) > CRITERE_VALEURS_MAX) {
            throw new CritereErreur(
                "valeur_invalide: '$critere' porte " . count($valeur) .
                ' valeurs, maximum ' . CRITERE_VALEURS_MAX
            );
        }
        return array_values($valeur);
    }
    if ($comparateur === 'entre') {
        if (!is_array($valeur) || count($valeur) !== 2) {
            throw new CritereErreur("valeur_invalide: '$critere' avec 'entre' attend exactement deux bornes");
        }
        $v = array_values($valeur);
        if ($type === 'date') {
            return array(criteres_date($critere, $v[0]), criteres_date($critere, $v[1]));
        }
        return array(criteres_nombre($critere, $v[0]), criteres_nombre($critere, $v[1]));
    }
    if ($type === 'numerique') { return criteres_nombre($critere, $valeur); }
    if ($type === 'date')      { return criteres_date($critere, $valeur); }
    if ($type === 'booleen') {
        if (!is_bool($valeur)) {
            throw new CritereErreur("valeur_invalide: '$critere' attend true ou false");
        }
        return $valeur;
    }
    // texte
    if (!is_string($valeur) || trim($valeur) === '') {
        throw new CritereErreur("valeur_invalide: '$critere' attend une chaine non vide");
    }
    return trim($valeur);
}

function criteres_nombre($critere, $v) {
    if (!is_int($v) && !is_float($v) && !(is_string($v) && is_numeric($v))) {
        throw new CritereErreur("valeur_invalide: '$critere' attend un nombre");
    }
    return $v + 0;
}

/** N'accepte que l'ISO AAAA-MM-JJ, et verifie que la date existe vraiment. */
function criteres_date($critere, $v) {
    if (!is_string($v) || !preg_match('/^(\d{4})-(\d{2})-(\d{2})$/', $v, $m)) {
        throw new CritereErreur("valeur_invalide: '$critere' attend une date AAAA-MM-JJ");
    }
    if (!checkdate((int)$m[2], (int)$m[3], (int)$m[1])) {
        throw new CritereErreur("valeur_invalide: '$critere' porte une date inexistante: $v");
    }
    return $v;
}
```

- [ ] **Step 4: Lancer les tests et vérifier qu'ils passent**

```bash
docker run --rm -v "$PWD":/src -w /src php:8.2-cli \
  php site/admin/mcp/hellodata/test/criteres.test.php
```

Attendu : toutes les assertions passent.

- [ ] **Step 5: Commiter la note de suivi**

```bash
git add docs/superpowers/plans/2026-09-21-mcp-hellodata-selection.md
git commit -m "docs(mcp-hellodata): mark A2 criteria whitelist done

EN: Criteria catalogue holds 23 criteria over columns confirmed to exist on
hpdata.acheteur. Each carries a self-contained SQL expression, which is what
lets leaves compose under ET, OU and NON without a join wrongly filtering
rows. No expression carries a placeholder: values are bound by the compiler.

FR: Le catalogue porte 23 criteres sur des colonnes confirmees existantes
sur hpdata.acheteur. Chacun porte une expression SQL autonome, ce qui permet
aux feuilles de se composer sous ET, OU et NON sans qu'une jointure filtre a
tort. Aucune expression ne porte de placeholder : les valeurs sont liees par
le compilateur."
```

---

### Task A3: Compilateur — arbre validé vers `(sql, params)`

**Files:**
- Create: `site/admin/mcp/hellodata/compilateur.php`
- Test: `site/admin/mcp/hellodata/test/compilateur.test.php`

**Interfaces:**
- Consumes: `arbre_valider()` (A1), `criteres_valider_feuille()`, `criteres_catalogue()` (A2)
- Produces: `compiler_arbre(array $noeud): array` → `array('sql' => string, 'params' => array)`. Les valeurs sont **toujours** des `?`, jamais concaténées.

- [ ] **Step 1: Écrire les tests qui échouent**

```php
<?php
// test/compilateur.test.php
require_once __DIR__ . '/_assert.php';
require_once __DIR__ . '/../compilateur.php';

function c($noeud) { return compiler_arbre($noeud); }

$r = c(array('critere' => 'region', 'comparateur' => 'dans', 'valeur' => array(6, 11)));
ok($r['sql'] === 'A.region_a IN (?, ?)', 'IN genere autant de ? que de valeurs');
ok($r['params'] === array(6, 11), 'les valeurs partent en parametres');

$r = c(array('critere' => 'region', 'comparateur' => 'pas_dans', 'valeur' => array(6)));
ok($r['sql'] === 'A.region_a NOT IN (?)', 'pas_dans genere NOT IN');

$r = c(array('critere' => 'annee_creation', 'comparateur' => '>=', 'valeur' => 2015));
ok($r['sql'] === 'A.annee_creat_a >= ?', 'comparateur numerique');

$r = c(array('critere' => 'annee_creation', 'comparateur' => 'entre', 'valeur' => array(2010, 2020)));
ok($r['sql'] === 'A.annee_creat_a BETWEEN ? AND ?', 'entre numerique');

// une date est un datetime en base : les bornes doivent couvrir la journee
$r = c(array('critere' => 'fiche_creation', 'comparateur' => 'apres', 'valeur' => '2025-06-01'));
ok($r['params'] === array('2025-06-01 23:59:59'), 'apres borne a la fin de journee');
$r = c(array('critere' => 'fiche_creation', 'comparateur' => 'avant', 'valeur' => '2025-06-01'));
ok($r['params'] === array('2025-06-01 00:00:00'), 'avant borne au debut de journee');
$r = c(array('critere' => 'fiche_creation', 'comparateur' => 'entre',
             'valeur' => array('2025-01-01', '2025-01-31')));
ok($r['params'] === array('2025-01-01 00:00:00', '2025-01-31 23:59:59'), 'entre couvre les deux journees entieres');

$r = c(array('critere' => 'a_siret', 'comparateur' => '=', 'valeur' => true));
ok($r['sql'] === "(A.siret_a <> '')", 'booleen vrai rend l expression telle quelle');
$r = c(array('critere' => 'a_siret', 'comparateur' => '=', 'valeur' => false));
ok($r['sql'] === "NOT ((A.siret_a <> ''))", 'booleen faux nie l expression');

$r = c(array('critere' => 'ville', 'comparateur' => 'contient', 'valeur' => 'Rennes'));
ok($r['sql'] === 'A.ville_a LIKE ?' && $r['params'] === array('%Rennes%'), 'contient');
$r = c(array('critere' => 'ville', 'comparateur' => 'commence_par', 'valeur' => 'Ren'));
ok($r['params'] === array('Ren%'), 'commence_par');

// un % dans la valeur ne doit pas devenir un joker
$r = c(array('critere' => 'ville', 'comparateur' => 'contient', 'valeur' => '100%'));
ok($r['params'] === array('%100\\%%'), 'le % de l utilisateur est echappe');
$r = c(array('critere' => 'ville', 'comparateur' => 'contient', 'valeur' => 'a_b'));
ok($r['params'] === array('%a\\_b%'), 'le _ de l utilisateur est echappe');

// --- composition : le test central de cette tache ---
$f1 = array('critere' => 'region', 'comparateur' => 'dans', 'valeur' => array(6));
$f2 = array('critere' => 'annee_creation', 'comparateur' => '>=', 'valeur' => 2015);

$r = c(array('operateur' => 'ET', 'conditions' => array($f1, $f2)));
ok($r['sql'] === '(A.region_a IN (?) AND A.annee_creat_a >= ?)', 'ET parenthese et joint');
ok($r['params'] === array(6, 2015), 'les parametres suivent l ordre de parcours');

$r = c(array('operateur' => 'OU', 'conditions' => array($f1, $f2)));
ok($r['sql'] === '(A.region_a IN (?) OR A.annee_creat_a >= ?)', 'OU parenthese et joint');

$r = c(array('operateur' => 'NON', 'conditions' => array($f1)));
ok($r['sql'] === 'NOT ((A.region_a IN (?)))', 'NON nie un groupe entier');

// imbrication : ET(f1, OU(f2, f1))
$r = c(array('operateur' => 'ET', 'conditions' => array(
        $f1, array('operateur' => 'OU', 'conditions' => array($f2, $f1)))));
ok($r['sql'] === '(A.region_a IN (?) AND (A.annee_creat_a >= ? OR A.region_a IN (?)))',
   'imbrication parenthesee correctement');
ok($r['params'] === array(6, 2015, 6), 'parametres de l arbre imbrique dans l ordre');

// AUCUN critere sur table liee ne doit produire de JOIN : tout est autonome
foreach (criteres_catalogue() as $nom => $def) {
    ok(stripos($def['expr'], ' join ') === false, "'$nom' ne porte pas de JOIN");
}

// les bornes structurelles de A1 s appliquent avant toute compilation
leve(function () { compiler_arbre(array('operateur' => 'ET', 'conditions' => array())); },
     'groupe_vide', 'la validation structurelle precede la compilation');
leve(function () { compiler_arbre(array('critere' => 'inconnu', 'comparateur' => 'dans', 'valeur' => array(1))); },
     'critere_inconnu', 'la liste blanche s applique a la compilation');

bilan();
```

- [ ] **Step 2: Lancer les tests et vérifier qu'ils échouent**

```bash
docker run --rm -v "$PWD":/src -w /src php:8.2-cli \
  php site/admin/mcp/hellodata/test/compilateur.test.php
```

Attendu : échec, `compilateur.php` absent.

- [ ] **Step 3: Écrire le compilateur**

```php
<?php
// compilateur.php — arbre valide -> fragment SQL + parametres lies.
// Aucune valeur n'est concatenee dans le SQL : elles sortent toutes en
// parametres, dans l'ordre de parcours de l'arbre.

require_once __DIR__ . '/arbre.php';
require_once __DIR__ . '/criteres.php';

function compiler_arbre($noeud) {
    arbre_valider($noeud);              // bornes structurelles d'abord
    $params = array();
    $sql = compiler_noeud($noeud, $params);
    return array('sql' => $sql, 'params' => $params);
}

function compiler_noeud($noeud, &$params) {
    if (arbre_est_feuille($noeud)) {
        return compiler_feuille($noeud, $params);
    }
    $morceaux = array();
    foreach ($noeud['conditions'] as $enfant) {
        $morceaux[] = compiler_noeud($enfant, $params);
    }
    if ($noeud['operateur'] === 'NON') {
        return 'NOT ((' . $morceaux[0] . '))';
    }
    $liant = ($noeud['operateur'] === 'ET') ? ' AND ' : ' OR ';
    return '(' . implode($liant, $morceaux) . ')';
}

function compiler_feuille($feuille, &$params) {
    $critere     = isset($feuille['critere']) ? $feuille['critere'] : '';
    $comparateur = isset($feuille['comparateur']) ? $feuille['comparateur'] : '';
    $valeur      = isset($feuille['valeur']) ? $feuille['valeur'] : null;

    list($type, $v) = criteres_valider_feuille($critere, $comparateur, $valeur);
    $cat  = criteres_catalogue();
    $expr = $cat[$critere]['expr'];

    switch ($comparateur) {
        case 'dans':
        case 'pas_dans':
            foreach ($v as $item) { $params[] = $item; }
            $trous = implode(', ', array_fill(0, count($v), '?'));
            $negation = ($comparateur === 'pas_dans') ? 'NOT ' : '';
            return $expr . ' ' . $negation . 'IN (' . $trous . ')';

        case '=': case '!=': case '<': case '<=': case '>': case '>=':
            if ($type === 'booleen') {
                return $v ? $expr : 'NOT (' . $expr . ')';
            }
            $params[] = $v;
            return $expr . ' ' . $comparateur . ' ?';

        case 'entre':
            if ($type === 'date') {
                $params[] = $v[0] . ' 00:00:00';
                $params[] = $v[1] . ' 23:59:59';
            } else {
                $params[] = $v[0];
                $params[] = $v[1];
            }
            return $expr . ' BETWEEN ? AND ?';

        // La colonne est un datetime. Une borne sans heure couperait la
        // journee a minuit et perdrait les fiches creees dans la journee.
        case 'avant':
            $params[] = $v . ' 00:00:00';
            return $expr . ' < ?';
        case 'apres':
            $params[] = $v . ' 23:59:59';
            return $expr . ' > ?';

        case 'contient':
            $params[] = '%' . compilateur_echapper_like($v) . '%';
            return $expr . ' LIKE ?';
        case 'ne_contient_pas':
            $params[] = '%' . compilateur_echapper_like($v) . '%';
            return $expr . ' NOT LIKE ?';
        case 'commence_par':
            $params[] = compilateur_echapper_like($v) . '%';
            return $expr . ' LIKE ?';
    }
    throw new CritereErreur("comparateur_invalide: '$comparateur' non compilable");
}

/**
 * Sans cet echappement, un utilisateur qui cherche "100%" obtiendrait un
 * joker et balaierait toute la table. L'anti-slash lui-meme passe en
 * premier, sinon on echapperait les echappements ajoutes ensuite.
 */
function compilateur_echapper_like($v) {
    return str_replace(array('\\', '%', '_'), array('\\\\', '\\%', '\\_'), $v);
}
```

- [ ] **Step 4: Lancer les tests et vérifier qu'ils passent**

```bash
docker run --rm -v "$PWD":/src -w /src php:8.2-cli \
  php site/admin/mcp/hellodata/test/compilateur.test.php
```

Attendu : toutes les assertions passent.

- [ ] **Step 5: Commiter la note de suivi**

```bash
git add docs/superpowers/plans/2026-09-21-mcp-hellodata-selection.md
git commit -m "docs(mcp-hellodata): mark A3 filter compiler done

EN: Tree compiles to a parameterised WHERE fragment. Every value leaves as a
bound parameter, LIKE wildcards in user input are escaped, and date bounds
span whole days because the column is a datetime. A test asserts no criterion
expression carries a JOIN, which is what keeps OR and NOT branches honest.

FR: L'arbre se compile en fragment WHERE parametre. Toute valeur sort en
parametre lie, les jokers LIKE saisis par l'utilisateur sont echappes, et les
bornes de date couvrent la journee entiere puisque la colonne est un
datetime. Un test verifie qu'aucune expression de critere ne porte de JOIN,
ce qui garde les branches OU et NON correctes."
```

---

### Task A4: Assemblage de la requête — dédoublonnage et curseur

Le point délicat de cette tâche n'est pas la fenêtre SQL, c'est **les fiches sans SIRET**. Un `PARTITION BY LEFT(siret_a, 9)` naïf mettrait toutes les fiches à SIRET vide dans une seule partition et n'en garderait **qu'une seule pour toute la base**. Le script du BO ne fait pas cette erreur : il teste `if (strlen($siren) == 9)` avant de dédoublonner. On reproduit ce comportement en donnant à chaque fiche sans SIRET exploitable **sa propre partition**.

**Files:**
- Create: `site/admin/mcp/hellodata/requete.php`
- Test: `site/admin/mcp/hellodata/test/requete.test.php`

**Interfaces:**
- Consumes: `compiler_arbre()` (A3)
- Produces:
  - `requete_colonnes(): array` — nom logique → `array('expr' => string, 'restreinte' => bool)`
  - `requete_construire(string $predicat, array $params, array $options): array` → `array('sql' => string, 'params' => array)`. `$options` : `colonnes` (array), `type_blocage` (int), `curseur` (int|null), `limite` (int), `mode` (`lignes`｜`comptage_approche`｜`comptage_exact`)
  - Constantes `REQUETE_LIMITE_MAX = 2000`, `REQUETE_PLAFOND_APPROCHE = 10001`

- [ ] **Step 1: Écrire les tests qui échouent**

```php
<?php
// test/requete.test.php
require_once __DIR__ . '/_assert.php';
require_once __DIR__ . '/../requete.php';

$c = compiler_arbre(array('critere' => 'region', 'comparateur' => 'dans', 'valeur' => array(6)));

function opts($o = array()) {
    return array_merge(array(
        'colonnes' => array('id_acheteur', 'raison_sociale'),
        'type_blocage' => 1, 'curseur' => null, 'limite' => 50, 'mode' => 'lignes',
    ), $o);
}

// --- type_blocage 1 : aucun dedoublonnage, donc aucune fenetre ---
$r = requete_construire($c['sql'], $c['params'], opts());
ok(strpos($r['sql'], 'ROW_NUMBER') === false, 'type_blocage 1 ne genere pas de fenetre');
ok(strpos($r['sql'], 'FROM acheteur A') !== false, 'la table de base est acheteur');
ok(strpos($r['sql'], 'A.bloquage_a = 0') !== false, 'le filtre de blocage est toujours pose');

// --- type_blocage 2 : dedoublonnage SIREN ---
$r = requete_construire($c['sql'], $c['params'], opts(array('type_blocage' => 2)));
ok(strpos($r['sql'], 'ROW_NUMBER() OVER') !== false, 'type_blocage 2 genere une fenetre');
ok(strpos($r['sql'], 'LEFT(A.siret_a, 9)') !== false, 'partition sur les 9 premiers caracteres');
ok(strpos($r['sql'], 'd.rn = 1') !== false, 'seule la premiere ligne de chaque partition est gardee');

// LE test de cette tache : une fiche sans SIRET ne doit pas etre fusionnee
// avec toutes les autres fiches sans SIRET.
ok(strpos($r['sql'], "CONCAT('#', A.id_acheteur)") !== false,
   'les fiches sans SIRET exploitable recoivent chacune leur partition');

// --- type_blocage 4 : dedoublonnage SIRET complet ---
$r = requete_construire($c['sql'], $c['params'], opts(array('type_blocage' => 4)));
ok(strpos($r['sql'], 'PARTITION BY CASE WHEN LENGTH(A.siret_a) >= 14') !== false,
   'type_blocage 4 partitionne sur le SIRET complet');

// --- curseur ---
$r = requete_construire($c['sql'], $c['params'], opts(array('curseur' => 12345)));
ok(strpos($r['sql'], 'id_acheteur > ?') !== false, 'le curseur devient une borne basse');
ok(in_array(12345, $r['params'], true), 'la valeur du curseur part en parametre');
ok(strpos($r['sql'], 'OFFSET') === false, 'aucun OFFSET : le cout doit rester constant');

// --- limite ---
$r = requete_construire($c['sql'], $c['params'], opts(array('limite' => 50)));
ok(end($r['params']) === 50, 'la limite est le dernier parametre');
leve(function () use ($c) {
        requete_construire($c['sql'], $c['params'], opts(array('limite' => 2001)));
     }, 'limite_invalide', 'au-dela de 2000 lignes, refus');
ok(requete_construire($c['sql'], $c['params'], opts(array('limite' => 2000)))
   !== null, 'exactement 2000 accepte');

// --- comptage ---
$r = requete_construire($c['sql'], $c['params'], opts(array('mode' => 'comptage_approche')));
ok(strpos($r['sql'], 'LIMIT ?') !== false && in_array(REQUETE_PLAFOND_APPROCHE, $r['params'], true),
   'le comptage approche est plafonne a 10001');
ok(strpos($r['sql'], 'COUNT(*)') !== false, 'le comptage approche compte bien');

$r = requete_construire($c['sql'], $c['params'], opts(array('mode' => 'comptage_exact')));
ok(strpos($r['sql'], 'COUNT(*)') !== false, 'le comptage exact compte');
ok(strpos($r['sql'], (string)REQUETE_PLAFOND_APPROCHE) === false
   && !in_array(REQUETE_PLAFOND_APPROCHE, $r['params'], true),
   'le comptage exact n est pas plafonne');

// --- colonnes ---
leve(function () use ($c) {
        requete_construire($c['sql'], $c['params'], opts(array('colonnes' => array('salaire_du_dirigeant'))));
     }, 'colonne_inconnue', 'colonne hors catalogue refusee');
leve(function () use ($c) {
        requete_construire($c['sql'], $c['params'], opts(array('colonnes' => array())));
     }, 'colonne_invalide', 'aucune colonne demandee refuse');

// une colonne restreinte n est servie que si l appelant y a droit
leve(function () use ($c) {
        requete_construire($c['sql'], $c['params'], opts(array('colonnes' => array('email'))));
     }, 'colonne_restreinte', 'email refuse sans le droit');
$r = requete_construire($c['sql'], $c['params'],
        opts(array('colonnes' => array('email'), 'colonnes_restreintes_autorisees' => true)));
ok(strpos($r['sql'], 'A.email_a') !== false, 'email servi avec le droit');

// l id_acheteur est toujours projete : le curseur de la page suivante en depend
$r = requete_construire($c['sql'], $c['params'], opts(array('colonnes' => array('ville'))));
ok(strpos($r['sql'], 'A.id_acheteur') !== false, 'id_acheteur toujours projete');

bilan();
```

- [ ] **Step 2: Lancer les tests et vérifier qu'ils échouent**

```bash
docker run --rm -v "$PWD":/src -w /src php:8.2-cli \
  php site/admin/mcp/hellodata/test/requete.test.php
```

- [ ] **Step 3: Écrire l'assemblage**

```php
<?php
// requete.php — assemblage de la requete complete a partir d'un predicat
// deja compile. Pur : rend du SQL et des parametres, n'execute rien.

require_once __DIR__ . '/compilateur.php';

define('REQUETE_LIMITE_MAX', 2000);
define('REQUETE_PLAFOND_APPROCHE', 10001);

class RequeteErreur extends Exception {}

/** Colonnes projetables. 'restreinte' = soumise au droit telephone/email. */
function requete_colonnes() {
    return array(
        'id_acheteur'    => array('expr' => 'A.id_acheteur',      'restreinte' => false),
        'id_fiche'       => array('expr' => 'A.id_source_a',      'restreinte' => false),
        'source'         => array('expr' => 'A.source_a',         'restreinte' => false),
        'raison_sociale' => array('expr' => 'A.raison_sociale_a', 'restreinte' => false),
        'nom_commercial' => array('expr' => 'A.nom_commercial_a', 'restreinte' => false),
        'civilite'       => array('expr' => 'A.civilite_a',       'restreinte' => false),
        'nom'            => array('expr' => 'A.nom_a',            'restreinte' => false),
        'prenom'         => array('expr' => 'A.prenom_a',         'restreinte' => false),
        'adresse'        => array('expr' => 'A.adresse_a',        'restreinte' => false),
        'code_postal'    => array('expr' => 'A.cp_a',             'restreinte' => false),
        'ville'          => array('expr' => 'A.ville_a',          'restreinte' => false),
        'departement'    => array('expr' => 'A.departement_a',    'restreinte' => false),
        'region'         => array('expr' => 'A.region_a',         'restreinte' => false),
        'pays'           => array('expr' => 'A.id_pays_a',        'restreinte' => false),
        'siret'          => array('expr' => 'A.siret_a',          'restreinte' => false),
        'siren'          => array('expr' => 'A.siren_a',          'restreinte' => false),
        'effectif'       => array('expr' => 'A.code_effectif_a',  'restreinte' => false),
        'naf'            => array('expr' => 'A.code_naf_a',       'restreinte' => false),
        'site_web'       => array('expr' => 'A.site_web_a',       'restreinte' => false),
        'statut'         => array('expr' => 'A.statut_a',         'restreinte' => false),
        'fonction'       => array('expr' => 'A.code_fonction_a',  'restreinte' => false),
        'service'        => array('expr' => 'A.code_service_a',   'restreinte' => false),
        'annee_creation' => array('expr' => 'A.annee_creat_a',    'restreinte' => false),
        'date_creation'  => array('expr' => 'A.date_creation_a',  'restreinte' => false),

        // Soumises au droit, equivalent du $debloque_tel_mail du BO.
        // fax, validite_email, chiffre_affaires, forme_juridique et
        // code_insee ne figurent PAS ici : leur existence sur acheteur
        // n'a pas ete confirmee (Task 0 step 11). Ne pas les ajouter sans
        // les avoir sondees.
        'email'          => array('expr' => 'A.email_a',            'restreinte' => true),
        'mobile'         => array('expr' => 'A.telephone_mobile_a', 'restreinte' => true),
    );
}

/**
 * Cle de partition du dedoublonnage.
 *
 * Le CASE n'est pas cosmetique. Sans lui, toutes les fiches a SIRET vide
 * tomberaient dans une seule partition et UNE SEULE survivrait pour toute
 * la base. Le script du BO evite le piege autrement (il teste
 * strlen($siren) == 9 avant de dedoublonner) ; ici chaque fiche sans SIRET
 * exploitable recoit sa propre partition, ce qui revient au meme.
 */
function requete_partition($type_blocage) {
    if ($type_blocage == 2 || $type_blocage == 3) {
        return "CASE WHEN LENGTH(A.siret_a) >= 9 THEN LEFT(A.siret_a, 9) "
             . "ELSE CONCAT('#', A.id_acheteur) END";
    }
    if (in_array((int)$type_blocage, array(4, 5, 7, 8), true)) {
        return "CASE WHEN LENGTH(A.siret_a) >= 14 THEN A.siret_a "
             . "ELSE CONCAT('#', A.id_acheteur) END";
    }
    return null; // type_blocage 1 : pas de dedoublonnage
}

function requete_construire($predicat, $params_predicat, $options) {
    $colonnes  = isset($options['colonnes']) ? $options['colonnes'] : array();
    $blocage   = isset($options['type_blocage']) ? (int)$options['type_blocage'] : 1;
    $curseur   = isset($options['curseur']) ? $options['curseur'] : null;
    $limite    = isset($options['limite']) ? (int)$options['limite'] : 50;
    $mode      = isset($options['mode']) ? $options['mode'] : 'lignes';
    $restreint = !empty($options['colonnes_restreintes_autorisees']);

    $projection = requete_projection($colonnes, $restreint);
    $partition  = requete_partition($blocage);
    $params     = $params_predicat;

    $interne = 'SELECT ' . implode(', ', $projection);
    if ($partition !== null) {
        $interne .= ', ROW_NUMBER() OVER (PARTITION BY ' . $partition
                  . ' ORDER BY A.id_acheteur) AS rn';
    }
    $interne .= ' FROM acheteur A WHERE A.id_acheteur <> 0 AND A.bloquage_a = 0'
              . ' AND (' . $predicat . ')';

    $ou = array();
    if ($partition !== null) { $ou[] = 'd.rn = 1'; }
    if ($curseur !== null) {
        $ou[] = 'd.id_acheteur > ?';
        $params[] = (int)$curseur;
    }
    $filtre_externe = $ou ? ' WHERE ' . implode(' AND ', $ou) : '';

    if ($mode === 'comptage_exact') {
        return array(
            'sql'    => 'SELECT COUNT(*) AS n FROM (' . $interne . ') d' . $filtre_externe,
            'params' => $params,
        );
    }
    if ($mode === 'comptage_approche') {
        // On plafonne AVANT de compter : la requete s'arrete des que le
        // plafond est atteint, au lieu de parcourir des millions de lignes
        // pour un nombre dont le LLM n'a pas besoin a l'unite pres.
        $params[] = REQUETE_PLAFOND_APPROCHE;
        return array(
            'sql' => 'SELECT COUNT(*) AS n FROM (SELECT d.id_acheteur FROM ('
                   . $interne . ') d' . $filtre_externe
                   . ' ORDER BY d.id_acheteur LIMIT ?) plafonne',
            'params' => $params,
        );
    }

    if ($limite < 1 || $limite > REQUETE_LIMITE_MAX) {
        throw new RequeteErreur('limite_invalide: ' . $limite
            . ' hors bornes 1..' . REQUETE_LIMITE_MAX);
    }
    $params[] = $limite;
    return array(
        'sql' => 'SELECT * FROM (' . $interne . ') d' . $filtre_externe
               . ' ORDER BY d.id_acheteur LIMIT ?',
        'params' => $params,
    );
}

function requete_projection($colonnes, $restreintes_autorisees) {
    if (!is_array($colonnes) || count($colonnes) === 0) {
        throw new RequeteErreur('colonne_invalide: au moins une colonne est requise');
    }
    $cat = requete_colonnes();
    // id_acheteur est toujours projete : c'est lui qui porte le curseur de
    // la page suivante. Sans lui, la pagination serait impossible a rendre.
    $noms = array_values(array_unique(array_merge(array('id_acheteur'), $colonnes)));
    $out = array();
    foreach ($noms as $nom) {
        if (!isset($cat[$nom])) {
            throw new RequeteErreur("colonne_inconnue: '$nom'. Colonnes connues: "
                . implode(', ', array_keys($cat)));
        }
        if ($cat[$nom]['restreinte'] && !$restreintes_autorisees) {
            throw new RequeteErreur("colonne_restreinte: '$nom' exige un droit que l appelant n a pas");
        }
        $out[] = $cat[$nom]['expr'] . ' AS ' . $nom;
    }
    return $out;
}
```

- [ ] **Step 4: Lancer les tests et vérifier qu'ils passent**

```bash
docker run --rm -v "$PWD":/src -w /src php:8.2-cli \
  php site/admin/mcp/hellodata/test/requete.test.php
```

- [ ] **Step 5: Vérifier la requête sur la vraie base**

Les tests unitaires prouvent la forme du SQL, pas qu'il s'exécute. Prends le SQL produit par le test `type_blocage 2`, substitue les `?` à la main, et exécute-le via `bdd_query_readonly` ou un client MySQL avec `LIMIT 5`.

Attendu : des lignes, et surtout **deux fiches partageant un SIREN n'apparaissent qu'une fois**, tandis que **plusieurs fiches à SIRET vide apparaissent toutes**. C'est le contrôle qui prouve que le `CASE` fait son travail — le test unitaire ne vérifie que la présence de la chaîne.

- [ ] **Step 6: Commiter la note de suivi**

```bash
git add docs/superpowers/plans/2026-09-21-mcp-hellodata-selection.md
git commit -m "docs(mcp-hellodata): mark A4 query assembly done

EN: Query assembly with window dedup and keyset pagination. Rows with no
usable SIRET each get their own partition, otherwise a single row would
survive for the whole base. Approximate count caps before counting, and
OFFSET is never generated so page cost stays flat.

FR: Assemblage de la requete avec dedoublonnage par fenetre et pagination
par curseur. Les fiches sans SIRET exploitable recoivent chacune leur
partition, sans quoi une seule ligne survivrait pour toute la base. Le
comptage approche plafonne avant de compter, et aucun OFFSET n'est genere
pour que le cout d'une page reste constant."
```

---

### Task A5: Coquille HTTP — auth Bearer, routeur, enveloppe

**Files:**
- Create: `site/admin/mcp/hellodata/reponse.php`, `auth.php`, `bdd.php`, `index.php`
- Test: `site/admin/mcp/hellodata/test/auth.test.php`

**Interfaces:**
- Consumes: A1–A4
- Produces: `repondre(array $payload)`, `echouer(string $code, string $message, int $http = 400)`, `auth_verifier(?string $entete, string $attendu): bool`, `bdd_lien(): mysqli`
- Contrat HTTP : enveloppe `{"code": <http>, "response": {...}}`, identique à ce que `bddcatalog/client.go` sait déballer.

- [ ] **Step 1: Écrire le test qui échoue**

`auth_verifier` est la seule partie pure de cette tâche ; le reste se teste par `curl` après déploiement.

```php
<?php
// test/auth.test.php
require_once __DIR__ . '/_assert.php';
require_once __DIR__ . '/../auth.php';

ok(auth_verifier('Bearer secret', 'secret') === true,  'bon jeton accepte');
ok(auth_verifier('Bearer mauvais', 'secret') === false, 'mauvais jeton refuse');
ok(auth_verifier('secret', 'secret') === false,         'sans le prefixe Bearer, refus');
ok(auth_verifier(null, 'secret') === false,             'en-tete absent, refus');
ok(auth_verifier('Bearer ', 'secret') === false,        'jeton vide, refus');
// un jeton attendu vide ne doit JAMAIS ouvrir la porte : une variable
// d'environnement oubliee au deploiement rendrait le service public.
ok(auth_verifier('Bearer ', '') === false,              'jeton attendu vide, refus');
ok(auth_verifier('Bearer nimporte', '') === false,      'jeton attendu vide, refus quel que soit l entrant');

bilan();
```

- [ ] **Step 2: Lancer le test et vérifier qu'il échoue**

```bash
docker run --rm -v "$PWD":/src -w /src php:8.2-cli \
  php site/admin/mcp/hellodata/test/auth.test.php
```

- [ ] **Step 3: Écrire les quatre fichiers**

```php
<?php
// auth.php — verification du Bearer. Rien d'autre.

/**
 * Comparaison a temps constant : hash_equals, pas ==. Un == sort au
 * premier octet different et laisse mesurer le jeton caractere par
 * caractere.
 */
function auth_verifier($entete, $attendu) {
    if (!is_string($attendu) || $attendu === '') {
        return false; // jeton non configure : on ferme, on n'ouvre pas
    }
    if (!is_string($entete) || strpos($entete, 'Bearer ') !== 0) {
        return false;
    }
    $fourni = substr($entete, 7);
    if ($fourni === '') { return false; }
    return hash_equals($attendu, $fourni);
}
```

```php
<?php
// reponse.php — enveloppe unique {code, response}, identique a celle que
// mcp-gateway-service/internal/bddcatalog/client.go sait deballer.

function repondre($payload, $http = 200) {
    http_response_code($http);
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode(array('code' => $http, 'response' => $payload));
    exit;
}

/**
 * $code est un code stable destine a la machine (critere_inconnu,
 * arbre_trop_complexe, timeout...). Le message MySQL brut n'y figure
 * JAMAIS : le script du BO fait die(hellopro_mysql_error($sql, ...)) et
 * renvoie ainsi la requete complete au client. On journalise, on ne
 * divulgue pas.
 */
function echouer($code, $message, $http = 400) {
    http_response_code($http);
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode(array('code' => $http, 'response' => array(
        'erreur'  => $code,
        'message' => $message,
    )));
    exit;
}

function journaliser($contexte, $detail) {
    error_log('[mcp-hellodata] ' . $contexte . ': ' . $detail);
}
```

```php
<?php
// bdd.php — connexion a la base hellopro_data, en lecture seule par usage.

function bdd_lien() {
    static $lien = null;
    if ($lien !== null) { return $lien; }
    require_once($_SERVER['DOCUMENT_ROOT'] . 'no_read_access/connexion_bdd_hellopro_data.php');
    if (!isset($GLOBALS['LINK_MYSQLI_HELLOPRO_DATA'])) {
        journaliser('bdd', 'LINK_MYSQLI_HELLOPRO_DATA absent apres inclusion');
        echouer('erreur_interne', 'base indisponible', 500);
    }
    $lien = $GLOBALS['LINK_MYSQLI_HELLOPRO_DATA'];
    mysqli_set_charset($lien, 'utf8mb4');
    return $lien;
}

/**
 * Execute une requete preparee. Tous les parametres sont lies en 's' :
 * MySQL convertit la constante vers le type de la colonne et l'index
 * reste utilisable, ce qui evite de tenir a jour une table de types
 * qui serait une source de bugs silencieux.
 */
function bdd_executer($sql, $params) {
    $lien = bdd_lien();
    $stmt = mysqli_prepare($lien, $sql);
    if ($stmt === false) {
        journaliser('prepare', mysqli_error($lien) . ' | ' . $sql);
        echouer('erreur_interne', 'requete refusee par la base', 500);
    }
    if (count($params) > 0) {
        mysqli_stmt_bind_param($stmt, str_repeat('s', count($params)), ...$params);
    }
    if (!mysqli_stmt_execute($stmt)) {
        journaliser('execute', mysqli_stmt_error($stmt) . ' | ' . $sql);
        echouer('erreur_interne', 'execution impossible', 500);
    }
    return $stmt;
}
```

```php
<?php
// index.php — routeur unique. Auth, bornes d'entree, dispatch. Aucune
// logique metier ici.

require_once __DIR__ . '/reponse.php';
require_once __DIR__ . '/auth.php';

// Une charge utile demesuree doit mourir avant json_decode, pas apres.
define('CORPS_MAX_OCTETS', 256 * 1024);

$entete = isset($_SERVER['HTTP_AUTHORIZATION']) ? $_SERVER['HTTP_AUTHORIZATION'] : null;
if (!auth_verifier($entete, getenv('MCP_HELLODATA_TOKEN'))) {
    echouer('non_autorise', 'jeton absent ou invalide', 401);
}

$action = isset($_GET['action']) ? $_GET['action'] : '';
$corps = array();
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $brut = file_get_contents('php://input', false, null, 0, CORPS_MAX_OCTETS + 1);
    if (strlen($brut) > CORPS_MAX_OCTETS) {
        echouer('charge_trop_grande', 'corps au-dela de ' . CORPS_MAX_OCTETS . ' octets', 413);
    }
    $corps = json_decode($brut, true);
    if (!is_array($corps)) {
        echouer('json_invalide', 'corps JSON illisible');
    }
}

$routes = array(
    'comptage'      => 'actions/comptage.php',
    'echantillon'   => 'actions/echantillon.php',
    'export_start'  => 'actions/export_start.php',
    'export_statut' => 'actions/export_statut.php',
    'export_fetch'  => 'actions/export_fetch.php',
);
if (!isset($routes[$action])) {
    echouer('action_inconnue', "action '$action'. Actions: " . implode(', ', array_keys($routes)), 404);
}
require __DIR__ . '/' . $routes[$action];
```

- [ ] **Step 4: Lancer le test et vérifier qu'il passe**

```bash
docker run --rm -v "$PWD":/src -w /src php:8.2-cli \
  php site/admin/mcp/hellodata/test/auth.test.php
```

Attendu : `OK - 7 assertions`.

- [ ] **Step 5: Vérifier que `HTTP_AUTHORIZATION` arrive bien**

Certaines configurations Apache/CGI ne propagent pas l'en-tête `Authorization` à PHP. Après le premier déploiement (Task A9), teste :

```bash
curl -s -o /dev/null -w '%{http_code}\n' -H 'Authorization: Bearer mauvais' \
  'https://<hôte-bo>/admin/mcp/hellodata/index.php?action=comptage'
```

Attendu : `401`. Si tu obtiens `401` même avec le **bon** jeton, l'en-tête n'arrive pas : ajoute au `.htaccess` du répertoire
`SetEnvIf Authorization "(.*)" HTTP_AUTHORIZATION=$1` et reteste.

- [ ] **Step 6: Commiter la note de suivi**

```bash
git add docs/superpowers/plans/2026-09-21-mcp-hellodata-selection.md
git commit -m "docs(mcp-hellodata): mark A5 http shell done

EN: Bearer auth, single router, stable error envelope. An unset expected
token denies instead of opening, comparison is constant time, the body is
capped before json_decode, and no MySQL message ever reaches a response.

FR: Auth Bearer, routeur unique, enveloppe d'erreur stable. Un jeton attendu
non configure refuse au lieu d'ouvrir, la comparaison est a temps constant,
le corps est plafonne avant json_decode, et aucun message MySQL n'atteint
jamais une reponse."
```

---

### Task A6: Action `comptage` — approché par défaut, cache court

**Files:**
- Create: `site/admin/mcp/hellodata/cache.php`, `site/admin/mcp/hellodata/actions/comptage.php`
- Test: `site/admin/mcp/hellodata/test/cache.test.php`

**Interfaces:**
- Consumes: A3, A4, A5
- Produces: `cache_cle(array $filtre, bool $exact, string $portee): string`, `cache_lire(string $cle)`, `cache_ecrire(string $cle, $valeur)`, `canoniser($noeud)`
- Réponse : `{count, exact, plafonne, duree_ms, depuis_cache}`

- [ ] **Step 1: Écrire les tests qui échouent**

La canonicalisation est le cœur : deux arbres de même sens écrits dans un ordre différent doivent toucher la même entrée.

```php
<?php
// test/cache.test.php
require_once __DIR__ . '/_assert.php';
require_once __DIR__ . '/../cache.php';

$f1 = array('critere' => 'region', 'comparateur' => 'dans', 'valeur' => array(11, 6));
$f2 = array('critere' => 'annee_creation', 'comparateur' => '>=', 'valeur' => 2015);

$a = array('operateur' => 'ET', 'conditions' => array($f1, $f2));
$b = array('operateur' => 'ET', 'conditions' => array($f2, $f1)); // ordre inverse
ok(cache_cle($a, false, 'admin') === cache_cle($b, false, 'admin'),
   'ET est commutatif : meme cle quel que soit l ordre des enfants');

$ou_a = array('operateur' => 'OU', 'conditions' => array($f1, $f2));
$ou_b = array('operateur' => 'OU', 'conditions' => array($f2, $f1));
ok(cache_cle($ou_a, false, 'admin') === cache_cle($ou_b, false, 'admin'),
   'OU est commutatif aussi');

// une liste de valeurs est un ensemble : l ordre ne doit pas compter
$l1 = array('critere' => 'region', 'comparateur' => 'dans', 'valeur' => array(6, 11));
ok(cache_cle($l1, false, 'admin') === cache_cle($f1, false, 'admin'),
   'les valeurs de liste sont triees');

// NON est unaire : rien a trier, mais il doit rester distinct
$non = array('operateur' => 'NON', 'conditions' => array($f1));
ok(cache_cle($non, false, 'admin') !== cache_cle($f1, false, 'admin'),
   'NON change la cle');

ok(cache_cle($a, true, 'admin') !== cache_cle($a, false, 'admin'),
   'exact et approche ne partagent pas d entree');

// LA regle qui protege les donnees : un comptage calcule pour une portee
// ne doit jamais etre resservi a une autre.
ok(cache_cle($a, false, 'admin') !== cache_cle($a, false, 'liste'),
   'la portee de droits fait partie de la cle');

// aller-retour
$cle = cache_cle($a, false, 'admin');
cache_ecrire($cle, array('n' => 42));
$lu = cache_lire($cle);
ok(is_array($lu) && $lu['n'] === 42, 'ecriture puis lecture rendent la valeur');
ok(cache_lire('cle_absente_' . uniqid()) === null, 'une cle absente rend null');

bilan();
```

- [ ] **Step 2: Lancer les tests et vérifier qu'ils échouent**

```bash
docker run --rm -v "$PWD":/src -w /src php:8.2-cli \
  php site/admin/mcp/hellodata/test/cache.test.php
```

- [ ] **Step 3: Écrire le cache**

```php
<?php
// cache.php — cache de comptage sur fichier. Le chemin vient de la
// Task 0 step 1 : il est HORS racine web.

define('CACHE_TTL_SECONDES', 300);

function cache_repertoire() {
    $base = getenv('MCP_HELLODATA_VAR');
    if (!$base) { $base = sys_get_temp_dir() . '/mcp-hellodata'; }
    $dir = rtrim($base, '/') . '/cache';
    if (!is_dir($dir)) { @mkdir($dir, 0700, true); }
    return $dir;
}

/**
 * Forme canonique : deux arbres de meme sens ecrits differemment doivent
 * donner la meme cle, sinon un LLM qui reformule son arbre paierait le
 * comptage a chaque fois.
 *
 * - les cles d'objet sont triees ;
 * - les enfants d'un ET ou d'un OU sont tries : ces operateurs sont
 *   commutatifs ;
 * - les enfants d'un NON ne le sont PAS : il est unaire, il n'y a rien a
 *   trier, et le trier masquerait une erreur de forme ;
 * - les valeurs de liste sont triees et dedoublonnees : c'est un ensemble.
 */
function canoniser($noeud) {
    if (!is_array($noeud)) { return $noeud; }
    if (isset($noeud['critere'])) {
        $f = $noeud;
        if (isset($f['valeur']) && is_array($f['valeur'])
            && ($f['comparateur'] === 'dans' || $f['comparateur'] === 'pas_dans')) {
            $v = array_values(array_unique($f['valeur']));
            sort($v);
            $f['valeur'] = $v;
        }
        ksort($f);
        return $f;
    }
    $g = $noeud;
    if (isset($g['conditions']) && is_array($g['conditions'])) {
        $enfants = array();
        foreach ($g['conditions'] as $e) { $enfants[] = canoniser($e); }
        if (isset($g['operateur']) && $g['operateur'] !== 'NON') {
            usort($enfants, function ($x, $y) {
                return strcmp(json_encode($x), json_encode($y));
            });
        }
        $g['conditions'] = $enfants;
    }
    ksort($g);
    return $g;
}

/** $portee : 'admin' ou 'liste'. Elle entre dans la cle, cf. spec § 4.6. */
function cache_cle($filtre, $exact, $portee) {
    return hash('sha256', json_encode(array(
        'filtre' => canoniser($filtre),
        'exact'  => (bool)$exact,
        'portee' => $portee,
    )));
}

function cache_lire($cle) {
    $f = cache_repertoire() . '/' . $cle . '.json';
    if (!is_file($f)) { return null; }
    if (time() - filemtime($f) > CACHE_TTL_SECONDES) { @unlink($f); return null; }
    $d = json_decode(@file_get_contents($f), true);
    return is_array($d) ? $d : null;
}

function cache_ecrire($cle, $valeur) {
    $dir = cache_repertoire();
    $f = $dir . '/' . $cle . '.json';
    // Ecriture atomique : un lecteur concurrent ne doit jamais voir un
    // fichier a moitie ecrit.
    $tmp = $f . '.' . getmypid() . '.tmp';
    if (@file_put_contents($tmp, json_encode($valeur)) !== false) { @rename($tmp, $f); }
    cache_purger($dir);
}

/** Purge paresseuse : une chance sur cinquante, pour ne pas payer a chaque appel. */
function cache_purger($dir) {
    if (mt_rand(1, 50) !== 1) { return; }
    foreach (glob($dir . '/*.json') as $f) {
        if (time() - filemtime($f) > CACHE_TTL_SECONDES) { @unlink($f); }
    }
}
```

- [ ] **Step 4: Écrire l'action**

```php
<?php
// actions/comptage.php — appele par index.php, qui a deja authentifie.

require_once __DIR__ . '/../requete.php';
require_once __DIR__ . '/../cache.php';
require_once __DIR__ . '/../bdd.php';

$debut = microtime(true);

$filtre = isset($corps['filtre']) ? $corps['filtre'] : null;
if (!is_array($filtre)) { echouer('filtre_manquant', "le champ 'filtre' est requis"); }
$exact   = !empty($corps['exact']);
$blocage = isset($corps['type_blocage']) ? (int)$corps['type_blocage'] : 1;
// Le type_blocage change le resultat : il entre dans la cle. Il est
// fondu dans la portee plutot qu'enrobe autour du filtre, sinon
// canoniser() ne verrait pas un noeud d'arbre et ne canoniserait rien.
$portee  = (!empty($corps['colonnes_restreintes_autorisees']) ? 'admin' : 'liste') . '|b' . $blocage;

$cle = cache_cle($filtre, $exact, $portee);
$hit = cache_lire($cle);
if ($hit !== null) {
    repondre(array(
        'count' => $hit['count'], 'exact' => $exact,
        'plafonne' => $hit['plafonne'], 'duree_ms' => 0, 'depuis_cache' => true,
    ));
}

try {
    $c = compiler_arbre($filtre);
    $r = requete_construire($c['sql'], $c['params'], array(
        'colonnes' => array('id_acheteur'),
        'type_blocage' => $blocage,
        'mode' => $exact ? 'comptage_exact' : 'comptage_approche',
    ));
} catch (ArbreErreur $e)   { echouer('arbre_trop_complexe', $e->getMessage()); }
  catch (CritereErreur $e) { echouer('critere_invalide', $e->getMessage()); }
  catch (RequeteErreur $e) { echouer('requete_invalide', $e->getMessage()); }

$stmt = bdd_executer($r['sql'], $r['params']);
$res  = mysqli_stmt_get_result($stmt);
$ligne = mysqli_fetch_assoc($res);
$n = (int)$ligne['n'];

$plafonne = (!$exact && $n >= REQUETE_PLAFOND_APPROCHE);
if ($plafonne) { $n = REQUETE_PLAFOND_APPROCHE - 1; }

cache_ecrire($cle, array('count' => $n, 'plafonne' => $plafonne));

repondre(array(
    'count' => $n, 'exact' => $exact, 'plafonne' => $plafonne,
    'duree_ms' => (int)round((microtime(true) - $debut) * 1000),
    'depuis_cache' => false,
));
```

- [ ] **Step 5: Lancer les tests et vérifier qu'ils passent**

```bash
docker run --rm -v "$PWD":/src -w /src php:8.2-cli \
  php site/admin/mcp/hellodata/test/cache.test.php
```

Attendu : `OK - 8 assertions`.

- [ ] **Step 6: Commiter la note de suivi**

```bash
git add docs/superpowers/plans/2026-09-21-mcp-hellodata-selection.md
git commit -m "docs(mcp-hellodata): mark A6 count action and cache done

EN: Approximate count by default, exact on request, both cached for five
minutes. The cache key is the canonical tree so a reworded filter hits the
same entry, and the rights scope is part of the key so a count computed for
an admin is never served to a list-authorised caller.

FR: Comptage approche par defaut, exact sur demande, les deux caches cinq
minutes. La cle est la forme canonique de l'arbre, pour qu'un filtre
reformule touche la meme entree, et la portee de droits fait partie de la
cle pour qu'un comptage calcule pour un admin ne soit jamais resservi a un
appelant autorise par liste."
```

---

### Task A7: Action `echantillon` — lecture paginée par curseur

**Files:**
- Create: `site/admin/mcp/hellodata/actions/echantillon.php`
- Test: vérification par `curl` après déploiement (l'action n'a pas de partie pure : A3, A4 et A6 couvrent déjà la logique)

**Interfaces:**
- Consumes: A3, A4, A5
- Produces: réponse `{rows: [...], next_cursor: int|null, has_more: bool}`

- [ ] **Step 1: Écrire l'action**

```php
<?php
// actions/echantillon.php — lecture paginee. index.php a deja authentifie.

require_once __DIR__ . '/../requete.php';
require_once __DIR__ . '/../bdd.php';

define('ECHANTILLON_TAILLE_DEFAUT', 50);

$filtre = isset($corps['filtre']) ? $corps['filtre'] : null;
if (!is_array($filtre)) { echouer('filtre_manquant', "le champ 'filtre' est requis"); }

$colonnes = isset($corps['colonnes']) && is_array($corps['colonnes']) && $corps['colonnes']
          ? $corps['colonnes']
          : array('id_acheteur', 'raison_sociale', 'ville', 'code_postal');
$taille   = isset($corps['taille']) ? (int)$corps['taille'] : ECHANTILLON_TAILLE_DEFAUT;
$curseur  = isset($corps['cursor']) && $corps['cursor'] !== null ? (int)$corps['cursor'] : null;
$blocage  = isset($corps['type_blocage']) ? (int)$corps['type_blocage'] : 1;

try {
    $c = compiler_arbre($filtre);
    // On demande une ligne de plus que la taille voulue : sa presence dit
    // s'il y a une page suivante, sans avoir a relancer un COUNT.
    $r = requete_construire($c['sql'], $c['params'], array(
        'colonnes' => $colonnes,
        'type_blocage' => $blocage,
        'curseur' => $curseur,
        'limite' => min($taille + 1, REQUETE_LIMITE_MAX + 1),
        'mode' => 'lignes',
        'colonnes_restreintes_autorisees' => !empty($corps['colonnes_restreintes_autorisees']),
    ));
} catch (ArbreErreur $e)   { echouer('arbre_trop_complexe', $e->getMessage()); }
  catch (CritereErreur $e) { echouer('critere_invalide', $e->getMessage()); }
  catch (RequeteErreur $e) { echouer('requete_invalide', $e->getMessage()); }

$stmt = bdd_executer($r['sql'], $r['params']);
$res  = mysqli_stmt_get_result($stmt);

$lignes = array();
while ($l = mysqli_fetch_assoc($res)) { $lignes[] = $l; }

$has_more = count($lignes) > $taille;
if ($has_more) { array_pop($lignes); }

// rn est un detail d'implementation du dedoublonnage : il ne sort pas.
foreach ($lignes as $i => $l) { unset($lignes[$i]['rn']); }

$next = null;
if ($has_more && count($lignes) > 0) {
    $dernier = $lignes[count($lignes) - 1];
    $next = (int)$dernier['id_acheteur'];
}

repondre(array('rows' => array_values($lignes), 'next_cursor' => $next, 'has_more' => $has_more));
```

- [ ] **Step 2: Vérifier après déploiement — page 1**

```bash
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"filtre":{"critere":"region","comparateur":"dans","valeur":[6]},"taille":5}' \
  'https://<hôte-bo>/admin/mcp/hellodata/index.php?action=echantillon' | jq .
```

Attendu : `code: 200`, `rows` de 5 éléments, `has_more: true`, `next_cursor` égal à l'`id_acheteur` de la dernière ligne.

- [ ] **Step 3: Vérifier la page 2 — le test qui compte vraiment**

Reprends le `next_cursor` de l'étape précédente :

```bash
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"filtre":{"critere":"region","comparateur":"dans","valeur":[6]},"taille":5,"cursor":<next_cursor>}' \
  'https://<hôte-bo>/admin/mcp/hellodata/index.php?action=echantillon' | jq '.response.rows[].id_acheteur'
```

Attendu : **aucun `id_acheteur` commun avec la page 1**, et tous strictement supérieurs au curseur. Un recouvrement signifierait que la pagination ne tient pas.

- [ ] **Step 4: Vérifier le refus d'une colonne restreinte**

```bash
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"filtre":{"critere":"region","comparateur":"dans","valeur":[6]},"colonnes":["email"]}' \
  'https://<hôte-bo>/admin/mcp/hellodata/index.php?action=echantillon' | jq .
```

Attendu : `erreur: "colonne_restreinte"`. C'est le contrôle négatif du droit téléphone/email.

- [ ] **Step 5: Commiter la note de suivi**

```bash
git add docs/superpowers/plans/2026-09-21-mcp-hellodata-selection.md
git commit -m "docs(mcp-hellodata): mark A7 sample action done

EN: Cursor-paginated read. One extra row is fetched to decide has_more
without a second count, the window helper column never leaves the response,
and page two is verified to share no row with page one.

FR: Lecture paginee par curseur. Une ligne supplementaire est lue pour
decider has_more sans second comptage, la colonne technique de la fenetre ne
sort jamais dans la reponse, et la page deux est verifiee sans recouvrement
avec la page une."
```

---

### Task A8: Export CSV — job asynchrone, écriture par tranches, purge

L'export ne tient pas dans une requête HTTP : il faut un job. Et il ne doit **jamais** accumuler en mémoire — le script du BO fait `ini_set("memory_limit", -1)` et empile tout, c'est précisément ce qu'on ne reproduit pas.

La sortie retenue est simple et réutilise du code déjà testé : le worker **boucle sur `requete_construire` par tranches de 2000 lignes**, en avançant le curseur, et append chaque tranche au CSV. L'empreinte mémoire est bornée par construction, sans avoir à manier un curseur MySQL non bufferisé.

**Files:**
- Create: `site/admin/mcp/hellodata/actions/export_start.php`, `export_worker.php`, `export_statut.php`, `export_fetch.php`
- Test: `site/admin/mcp/hellodata/test/export.test.php` (parties pures : nom de fichier, purge)

**Interfaces:**
- Consumes: A3, A4, A5
- Produces: `export_chemin(string $id, string $suffixe): string`, `export_nouvel_id(): string`, `export_purger(): int`
- Réponses : `export_start` → `{job_id}` · `export_statut` → `{state, lignes_ecrites, handle?, erreur?}` · `export_fetch` → flux `text/csv`

- [ ] **Step 1: Écrire les tests qui échouent**

```php
<?php
// test/export.test.php
require_once __DIR__ . '/_assert.php';
putenv('MCP_HELLODATA_VAR=' . sys_get_temp_dir() . '/mcp-hellodata-test-' . getmypid());
require_once __DIR__ . '/../actions/export_commun.php';

$a = export_nouvel_id();
$b = export_nouvel_id();
ok(strlen($a) === 32, 'un identifiant fait 32 caracteres');
ok(preg_match('/^[0-9a-f]{32}$/', $a) === 1, 'un identifiant est hexadecimal');
ok($a !== $b, 'deux identifiants different');

// Le nom de fichier ne doit rien reveler : les exports existants du BO
// s appellent export_202602261600_1938.csv, entierement devinables.
ok(strpos($a, date('Y')) === false, 'l identifiant ne porte pas la date');

// traversee de chemin
leve(function () { export_chemin('../../etc/passwd', 'csv'); },
     'handle_invalide', 'une traversee de chemin est refusee');
leve(function () { export_chemin('pas-hexa!', 'csv'); },
     'handle_invalide', 'un identifiant non hexadecimal est refuse');
ok(strpos(export_chemin($a, 'csv'), $a . '.csv') !== false, 'chemin construit pour un id valide');

// purge
$vieux = export_chemin($a, 'csv');
@mkdir(dirname($vieux), 0700, true);
file_put_contents($vieux, 'x');
touch($vieux, time() - (25 * 3600));
$recent = export_chemin($b, 'csv');
file_put_contents($recent, 'x');
ok(export_purger() >= 1, 'la purge supprime au moins le fichier de 25 h');
ok(!is_file($vieux), 'le fichier de plus de 24 h est supprime');
ok(is_file($recent), 'le fichier recent est conserve');

bilan();
```

- [ ] **Step 2: Lancer les tests et vérifier qu'ils échouent**

```bash
docker run --rm -v "$PWD":/src -w /src php:8.2-cli \
  php site/admin/mcp/hellodata/test/export.test.php
```

- [ ] **Step 3: Écrire le module commun**

```php
<?php
// actions/export_commun.php — identifiants, chemins, purge.

define('EXPORT_RETENTION_SECONDES', 24 * 3600);
define('EXPORT_TRANCHE', 2000);

function export_base() {
    $base = getenv('MCP_HELLODATA_VAR');
    if (!$base) { $base = sys_get_temp_dir() . '/mcp-hellodata'; }
    $dir = rtrim($base, '/') . '/exports';
    if (!is_dir($dir)) { @mkdir($dir, 0700, true); }
    return $dir;
}

/** 128 bits d'alea. Pas d'horodatage, pas d'identifiant utilisateur. */
function export_nouvel_id() { return bin2hex(random_bytes(16)); }

/**
 * Le handle vient du reseau. La liste blanche hexadecimale est ce qui
 * empeche un ../../ de sortir du repertoire : on ne nettoie pas le
 * chemin, on refuse tout ce qui n'est pas exactement 32 hexa.
 */
function export_chemin($id, $suffixe) {
    if (!is_string($id) || preg_match('/^[0-9a-f]{32}$/', $id) !== 1) {
        throw new Exception('handle_invalide: identifiant attendu de 32 caracteres hexadecimaux');
    }
    return export_base() . '/' . $id . '.' . $suffixe;
}

function export_lire_job($id) {
    $f = export_chemin($id, 'json');
    if (!is_file($f)) { return null; }
    $d = json_decode(@file_get_contents($f), true);
    return is_array($d) ? $d : null;
}

function export_ecrire_job($id, $job) {
    $f = export_chemin($id, 'json');
    $tmp = $f . '.' . getmypid() . '.tmp';
    if (@file_put_contents($tmp, json_encode($job)) !== false) { @rename($tmp, $f); }
}

/** Rend le nombre de fichiers supprimes. */
function export_purger() {
    $n = 0;
    foreach (glob(export_base() . '/*') as $f) {
        if (is_file($f) && time() - filemtime($f) > EXPORT_RETENTION_SECONDES) {
            if (@unlink($f)) { $n++; }
        }
    }
    return $n;
}
```

- [ ] **Step 4: Écrire le démarrage, le worker, le statut et le téléchargement**

```php
<?php
// actions/export_start.php
require_once __DIR__ . '/export_commun.php';
require_once __DIR__ . '/../requete.php';

$filtre = isset($corps['filtre']) ? $corps['filtre'] : null;
if (!is_array($filtre)) { echouer('filtre_manquant', "le champ 'filtre' est requis"); }
$colonnes = isset($corps['colonnes']) && is_array($corps['colonnes']) && $corps['colonnes']
          ? $corps['colonnes'] : array('id_acheteur', 'raison_sociale', 'ville', 'code_postal');

// On compile TOUT de suite : un filtre invalide doit echouer maintenant,
// avec un message utile, pas silencieusement dans un job une minute plus tard.
try {
    $c = compiler_arbre($filtre);
    requete_construire($c['sql'], $c['params'], array(
        'colonnes' => $colonnes, 'limite' => 1, 'mode' => 'lignes',
        'colonnes_restreintes_autorisees' => !empty($corps['colonnes_restreintes_autorisees']),
    ));
} catch (ArbreErreur $e)   { echouer('arbre_trop_complexe', $e->getMessage()); }
  catch (CritereErreur $e) { echouer('critere_invalide', $e->getMessage()); }
  catch (RequeteErreur $e) { echouer('requete_invalide', $e->getMessage()); }

export_purger();

$id = export_nouvel_id();
export_ecrire_job($id, array(
    'state' => 'en_attente', 'lignes_ecrites' => 0, 'cree_le' => time(),
    'filtre' => $filtre, 'colonnes' => $colonnes,
    'type_blocage' => isset($corps['type_blocage']) ? (int)$corps['type_blocage'] : 1,
    'restreintes' => !empty($corps['colonnes_restreintes_autorisees']),
    'demandeur' => isset($corps['demandeur']) ? $corps['demandeur'] : '',
));

// Journalisation nominative : la liste statique d'autorises ne fournit
// aucune trace, celle-ci est la seule qui existera sur un export.
journaliser('export_start', 'job=' . $id . ' demandeur=' . (isset($corps['demandeur']) ? $corps['demandeur'] : '?'));

// Rendre la main AVANT de travailler. fastcgi_finish_request est le chemin
// propre sous PHP-FPM ; exec est le repli. Si aucun des deux n'existe sur
// Ecritel (a verifier en Task A9), il faut un cron, et il faut le dire.
ignore_user_abort(true);
if (function_exists('fastcgi_finish_request')) {
    http_response_code(200);
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode(array('code' => 200, 'response' => array('job_id' => $id)));
    fastcgi_finish_request();
    require __DIR__ . '/export_worker.php';
    export_executer($id);
    exit;
}
@exec('php ' . escapeshellarg(__DIR__ . '/export_cli.php') . ' ' . escapeshellarg($id) . ' > /dev/null 2>&1 &');
repondre(array('job_id' => $id));
```

```php
<?php
// actions/export_worker.php — ecrit le CSV par tranches.
require_once __DIR__ . '/export_commun.php';
require_once __DIR__ . '/../requete.php';
require_once __DIR__ . '/../bdd.php';

function export_executer($id) {
    $job = export_lire_job($id);
    if ($job === null) { return; }
    $job['state'] = 'en_cours';
    export_ecrire_job($id, $job);

    $chemin = export_chemin($id, 'csv');
    $fh = @fopen($chemin, 'w');
    if ($fh === false) {
        $job['state'] = 'echec'; $job['erreur'] = 'ecriture_impossible';
        export_ecrire_job($id, $job); return;
    }
    // BOM UTF-8 : sans lui, Excel affiche les accents en mojibake, et le
    // fichier part en campagne tel quel.
    fwrite($fh, "\xEF\xBB\xBF");
    $entete_ecrit = false;
    $curseur = null;
    $total = 0;

    try {
        $c = compiler_arbre($job['filtre']);
        while (true) {
            // Une tranche a la fois : l'empreinte memoire est bornee par
            // EXPORT_TRANCHE, quelle que soit la taille du resultat.
            $r = requete_construire($c['sql'], $c['params'], array(
                'colonnes' => $job['colonnes'],
                'type_blocage' => $job['type_blocage'],
                'curseur' => $curseur,
                'limite' => EXPORT_TRANCHE,
                'mode' => 'lignes',
                'colonnes_restreintes_autorisees' => !empty($job['restreintes']),
            ));
            $stmt = bdd_executer($r['sql'], $r['params']);
            $res = mysqli_stmt_get_result($stmt);
            $n = 0;
            while ($l = mysqli_fetch_assoc($res)) {
                unset($l['rn']);
                if (!$entete_ecrit) { fputcsv($fh, array_keys($l), ';'); $entete_ecrit = true; }
                fputcsv($fh, array_values($l), ';');
                $curseur = (int)$l['id_acheteur'];
                $n++; $total++;
            }
            mysqli_stmt_close($stmt);
            if ($n < EXPORT_TRANCHE) { break; }

            $job['lignes_ecrites'] = $total;
            export_ecrire_job($id, $job);
        }
    } catch (Exception $e) {
        fclose($fh);
        journaliser('export_worker', 'job=' . $id . ' ' . $e->getMessage());
        $job['state'] = 'echec'; $job['erreur'] = 'erreur_interne';
        export_ecrire_job($id, $job);
        return;
    }

    fclose($fh);
    $job['state'] = 'termine';
    $job['lignes_ecrites'] = $total;
    export_ecrire_job($id, $job);
    journaliser('export_worker', 'job=' . $id . ' termine lignes=' . $total);
}
```

```php
<?php
// actions/export_cli.php — repli quand fastcgi_finish_request n'existe pas.
// Invoque en CLI uniquement.
if (PHP_SAPI !== 'cli') { exit(1); }
require_once __DIR__ . '/export_worker.php';
export_executer(isset($argv[1]) ? $argv[1] : '');
```

```php
<?php
// actions/export_statut.php
require_once __DIR__ . '/export_commun.php';

$id = isset($_GET['job_id']) ? $_GET['job_id'] : '';
try { export_chemin($id, 'json'); }
catch (Exception $e) { echouer('handle_invalide', $e->getMessage()); }

$job = export_lire_job($id);
if ($job === null) { echouer('job_inconnu', 'job absent ou expire', 404); }

$out = array('state' => $job['state'], 'lignes_ecrites' => (int)$job['lignes_ecrites']);
if ($job['state'] === 'termine') { $out['handle'] = $id; }
if ($job['state'] === 'echec')   { $out['erreur'] = $job['erreur']; }
repondre($out);
```

```php
<?php
// actions/export_fetch.php — seul chemin vers le fichier. Il n'est servi
// par aucune URL directe : il vit hors racine web.
require_once __DIR__ . '/export_commun.php';

$id = isset($_GET['handle']) ? $_GET['handle'] : '';
try { $chemin = export_chemin($id, 'csv'); }
catch (Exception $e) { echouer('handle_invalide', $e->getMessage()); }

$job = export_lire_job($id);
if ($job === null || $job['state'] !== 'termine' || !is_file($chemin)) {
    echouer('export_indisponible', 'export absent, incomplet ou expire', 404);
}

journaliser('export_fetch', 'job=' . $id);
header('Content-Type: text/csv; charset=utf-8');
header('Content-Length: ' . filesize($chemin));
header('Content-Disposition: attachment; filename="selection-' . $id . '.csv"');
readfile($chemin);
exit;
```

- [ ] **Step 5: Lancer les tests et vérifier qu'ils passent**

```bash
docker run --rm -v "$PWD":/src -w /src php:8.2-cli \
  php site/admin/mcp/hellodata/test/export.test.php
```

Attendu : `OK - 10 assertions`.

- [ ] **Step 6: Vérifier le cycle complet après déploiement**

```bash
JOB=$(curl -s -X POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"filtre":{"critere":"region","comparateur":"dans","valeur":[6]}}' \
  'https://<hôte-bo>/admin/mcp/hellodata/index.php?action=export_start' | jq -r '.response.job_id')

curl -s -H "Authorization: Bearer $TOKEN" \
  "https://<hôte-bo>/admin/mcp/hellodata/index.php?action=export_statut&job_id=$JOB" | jq .

curl -s -H "Authorization: Bearer $TOKEN" \
  "https://<hôte-bo>/admin/mcp/hellodata/index.php?action=export_fetch&handle=$JOB" | head -3
```

Attendu : un `job_id`, puis `state` passant de `en_cours` à `termine`, puis un CSV dont la première ligne est l'en-tête.

**Vérifie aussi que le fichier n'est PAS joignable directement** :

```bash
curl -s -o /dev/null -w '%{http_code}\n' "https://<hôte-bo>/admin/mcp/hellodata/exports/$JOB.csv"
```

Attendu : `404`. Un `200` signifie que le répertoire d'état n'est pas hors racine web, et **l'export doit être désactivé jusqu'à correction**.

- [ ] **Step 7: Commiter la note de suivi**

```bash
git add docs/superpowers/plans/2026-09-21-mcp-hellodata-selection.md
git commit -m "docs(mcp-hellodata): mark A8 CSV export done

EN: Asynchronous export writing the CSV in 2000-row cursor slices, so memory
stays bounded whatever the result size, reusing the query builder already
tested. Handles are 128 random bits with no date or user id, path traversal
is refused by an hex allowlist rather than sanitised, files live outside the
web root and expire after 24h, and every start and fetch is logged since the
static allowlist provides no audit trail.

FR: Export asynchrone ecrivant le CSV par tranches de 2000 lignes au
curseur, pour que la memoire reste bornee quelle que soit la taille du
resultat, en reutilisant le constructeur de requete deja teste. Les handles
sont 128 bits aleatoires sans date ni identifiant utilisateur, la traversee
de chemin est refusee par liste blanche hexadecimale plutot que nettoyee,
les fichiers vivent hors racine web et expirent a 24 h, et chaque demarrage
et telechargement est journalise puisque la liste statique ne fournit
aucune trace."
```

---

### Task A9: Déploiement du moteur sur Ecritel

Le PHP n'est pas tracké. La procédure de `site/CLAUDE.md` s'applique : **une PR contenant uniquement un `.md`**, puis un upload FTP manuel par le développeur.

**Files:**
- Create: `site/moteur_recherche/MCP_HELLODATA_MOTEUR_2026-09-21.md`

**Interfaces:**
- Consumes: A1–A8
- Produces: le moteur en ligne, et les valeurs dont la Phase B a besoin — URL de base, jeton

- [ ] **Step 1: Écrire le document de déploiement**

Il contient, dans cet ordre : la liste exhaustive des fichiers à uploader avec leur chemin distant ; le contenu complet de chacun ; les deux variables d'environnement à poser (`MCP_HELLODATA_TOKEN`, `MCP_HELLODATA_VAR`) et **où** les poser ; la création du répertoire d'état hors racine web avec ses droits `0700` ; et les tests post-déploiement des étapes suivantes.

- [ ] **Step 2: Vérifier que le répertoire d'état est bien hors racine web**

Le test décisif, avant tout le reste : dépose un fichier témoin dans `<chemin_var>/exports/`, puis tente de le récupérer par URL :

```
curl -s -o /dev/null -w '%{http_code}\n' 'https://<hôte-bo>/admin/mcp/hellodata/exports/temoin.txt'
```

Attendu : `404`. Un `200` **bloque la mise en service de l'export**. Supprime le témoin ensuite.

- [ ] **Step 3: Vérifier quel mécanisme de tâche de fond fonctionne**

Lance un `export_start` et observe le statut. Si le `job_id` revient immédiatement **et** que `lignes_ecrites` progresse, `fastcgi_finish_request` fonctionne. Si le `job_id` revient mais que l'état reste `en_attente`, ni PHP-FPM ni `exec` ne sont disponibles — **remonte-le** : il faudra un cron qui balaie les jobs `en_attente`, et ce n'est pas dans ce plan.

- [ ] **Step 4: Vérifier l'auth de bout en bout**

Sans en-tête → `401`. Mauvais jeton → `401`. Bon jeton → `200`. Les trois, pas seulement le dernier.

- [ ] **Step 5: Commiter le document et ouvrir la PR**

Message de commit, préfixe `docs(site):`, sujet `add MCP HelloData engine deployment spec`, corps bilingue :

> EN: Deployment spec for the new /admin/mcp/hellodata engine: file list, full contents, the two environment variables, the state directory outside the web root, and the post-deploy checks. The PHP itself stays untracked per site/CLAUDE.md and is uploaded by FTP.
>
> FR: Spec de deploiement du nouveau moteur /admin/mcp/hellodata : liste des fichiers, contenu complet, les deux variables d'environnement, le repertoire d'etat hors racine web, et les tests post-deploiement. Le PHP lui-meme reste non tracke conformement a site/CLAUDE.md et part par FTP.

---

## Phase B — Wrapper Go `mcp-hellodata-service`

### Task B1: Squelette du service

**Files:**
- Create: `apps-microservices/mcp-hellodata-service/go.mod`
- Create: `apps-microservices/mcp-hellodata-service/internal/config/config.go`
- Create: `apps-microservices/mcp-hellodata-service/internal/mcp/types.go`
- Test: `apps-microservices/mcp-hellodata-service/internal/config/config_test.go`

**Interfaces:**
- Consumes: rien
- Produces: `config.Charger() (Config, error)` avec les champs `Port int`, `BaseURL string`, `Token string`, `EmailsAutorises string`, `PublicURL string` · types `mcp.Requete`, `mcp.Reponse`, `mcp.ErreurRPC`, `mcp.Outil`, fonctions `mcp.OK`, `mcp.Echec`

- [ ] **Step 1: Écrire le test qui échoue**

```go
package config

import (
	"os"
	"testing"
)

func poser(t *testing.T, kv map[string]string) {
	t.Helper()
	for _, k := range []string{"HELLODATA_BASE_URL", "HELLODATA_TOKEN", "HELLODATA_ALLOWED_EMAILS", "HELLODATA_PUBLIC_URL", "MCP_PORT"} {
		os.Unsetenv(k)
	}
	for k, v := range kv {
		os.Setenv(k, v)
	}
}

func TestCharger_ValeursParDefaut(t *testing.T) {
	poser(t, map[string]string{
		"HELLODATA_BASE_URL": "https://bo.example.test/admin/mcp/hellodata",
		"HELLODATA_TOKEN":    "jeton",
	})
	c, err := Charger()
	if err != nil {
		t.Fatalf("erreur inattendue: %v", err)
	}
	if c.Port != 8597 {
		t.Errorf("Port = %d, attendu 8597", c.Port)
	}
	if c.EmailsAutorises != "" {
		t.Errorf("EmailsAutorises = %q, attendu vide", c.EmailsAutorises)
	}
}

// Une URL ou un jeton manquant doit empecher le demarrage. Un service qui
// demarre sans jeton ne peut rien faire et le decouvre au premier appel.
func TestCharger_RefuseUneConfigIncomplete(t *testing.T) {
	cas := []struct {
		nom string
		env map[string]string
	}{
		{"sans URL", map[string]string{"HELLODATA_TOKEN": "jeton"}},
		{"sans jeton", map[string]string{"HELLODATA_BASE_URL": "https://bo.example.test"}},
		{"les deux absents", map[string]string{}},
	}
	for _, c := range cas {
		t.Run(c.nom, func(t *testing.T) {
			poser(t, c.env)
			if _, err := Charger(); err == nil {
				t.Fatal("attendu une erreur, obtenu nil")
			}
		})
	}
}

func TestCharger_PortInvalide(t *testing.T) {
	poser(t, map[string]string{
		"HELLODATA_BASE_URL": "https://bo.example.test",
		"HELLODATA_TOKEN":    "jeton",
		"MCP_PORT":           "pas-un-nombre",
	})
	if _, err := Charger(); err == nil {
		t.Fatal("attendu une erreur sur un port illisible")
	}
}

func TestCharger_RetireLeSlashFinal(t *testing.T) {
	poser(t, map[string]string{
		"HELLODATA_BASE_URL": "https://bo.example.test/admin/mcp/hellodata/",
		"HELLODATA_TOKEN":    "jeton",
	})
	c, _ := Charger()
	if c.BaseURL != "https://bo.example.test/admin/mcp/hellodata" {
		t.Errorf("BaseURL = %q, slash final non retire", c.BaseURL)
	}
}
```

- [ ] **Step 2: Lancer le test et vérifier qu'il échoue**

Depuis `apps-microservices/mcp-hellodata-service/` :

```
docker run --rm -v "$PWD":/src -w /src golang:1.24-alpine go test ./internal/config/
```

Attendu : échec de compilation, `Charger` non défini.

- [ ] **Step 3: Écrire `go.mod` et la configuration**

`go.mod` :

```
module mcp-hellodata

go 1.24
```

`internal/config/config.go` :

```go
package config

import (
	"fmt"
	"os"
	"strconv"
	"strings"
)

// Config porte tout ce que le service lit de son environnement.
// Aucune URL ni aucun jeton n'est code en dur (.claude/rules/security.md).
type Config struct {
	Port int
	// BaseURL du moteur /admin/mcp/hellodata sur Ecritel.
	BaseURL string
	// Token presente au moteur en Bearer.
	Token string
	// EmailsAutorises : adresses separees par des virgules, autorisees en
	// plus des admin. Les VALEURS ne sont jamais dans le code : le depot
	// est public.
	EmailsAutorises string
	// PublicURL sert a fabriquer les liens /download rendus au LLM.
	PublicURL string
}

func Charger() (Config, error) {
	c := Config{
		Port:            8597,
		BaseURL:         strings.TrimRight(os.Getenv("HELLODATA_BASE_URL"), "/"),
		Token:           os.Getenv("HELLODATA_TOKEN"),
		EmailsAutorises: os.Getenv("HELLODATA_ALLOWED_EMAILS"),
		PublicURL:       strings.TrimRight(os.Getenv("HELLODATA_PUBLIC_URL"), "/"),
	}
	if v := os.Getenv("MCP_PORT"); v != "" {
		p, err := strconv.Atoi(v)
		if err != nil || p < 1 || p > 65535 {
			return Config{}, fmt.Errorf("MCP_PORT invalide: %q", v)
		}
		c.Port = p
	}
	if c.BaseURL == "" {
		return Config{}, fmt.Errorf("HELLODATA_BASE_URL est requis")
	}
	if c.Token == "" {
		return Config{}, fmt.Errorf("HELLODATA_TOKEN est requis")
	}
	return c, nil
}
```

- [ ] **Step 4: Écrire les types MCP**

`internal/mcp/types.go` :

```go
package mcp

import "encoding/json"

const (
	CodeErreurParsing   = -32700
	CodeRequeteInvalide = -32600
	CodeMethodeInconnue = -32601
	CodeParamsInvalides = -32602
	CodeErreurInterne   = -32603
)

type Requete struct {
	JSONRPC string          `json:"jsonrpc"`
	ID      json.RawMessage `json:"id,omitempty"`
	Methode string          `json:"method"`
	Params  json.RawMessage `json:"params,omitempty"`
}

type ErreurRPC struct {
	Code    int    `json:"code"`
	Message string `json:"message"`
}

type Reponse struct {
	JSONRPC string          `json:"jsonrpc"`
	ID      json.RawMessage `json:"id,omitempty"`
	Result  interface{}     `json:"result,omitempty"`
	Error   *ErreurRPC      `json:"error,omitempty"`
}

type Outil struct {
	Nom         string      `json:"name"`
	Description string      `json:"description"`
	SchemaEntre interface{} `json:"inputSchema"`
}

func OK(id json.RawMessage, result interface{}) Reponse {
	return Reponse{JSONRPC: "2.0", ID: id, Result: result}
}

func Echec(id json.RawMessage, code int, message string) Reponse {
	return Reponse{JSONRPC: "2.0", ID: id, Error: &ErreurRPC{Code: code, Message: message}}
}
```

- [ ] **Step 5: Lancer le test et vérifier qu'il passe**

```
docker run --rm -v "$PWD":/src -w /src golang:1.24-alpine go test ./internal/config/ -v
```

Attendu : les quatre tests passent.

- [ ] **Step 6: Commiter**

Préfixe `feat(mcp-hellodata-service):`, sujet `scaffold service config and MCP types`, corps bilingue :

> EN: Module skeleton with environment-based config and JSON-RPC 2.0 types, Go stdlib only as in mcp-leexi-service. A missing base URL or token refuses to start rather than failing at the first call.
>
> FR: Squelette du module avec configuration par environnement et types JSON-RPC 2.0, bibliotheque standard seule comme dans mcp-leexi-service. Une URL de base ou un jeton manquant empeche le demarrage plutot que d'echouer au premier appel.

---

### Task B2: Contrôle d'accès — `admin` ou liste statique

C'est la tâche la plus sensible de la Phase B : c'est ici, et nulle part ailleurs, que se décide qui peut interroger les acheteurs.

**Files:**
- Create: `apps-microservices/mcp-hellodata-service/internal/acces/acces.go`
- Test: `apps-microservices/mcp-hellodata-service/internal/acces/acces_test.go`

**Interfaces:**
- Consumes: rien
- Produces: `acces.Nouveau(liste string) *Acces` · `(*Acces).Autorise(email, role string) bool` · `(*Acces).EstAdmin(role string) bool` · `acces.Normaliser(email string) string` · constante `acces.RoleAdmin = "admin"`
- En-têtes lus en amont par le transport : `X-End-User-Email`, `X-End-User-Role`

- [ ] **Step 1: Écrire le test qui échoue**

```go
package acces

import "testing"

// Adresses fictives en .test : le depot est public, aucune adresse reelle
// ne doit apparaitre, y compris dans un test.
const liste = "alice@example.test, BOB@Example.TEST ,,carol@example.test"

func TestAutorise(t *testing.T) {
	a := Nouveau(liste)
	cas := []struct {
		nom    string
		email  string
		role   string
		attend bool
	}{
		{"admin hors liste passe", "dave@example.test", "admin", true},
		{"readonly hors liste refuse", "dave@example.test", "readonly", false},
		{"readonly dans la liste passe", "alice@example.test", "readonly", true},
		{"casse et espaces normalises des deux cotes", "  BoB@EXAMPLE.test  ", "readonly", true},
		{"email vide refuse", "", "readonly", false},
		{"email vide avec role admin refuse", "", "admin", false},
		{"role vide hors liste refuse", "dave@example.test", "", false},
		{"role Admin capitalise n est pas admin", "dave@example.test", "Admin", false},
		{"role superadmin n est pas admin", "dave@example.test", "superadmin", false},
		{"role avec espaces reste admin", "dave@example.test", " admin ", true},
	}
	for _, c := range cas {
		t.Run(c.nom, func(t *testing.T) {
			if got := a.Autorise(c.email, c.role); got != c.attend {
				t.Errorf("Autorise(%q, %q) = %v, attendu %v", c.email, c.role, got, c.attend)
			}
		})
	}
}

// Une entree vide dans la liste ne doit pas devenir une cle vide, sinon un
// email vide correspondrait.
func TestEntreeVideIgnoree(t *testing.T) {
	a := Nouveau("alice@example.test,,")
	if len(a.autorises) != 1 {
		t.Errorf("liste = %d entrees, attendu 1", len(a.autorises))
	}
}

// Controle positif de l'absence : sans lui, un bug qui refuserait tout
// ferait passer tous les tests de refus ci-dessus.
func TestListeVide_SeulsLesAdminsPassent(t *testing.T) {
	a := Nouveau("")
	if a.Autorise("alice@example.test", "readonly") {
		t.Error("liste vide: un readonly ne doit pas passer")
	}
	if !a.Autorise("alice@example.test", "admin") {
		t.Error("liste vide: un admin doit toujours passer")
	}
}

// Un receveur nil ne doit jamais autoriser : un cablage oublie au demarrage
// deviendrait sinon une porte ouverte.
func TestReceveurNil_Refuse(t *testing.T) {
	var a *Acces
	if a.Autorise("alice@example.test", "admin") {
		t.Error("un Acces nil ne doit jamais autoriser")
	}
}

func TestEstAdmin(t *testing.T) {
	a := Nouveau("")
	if !a.EstAdmin("admin") {
		t.Error("admin doit etre admin")
	}
	if a.EstAdmin("readonly") {
		t.Error("readonly ne doit pas etre admin")
	}
}
```

- [ ] **Step 2: Lancer le test et vérifier qu'il échoue**

```
docker run --rm -v "$PWD":/src -w /src golang:1.24-alpine go test ./internal/acces/
```

- [ ] **Step 3: Écrire l'implémentation**

`internal/acces/acces.go` :

```go
// Package acces decide qui peut utiliser ce service.
//
// Deux voies, et deux seulement : le role admin, ou la presence dans une
// liste statique. Le gateway n'applique qu'une barriere de role minimale
// (min_role = readonly) qui ecarte les chemins sans utilisateur ; la
// decision nominative se prend ici.
//
// Toute absence refuse. Un appel sans identite n'est pas un appel interne
// de confiance, c'est un appel dont on ignore l'auteur.
package acces

import "strings"

// RoleAdmin est la valeur exacte de gateway_users.role pour un
// administrateur (internal/auth/role.go du gateway). La comparaison est
// stricte : ce service ne recoit pas la table des niveaux de role et n'a
// pas a la dupliquer, donc un role inconnu n'est pas admin.
const RoleAdmin = "admin"

type Acces struct {
	autorises map[string]struct{}
}

// Nouveau construit la liste depuis HELLODATA_ALLOWED_EMAILS. Les entrees
// vides sont ignorees, ce qui rend inoffensive une virgule en trop et
// evite qu'une cle vide corresponde a un email vide.
func Nouveau(liste string) *Acces {
	a := &Acces{autorises: make(map[string]struct{})}
	for _, brut := range strings.Split(liste, ",") {
		if e := Normaliser(brut); e != "" {
			a.autorises[e] = struct{}{}
		}
	}
	return a
}

// Normaliser est appliquee des deux cotes — au chargement de la liste et a
// l'email entrant — pour qu'une difference de casse ne produise pas un
// refus silencieux.
func Normaliser(email string) string {
	return strings.ToLower(strings.TrimSpace(email))
}

func (a *Acces) Autorise(email, role string) bool {
	if a == nil {
		return false
	}
	e := Normaliser(email)
	if e == "" {
		return false
	}
	if strings.TrimSpace(role) == RoleAdmin {
		return true
	}
	_, ok := a.autorises[e]
	return ok
}

// EstAdmin commande l'acces aux colonnes email et telephone, equivalent du
// $debloque_tel_mail du BO. Tant que la precondition 5 n'est pas tranchee,
// un autorise par liste n'y a pas droit.
func (a *Acces) EstAdmin(role string) bool {
	return strings.TrimSpace(role) == RoleAdmin
}
```

- [ ] **Step 4: Lancer le test et vérifier qu'il passe**

```
docker run --rm -v "$PWD":/src -w /src golang:1.24-alpine go test ./internal/acces/ -v
```

Attendu : tous les sous-cas passent.

- [ ] **Step 5: Vérifier qu'aucune adresse réelle n'a été écrite**

Depuis la racine du dépôt :

```
grep -rn "hellopro.fr" apps-microservices/mcp-hellodata-service/
```

Attendu : aucune correspondance. Le dépôt est public ; une adresse committée survit dans l'historique même après suppression.

- [ ] **Step 6: Commiter**

Préfixe `feat(mcp-hellodata-service):`, sujet `add admin-or-allowlist access check`, corps bilingue :

> EN: Access is the admin role or membership in a static allowlist, with every absence denying. Role comparison is strict so an unknown role is not admin, emails are normalised on both sides so case never causes a silent refusal, and a nil receiver denies so a missed wiring is not an open door. Test addresses use example.test because the repository is public.
>
> FR: L'acces est le role admin ou l'appartenance a une liste statique, toute absence refusant. La comparaison de role est stricte pour qu'un role inconnu ne soit pas admin, les adresses sont normalisees des deux cotes pour qu'une casse ne provoque pas de refus silencieux, et un receveur nil refuse pour qu'un cablage oublie ne soit pas une porte ouverte. Les adresses de test sont en example.test parce que le depot est public.

---

### Task B3: Validation structurelle de l'arbre côté wrapper

Le wrapper valide **la forme** de l'arbre pour refuser tôt et rendre un message utile au LLM. Il ne valide **pas** les critères : la liste blanche reste côté moteur, en un seul endroit. Un wrapper qui dupliquerait la liste divergerait d'elle au premier critère ajouté.

**Files:**
- Create: `apps-microservices/mcp-hellodata-service/internal/filtre/filtre.go`
- Test: `apps-microservices/mcp-hellodata-service/internal/filtre/filtre_test.go`

**Interfaces:**
- Consumes: rien
- Produces: type `filtre.Noeud` · `filtre.Valider(n Noeud) (int, error)` · constantes `ProfondeurMax = 5`, `FeuillesMax = 50`, `EnfantsMax = 20`

- [ ] **Step 1: Écrire le test qui échoue**

```go
package filtre

import (
	"encoding/json"
	"strings"
	"testing"
)

func feuille() Noeud {
	return Noeud{Critere: "region", Comparateur: "dans", Valeur: json.RawMessage(`[6]`)}
}

func groupe(op string, enfants ...Noeud) Noeud {
	return Noeud{Operateur: op, Conditions: enfants}
}

func TestValider_CasAcceptes(t *testing.T) {
	cas := []struct {
		nom      string
		noeud    Noeud
		feuilles int
	}{
		{"feuille seule", feuille(), 1},
		{"ET de deux feuilles", groupe("ET", feuille(), feuille()), 2},
		{"OU imbrique", groupe("ET", feuille(), groupe("OU", feuille(), feuille())), 3},
		{"NON unaire", groupe("NON", feuille()), 1},
	}
	for _, c := range cas {
		t.Run(c.nom, func(t *testing.T) {
			n, err := Valider(c.noeud)
			if err != nil {
				t.Fatalf("erreur inattendue: %v", err)
			}
			if n != c.feuilles {
				t.Errorf("feuilles = %d, attendu %d", n, c.feuilles)
			}
		})
	}
}

// Controle positif de la borne : exactement 5 doit passer, 6 doit echouer.
// Sans le cas acceptant, un bug refusant tout ferait passer le cas refusant.
func TestValider_ProfondeurLimite(t *testing.T) {
	n := feuille()
	for i := 0; i < 4; i++ {
		n = groupe("ET", n)
	}
	if _, err := Valider(n); err != nil {
		t.Fatalf("profondeur 5 doit passer, obtenu: %v", err)
	}
	if _, err := Valider(groupe("ET", n)); err == nil {
		t.Fatal("profondeur 6 doit echouer")
	}
}

func TestValider_CasRefuses(t *testing.T) {
	large := Noeud{Operateur: "ET"}
	for i := 0; i < 20; i++ {
		large.Conditions = append(large.Conditions, feuille())
	}
	vingtEtUn := Noeud{Operateur: "OU"}
	for i := 0; i < 21; i++ {
		vingtEtUn.Conditions = append(vingtEtUn.Conditions, feuille())
	}

	cas := []struct {
		nom      string
		noeud    Noeud
		fragment string
	}{
		{"groupe vide", groupe("ET"), "groupe_vide"},
		{"NON binaire", groupe("NON", feuille(), feuille()), "non_unaire"},
		{"21 enfants", vingtEtUn, "arbre_trop_complexe"},
		{"60 feuilles", groupe("ET", large, large, large), "arbre_trop_complexe"},
		{"operateur inconnu", groupe("XOR", feuille()), "operateur_inconnu"},
		{"ni feuille ni groupe", Noeud{}, "noeud_invalide"},
	}
	for _, c := range cas {
		t.Run(c.nom, func(t *testing.T) {
			_, err := Valider(c.noeud)
			if err == nil {
				t.Fatal("attendu une erreur, obtenu nil")
			}
			if !strings.Contains(err.Error(), c.fragment) {
				t.Errorf("message = %q, attendu contenant %q", err.Error(), c.fragment)
			}
		})
	}
}

// Le message doit apprendre au LLM ce qui etait attendu, pas seulement
// refuser : sans cela il reformule au hasard.
func TestValider_MessageEnonceLaLimite(t *testing.T) {
	vingtEtUn := Noeud{Operateur: "OU"}
	for i := 0; i < 21; i++ {
		vingtEtUn.Conditions = append(vingtEtUn.Conditions, feuille())
	}
	_, err := Valider(vingtEtUn)
	if err == nil || !strings.Contains(err.Error(), "20") {
		t.Errorf("le message doit citer la limite 20, obtenu: %v", err)
	}
}

// Un arbre decode depuis du JSON doit se valider comme un arbre construit
// en Go : c'est la forme qui arrivera reellement.
func TestValider_DepuisJSON(t *testing.T) {
	brut := `{"operateur":"ET","conditions":[
		{"critere":"region","comparateur":"dans","valeur":[6]},
		{"operateur":"OU","conditions":[
			{"critere":"effectif","comparateur":"dans","valeur":["10"]},
			{"critere":"a_siret","comparateur":"=","valeur":true}]}]}`
	var n Noeud
	if err := json.Unmarshal([]byte(brut), &n); err != nil {
		t.Fatalf("decodage: %v", err)
	}
	f, err := Valider(n)
	if err != nil {
		t.Fatalf("erreur inattendue: %v", err)
	}
	if f != 3 {
		t.Errorf("feuilles = %d, attendu 3", f)
	}
}
```

- [ ] **Step 2: Lancer le test et vérifier qu'il échoue**

```
docker run --rm -v "$PWD":/src -w /src golang:1.24-alpine go test ./internal/filtre/
```

- [ ] **Step 3: Écrire l'implémentation**

`internal/filtre/filtre.go` :

```go
// Package filtre porte la forme de l'arbre de filtres et ses bornes.
//
// Il valide la STRUCTURE, jamais le contenu des feuilles : la liste
// blanche des criteres vit cote moteur, en un seul endroit. La dupliquer
// ici garantirait qu'elle diverge au premier critere ajoute.
package filtre

import (
	"encoding/json"
	"fmt"
)

const (
	ProfondeurMax = 5
	FeuillesMax   = 50
	EnfantsMax    = 20
)

// Noeud est soit un groupe (Operateur + Conditions), soit une feuille
// (Critere + Comparateur + Valeur). Valeur reste brute pour traverser le
// wrapper sans perte : c'est le moteur qui en juge.
type Noeud struct {
	Operateur   string          `json:"operateur,omitempty"`
	Conditions  []Noeud         `json:"conditions,omitempty"`
	Critere     string          `json:"critere,omitempty"`
	Comparateur string          `json:"comparateur,omitempty"`
	Valeur      json.RawMessage `json:"valeur,omitempty"`
}

func (n Noeud) estFeuille() bool { return n.Critere != "" }

// Valider rend le nombre de feuilles, ou la premiere erreur rencontree.
func Valider(n Noeud) (int, error) {
	feuilles := 0
	if err := parcourir(n, 1, &feuilles); err != nil {
		return 0, err
	}
	return feuilles, nil
}

// Le compteur est verifie a CHAQUE feuille, pas a la fin : avec 20 enfants
// et 5 niveaux un arbre peut porter 3,2 millions de feuilles, et le
// parcourir entierement avant de le refuser serait le deni de service
// qu'on veut eviter.
func parcourir(n Noeud, profondeur int, feuilles *int) error {
	if n.estFeuille() {
		*feuilles++
		if *feuilles > FeuillesMax {
			return fmt.Errorf("arbre_trop_complexe: plus de %d feuilles", FeuillesMax)
		}
		return nil
	}
	if n.Operateur == "" {
		return fmt.Errorf("noeud_invalide: ni 'critere' ni 'operateur'")
	}
	if n.Operateur != "ET" && n.Operateur != "OU" && n.Operateur != "NON" {
		return fmt.Errorf("operateur_inconnu: %q (attendus: ET, OU, NON)", n.Operateur)
	}
	if profondeur > ProfondeurMax {
		return fmt.Errorf("arbre_trop_complexe: profondeur superieure a %d", ProfondeurMax)
	}
	if len(n.Conditions) == 0 {
		return fmt.Errorf("groupe_vide: %q doit porter au moins une condition", n.Operateur)
	}
	if n.Operateur == "NON" && len(n.Conditions) != 1 {
		return fmt.Errorf("non_unaire: NON prend exactement 1 condition, %d fournies", len(n.Conditions))
	}
	if len(n.Conditions) > EnfantsMax {
		return fmt.Errorf("arbre_trop_complexe: %d enfants, maximum %d", len(n.Conditions), EnfantsMax)
	}
	for _, enfant := range n.Conditions {
		if err := parcourir(enfant, profondeur+1, feuilles); err != nil {
			return err
		}
	}
	return nil
}
```

- [ ] **Step 4: Lancer le test et vérifier qu'il passe**

```
docker run --rm -v "$PWD":/src -w /src golang:1.24-alpine go test ./internal/filtre/ -v
```

- [ ] **Step 5: Commiter**

Préfixe `feat(mcp-hellodata-service):`, sujet `add filter tree structural validation`, corps bilingue :

> EN: Structural bounds on the nested filter tree — depth, leaf count, arity, unary NOT — checked per leaf so an oversized tree is refused before it is fully walked. Criterion names are deliberately not validated here: the whitelist lives in the engine, and duplicating it would guarantee divergence.
>
> FR: Bornes structurelles de l'arbre imbrique — profondeur, nombre de feuilles, arite, NON unaire — verifiees a chaque feuille pour qu'un arbre surdimensionne soit refuse avant d'etre entierement parcouru. Les noms de criteres ne sont volontairement pas valides ici : la liste blanche vit dans le moteur, et la dupliquer garantirait la divergence.

---

### Task B4: Client HTTP du moteur

**Files:**
- Create: `apps-microservices/mcp-hellodata-service/internal/hellodata/client.go`
- Create: `apps-microservices/mcp-hellodata-service/internal/hellodata/types.go`
- Test: `apps-microservices/mcp-hellodata-service/internal/hellodata/client_test.go`

**Interfaces:**
- Consumes: `filtre.Noeud` (B3)
- Produces:
  - `hellodata.Nouveau(baseURL, token string) *Client`
  - `(*Client).Compter(ctx, Demande) (Comptage, error)`
  - `(*Client).Echantillon(ctx, Demande) (Echantillon, error)`
  - `(*Client).DemarrerExport(ctx, Demande) (Job, error)`
  - `(*Client).StatutExport(ctx, jobID string) (Statut, error)`
  - `(*Client).RecupererExport(ctx, handle string) (io.ReadCloser, error)` — l'appelant ferme
  - type `ErreurMoteur{Code, Message string}` implémentant `error`

- [ ] **Step 1: Écrire le test qui échoue**

```go
package hellodata

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func serveur(t *testing.T, gestionnaire http.HandlerFunc) *Client {
	t.Helper()
	s := httptest.NewServer(gestionnaire)
	t.Cleanup(s.Close)
	return Nouveau(s.URL, "jeton-test")
}

func TestCompter_DeballeLEnveloppe(t *testing.T) {
	c := serveur(t, func(w http.ResponseWriter, r *http.Request) {
		if got := r.Header.Get("Authorization"); got != "Bearer jeton-test" {
			t.Errorf("Authorization = %q", got)
		}
		if r.URL.Query().Get("action") != "comptage" {
			t.Errorf("action = %q", r.URL.Query().Get("action"))
		}
		io.WriteString(w, `{"code":200,"response":{"count":1234,"exact":false,"plafonne":false,"depuis_cache":true}}`)
	})
	got, err := c.Compter(context.Background(), Demande{Filtre: json.RawMessage(`{"critere":"region","comparateur":"dans","valeur":[6]}`)})
	if err != nil {
		t.Fatalf("erreur inattendue: %v", err)
	}
	if got.Count != 1234 || !got.DepuisCache {
		t.Errorf("Comptage = %+v", got)
	}
}

// Le code d'erreur stable du moteur doit remonter tel quel : c'est lui que
// le LLM lit pour corriger son appel.
func TestCompter_RemonteLeCodeDErreurDuMoteur(t *testing.T) {
	c := serveur(t, func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusBadRequest)
		io.WriteString(w, `{"code":400,"response":{"erreur":"critere_invalide","message":"critere_inconnu: 'couleur'. Criteres connus: region, ..."}}`)
	})
	_, err := c.Compter(context.Background(), Demande{Filtre: json.RawMessage(`{}`)})
	var em *ErreurMoteur
	if !errors.As(err, &em) {
		t.Fatalf("attendu une *ErreurMoteur, obtenu %T: %v", err, err)
	}
	if em.Code != "critere_invalide" {
		t.Errorf("Code = %q, attendu critere_invalide", em.Code)
	}
	if !strings.Contains(em.Message, "Criteres connus") {
		t.Errorf("le message du moteur doit etre conserve, obtenu %q", em.Message)
	}
}

// Un moteur qui rend du HTML (page d'erreur Apache, redirection de session)
// ne doit pas produire un resultat vide qui passerait pour un succes.
func TestCompter_ReponseNonJSON(t *testing.T) {
	c := serveur(t, func(w http.ResponseWriter, r *http.Request) {
		io.WriteString(w, "<html>Service Unavailable</html>")
	})
	if _, err := c.Compter(context.Background(), Demande{Filtre: json.RawMessage(`{}`)}); err == nil {
		t.Fatal("attendu une erreur sur une reponse non JSON")
	}
}

func TestEchantillon_TransmetCurseurEtTaille(t *testing.T) {
	c := serveur(t, func(w http.ResponseWriter, r *http.Request) {
		var recu Demande
		json.NewDecoder(r.Body).Decode(&recu)
		if recu.Taille != 50 || recu.Cursor == nil || *recu.Cursor != 999 {
			t.Errorf("Demande = %+v", recu)
		}
		io.WriteString(w, `{"code":200,"response":{"rows":[{"id_acheteur":1}],"next_cursor":1,"has_more":true}}`)
	})
	cur := 999
	got, err := c.Echantillon(context.Background(), Demande{
		Filtre: json.RawMessage(`{}`), Taille: 50, Cursor: &cur})
	if err != nil {
		t.Fatalf("erreur inattendue: %v", err)
	}
	if !got.HasMore || len(got.Rows) != 1 {
		t.Errorf("Echantillon = %+v", got)
	}
}

// Le budget de l'appel doit etre honore, sinon un moteur lent bloque le
// gateway.
func TestCompter_RespecteLeContexte(t *testing.T) {
	c := serveur(t, func(w http.ResponseWriter, r *http.Request) {
		<-r.Context().Done()
	})
	ctx, annule := context.WithCancel(context.Background())
	annule()
	if _, err := c.Compter(ctx, Demande{Filtre: json.RawMessage(`{}`)}); err == nil {
		t.Fatal("attendu une erreur sur contexte annule")
	}
}

func TestRecupererExport_RendUnFlux(t *testing.T) {
	c := serveur(t, func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Query().Get("handle") != "abc" {
			t.Errorf("handle = %q", r.URL.Query().Get("handle"))
		}
		w.Header().Set("Content-Type", "text/csv")
		io.WriteString(w, "id;ville\n1;Rennes\n")
	})
	flux, err := c.RecupererExport(context.Background(), "abc")
	if err != nil {
		t.Fatalf("erreur inattendue: %v", err)
	}
	defer flux.Close()
	b, _ := io.ReadAll(flux)
	if !strings.Contains(string(b), "Rennes") {
		t.Errorf("contenu = %q", string(b))
	}
}
```

- [ ] **Step 2: Lancer le test et vérifier qu'il échoue**

```
docker run --rm -v "$PWD":/src -w /src golang:1.24-alpine go test ./internal/hellodata/
```

- [ ] **Step 3: Écrire les types**

`internal/hellodata/types.go` :

```go
package hellodata

import "encoding/json"

// Demande est la charge utile envoyee au moteur. Filtre reste brut :
// le wrapper en a valide la forme (package filtre), le moteur en juge
// le contenu.
type Demande struct {
	Filtre       json.RawMessage `json:"filtre"`
	Colonnes     []string        `json:"colonnes,omitempty"`
	Taille       int             `json:"taille,omitempty"`
	Cursor       *int            `json:"cursor,omitempty"`
	TypeBlocage  int             `json:"type_blocage,omitempty"`
	Exact        bool            `json:"exact,omitempty"`
	Restreintes  bool            `json:"colonnes_restreintes_autorisees,omitempty"`
	Demandeur    string          `json:"demandeur,omitempty"`
}

type Comptage struct {
	Count       int  `json:"count"`
	Exact       bool `json:"exact"`
	Plafonne    bool `json:"plafonne"`
	DureeMs     int  `json:"duree_ms"`
	DepuisCache bool `json:"depuis_cache"`
}

type Echantillon struct {
	Rows       []map[string]interface{} `json:"rows"`
	NextCursor *int                     `json:"next_cursor"`
	HasMore    bool                     `json:"has_more"`
}

type Job struct {
	JobID string `json:"job_id"`
}

type Statut struct {
	State         string `json:"state"`
	LignesEcrites int    `json:"lignes_ecrites"`
	Handle        string `json:"handle,omitempty"`
	Erreur        string `json:"erreur,omitempty"`
}

// ErreurMoteur porte le code stable rendu par le moteur. Le LLM le lit
// pour corriger son appel, donc il remonte tel quel jusqu'au tool.
type ErreurMoteur struct {
	Code    string
	Message string
}

func (e *ErreurMoteur) Error() string { return e.Code + ": " + e.Message }
```

- [ ] **Step 4: Écrire le client**

`internal/hellodata/client.go` :

```go
// Package hellodata parle au moteur /admin/mcp/hellodata.
//
// Le contrat est celui que mcp-gateway-service/internal/bddcatalog utilise
// deja : Bearer, enveloppe {code, response}, et un budget de temps
// DIFFERENT par endpoint — un comptage exact et un statut de job n'ont
// aucune raison de partager la meme patience.
package hellodata

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"
)

// Budgets par endpoint, repris de la spec section 8.
const (
	BudgetComptageApproche = 20 * time.Second
	BudgetComptageExact    = 120 * time.Second
	BudgetEchantillon      = 30 * time.Second
	BudgetExportStart      = 5 * time.Second
	BudgetExportStatut     = 5 * time.Second
	BudgetExportFetch      = 10 * time.Minute
)

// Plafond de lecture d'une reponse JSON. Un moteur qui deraille ne doit
// pas pouvoir epuiser la memoire du wrapper.
const corpsMax = 16 << 20

type Client struct {
	baseURL string
	token   string
	http    *http.Client
}

// Le http.Client ne porte pas de Timeout : chaque appel pose le sien par
// contexte, sinon le budget le plus court s'appliquerait a tous.
func Nouveau(baseURL, token string) *Client {
	return &Client{baseURL: baseURL, token: token, http: &http.Client{}}
}

type enveloppe struct {
	Code     int             `json:"code"`
	Response json.RawMessage `json:"response"`
}

type erreurCorps struct {
	Erreur  string `json:"erreur"`
	Message string `json:"message"`
}

func (c *Client) Compter(ctx context.Context, d Demande) (Comptage, error) {
	budget := BudgetComptageApproche
	if d.Exact {
		budget = BudgetComptageExact
	}
	var out Comptage
	err := c.poster(ctx, "comptage", d, budget, &out)
	return out, err
}

func (c *Client) Echantillon(ctx context.Context, d Demande) (Echantillon, error) {
	var out Echantillon
	err := c.poster(ctx, "echantillon", d, BudgetEchantillon, &out)
	return out, err
}

func (c *Client) DemarrerExport(ctx context.Context, d Demande) (Job, error) {
	var out Job
	err := c.poster(ctx, "export_start", d, BudgetExportStart, &out)
	return out, err
}

func (c *Client) StatutExport(ctx context.Context, jobID string) (Statut, error) {
	var out Statut
	err := c.obtenir(ctx, "export_statut", map[string]string{"job_id": jobID}, BudgetExportStatut, &out)
	return out, err
}

// RecupererExport rend le flux CSV. L'appelant DOIT fermer : le corps est
// streame vers le client sans jamais etre charge en memoire.
func (c *Client) RecupererExport(ctx context.Context, handle string) (io.ReadCloser, error) {
	ctx, annule := context.WithTimeout(ctx, BudgetExportFetch)
	req, err := c.requete(ctx, http.MethodGet, "export_fetch",
		map[string]string{"handle": handle}, nil)
	if err != nil {
		annule()
		return nil, err
	}
	resp, err := c.http.Do(req)
	if err != nil {
		annule()
		return nil, fmt.Errorf("export_fetch: %w", err)
	}
	if resp.StatusCode != http.StatusOK {
		defer resp.Body.Close()
		annule()
		return nil, c.erreurDepuis(resp)
	}
	// Le contexte doit vivre aussi longtemps que le flux : on l'annule a
	// la fermeture, pas au retour de la fonction.
	return &fluxAnnulable{ReadCloser: resp.Body, annule: annule}, nil
}

type fluxAnnulable struct {
	io.ReadCloser
	annule context.CancelFunc
}

func (f *fluxAnnulable) Close() error {
	err := f.ReadCloser.Close()
	f.annule()
	return err
}

func (c *Client) poster(ctx context.Context, action string, corps interface{}, budget time.Duration, out interface{}) error {
	ctx, annule := context.WithTimeout(ctx, budget)
	defer annule()
	brut, err := json.Marshal(corps)
	if err != nil {
		return fmt.Errorf("%s: encodage: %w", action, err)
	}
	req, err := c.requete(ctx, http.MethodPost, action, nil, brut)
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	return c.executer(req, action, out)
}

func (c *Client) obtenir(ctx context.Context, action string, params map[string]string, budget time.Duration, out interface{}) error {
	ctx, annule := context.WithTimeout(ctx, budget)
	defer annule()
	req, err := c.requete(ctx, http.MethodGet, action, params, nil)
	if err != nil {
		return err
	}
	return c.executer(req, action, out)
}

func (c *Client) requete(ctx context.Context, methode, action string, params map[string]string, corps []byte) (*http.Request, error) {
	var lecteur io.Reader
	if corps != nil {
		lecteur = bytes.NewReader(corps)
	}
	req, err := http.NewRequestWithContext(ctx, methode, c.baseURL+"/index.php", lecteur)
	if err != nil {
		return nil, fmt.Errorf("%s: construction: %w", action, err)
	}
	q := req.URL.Query()
	q.Set("action", action)
	for k, v := range params {
		q.Set(k, v)
	}
	req.URL.RawQuery = q.Encode()
	req.Header.Set("Authorization", "Bearer "+c.token)
	req.Header.Set("Accept", "application/json")
	return req, nil
}

func (c *Client) executer(req *http.Request, action string, out interface{}) error {
	resp, err := c.http.Do(req)
	if err != nil {
		return fmt.Errorf("%s: %w", action, err)
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return c.erreurDepuis(resp)
	}
	brut, err := io.ReadAll(io.LimitReader(resp.Body, corpsMax))
	if err != nil {
		return fmt.Errorf("%s: lecture: %w", action, err)
	}
	var env enveloppe
	if err := json.Unmarshal(brut, &env); err != nil || env.Response == nil {
		// Une page HTML d'Apache ou une redirection de session arrive ici.
		// La traiter comme un resultat vide la ferait passer pour un
		// succes ; on echoue explicitement.
		return fmt.Errorf("%s: reponse hors contrat (enveloppe {code, response} attendue)", action)
	}
	if err := json.Unmarshal(env.Response, out); err != nil {
		return fmt.Errorf("%s: decodage du payload: %w", action, err)
	}
	return nil
}

func (c *Client) erreurDepuis(resp *http.Response) error {
	brut, _ := io.ReadAll(io.LimitReader(resp.Body, 64<<10))
	var env enveloppe
	if json.Unmarshal(brut, &env) == nil && env.Response != nil {
		var e erreurCorps
		if json.Unmarshal(env.Response, &e) == nil && e.Erreur != "" {
			return &ErreurMoteur{Code: e.Erreur, Message: e.Message}
		}
	}
	return &ErreurMoteur{
		Code:    "moteur_indisponible",
		Message: fmt.Sprintf("statut HTTP %d", resp.StatusCode),
	}
}
```

- [ ] **Step 5: Lancer le test et vérifier qu'il passe**

```
docker run --rm -v "$PWD":/src -w /src golang:1.24-alpine go test ./internal/hellodata/ -v
```

- [ ] **Step 6: Commiter**

Préfixe `feat(mcp-hellodata-service):`, sujet `add engine HTTP client`, corps bilingue :

> EN: Bearer client over the {code, response} envelope already used by the gateway's bddcatalog, with a separate time budget per endpoint so an exact count and a job status do not share the same patience. A non-JSON body, such as an Apache error page or a session redirect, fails explicitly instead of decoding to an empty result that would read as success. The CSV fetch returns a stream whose context is cancelled on Close, never a buffered body.
>
> FR: Client Bearer sur l'enveloppe {code, response} deja utilisee par le bddcatalog du gateway, avec un budget de temps distinct par endpoint pour qu'un comptage exact et un statut de job ne partagent pas la meme patience. Un corps non JSON, page d'erreur Apache ou redirection de session, echoue explicitement au lieu de se decoder en resultat vide qui passerait pour un succes. La recuperation du CSV rend un flux dont le contexte est annule a la fermeture, jamais un corps bufferise.

---

### Task B5: Les quatre outils et le `tools/list` variable

C'est ici que le garde-fou prend forme : `compter` et `echantillon` ne produisent rien de rapatriable en masse, `export_csv` est un acte séparé et journalisé. Et c'est ici que `tools/list` devient **variable selon l'appelant** — un non-autorisé reçoit une liste vide, donc son LLM n'invente pas d'explication sur un outil qu'il ne peut pas appeler.

**Files:**
- Create: `apps-microservices/mcp-hellodata-service/internal/tools/registry.go`
- Create: `apps-microservices/mcp-hellodata-service/internal/tools/handler.go`
- Create: `apps-microservices/mcp-hellodata-service/internal/tools/selection.go`
- Test: `apps-microservices/mcp-hellodata-service/internal/tools/handler_test.go`

**Interfaces:**
- Consumes: `acces.Acces` (B2), `filtre.Valider` (B3), `hellodata.Client` (B4), types `mcp` (B1)
- Produces:
  - `tools.Identite{Email, Role string}`
  - `tools.Nouveau(c *hellodata.Client, a *acces.Acces, publicURL string) *Handler`
  - `(*Handler).Traiter(ctx context.Context, id Identite, req mcp.Requete) mcp.Reponse`
  - `tools.Definitions() []mcp.Outil` — les 4 outils
  - Noms : `hellodata_compter`, `hellodata_echantillon`, `hellodata_export_csv`, `hellodata_export_statut`

- [ ] **Step 1: Écrire le test qui échoue**

```go
package tools

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"mcp-hellodata/internal/acces"
	"mcp-hellodata/internal/hellodata"
	"mcp-hellodata/internal/mcp"
)

func handler(t *testing.T, g http.HandlerFunc) *Handler {
	t.Helper()
	s := httptest.NewServer(g)
	t.Cleanup(s.Close)
	return Nouveau(hellodata.Nouveau(s.URL, "jeton"),
		acces.Nouveau("alice@example.test"), "https://mcp.example.test")
}

func req(methode string, params string) mcp.Requete {
	return mcp.Requete{JSONRPC: "2.0", ID: json.RawMessage(`1`),
		Methode: methode, Params: json.RawMessage(params)}
}

func outils(t *testing.T, r mcp.Reponse) []interface{} {
	t.Helper()
	b, _ := json.Marshal(r.Result)
	var out struct {
		Tools []interface{} `json:"tools"`
	}
	json.Unmarshal(b, &out)
	return out.Tools
}

func TestToolsList_VariableSelonLAppelant(t *testing.T) {
	h := handler(t, func(w http.ResponseWriter, r *http.Request) {})
	cas := []struct {
		nom    string
		id     Identite
		attend int
	}{
		{"admin voit les quatre outils", Identite{"dave@example.test", "admin"}, 4},
		{"autorise par liste voit les quatre", Identite{"alice@example.test", "readonly"}, 4},
		{"non autorise ne voit rien", Identite{"dave@example.test", "readonly"}, 0},
		{"sans identite ne voit rien", Identite{"", ""}, 0},
	}
	for _, c := range cas {
		t.Run(c.nom, func(t *testing.T) {
			got := outils(t, h.Traiter(context.Background(), c.id, req("tools/list", `{}`)))
			if len(got) != c.attend {
				t.Errorf("%d outils, attendu %d", len(got), c.attend)
			}
		})
	}
}

// Le masquage est du confort. La barriere, c'est le refus a l'appel :
// un outil non liste reste appelable directement.
func TestToolsCall_RefuseUnNonAutorise(t *testing.T) {
	appele := false
	h := handler(t, func(w http.ResponseWriter, r *http.Request) { appele = true })
	r := h.Traiter(context.Background(), Identite{"dave@example.test", "readonly"},
		req("tools/call", `{"name":"hellodata_compter","arguments":{"filtre":{"critere":"region","comparateur":"dans","valeur":[6]}}}`))
	if r.Error == nil {
		t.Fatal("attendu une erreur pour un appelant non autorise")
	}
	if appele {
		t.Error("le moteur ne doit pas etre appele pour un non autorise")
	}
}

func TestCompter_CheminNominal(t *testing.T) {
	h := handler(t, func(w http.ResponseWriter, r *http.Request) {
		io.WriteString(w, `{"code":200,"response":{"count":42,"exact":false,"plafonne":false,"depuis_cache":false}}`)
	})
	r := h.Traiter(context.Background(), Identite{"alice@example.test", "readonly"},
		req("tools/call", `{"name":"hellodata_compter","arguments":{"filtre":{"critere":"region","comparateur":"dans","valeur":[6]}}}`))
	if r.Error != nil {
		t.Fatalf("erreur inattendue: %+v", r.Error)
	}
	b, _ := json.Marshal(r.Result)
	if !strings.Contains(string(b), "42") {
		t.Errorf("resultat = %s", string(b))
	}
}

// Les bornes structurelles doivent refuser AVANT tout appel reseau.
func TestEchantillon_ArbreTropProfondRefuseAvantAppel(t *testing.T) {
	appele := false
	h := handler(t, func(w http.ResponseWriter, r *http.Request) { appele = true })
	profond := `{"critere":"region","comparateur":"dans","valeur":[6]}`
	for i := 0; i < 6; i++ {
		profond = `{"operateur":"ET","conditions":[` + profond + `]}`
	}
	r := h.Traiter(context.Background(), Identite{"alice@example.test", "readonly"},
		req("tools/call", `{"name":"hellodata_echantillon","arguments":{"filtre":`+profond+`}}`))
	if r.Error == nil || !strings.Contains(r.Error.Message, "arbre_trop_complexe") {
		t.Fatalf("attendu arbre_trop_complexe, obtenu %+v", r.Error)
	}
	if appele {
		t.Error("le moteur ne doit pas etre appele pour un arbre hors bornes")
	}
}

func TestEchantillon_PlafondDeTaille(t *testing.T) {
	h := handler(t, func(w http.ResponseWriter, r *http.Request) {
		io.WriteString(w, `{"code":200,"response":{"rows":[],"next_cursor":null,"has_more":false}}`)
	})
	r := h.Traiter(context.Background(), Identite{"alice@example.test", "readonly"},
		req("tools/call", `{"name":"hellodata_echantillon","arguments":{"filtre":{"critere":"a_siret","comparateur":"=","valeur":true},"taille":5000}}`))
	if r.Error == nil || !strings.Contains(r.Error.Message, "2000") {
		t.Fatalf("attendu un refus citant 2000, obtenu %+v", r.Error)
	}
}

// Sans le droit, une colonne restreinte ne doit meme pas etre demandee au
// moteur : le refus se prend ici.
func TestEchantillon_ColonneRestreinteSansDroit(t *testing.T) {
	appele := false
	h := handler(t, func(w http.ResponseWriter, r *http.Request) { appele = true })
	r := h.Traiter(context.Background(), Identite{"alice@example.test", "readonly"},
		req("tools/call", `{"name":"hellodata_echantillon","arguments":{"filtre":{"critere":"a_siret","comparateur":"=","valeur":true},"colonnes":["email"]}}`))
	if r.Error == nil || !strings.Contains(r.Error.Message, "colonne_restreinte") {
		t.Fatalf("attendu colonne_restreinte, obtenu %+v", r.Error)
	}
	if appele {
		t.Error("le moteur ne doit pas etre appele")
	}
}

// LE test du proxy : l'URL rendue au LLM pointe le wrapper, jamais le BO.
func TestExportStatut_LUrlPointeLeWrapper(t *testing.T) {
	var urlMoteur string
	h := handler(t, func(w http.ResponseWriter, r *http.Request) {
		urlMoteur = "http://" + r.Host
		io.WriteString(w, `{"code":200,"response":{"state":"termine","lignes_ecrites":1234,"handle":"deadbeefdeadbeefdeadbeefdeadbeef"}}`)
	})
	r := h.Traiter(context.Background(), Identite{"alice@example.test", "readonly"},
		req("tools/call", `{"name":"hellodata_export_statut","arguments":{"job_id":"deadbeefdeadbeefdeadbeefdeadbeef"}}`))
	if r.Error != nil {
		t.Fatalf("erreur inattendue: %+v", r.Error)
	}
	b, _ := json.Marshal(r.Result)
	if !strings.Contains(string(b), "https://mcp.example.test/download/deadbeefdeadbeefdeadbeefdeadbeef") {
		t.Errorf("l URL rendue doit pointer le wrapper, obtenu %s", string(b))
	}
	if urlMoteur != "" && strings.Contains(string(b), urlMoteur) {
		t.Errorf("l URL du moteur a fuite dans la reponse: %s", string(b))
	}
}

func TestMethodeInconnue(t *testing.T) {
	h := handler(t, func(w http.ResponseWriter, r *http.Request) {})
	r := h.Traiter(context.Background(), Identite{"dave@example.test", "admin"}, req("resources/list", `{}`))
	if r.Error == nil || r.Error.Code != mcp.CodeMethodeInconnue {
		t.Fatalf("attendu CodeMethodeInconnue, obtenu %+v", r.Error)
	}
}

func TestInitialize_RepondSansIdentite(t *testing.T) {
	h := handler(t, func(w http.ResponseWriter, r *http.Request) {})
	r := h.Traiter(context.Background(), Identite{}, req("initialize", `{}`))
	if r.Error != nil {
		t.Fatalf("initialize doit repondre meme sans identite: %+v", r.Error)
	}
}
```

- [ ] **Step 2: Lancer le test et vérifier qu'il échoue**

```
docker run --rm -v "$PWD":/src -w /src golang:1.24-alpine go test ./internal/tools/
```

- [ ] **Step 3: Écrire le registre des outils**

`internal/tools/registry.go` :

```go
package tools

import "mcp-hellodata/internal/mcp"

// TailleMax et TailleDefaut bornent la lecture. 2000 est le plafond de la
// spec ; 50 est un echantillon, pas une extraction.
const (
	TailleMax     = 2000
	TailleDefaut  = 50
)

// schemaFiltre decrit l'arbre imbrique. La recursion passe par $ref sur
// la definition, ce que les clients MCP savent lire.
func schemaFiltre() map[string]interface{} {
	return map[string]interface{}{
		"$ref": "#/definitions/noeud",
		"definitions": map[string]interface{}{
			"noeud": map[string]interface{}{
				"type":        "object",
				"description": "Soit un groupe {operateur, conditions}, soit une feuille {critere, comparateur, valeur}.",
				"properties": map[string]interface{}{
					"operateur": map[string]interface{}{
						"type": "string", "enum": []string{"ET", "OU", "NON"},
						"description": "NON est unaire : exactement une condition.",
					},
					"conditions": map[string]interface{}{
						"type":     "array",
						"items":    map[string]interface{}{"$ref": "#/definitions/noeud"},
						"minItems": 1, "maxItems": 20,
					},
					"critere":     map[string]interface{}{"type": "string"},
					"comparateur": map[string]interface{}{"type": "string"},
					"valeur":      map[string]interface{}{},
				},
			},
		},
	}
}

func objet(props map[string]interface{}, requis ...string) map[string]interface{} {
	return map[string]interface{}{"type": "object", "properties": props, "required": requis}
}

func Definitions() []mcp.Outil {
	colonnes := map[string]interface{}{
		"type":        "array",
		"items":       map[string]interface{}{"type": "string"},
		"description": "Colonnes a restituer. email et mobile exigent le role admin.",
	}
	blocage := map[string]interface{}{
		"type": "integer", "enum": []int{1, 2, 3, 4, 5, 7, 8},
		"description": "Dedoublonnage : 1 aucun, 2 ou 3 par SIREN, 4/5/7/8 par SIRET.",
	}
	return []mcp.Outil{
		{
			Nom: "hellodata_compter",
			Description: "Compte les acheteurs correspondant a un arbre de filtres. " +
				"Approche par defaut et plafonne a 10000, ce qui suffit pour affiner un ciblage " +
				"et repond en quelques secondes ; exact=true rend le compte reel mais peut prendre " +
				"plus d'une minute. C'est l'appel a repeter pour affiner, avant tout echantillon.",
			SchemaEntre: objet(map[string]interface{}{
				"filtre":       schemaFiltre(),
				"exact":        map[string]interface{}{"type": "boolean", "default": false},
				"type_blocage": blocage,
			}, "filtre"),
		},
		{
			Nom: "hellodata_echantillon",
			Description: "Lit les acheteurs correspondant au filtre, page par page. " +
				"Maximum 2000 lignes par appel, 50 par defaut. Pour la page suivante, repasser " +
				"next_cursor dans cursor. Pour recuperer l'integralite d'une selection volumineuse, " +
				"utiliser hellodata_export_csv plutot que de boucler ici.",
			SchemaEntre: objet(map[string]interface{}{
				"filtre":   schemaFiltre(),
				"colonnes": colonnes,
				"taille": map[string]interface{}{
					"type": "integer", "minimum": 1, "maximum": TailleMax, "default": TailleDefaut,
				},
				"cursor":       map[string]interface{}{"type": "integer"},
				"type_blocage": blocage,
			}, "filtre"),
		},
		{
			Nom: "hellodata_export_csv",
			Description: "Demarre l'extraction complete de la selection dans un fichier CSV. " +
				"Rend un job_id ; interroger hellodata_export_statut pour obtenir le lien. " +
				"Cet appel produit un fichier de donnees personnelles et est journalise nominativement : " +
				"ne l'utiliser que sur demande explicite, jamais pour explorer.",
			SchemaEntre: objet(map[string]interface{}{
				"filtre":       schemaFiltre(),
				"colonnes":     colonnes,
				"type_blocage": blocage,
			}, "filtre"),
		},
		{
			Nom: "hellodata_export_statut",
			Description: "Etat d'un export. Quand state vaut termine, rend l'URL de telechargement. " +
				"Les etats possibles sont en_attente, en_cours, termine, echec.",
			SchemaEntre: objet(map[string]interface{}{
				"job_id": map[string]interface{}{"type": "string"},
			}, "job_id"),
		},
	}
}
```

- [ ] **Step 4: Écrire le handler**

`internal/tools/handler.go` :

```go
package tools

import (
	"context"
	"encoding/json"

	"mcp-hellodata/internal/acces"
	"mcp-hellodata/internal/hellodata"
	"mcp-hellodata/internal/mcp"
)

// Identite est ce que le gateway injecte en X-End-User-Email et
// X-End-User-Role. Les deux champs vides signifient "on ignore qui
// appelle", ce qui vaut refus — pas confiance.
type Identite struct {
	Email string
	Role  string
}

type Handler struct {
	client    *hellodata.Client
	acces     *acces.Acces
	publicURL string
}

func Nouveau(c *hellodata.Client, a *acces.Acces, publicURL string) *Handler {
	return &Handler{client: c, acces: a, publicURL: publicURL}
}

func (h *Handler) Traiter(ctx context.Context, id Identite, req mcp.Requete) mcp.Reponse {
	switch req.Methode {
	case "initialize":
		// initialize ne divulgue rien et doit repondre meme sans identite,
		// sinon aucun client ne peut se connecter pour decouvrir qu'il n'a
		// pas acces.
		return mcp.OK(req.ID, map[string]interface{}{
			"protocolVersion": "2025-03-26",
			"capabilities":    map[string]interface{}{"tools": map[string]interface{}{}},
			"serverInfo":      map[string]interface{}{"name": "mcp-hellodata", "version": "1.0.0"},
		})

	case "tools/list":
		// Liste variable selon l'appelant : un non autorise ne voit rien,
		// donc son LLM n'essaie pas d'appeler ce qu'il ne peut pas obtenir.
		if !h.acces.Autorise(id.Email, id.Role) {
			return mcp.OK(req.ID, map[string]interface{}{"tools": []mcp.Outil{}})
		}
		return mcp.OK(req.ID, map[string]interface{}{"tools": Definitions()})

	case "tools/call":
		// Le masquage de tools/list est du confort. La barriere est ici :
		// un outil non liste reste appelable directement.
		if !h.acces.Autorise(id.Email, id.Role) {
			return mcp.Echec(req.ID, mcp.CodeParamsInvalides,
				"acces_refuse: ce service est reserve aux administrateurs et aux utilisateurs autorises")
		}
		var p struct {
			Name      string          `json:"name"`
			Arguments json.RawMessage `json:"arguments"`
		}
		if err := json.Unmarshal(req.Params, &p); err != nil {
			return mcp.Echec(req.ID, mcp.CodeParamsInvalides, "params illisibles: "+err.Error())
		}
		return h.appeler(ctx, id, req.ID, p.Name, p.Arguments)
	}
	return mcp.Echec(req.ID, mcp.CodeMethodeInconnue, "methode inconnue: "+req.Methode)
}
```

- [ ] **Step 5: Écrire les quatre outils**

`internal/tools/selection.go` :

```go
package tools

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log"

	"mcp-hellodata/internal/filtre"
	"mcp-hellodata/internal/hellodata"
	"mcp-hellodata/internal/mcp"
)

// colonnesRestreintes reflete requete.php cote moteur. Le refus se prend
// ici pour eviter un aller-retour reseau qui echouerait de toute facon.
var colonnesRestreintes = map[string]bool{"email": true, "mobile": true}

type argsCommuns struct {
	Filtre      json.RawMessage `json:"filtre"`
	Colonnes    []string        `json:"colonnes"`
	Taille      int             `json:"taille"`
	Cursor      *int            `json:"cursor"`
	TypeBlocage int             `json:"type_blocage"`
	Exact       bool            `json:"exact"`
	JobID       string          `json:"job_id"`
}

func (h *Handler) appeler(ctx context.Context, id Identite, rpcID json.RawMessage, nom string, brut json.RawMessage) mcp.Reponse {
	var a argsCommuns
	if len(brut) > 0 {
		if err := json.Unmarshal(brut, &a); err != nil {
			return mcp.Echec(rpcID, mcp.CodeParamsInvalides, "arguments illisibles: "+err.Error())
		}
	}
	admin := h.acces.EstAdmin(id.Role)

	switch nom {
	case "hellodata_compter":
		d, errRep := h.demande(rpcID, a, admin, false)
		if errRep != nil {
			return *errRep
		}
		d.Exact = a.Exact
		res, err := h.client.Compter(ctx, d)
		if err != nil {
			return erreurMoteur(rpcID, err)
		}
		return contenu(rpcID, res)

	case "hellodata_echantillon":
		if a.Taille < 0 || a.Taille > TailleMax {
			return mcp.Echec(rpcID, mcp.CodeParamsInvalides,
				fmt.Sprintf("taille_invalide: %d hors bornes 1..%d", a.Taille, TailleMax))
		}
		d, errRep := h.demande(rpcID, a, admin, true)
		if errRep != nil {
			return *errRep
		}
		if d.Taille == 0 {
			d.Taille = TailleDefaut
		}
		d.Cursor = a.Cursor
		res, err := h.client.Echantillon(ctx, d)
		if err != nil {
			return erreurMoteur(rpcID, err)
		}
		return contenu(rpcID, res)

	case "hellodata_export_csv":
		d, errRep := h.demande(rpcID, a, admin, true)
		if errRep != nil {
			return *errRep
		}
		d.Demandeur = id.Email
		res, err := h.client.DemarrerExport(ctx, d)
		if err != nil {
			return erreurMoteur(rpcID, err)
		}
		// La liste statique ne fournit aucune trace d'audit. Cette ligne
		// est la seule qui existera sur une extraction de donnees
		// personnelles.
		log.Printf("[hellodata] export demarre job=%s demandeur=%s", res.JobID, id.Email)
		return contenu(rpcID, res)

	case "hellodata_export_statut":
		if a.JobID == "" {
			return mcp.Echec(rpcID, mcp.CodeParamsInvalides, "job_id requis")
		}
		res, err := h.client.StatutExport(ctx, a.JobID)
		if err != nil {
			return erreurMoteur(rpcID, err)
		}
		sortie := map[string]interface{}{
			"state": res.State, "lignes": res.LignesEcrites,
		}
		if res.Erreur != "" {
			sortie["erreur"] = res.Erreur
		}
		// L'URL pointe le wrapper, JAMAIS le moteur : aucune URL du BO ne
		// doit circuler, et le telechargement doit passer par notre auth.
		if res.State == "termine" && res.Handle != "" {
			sortie["url"] = h.publicURL + "/download/" + res.Handle
		}
		return contenu(rpcID, sortie)
	}
	return mcp.Echec(rpcID, mcp.CodeParamsInvalides, "outil inconnu: "+nom)
}

// demande valide la forme de l'arbre et les colonnes AVANT tout appel
// reseau : un refus doit etre immediat et porter un message que le LLM
// peut corriger.
func (h *Handler) demande(rpcID json.RawMessage, a argsCommuns, admin, avecColonnes bool) (hellodata.Demande, *mcp.Reponse) {
	if len(a.Filtre) == 0 {
		r := mcp.Echec(rpcID, mcp.CodeParamsInvalides, "filtre requis")
		return hellodata.Demande{}, &r
	}
	var n filtre.Noeud
	if err := json.Unmarshal(a.Filtre, &n); err != nil {
		r := mcp.Echec(rpcID, mcp.CodeParamsInvalides, "filtre illisible: "+err.Error())
		return hellodata.Demande{}, &r
	}
	if _, err := filtre.Valider(n); err != nil {
		r := mcp.Echec(rpcID, mcp.CodeParamsInvalides, err.Error())
		return hellodata.Demande{}, &r
	}
	if avecColonnes && !admin {
		for _, c := range a.Colonnes {
			if colonnesRestreintes[c] {
				r := mcp.Echec(rpcID, mcp.CodeParamsInvalides,
					"colonne_restreinte: '"+c+"' exige le role admin")
				return hellodata.Demande{}, &r
			}
		}
	}
	return hellodata.Demande{
		Filtre:      a.Filtre,
		Colonnes:    a.Colonnes,
		Taille:      a.Taille,
		TypeBlocage: a.TypeBlocage,
		Restreintes: admin,
	}, nil
}

func contenu(rpcID json.RawMessage, v interface{}) mcp.Reponse {
	b, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		return mcp.Echec(rpcID, mcp.CodeErreurInterne, "encodage du resultat")
	}
	return mcp.OK(rpcID, map[string]interface{}{
		"content": []map[string]interface{}{{"type": "text", "text": string(b)}},
	})
}

// erreurMoteur conserve le code stable du moteur : c'est ce que le LLM lit
// pour corriger son appel. Une erreur reseau devient un code generique,
// jamais un message technique brut.
func erreurMoteur(rpcID json.RawMessage, err error) mcp.Reponse {
	var em *hellodata.ErreurMoteur
	if errors.As(err, &em) {
		return mcp.Echec(rpcID, mcp.CodeParamsInvalides, em.Code+": "+em.Message)
	}
	log.Printf("[hellodata] appel moteur en echec: %v", err)
	return mcp.Echec(rpcID, mcp.CodeErreurInterne, "moteur_indisponible: reessayer plus tard")
}
```

- [ ] **Step 6: Lancer le test et vérifier qu'il passe**

```
docker run --rm -v "$PWD":/src -w /src golang:1.24-alpine go test ./internal/tools/ -v
```

- [ ] **Step 7: Commiter**

Préfixe `feat(mcp-hellodata-service):`, sujet `add the four selection tools`, corps bilingue :

> EN: Four tools with a per-caller tools/list: an unauthorised caller sees an empty list so its model does not invent reasons about a tool it cannot use. Hiding is comfort, the barrier is the refusal on tools/call, which is tested to prove the engine is never reached. Structural tree bounds, the 2000-row cap and restricted columns all refuse before any network call, and export_statut returns a wrapper URL so no BO URL ever circulates.
>
> FR: Quatre outils avec un tools/list variable selon l'appelant : un non autorise recoit une liste vide, pour que son modele n'invente pas d'explication sur un outil inutilisable. Le masquage est du confort, la barriere est le refus a tools/call, verifie par un test qui prouve que le moteur n'est jamais atteint. Les bornes structurelles de l'arbre, le plafond de 2000 lignes et les colonnes restreintes refusent tous avant le moindre appel reseau, et export_statut rend une URL du wrapper pour qu'aucune URL du BO ne circule.

---

### Task B6: Proxy de téléchargement et transport HTTP

**Files:**
- Create: `apps-microservices/mcp-hellodata-service/internal/download/proxy.go`
- Create: `apps-microservices/mcp-hellodata-service/internal/transport/http.go`
- Create: `apps-microservices/mcp-hellodata-service/cmd/server/main.go`
- Test: `apps-microservices/mcp-hellodata-service/internal/download/proxy_test.go`

**Interfaces:**
- Consumes: `hellodata.Client` (B4), `acces.Acces` (B2), `tools.Handler` (B5)
- Produces: `download.Nouveau(c *hellodata.Client, a *acces.Acces) http.Handler` monté sur `/download/`, `transport.IdentiteDepuis(r *http.Request) tools.Identite`

- [ ] **Step 1: Écrire le test qui échoue**

```go
package download

import (
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"mcp-hellodata/internal/acces"
	"mcp-hellodata/internal/hellodata"
)

func monter(t *testing.T, g http.HandlerFunc) http.Handler {
	t.Helper()
	s := httptest.NewServer(g)
	t.Cleanup(s.Close)
	return Nouveau(hellodata.Nouveau(s.URL, "jeton"), acces.Nouveau("alice@example.test"))
}

func appel(h http.Handler, chemin, email, role string) *httptest.ResponseRecorder {
	r := httptest.NewRequest(http.MethodGet, chemin, nil)
	r.Header.Set("X-End-User-Email", email)
	r.Header.Set("X-End-User-Role", role)
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	return w
}

func TestTelechargement_Autorise(t *testing.T) {
	h := monter(t, func(w http.ResponseWriter, r *http.Request) {
		io.WriteString(w, "id;ville\n1;Rennes\n")
	})
	w := appel(h, "/download/deadbeefdeadbeefdeadbeefdeadbeef", "alice@example.test", "readonly")
	if w.Code != http.StatusOK {
		t.Fatalf("code = %d", w.Code)
	}
	if !strings.Contains(w.Body.String(), "Rennes") {
		t.Errorf("corps = %q", w.Body.String())
	}
	if ct := w.Header().Get("Content-Type"); !strings.Contains(ct, "text/csv") {
		t.Errorf("Content-Type = %q", ct)
	}
}

func TestTelechargement_Refus(t *testing.T) {
	appeleMoteur := false
	h := monter(t, func(w http.ResponseWriter, r *http.Request) { appeleMoteur = true })
	cas := []struct{ nom, email, role string }{
		{"non autorise", "dave@example.test", "readonly"},
		{"sans identite", "", ""},
	}
	for _, c := range cas {
		t.Run(c.nom, func(t *testing.T) {
			appeleMoteur = false
			w := appel(h, "/download/deadbeefdeadbeefdeadbeefdeadbeef", c.email, c.role)
			if w.Code != http.StatusForbidden {
				t.Errorf("code = %d, attendu 403", w.Code)
			}
			if appeleMoteur {
				t.Error("le moteur ne doit pas etre appele")
			}
		})
	}
}

// Le handle vient du reseau : une traversee de chemin ne doit pas
// atteindre le moteur.
func TestTelechargement_HandleInvalide(t *testing.T) {
	appeleMoteur := false
	h := monter(t, func(w http.ResponseWriter, r *http.Request) { appeleMoteur = true })
	for _, mauvais := range []string{"../../etc/passwd", "pas-hexa", "", "DEADBEEFDEADBEEFDEADBEEFDEADBEEF"} {
		w := appel(h, "/download/"+mauvais, "alice@example.test", "readonly")
		if w.Code != http.StatusBadRequest && w.Code != http.StatusNotFound {
			t.Errorf("handle %q: code = %d, attendu 400 ou 404", mauvais, w.Code)
		}
	}
	if appeleMoteur {
		t.Error("un handle invalide ne doit jamais atteindre le moteur")
	}
}

// L'URL du moteur ne doit jamais apparaitre dans une reponse d'erreur.
func TestTelechargement_PasDeFuiteDUrlMoteur(t *testing.T) {
	s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNotFound)
		io.WriteString(w, `{"code":404,"response":{"erreur":"export_indisponible","message":"absent"}}`)
	}))
	defer s.Close()
	h := Nouveau(hellodata.Nouveau(s.URL, "jeton"), acces.Nouveau("alice@example.test"))
	w := appel(h, "/download/deadbeefdeadbeefdeadbeefdeadbeef", "alice@example.test", "readonly")
	if strings.Contains(w.Body.String(), s.URL) {
		t.Errorf("l URL du moteur a fuite: %q", w.Body.String())
	}
}
```

- [ ] **Step 2: Lancer le test et vérifier qu'il échoue**

```
docker run --rm -v "$PWD":/src -w /src golang:1.24-alpine go test ./internal/download/
```

- [ ] **Step 3: Écrire le proxy**

`internal/download/proxy.go` :

```go
// Package download sert le CSV au client sans jamais exposer le moteur.
//
// Le fichier vit hors racine web cote Ecritel et n'est accessible que par
// un endpoint authentifie. Ici, on le relaie derriere la meme autorisation
// que les outils : le lien rendu au LLM est une URL de ce service.
package download

import (
	"io"
	"log"
	"net/http"
	"regexp"
	"strings"

	"mcp-hellodata/internal/acces"
	"mcp-hellodata/internal/hellodata"
)

// Le handle vient du reseau. Liste blanche stricte plutot que nettoyage :
// on refuse tout ce qui n'est pas exactement 32 hexadecimaux minuscules.
var handleValide = regexp.MustCompile(`^[0-9a-f]{32}$`)

type proxy struct {
	client *hellodata.Client
	acces  *acces.Acces
}

func Nouveau(c *hellodata.Client, a *acces.Acces) http.Handler {
	return &proxy{client: c, acces: a}
}

func (p *proxy) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	email := r.Header.Get("X-End-User-Email")
	role := r.Header.Get("X-End-User-Role")
	if !p.acces.Autorise(email, role) {
		http.Error(w, "acces refuse", http.StatusForbidden)
		return
	}
	handle := strings.TrimPrefix(r.URL.Path, "/download/")
	if !handleValide.MatchString(handle) {
		http.Error(w, "handle invalide", http.StatusBadRequest)
		return
	}

	flux, err := p.client.RecupererExport(r.Context(), handle)
	if err != nil {
		// Le message du moteur peut porter son URL ou un detail
		// d'implementation : on journalise, on ne relaie pas.
		log.Printf("[hellodata] download handle=%s demandeur=%s erreur=%v", handle, email, err)
		http.Error(w, "export indisponible", http.StatusNotFound)
		return
	}
	defer flux.Close()

	log.Printf("[hellodata] download handle=%s demandeur=%s", handle, email)
	w.Header().Set("Content-Type", "text/csv; charset=utf-8")
	w.Header().Set("Content-Disposition", `attachment; filename="selection-`+handle+`.csv"`)
	if _, err := io.Copy(w, flux); err != nil {
		// L'en-tete est deja parti : on ne peut plus changer le statut,
		// seulement tracer la coupure.
		log.Printf("[hellodata] download handle=%s interrompu: %v", handle, err)
	}
}
```

- [ ] **Step 4: Écrire le transport et le point d'entrée**

`internal/transport/http.go` :

```go
package transport

import (
	"encoding/json"
	"net/http"

	"mcp-hellodata/internal/mcp"
	"mcp-hellodata/internal/tools"
)

// Plafond du corps JSON-RPC entrant, aligne sur celui du moteur.
const corpsMax = 256 << 10

// IdentiteDepuis lit ce que le gateway injecte. Un en-tete absent donne
// une chaine vide, qui vaut refus en aval : l'absence n'est pas une
// confiance implicite.
func IdentiteDepuis(r *http.Request) tools.Identite {
	return tools.Identite{
		Email: r.Header.Get("X-End-User-Email"),
		Role:  r.Header.Get("X-End-User-Role"),
	}
}

func MCP(h *tools.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			w.Header().Set("Allow", "POST")
			http.Error(w, "methode non autorisee", http.StatusMethodNotAllowed)
			return
		}
		var req mcp.Requete
		if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, corpsMax)).Decode(&req); err != nil {
			ecrire(w, mcp.Echec(nil, mcp.CodeErreurParsing, "JSON illisible"))
			return
		}
		ecrire(w, h.Traiter(r.Context(), IdentiteDepuis(r), req))
	})
}

func ecrire(w http.ResponseWriter, rep mcp.Reponse) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(rep)
}
```

`cmd/server/main.go` :

```go
package main

import (
	"fmt"
	"log"
	"net/http"

	"mcp-hellodata/internal/acces"
	"mcp-hellodata/internal/config"
	"mcp-hellodata/internal/download"
	"mcp-hellodata/internal/hellodata"
	"mcp-hellodata/internal/tools"
	"mcp-hellodata/internal/transport"
)

func main() {
	c, err := config.Charger()
	if err != nil {
		log.Fatalf("configuration: %v", err)
	}
	client := hellodata.Nouveau(c.BaseURL, c.Token)
	autorisation := acces.Nouveau(c.EmailsAutorises)
	h := tools.Nouveau(client, autorisation, c.PublicURL)

	mux := http.NewServeMux()
	mux.Handle("/mcp", transport.MCP(h))
	mux.Handle("/download/", download.Nouveau(client, autorisation))
	// /health ne porte aucune donnee metier : c'est le seul endpoint qui
	// repond sans identite, et il doit le rester.
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		fmt.Fprint(w, `{"status":"ok"}`)
	})

	adresse := fmt.Sprintf(":%d", c.Port)
	log.Printf("mcp-hellodata-service ecoute sur %s", adresse)
	log.Fatal(http.ListenAndServe(adresse, mux))
}
```

- [ ] **Step 5: Lancer toute la suite**

```
docker run --rm -v "$PWD":/src -w /src golang:1.24-alpine go test ./... -v
docker run --rm -v "$PWD":/src -w /src golang:1.24-alpine go vet ./...
```

Attendu : tous les paquets passent, `go vet` sans signalement.

- [ ] **Step 6: Commiter**

Préfixe `feat(mcp-hellodata-service):`, sujet `add download proxy and HTTP transport`, corps bilingue :

> EN: The CSV is relayed behind the same authorisation as the tools, so the engine URL never reaches a client, not even in an error message. The handle is matched against a strict hex allowlist rather than sanitised, and an invalid one never reaches the engine. Health is the only endpoint answering without an identity and carries no business data.
>
> FR: Le CSV est relaye derriere la meme autorisation que les outils, si bien que l'URL du moteur n'atteint jamais un client, pas meme dans un message d'erreur. Le handle est compare a une liste blanche hexadecimale stricte plutot que nettoye, et un handle invalide n'atteint jamais le moteur. Health est le seul endpoint repondant sans identite et ne porte aucune donnee metier.

---

### Task B7: Conteneurisation et documentation de service

**Files:**
- Create: `apps-microservices/mcp-hellodata-service/Dockerfile`
- Create: `apps-microservices/mcp-hellodata-service/CLAUDE.md`
- Modify: `docker-compose.yml` (ajout du service dans le profil `mcp`)

**Interfaces:**
- Consumes: B1–B6
- Produces: l'image et l'entrée de composition. **`expose:` et jamais `ports:`**

- [ ] **Step 1: Écrire le Dockerfile**

Construction multi-étages, binaire statique, image finale Alpine, utilisateur non root (`.claude/rules/docker-security.md`).

```dockerfile
FROM golang:1.24-alpine AS builder
WORKDIR /build
COPY apps-microservices/mcp-hellodata-service/go.mod ./
RUN go mod download
COPY apps-microservices/mcp-hellodata-service/ ./
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o /bin/mcp-hellodata ./cmd/server

FROM alpine:3.20
RUN apk add --no-cache ca-certificates \
 && adduser -D -u 10001 nonroot
COPY --from=builder /bin/mcp-hellodata /bin/mcp-hellodata
USER nonroot
EXPOSE 8597
ENTRYPOINT ["/bin/mcp-hellodata"]
```

- [ ] **Step 2: Ajouter le service à `docker-compose.yml`**

À insérer à côté des autres services du profil `mcp` :

```yaml
  # ── MCP HelloData Service ───────────────────────────────────────────────
  mcp-hellodata-service:
    build:
      context: .
      dockerfile: ./apps-microservices/mcp-hellodata-service/Dockerfile
    container_name: mcp-hellodata-service
    profiles: [ "mcp" ]
    restart: unless-stopped
    # expose, PAS ports. L'autorisation de ce service repose sur des
    # en-tetes non signes : si un tiers peut joindre 8597 directement,
    # X-End-User-Role: admin est forgeable et la liste ne protege rien.
    # mcp-leexi-service publie 8589:8589 ; cette divergence est voulue.
    expose:
      - "8597"
    environment:
      - MCP_PORT=8597
      - HELLODATA_BASE_URL=${HELLODATA_BASE_URL}
      - HELLODATA_TOKEN=${HELLODATA_TOKEN}
      - HELLODATA_PUBLIC_URL=${HELLODATA_PUBLIC_URL}
      # Adresses separees par des virgules. JAMAIS de valeur ici ni dans
      # un .env.example : le depot est public.
      - HELLODATA_ALLOWED_EMAILS=${HELLODATA_ALLOWED_EMAILS}
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost:8597/health"]
      interval: 30s
      timeout: 5s
      retries: 3
    networks:
      - services-net
    logging: *logging_defaults
```

- [ ] **Step 3: Écrire le `CLAUDE.md` du service**

Sur le modèle de `apps-microservices/mcp-leexi-service/CLAUDE.md` : rôle, pile technique, build et run, arborescence, variables d'environnement, et une section **Accès** qui énonce que l'autorisation se décide ici et non dans le gateway, avec le renvoi à la spec § 7.1.

- [ ] **Step 4: Construire et vérifier**

Depuis la racine du dépôt :

```
docker compose --profile mcp build mcp-hellodata-service
```

Puis vérifier qu'aucun port n'est publié :

```
grep -A4 "mcp-hellodata-service:" docker-compose.yml | grep -q "ports:" && echo "STOP: ports publie" || echo "OK: expose seulement"
```

Attendu : `OK`.

- [ ] **Step 5: Vérifier une dernière fois l'absence d'adresse réelle**

```
grep -rn "hellopro.fr" apps-microservices/mcp-hellodata-service/ docker-compose.yml
```

Attendu : aucune correspondance dans les fichiers du service.

- [ ] **Step 6: Commiter**

Préfixe `feat(mcp-hellodata-service):`, sujet `containerise the service`, corps bilingue :

> EN: Multi-stage build to a non-root Alpine image, and a compose entry in the mcp profile that uses expose rather than ports. That divergence from mcp-leexi-service is deliberate: this service authorises on unsigned headers, so reachability from outside the internal network would make the allowlist meaningless.
>
> FR: Construction multi-etages vers une image Alpine non root, et une entree de composition dans le profil mcp qui utilise expose plutot que ports. Cette divergence d'avec mcp-leexi-service est voulue : ce service autorise sur des en-tetes non signes, donc une joignabilite depuis l'exterieur du reseau interne rendrait la liste sans effet.

---

## Phase C — Gateway

> `internal/gateway/access_gate.go` **n'est pas modifié**. C'est le point du design : le prédicat fail-closed durci par les commits `e53e07df`, `bf44e7f0` et `58f13bf9` reste intact.

### Task C1: Injection de l'identité vers le backend hellodata

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/internal/gateway/scoped_gateway.go`
- Test: `apps-microservices/mcp-gateway-service/internal/gateway/hellodata_identity_test.go`

**Interfaces:**
- Consumes: `gatewayUserRole()` (déjà dans `access_gate.go`, même paquet, **non modifié**)
- Produces: constantes `hellodataToolPrefix = "hellodata"`, `EndUserEmailHeader`, `EndUserRoleHeader` · méthode `(*ScopedGateway).injectHellodataIdentity(ctx, headers)`

- [ ] **Step 1: Écrire le test qui échoue**

```go
package gateway

import (
	"context"
	"testing"

	"mcp-gateway/internal/scopetoken"
)

func TestRequestHeadersFor_HellodataInjecteIdentiteEtRole(t *testing.T) {
	sg := &ScopedGateway{gatewayUsers: stubUsers(map[string]string{"alice@example.test": "readonly"})}
	b := &BackendServer{ID: "hd", ToolPrefix: hellodataToolPrefix}
	ctx := context.WithValue(context.Background(), scopetoken.EndUserEmailContextKey, "alice@example.test")

	h := sg.requestHeadersFor(ctx, b)
	if h[EndUserEmailHeader] != "alice@example.test" {
		t.Errorf("%s = %q", EndUserEmailHeader, h[EndUserEmailHeader])
	}
	if h[EndUserRoleHeader] != "readonly" {
		t.Errorf("%s = %q", EndUserRoleHeader, h[EndUserRoleHeader])
	}
}

// Les autres backends ne doivent RIEN recevoir : on n'elargit pas la
// diffusion de l'identite au passage.
func TestRequestHeadersFor_IdentiteAbsentePourLesAutresBackends(t *testing.T) {
	sg := &ScopedGateway{gatewayUsers: stubUsers(map[string]string{"alice@example.test": "admin"})}
	b := &BackendServer{ID: "autre", ToolPrefix: "semrush"}
	ctx := context.WithValue(context.Background(), scopetoken.EndUserEmailContextKey, "alice@example.test")

	h := sg.requestHeadersFor(ctx, b)
	if _, ok := h[EndUserRoleHeader]; ok {
		t.Errorf("%s ne doit pas etre pose sur un backend non hellodata", EndUserRoleHeader)
	}
}

// Fail-closed a l'emission : une resolution de role en echec n'envoie
// AUCUN en-tete de role. En aval, une valeur par defaut deviendrait un
// role effectif.
func TestRequestHeadersFor_HellodataRoleNonResoluNEnvoieRien(t *testing.T) {
	cas := []struct {
		nom   string
		users gatewayUserFinder
	}{
		{"depot non cable", nil},
		{"email absent du depot", stubUsers(map[string]string{})},
		{"depot en erreur", stubUsersEnErreur()},
	}
	for _, c := range cas {
		t.Run(c.nom, func(t *testing.T) {
			sg := &ScopedGateway{gatewayUsers: c.users}
			b := &BackendServer{ID: "hd", ToolPrefix: hellodataToolPrefix}
			ctx := context.WithValue(context.Background(), scopetoken.EndUserEmailContextKey, "alice@example.test")

			h := sg.requestHeadersFor(ctx, b)
			if v, ok := h[EndUserRoleHeader]; ok {
				t.Errorf("%s = %q, attendu absent", EndUserRoleHeader, v)
			}
			if h[EndUserEmailHeader] != "alice@example.test" {
				t.Errorf("l email doit rester pose meme sans role")
			}
		})
	}
}

// Sans identite sur le contexte — token de scope, client_credentials,
// sonde de sante — rien n'est pose. Le backend refusera, c'est voulu.
func TestRequestHeadersFor_HellodataSansIdentite(t *testing.T) {
	sg := &ScopedGateway{gatewayUsers: stubUsers(map[string]string{})}
	b := &BackendServer{ID: "hd", ToolPrefix: hellodataToolPrefix}

	h := sg.requestHeadersFor(context.Background(), b)
	if _, ok := h[EndUserEmailHeader]; ok {
		t.Error("aucun en-tete d identite sans email sur le contexte")
	}
}
```

Les fonctions `stubUsers` et `stubUsersEnErreur` implémentent `gatewayUserFinder`. Si des équivalents existent déjà dans les tests du paquet (`scoped_gateway_test.go`), réutilise-les plutôt que d'en créer.

- [ ] **Step 2: Lancer le test et vérifier qu'il échoue**

```
cd apps-microservices/mcp-gateway-service
docker run --rm -v "$PWD":/src -w /src golang:1.24-alpine go test ./internal/gateway/ -run Hellodata
```

- [ ] **Step 3: Ajouter les constantes**

À côté de `leexiToolPrefix`, `ringoverToolPrefix` et `bddToolPrefix` dans `scoped_gateway.go` :

```go
// hellodataToolPrefix identifie le backend mcp-hellodata-service. Il
// recoit l'identite de l'utilisateur final parce que c'est LUI qui decide
// de l'autorisation : le gateway ne pose sur ce serveur qu'un min_role
// minimal, qui ecarte les chemins sans utilisateur.
const hellodataToolPrefix = "hellodata"

// En-tetes d'identite. X-End-User-Email existe deja en litteral sur le
// chemin Zoho (injectZohoIdentity) ; on le nomme ici et on remplace le
// litteral par la constante.
const (
	EndUserEmailHeader = "X-End-User-Email"
	EndUserRoleHeader  = "X-End-User-Role"
)
```

- [ ] **Step 4: Ajouter le `case` et la méthode d'injection**

Dans le `switch backend.ToolPrefix` de `requestHeadersFor`, après `case bddToolPrefix:` :

```go
		case hellodataToolPrefix:
			sg.injectHellodataIdentity(ctx, headers)
```

Et la méthode :

```go
// injectHellodataIdentity pose l'identite de l'utilisateur final pour
// mcp-hellodata-service, qui decide seul de l'autorisation (admin ou
// liste statique).
//
// Fail-closed a l'emission : quand le role ne peut pas etre resolu —
// depot non cable, erreur SQL, email sans ligne dans gateway_users — on
// n'envoie AUCUN en-tete de role. Jamais de valeur par defaut : en aval,
// une valeur par defaut deviendrait un role effectif.
//
// Sans email sur le contexte, rien n'est pose du tout. C'est le cas des
// tokens de scope, des grants client_credentials et des sondes de sante ;
// le backend refusera, et c'est le comportement voulu.
func (sg *ScopedGateway) injectHellodataIdentity(ctx context.Context, headers map[string]string) {
	email, ok := scopetoken.EndUserEmailFromContext(ctx)
	if !ok || email == "" {
		return
	}
	headers[EndUserEmailHeader] = email
	role, ok := gatewayUserRole(sg.gatewayUsers, email)
	if !ok {
		log.Printf("[scoped] hellodata: role non resolu pour %s — aucun en-tete de role envoye", email)
		return
	}
	headers[EndUserRoleHeader] = role
}
```

- [ ] **Step 5: Lancer les tests du paquet en entier**

Pas seulement les nouveaux : cette modification touche un fichier partagé.

```
docker run --rm -v "$PWD":/src -w /src golang:1.24-alpine go test ./internal/gateway/ -v
```

Attendu : tous les tests existants passent, y compris `TestScopeTokenPathLeavesEndUserEmailUnset`.

- [ ] **Step 6: Commiter**

Préfixe `feat(mcp-gateway-service):`, sujet `inject end-user identity for the hellodata backend`, corps bilingue :

> EN: One case in the requestHeadersFor switch posts X-End-User-Email and X-End-User-Role for the hellodata backend only, which decides authorisation itself. Emission is fail-closed: an unresolved role sends no role header at all, never a default, because downstream a default would become an effective role. access_gate.go is untouched, so the hardened predicate and its five call sites stay exactly as they are.
>
> FR: Un case dans le switch de requestHeadersFor pose X-End-User-Email et X-End-User-Role pour le seul backend hellodata, qui decide lui-meme de l'autorisation. L'emission est fail-closed : un role non resolu n'envoie aucun en-tete de role, jamais une valeur par defaut, parce qu'en aval une valeur par defaut deviendrait un role effectif. access_gate.go n'est pas touche, si bien que le predicat durci et ses cinq points d'appel restent exactement en l'etat.

---

### Task C2: `tools/list` en direct pour hellodata, avec repli sur liste vide

La divergence d'avec Zoho est le point de vigilance de cette tâche. `fetchZohoTools` se replie sur **le catalogue en cache** quand le live-fetch échoue, pour qu'une panne passagère ne vide pas la liste. Pour hellodata, ce repli serait une faille : un backend injoignable rendrait les outils visibles à tout le monde. Le repli est donc **la liste vide**. Copier le repli Zoho est l'erreur naturelle ; c'est pour ça qu'elle a son propre test.

**Files:**
- Modify: `apps-microservices/mcp-gateway-service/internal/gateway/scoped_gateway.go`
- Test: `apps-microservices/mcp-gateway-service/internal/gateway/hellodata_toolslist_test.go`

**Interfaces:**
- Consumes: C1
- Produces: `(*ScopedGateway).hellodataBackendsInScope() []*BackendServer` · `(*ScopedGateway).fetchHellodataTools(ctx, b) []mcp.Tool`

- [ ] **Step 1: Écrire le test qui échoue**

```go
package gateway

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
)

// Un backend injoignable ne doit PAS rendre les outils visibles. C'est la
// divergence deliberee d'avec fetchZohoTools, qui se replie sur le cache.
func TestFetchHellodataTools_BackendInjoignableRendListeVide(t *testing.T) {
	s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer s.Close()

	sg := &ScopedGateway{gatewayUsers: stubUsers(map[string]string{"alice@example.test": "admin"})}
	b := &BackendServer{ID: "hd", ToolPrefix: hellodataToolPrefix, MessageURL: s.URL}

	if got := sg.fetchHellodataTools(context.Background(), b); len(got) != 0 {
		t.Errorf("%d outils, attendu 0 sur backend injoignable", len(got))
	}
}

// Un backend qui repond une liste vide — appelant non autorise — rend
// bien zero outil, sans repli sur le cache.
func TestFetchHellodataTools_ListeVideRespectee(t *testing.T) {
	s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(`{"jsonrpc":"2.0","id":1,"result":{"tools":[]}}`))
	}))
	defer s.Close()

	sg := &ScopedGateway{gatewayUsers: stubUsers(map[string]string{"dave@example.test": "readonly"})}
	b := &BackendServer{ID: "hd", ToolPrefix: hellodataToolPrefix, MessageURL: s.URL}

	if got := sg.fetchHellodataTools(context.Background(), b); len(got) != 0 {
		t.Errorf("%d outils, attendu 0 pour un appelant non autorise", len(got))
	}
}
```

- [ ] **Step 2: Lancer le test et vérifier qu'il échoue**

```
docker run --rm -v "$PWD":/src -w /src golang:1.24-alpine go test ./internal/gateway/ -run Hellodata
```

- [ ] **Step 3: Écrire les deux méthodes**

```go
// hellodataBackendsInScope rend les backends hellodata autorises dans la
// portee courante. Ordre indefini.
func (sg *ScopedGateway) hellodataBackendsInScope(allowedIDs map[string]bool) []*BackendServer {
	var out []*BackendServer
	for _, s := range sg.registry.All() {
		if allowedIDs[s.ID] && s.ToolPrefix == hellodataToolPrefix {
			out = append(out, s)
		}
	}
	return out
}

// fetchHellodataTools interroge le backend avec l'identite de l'appelant.
// Le backend rend ses quatre outils a un autorise, une liste vide sinon.
//
// DIVERGENCE DELIBEREE d'avec fetchZohoTools : en cas d'echec, le repli
// est la LISTE VIDE, pas le catalogue en cache. Se replier sur le cache
// rendrait les outils visibles a tout le monde des que le backend est
// injoignable, ce qui est exactement ce que ce masquage doit empecher.
// Ne pas "harmoniser" avec le chemin Zoho.
func (sg *ScopedGateway) fetchHellodataTools(ctx context.Context, b *BackendServer) []mcp.Tool {
	headers := sg.requestHeadersFor(ctx, b)
	client := transport.NewBackendClientWithEndpoint(b.MessageURL, headers)
	liveTools, err := client.ListTools(ctx)
	if err != nil {
		log.Printf("[scoped] hellodata tools/list live-fetch backend=%s err=%v — liste vide (pas de repli sur le cache)", b.ID, err)
		return nil
	}
	if len(liveTools) == 0 {
		return nil
	}
	return sg.registry.MergedToolsFilteredWithTools(map[string]bool{b.ID: true}, sg.allowedTools)
}
```

- [ ] **Step 4: Brancher dans `handleToolsList`**

Au début de `handleToolsList`, juste après `allowedIDs := sg.allowedIDsMinusGated(ctx)`, retirer les backends hellodata de la fusion en cache et les traiter en direct. Les backends hellodata retirés de `allowedIDs` avant la branche Zoho : la logique Zoho existante n'est pas touchée.

```go
	// Backends hellodata : leur catalogue depend de l'appelant, donc il ne
	// peut pas venir du cache du registre. On les retire de la fusion et
	// on les interroge en direct.
	hdBackends := sg.hellodataBackendsInScope(allowedIDs)
	var hdTools []mcp.Tool
	if len(hdBackends) > 0 {
		sansHD := make(map[string]bool, len(allowedIDs))
		for id, ok := range allowedIDs {
			sansHD[id] = ok
		}
		for _, b := range hdBackends {
			delete(sansHD, b.ID)
			hdTools = append(hdTools, sg.fetchHellodataTools(ctx, b)...)
		}
		allowedIDs = sansHD
	}
```

Puis ajouter `hdTools` aux deux points de retour de la fonction, avant `sg.toolsListResp(...)` : `tools = append(tools, hdTools...)`. Il y a **trois** retours dans `handleToolsList` (chemin sans Zoho, chemin Zoho non configuré, chemin Zoho complet) — les trois doivent recevoir `hdTools`, sinon les outils disparaissent selon la configuration Zoho de l'appelant, ce qui serait incompréhensible à déboguer.

- [ ] **Step 5: Vérifier qu'aucun repli de `tools/call` n'est ajouté**

`handleToolsCall` porte un « Zoho fallback » qui route un nom d'outil inconnu vers le stub Zoho. **Aucun équivalent ne doit exister pour hellodata** : un nom inconnu doit rester inconnu. Vérifie par lecture, et lance la suite complète du paquet :

```
docker run --rm -v "$PWD":/src -w /src golang:1.24-alpine go test ./internal/gateway/ -v
docker run --rm -v "$PWD":/src -w /src golang:1.24-alpine go vet ./...
```

- [ ] **Step 6: Commiter**

Préfixe `feat(mcp-gateway-service):`, sujet `serve a per-caller tools list for hellodata`, corps bilingue :

> EN: The hellodata backend's catalogue depends on who is asking, so it is fetched live instead of merged from the registry cache, and added on all three return paths of handleToolsList so it does not vanish depending on the caller's Zoho configuration. The fallback on failure is the empty list, not the cache: falling back to the cache would reveal the tools to everyone whenever the backend is unreachable, which is what this hiding exists to prevent.
>
> FR: Le catalogue du backend hellodata depend de qui demande, il est donc recupere en direct plutot que fusionne depuis le cache du registre, et ajoute sur les trois chemins de retour de handleToolsList pour qu'il ne disparaisse pas selon la configuration Zoho de l'appelant. Le repli en cas d'echec est la liste vide, pas le cache : se replier sur le cache revelerait les outils a tout le monde des que le backend est injoignable, ce que ce masquage existe precisement pour empecher.

---

### Task C3: Enregistrement du backend et vérification de bout en bout

**Files:**
- Modify: base du gateway (ligne `mcp_servers`), via l'API d'administration
- Create: `docs/superpowers/plans/2026-09-21-mcp-hellodata-recette.md`

**Interfaces:**
- Consumes: A9, B7, C1, C2
- Produces: le service joignable par le LLM

- [ ] **Step 1: Enregistrer le serveur**

Via l'API d'administration du gateway, avec :

| Champ | Valeur |
|---|---|
| `tool_prefix` | `hellodata` — **exactement**, c'est la clé du dispatch de C1 et C2 |
| `message_url` | `http://mcp-hellodata-service:8597/mcp` (réseau Docker interne) |
| `min_role` | `readonly` |

`min_role = readonly` et non vide : `GateAllows` refuse quand aucun e-mail n'est sur le contexte, ce qui écarte les tokens de scope et les grants `client_credentials`. Un service qui exporte des coordonnées d'acheteurs n'a rien à faire derrière une authentification sans utilisateur.

- [ ] **Step 2: Recette — un admin voit et utilise les outils**

Avec un compte `admin`, via un client MCP passant par le gateway :
`tools/list` montre les 4 outils · `hellodata_compter` rend un nombre · `hellodata_echantillon` rend des lignes.

- [ ] **Step 3: Recette — un autorisé par liste, mais pas les colonnes restreintes**

Avec un compte `readonly` **présent** dans `HELLODATA_ALLOWED_EMAILS` : les 4 outils sont visibles, le comptage fonctionne, et `hellodata_echantillon` avec `colonnes: ["email"]` est **refusé** avec `colonne_restreinte`.

- [ ] **Step 4: Recette — un non autorisé ne voit rien**

Avec un compte `readonly` **absent** de la liste : `tools/list` ne montre **aucun** outil hellodata, et un appel direct à `hellodata_compter` est refusé.

C'est le contrôle négatif central du modèle d'accès. S'il échoue, **rien d'autre ne compte**.

- [ ] **Step 5: Recette — l'export de bout en bout**

`hellodata_export_csv` rend un `job_id` · `hellodata_export_statut` finit par rendre `state: termine` et une `url` · l'URL pointe **le wrapper**, pas le BO · elle télécharge bien le CSV · la même URL appelée par un utilisateur non autorisé rend **403**.

- [ ] **Step 6: Recette — l'isolation réseau (précondition 7)**

Depuis une machine hors du réseau Docker :

```
curl -s -o /dev/null -w '%{http_code}\n' --max-time 5 http://<hôte>:8597/health
```

Attendu : échec de connexion. Une réponse **invalide tout le modèle d'accès** : `X-End-User-Role: admin` serait forgeable. Dans ce cas, **retirer le serveur du gateway** jusqu'à correction.

- [ ] **Step 7: Écrire le compte rendu de recette et commiter**

Une ligne par étape : ce qui a été testé, avec quel compte, et le résultat observé. Les étapes 4 et 6 sont notées comme bloquantes si elles échouent.

Préfixe `docs(mcp-hellodata):`, sujet `record end-to-end acceptance run`, corps bilingue :

> EN: Acceptance run across the three caller shapes — admin, allowlisted readonly, unauthorised readonly — plus the export round trip and the network isolation check. The unauthorised case and the isolation check are the two that invalidate the whole access model if they fail.
>
> FR: Recette sur les trois formes d'appelant — admin, readonly autorise par liste, readonly non autorise — plus le cycle complet d'export et la verification d'isolation reseau. Le cas non autorise et la verification d'isolation sont les deux qui invalident tout le modele d'acces s'ils echouent.

---

## Récapitulatif des tâches

| # | Tâche | Livrable testable seul |
|---|---|---|
| 0 | Préconditions | Compte rendu des 11 vérifications |
| A1 | Validation structurelle de l'arbre | `arbre.php` + harnais |
| A2 | Liste blanche des critères | `criteres.php`, 23 critères |
| A3 | Compilateur | `compilateur.php` |
| A4 | Assemblage de la requête | `requete.php` |
| A5 | Coquille HTTP | `index.php`, `auth.php`, `reponse.php`, `bdd.php` |
| A6 | Comptage et cache | `actions/comptage.php`, `cache.php` |
| A7 | Échantillon | `actions/echantillon.php` |
| A8 | Export CSV | les cinq fichiers d'export |
| A9 | Déploiement Ecritel | Moteur en ligne |
| B1 | Squelette Go | `config`, `mcp` |
| B2 | Contrôle d'accès | `internal/acces` |
| B3 | Validation de l'arbre | `internal/filtre` |
| B4 | Client du moteur | `internal/hellodata` |
| B5 | Les 4 outils | `internal/tools` |
| B6 | Proxy et transport | `internal/download`, `internal/transport`, `main.go` |
| B7 | Conteneurisation | Dockerfile, compose, CLAUDE.md |
| C1 | Injection d'identité | `scoped_gateway.go` |
| C2 | `tools/list` en direct | `scoped_gateway.go` |
| C3 | Enregistrement et recette | Service joignable |

## Ce que ce plan ne couvre pas

Repris du § 11 de la spec, pour que les absences restent des choix :

- la très large majorité des 545 paramètres de l'écran BO ;
- la reproduction fidèle des `liason1..7` ;
- les critères fournisseur, opération emailing et le filtre profiling ;
- l'optimisation `INNER JOIN` pour la chaîne `ET` de premier niveau — elle dépend de la mesure de la Task 0 step 6 ;
- toute gestion dynamique des autorisations : table, écran d'administration, trace d'audit ;
- la correction des CSV devinables existants dans `/admin/hellodata/fichiers_exports/` ;
- les colonnes `fax`, `validite_email`, `chiffre_affaires`, `forme_juridique`, `code_insee`, `secteur_activite`, dont l'existence sur `acheteur` n'est pas confirmée.

### Écart assumé avec la spec § 4.3.4

La spec annonce **46 champs** de critères. Ce plan en livre **23**, et l'écart
n'est pas un oubli : les familles manquantes — volumétrie DI, comportement
emailing, rubrique, consentement — portent toutes sur des **tables liées
dont le schéma n'est pas confirmé** (Task 0 step 11). Les écrire
maintenant reviendrait à inventer des noms de colonnes.

Les 23 critères livrés reposent tous sur des colonnes vérifiées, et couvrent
la géographie, l'entreprise, le contact et les dates de fiche — de quoi
exercer l'ensemble de la chaîne de bout en bout.

**Ajouter les familles manquantes est une tâche de suite**, une fois le
schéma obtenu : la procédure est mécanique, une ligne par critère dans
`criteres_catalogue()` plus un cas de test, et le compilateur les accepte
sans modification puisque chaque feuille est une expression autonome. La
clé de jointure DI est déjà connue de `lancer_comptage_combine.php` :
`DI.id_societe = A.id_source_a`.

---

## Amendement du 2026-09-21 — chemin de déploiement réel

Décision de l'utilisateur, postérieure à la rédaction initiale : **deux
chemins de déploiement distincts, et non un seul**.

| Environnement | Mécanisme | Qui le fait |
|---|---|---|
| **BO de dev** | SFTP direct via `sftp-mcp/dev-write-prod` (écriture) et `sftp-mcp/dev-read-prod` (lecture) | L'agent, en autonomie |
| **BO de production** | **MEP** — paquet `site/` + `backup/`, skill `prepare-mep` | Le développeur, manuellement |

Vérifié le 2026-09-21 par `sftp_list_servers` : `dev-write-prod` porte bien
`env=dev, WRITABLE` ; `prod` et `front` restent `read-only` par
construction (`assertWritable()` dans `write.ts` du MCP `sftp-reader` exige
`writable: true` **et** `env: dev`, et les entrées de production ne portent
ni l'un ni l'autre).

### Ce que cela change

**La Task 0 cesse d'être bloquée sur l'extérieur.** Sept de ses onze
vérifications deviennent exécutables par l'agent sur le BO de dev, au lieu
d'attendre une réponse : chemin en écriture hors racine web, `.htaccess`
sur `/admin/`, version de PHP, disponibilité de `fastcgi_finish_request`,
schéma réel de `acheteur`, propagation de `HTTP_AUTHORIZATION`, et le
comportement réel des sous-requêtes corrélées.

Restent hors de portée de l'agent, donc toujours à fournir :

- la **joignabilité réseau RAG → BO** depuis l'hôte qui exécutera
  `mcp-hellodata-service` ;
- **où sont injectées les variables d'environnement** en production ;
- l'**isolation réelle du port 8597** sur le déploiement de production ;
- le **droit aux colonnes téléphone et e-mail** pour un autorisé par liste,
  qui est une décision métier et non une observation.

**La Task A9 se scinde en deux.** Le déploiement de dev devient une étape
outillée et répétable, exécutée avant chaque vérification de bout en bout ;
la mise en production devient une tâche distincte, à la toute fin, par MEP.

### Task A9 révisée — déploiement sur le BO de dev

Remplace l'ancienne Task A9. Le document `.md` de déploiement reste dû,
mais il devient le **livrable de la MEP** (Task A10), pas un préalable aux
tests.

- [ ] **Step 1: Créer l'arborescence distante**

Par `sftp_mkdir` sur `dev-write-prod` : `/admin/mcp/hellodata` et
`/admin/mcp/hellodata/actions`. Le répertoire d'état va hors racine web, au
chemin retenu en Task 0 step 1.

- [ ] **Step 2: Téléverser les fichiers du moteur**

Un `sftp_write_file` par fichier, avec `sourcePath` pointant la copie
locale sous `site/admin/mcp/hellodata/` — `sourcePath` lit le fichier brut,
donc les fins de ligne et l'encodage survivent. Compte **~40 s par
opération** : le bastion Wallix est lent, et un
`getConnection: Timed out while waiting for handshake` est **transitoire**,
pas un échec définitif — réessaie plutôt que de conclure à un problème.

Enchaîne les envois **un fichier à la fois, en tâche de fond** : une série
de dix fichiers dépasse largement un timeout de 180 s.

- [ ] **Step 3: Vérifier chaque envoi**

`sftp_write_file` relit la taille distante après `put` et signale un
désaccord comme un **échec** — un envoi partiel ne doit pas se lire comme
un succès. Vérifie que chaque appel rend bien un succès, ne te contente pas
de l'absence d'erreur visible.

- [ ] **Step 4: Dérouler les vérifications de la Task 0 sur dev**

Maintenant que le moteur est en place, les steps 2, 3, 9 et 11 de la Task 0
deviennent des `curl` contre le BO de dev. Consigne chaque résultat dans le
compte rendu de préconditions.

- [ ] **Step 5: Dérouler les tests de bout en bout des Tasks A5, A7 et A8**

Les étapes `curl` de ces tâches, écrites contre `<hôte-bo>`, s'exécutent
ici contre l'hôte de dev. **Y compris le contrôle négatif** : le CSV ne
doit pas être joignable par URL directe.

- [ ] **Step 6: Commiter la note de suivi**

Préfixe `docs(mcp-hellodata):`, sujet `record dev deployment and checks`,
corps bilingue décrivant ce qui a été déployé et ce que les vérifications
ont donné.

### Task A10 — mise en production par MEP

À exécuter **en dernier**, après que la Phase C est recettée sur dev.

- [ ] **Step 1: Invoquer le skill `prepare-mep`**

Cible `BO` (donc serveur `prod` pour les sauvegardes). Les fichiers du
moteur sont **nouveaux** : ils n'existent pas encore en production, donc le
paquet ne contient que `site/`, sans `backup/`. C'est la convention
existante pour les fichiers neufs, et `backup/` ne doit pas être créé vide.

- [ ] **Step 2: Écrire le `.md` de déploiement**

Dans `site/moteur_recherche/MCP_HELLODATA_MOTEUR_<date>.md` : liste des
fichiers et leur chemin distant, contenu complet, les deux variables
d'environnement (`MCP_HELLODATA_TOKEN`, `MCP_HELLODATA_VAR`) et où les
poser, la création du répertoire d'état hors racine web en `0700`, et les
tests post-déploiement. PR contenant **uniquement** ce `.md`
(`site/CLAUDE.md`).

- [ ] **Step 3: Rejouer les vérifications critiques sur la production**

Après l'upload manuel par le développeur, trois contrôles, et pas un de
moins :

1. le CSV n'est **pas** joignable par URL directe ;
2. sans en-tête `Authorization` → `401`, avec un mauvais jeton → `401`,
   avec le bon → `200` ;
3. le port 8597 n'est **pas** joignable depuis l'extérieur du réseau Docker
   (précondition 7).

Un échec sur l'un des trois : retirer le serveur du gateway jusqu'à
correction.

### Observation du 2026-09-21 — la racine SFTP est la racine web

Listage de `/` sur `dev-read-prod` : le répertoire contient
`maj_prod_bureaustore.php`, `redirection_lien_acheteur.php`,
`test_serveur.php`, `mon_compte_acheteur/`, `comptabilite/`, `images_cmp/`.
Ce sont des fichiers servis par le web.

Recoupement avec la source de production : `lancer_comptage_combine.php`
fait `require_once($_SERVER['DOCUMENT_ROOT']."admin/secure/check_session.php")`
— donc `DOCUMENT_ROOT` se termine par `/` et `/admin` est directement
dessous. **La racine SFTP `/` est donc le `DOCUMENT_ROOT` lui-même.**

Conséquence : **aucun répertoire hors racine web n'est accessible par ce
compte SFTP.** Le chemin nominal du § 4.1 de la spec n'est pas réalisable
tel quel, et c'est le repli documenté qui s'applique — un répertoire sous
`/admin/mcp/hellodata/var/` protégé par un `.htaccess` `Deny from all`.

**Ce repli ne vaut que s'il est prouvé.** Un `.htaccess` est sans effet si
Apache est configuré avec `AllowOverride None`, et l'échec serait
silencieux : les CSV seraient téléchargeables par URL directe sans qu'aucune
erreur ne le signale. La Task 0 step 1 doit donc se terminer par une preuve
par `curl`, pas par la présence du fichier `.htaccess`.

Trois issues possibles, à trancher à la lumière de ce test :

1. **`.htaccess` efficace** → on l'utilise, et le test `curl` devient un
   contrôle permanent rejoué à chaque déploiement (Task A9 step 5,
   Task A10 step 3).
2. **`.htaccess` sans effet** → le répertoire d'état ne peut pas vivre sous
   la racine web. Il faut alors soit un chemin fourni par l'hébergeur hors
   `DOCUMENT_ROOT`, soit renoncer au fichier CSV sur disque et faire
   streamer l'export directement par le moteur vers le wrapper, sans
   matérialisation. **C'est un changement de design, à remonter, pas à
   décider seul.**
3. **Un chemin hors racine existe mais n'est pas visible par SFTP** →
   à confirmer auprès de l'hébergeur ; c'est la meilleure issue.

### Ce qui manque encore pour dérouler les tests sur dev

Le déploiement SFTP est ouvert, mais les vérifications de bout en bout sont
des appels HTTP. Il manque donc :

- **l'URL du BO de dev** — sans elle, aucun `curl` des Tasks A5, A7, A8 et
  A9 ne peut être joué ;
- **la valeur de `MCP_HELLODATA_TOKEN` sur dev**, et l'endroit où la poser
  pour que PHP la lise (`getenv`) : selon l'hébergement, ce peut être un
  `SetEnv` dans le `.htaccess`, un fichier de configuration PHP-FPM, ou un
  `.env` lu par un include maison. À observer sur place.

---

## Amendement du 2026-09-21 (2) — export en flux

Découle du § 13 de la spec. Motif : la racine SFTP **est** le
`DOCUMENT_ROOT` (vérifié sur dev), et le repli `.htaccess` a été écarté
parce qu'un `AllowOverride None` le rendrait inopérant **en silence**.

Le test avait été armé sur dev et il était concluant : un témoin non
protégé déposé à `/admin/mcp/hellodata/temoin_public.txt` a répondu
**200**, prouvant que le chemin est servi. Les témoins ont été supprimés et
vérifiés en 404 ; le répertoire `var/` a été retiré.

### Task A8 — remplacée

L'ancienne Task A8 (job asynchrone, worker, handles, purge) est
**annulée**. Elle est remplacée par une tâche plus petite.

**Files:**
- Create: `site/admin/mcp/hellodata/actions/export.php`
- Test: vérification par `curl` sur dev (aucune partie pure : la boucle de
  tranches est celle de A4, déjà testée)

**Interfaces:**
- Consumes: A3, A4, A5
- Produces: l'action `export` — répond `text/csv` en flux, se termine par
  une ligne sentinelle

- [ ] **Step 1: Écrire l'action**

```php
<?php
// actions/export.php — streame le CSV. Rien n'est ecrit sur disque :
// aucun fichier de donnees personnelles ne doit rester au repos sur le BO.

require_once __DIR__ . '/../requete.php';
require_once __DIR__ . '/../bdd.php';

define('EXPORT_TRANCHE', 2000);
// Ecrite en derniere ligne. C'est ce qui permet au wrapper de distinguer
// un flux complet d'un flux coupe par un timeout : sans elle, un CSV
// tronque arriverait au client sans la moindre erreur visible.
define('EXPORT_SENTINELLE', '# fin-export');

$filtre = isset($corps['filtre']) ? $corps['filtre'] : null;
if (!is_array($filtre)) { echouer('filtre_manquant', "le champ 'filtre' est requis"); }
$colonnes = isset($corps['colonnes']) && is_array($corps['colonnes']) && $corps['colonnes']
          ? $corps['colonnes'] : array('id_acheteur', 'raison_sociale', 'ville', 'code_postal');
$blocage  = isset($corps['type_blocage']) ? (int)$corps['type_blocage'] : 1;
$restr    = !empty($corps['colonnes_restreintes_autorisees']);

// On compile AVANT d'emettre le moindre octet : une fois les en-teetes
// partis, on ne peut plus rendre une erreur HTTP propre.
try {
    $c = compiler_arbre($filtre);
    requete_construire($c['sql'], $c['params'], array(
        'colonnes' => $colonnes, 'type_blocage' => $blocage,
        'limite' => 1, 'mode' => 'lignes',
        'colonnes_restreintes_autorisees' => $restr,
    ));
} catch (ArbreErreur $e)   { echouer('arbre_trop_complexe', $e->getMessage()); }
  catch (CritereErreur $e) { echouer('critere_invalide', $e->getMessage()); }
  catch (RequeteErreur $e) { echouer('requete_invalide', $e->getMessage()); }

// Le client peut partir en cours de route ; on veut que la boucle s'arrete
// alors, pas qu'elle continue a marteler MySQL pour personne.
ignore_user_abort(false);
@set_time_limit(0);

header('Content-Type: text/csv; charset=utf-8');
header('Content-Disposition: attachment; filename="selection.csv"');
while (ob_get_level() > 0) { ob_end_flush(); }

$sortie = fopen('php://output', 'w');
fwrite($sortie, "\xEF\xBB\xBF"); // BOM : sans lui Excel affiche des mojibake

$entete_ecrit = false;
$curseur = null;
$total = 0;

while (true) {
    $r = requete_construire($c['sql'], $c['params'], array(
        'colonnes' => $colonnes, 'type_blocage' => $blocage,
        'curseur' => $curseur, 'limite' => EXPORT_TRANCHE, 'mode' => 'lignes',
        'colonnes_restreintes_autorisees' => $restr,
    ));
    $stmt = bdd_executer($r['sql'], $r['params']);
    $res = mysqli_stmt_get_result($stmt);
    $n = 0;
    while ($l = mysqli_fetch_assoc($res)) {
        unset($l['rn']);
        if (!$entete_ecrit) { fputcsv($sortie, array_keys($l), ';'); $entete_ecrit = true; }
        fputcsv($sortie, array_values($l), ';');
        $curseur = (int)$l['id_acheteur'];
        $n++; $total++;
    }
    mysqli_stmt_close($stmt);
    // Une tranche a la fois : l'empreinte memoire est bornee par
    // EXPORT_TRANCHE, quelle que soit la taille du resultat. Pas de
    // ini_set("memory_limit", -1) comme dans le script du BO.
    flush();
    if ($n < EXPORT_TRANCHE) { break; }
    if (connection_aborted()) { journaliser('export', 'client parti apres ' . $total . ' lignes'); return; }
}

fwrite($sortie, EXPORT_SENTINELLE . ';' . $total . "\n");
fclose($sortie);
journaliser('export', 'flux termine lignes=' . $total);
```

- [ ] **Step 2: Retirer `export` du plan de route des fichiers supprimés**

Ne créent plus rien : `export_commun.php`, `export_worker.php`,
`export_cli.php`, `export_start.php`, `export_statut.php`,
`export_fetch.php`. La route `export` remplace les cinq dans le tableau de
`index.php` :

```php
$routes = array(
    'comptage'    => 'actions/comptage.php',
    'echantillon' => 'actions/echantillon.php',
    'export'      => 'actions/export.php',
);
```

- [ ] **Step 3: Faire vivre le cache hors racine web**

`cache_repertoire()` ne doit plus dépendre de `MCP_HELLODATA_VAR` : il n'y
a pas de répertoire d'état sur le BO. `sys_get_temp_dir()` est hors racine
web par nature, et le cache ne contient que des entiers — aucune donnée
personnelle.

```php
function cache_repertoire() {
    $dir = sys_get_temp_dir() . '/mcp-hellodata-cache';
    if (!is_dir($dir)) { @mkdir($dir, 0700, true); }
    return $dir;
}
```

`MCP_HELLODATA_VAR` disparaît des variables d'environnement à poser.

- [ ] **Step 4: Vérifier sur dev — le flux complet**

```
curl -s -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"filtre":{"critere":"region","comparateur":"dans","valeur":[6]}}' \
  -X POST 'https://dev-bo.hellopro.fr/admin/mcp/hellodata/index.php?action=export' \
  | tail -2
```

Attendu : l'avant-dernière ligne est une ligne de données, la dernière est
`# fin-export;<n>`. **La sentinelle est le test**, pas le fait d'obtenir
des octets.

- [ ] **Step 5: Vérifier que rien n'est écrit sur le BO**

```
curl -s -o /dev/null -w '%{http_code}\n' 'https://dev-bo.hellopro.fr/admin/mcp/hellodata/selection.csv'
```

Attendu : `404`. Et un `sftp_list_dir` sur `/admin/mcp/hellodata` ne doit
montrer **aucun** `.csv`.

- [ ] **Step 6: Éprouver la limite de durée — la nouvelle précondition n° 1**

Lance un export volumineux et **chronomètre-le**. Si le flux s'arrête sans
sentinelle, Ecritel coupe : relève `max_execution_time` et les timeouts de
proxy, et remonte la valeur observée. Un CSV tronqué qui ne se signale pas
est le principal risque de ce modèle.

### Task B4 — delta

Remplacer `DemarrerExport`, `StatutExport` et `RecupererExport` par une
seule méthode :

```go
// Exporter ouvre le flux CSV. L'appelant DOIT fermer. Rien n'est
// bufferise : le corps est relaye tel quel vers le client.
func (c *Client) Exporter(ctx context.Context, d Demande) (io.ReadCloser, error)
```

Elle poste sur `?action=export` avec le budget `BudgetExportFetch`
(10 minutes) et rend `resp.Body` enveloppé dans le `fluxAnnulable` déjà
écrit. Les types `Job` et `Statut` disparaissent.

### Task B5 — delta

- `hellodata_export_statut` est **supprimé**. Les définitions passent de
  quatre à trois outils.
- `hellodata_export_csv` rend `{url}` immédiatement, sans appeler le
  moteur. Sa description devient : « Rend une URL de téléchargement du CSV
  complet. Le calcul démarre au téléchargement, pas ici. Le lien expire
  après 15 minutes et ne survit pas à un redémarrage du service. »
- Le handler frappe un jeton et le mémorise :

```go
// jetons associe un jeton a la demande qu'il rejouera. En memoire, borne
// et purge par TTL : un LLM en boucle ne doit pas faire croitre la
// memoire du service. Un lien mort apres redemarrage vaut mieux qu'un
// lien orphelin qui reste valable.
type jetons struct {
	mu      sync.Mutex
	entrees map[string]entree
}

type entree struct {
	demande hellodata.Demande
	expire  time.Time
}

const (
	JetonTTL = 15 * time.Minute
	JetonMax = 256
)
```

`Frapper(d) (string, error)` purge les entrées expirées, refuse au-delà de
`JetonMax`, tire 128 bits d'aléa et rend le jeton en hexadécimal
minuscule — le même format que la liste blanche de `download.Nouveau`
accepte déjà.

### Task B6 — delta

`download.Nouveau` prend en plus la table de jetons. `ServeHTTP` :
autorisation, validation du format du jeton, **résolution du jeton en
demande** (un jeton inconnu ou expiré rend 404), puis `client.Exporter` et
`io.Copy`.

Ajouter un test : un jeton expiré rend 404 et **n'atteint pas le moteur**.

### Préconditions — mises à jour

| # | Devenir |
|---|---|
| 1 | **Remplacée.** La question n'est plus « où écrire hors racine web » mais « jusqu'où Ecritel laisse courir une réponse HTTP ». Un CSV tronqué silencieux est le risque à couvrir, d'où la sentinelle |
| 2 | Inchangée — version de PHP |
| 3 | **Résolue** — `/admin/` rend 200 sans authentification HTTP |
| 4 | Inchangée — joignabilité depuis l'hôte du wrapper |
| 5 | Inchangée — droit aux colonnes téléphone et e-mail |
| 6 | Inchangée — coût des sous-requêtes corrélées |
| 7 | Inchangée — isolation du port 8597 |
| 8 | **Allégée** — `MCP_HELLODATA_VAR` disparaît, il ne reste que `MCP_HELLODATA_TOKEN` côté Ecritel |
| 9 | Inchangée — budget du live-fetch `tools/list` |
| 11 | Inchangée — schéma réel de `acheteur` |

La précondition sur `fastcgi_finish_request` et `exec()` **disparaît** : il
n'y a plus de tâche de fond.
