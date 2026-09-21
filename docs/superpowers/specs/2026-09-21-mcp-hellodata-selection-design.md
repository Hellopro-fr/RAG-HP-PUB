# MCP HelloData — sélection d'acheteurs paginée et export CSV

- **Date** : 2026-09-21
- **Statut** : design validé, prêt pour plan d'implémentation
- **Origine** : exposer au LLM le moteur de ciblage du BO
  (`/admin/hellodata/lancer_comptage_combine.php`) en rendant **les données**
  et plus seulement **le comptage**.

---

## 1. Contexte — ce qui existe aujourd'hui

### 1.1 L'écran de comptage combiné

`/admin/hellodata/lancer_comptage_combine.php` (prod Ecritel) — **11 147 lignes,
413 Ko, 545 paramètres `$_POST` distincts**, mesurés le 2026-09-21 sur
`sftp-mcp/prod`.

Familles de paramètres :

| Préfixe | Domaine | ~ nb |
|---|---|---|
| `ca_*`, `ca_comb_*` | Critères acheteur (identité, coordonnées, géo, NPAI) | ~90 |
| `ia_*`, `ia_comb_*` | Infos acheteur (volumétrie DI, leads, récence) | ~60 |
| `id_*`, `id_comb_*` | Demande d'information (état, origine, rappel) | ~70 |
| `ie_*` | Infos emailing (reçu / ouvert / cliqué / bounce / optin) | ~60 |
| `if_*`, `if_comb_*` | Infos fournisseur | ~70 |
| `oe_*` | Opération emailing | ~10 |
| `liste_*` | Listes (région, NAF, commune, rubrique, pays) | ~18 |
| `liason1..7` | Opérateurs ET/OU entre blocs | 7 |

Requête construite (ligne ~9826) :

```sql
SELECT DISTINCT A.id_acheteur, A.id_source_a AS id_fiche, A.source_a AS source,
       A.siret_a, A.siren_a  [, raison_sociale_a, nom_commercial_a]
FROM acheteur A
  <15 jointures conditionnelles>
WHERE A.id_acheteur != 0 AND A.bloquage_a = 0
  <where_ca><where_ia><where_di><where_ie><where_oe>…
```

### 1.2 Trois propriétés du script qui contraignent le design

1. **Le comptage n'est pas un `COUNT(*)`.** Le script exécute le SELECT complet
   puis compte **en PHP**, en dédoublonnant par SIREN ou SIRET selon
   `type_blocage` (valeurs 2, 3, 4, 5, 7, 8) et en appliquant un `preg_match`
   sur raison sociale / nom commercial. Un `LIMIT` naïf casserait cette
   sémantique.
2. **La sortie est un fragment HTML**, mais le script expose déjà la requête
   construite dans `<textarea id="bkp_requete">` et tout le `$_POST` sérialisé
   en base64 dans `bkp_post`.
3. **`ini_set("memory_limit", -1)`** et une boucle `while(mysqli_fetch_assoc)`
   qui accumule tout en mémoire. En cas d'échec, `die(hellopro_mysql_error($sql, …))`
   renvoie **la requête complète au client**.

### 1.3 Ce dont dispose déjà le LLM

La table `acheteur` (base `hpdata`, **5 598 044 lignes**, PK `id_acheteur`,
`default_order_by = id_acheteur DESC`) est **déjà exposée** par le MCP `bdd`
via `bdd_query_readonly`. Mais ce tool plafonne à **500 lignes, sans pagination,
en SQL brut**. C'est exactement l'écart que ce design comble : 2000 lignes,
pagination, et des filtres métier nommés au lieu de SQL.

### 1.4 Précédents réutilisables dans le monorepo

| Élément | Emplacement | Ce qu'on en reprend |
|---|---|---|
| Client HTTP vers API admin Hellopro | `mcp-gateway-service/internal/bddcatalog/client.go` | Bearer, enveloppe `{code, response}`, budgets de timeout par endpoint |
| Serveur MCP Go | `apps-microservices/mcp-leexi-service/` | `cmd/` + `internal/{config,mcp,tools,transport}`, Go stdlib seule, SSE + streamable HTTP, `/health` |
| Contrôle d'accès | `mcp-gateway-service` — `min_role`, scope tokens, écran de consentement | Enregistrement du backend et gating par rôle |

### 1.5 Constat de sécurité préexistant

`/admin/hellodata/fichiers_exports/` contient des CSV nommés
`export_<YYYYMMDDHHMM>_<id_user>.csv` — **devinables** — accumulés depuis
juin 2024 sans purge. L'authentification du BO se fait **par fichier**
(`require_once .../admin/secure/check_session.php` en tête de chaque `.php`),
donc un `.csv` déposé sous `/admin/` est servi directement par le serveur web,
sans passer par PHP.

Ce design **n'aggrave pas** cette situation et ne la corrige pas non plus pour
l'existant : il s'assure seulement que les nouveaux exports n'y participent pas.

---

## 2. Décisions de design

| # | Question | Décision |
|---|---|---|
| D1 | Usage visé | **Les deux**, avec garde-fou : exploration par défaut, extraction complète explicite et tracée, via des tools distincts |
| D2 | Architecture | **Moteur PHP côté Ecritel + wrapper Go côté RAG-HP-PUB** ; le moteur exécute et renvoie, le wrapper traduit en MCP |
| D3 | Matérialisation | **Aucune** — les filtres sont rejoués à chaque appel. Conséquence obligatoire : le dédoublonnage passe en SQL (§ 4.2) |
| D4 | Périmètre des critères | **Sous-ensemble curé**, pas les 545. Le moteur n'est explicitement **pas** un miroir de l'écran BO |
| D5 | Livraison du CSV | **Le wrapper proxifie le téléchargement** : le moteur rend un handle, jamais une URL ; le lien vu par le LLM est une URL du wrapper |
| D6 | Emplacement git du PHP | **Non tracké**, spec `.md` seule, conformément à `site/CLAUDE.md`. Chemin serveur : `/admin/mcp/hellodata/` |
| D7 | Coût du comptage | **Comptage approché par défaut + cache court**, comptage exact sur demande |
| D8 | Service MCP | **Service séparé** `mcp-hellodata-service`, distinct du MCP `bdd` |

---

## 3. Vue d'ensemble

```
LLM
 │
 ▼
mcp-gateway-service          min_role, scope token, consentement
 │  (Go, port 8592)
 ▼
mcp-hellodata-service        contrat MCP, 4 tools, proxy de téléchargement
 │  (Go, port 8597)
 │  HTTPS + Bearer
 ▼
/admin/mcp/hellodata/        métier du ciblage : critères → SQL → résultats
 │  (PHP, Ecritel BO)
 ▼
MySQL hpdata                 acheteur + 15 tables jointes
```

Le métier de ciblage reste collé à la base ; le contrat MCP et l'autorisation
restent côté RAG. Chaque couche est modifiable sans l'autre.

---

## 4. Le moteur — `/admin/mcp/hellodata/` (PHP, Ecritel)

### 4.1 Arborescence

```
/admin/mcp/hellodata/
  index.php          # routeur unique : auth → dispatch → enveloppe JSON
  auth.php           # Bearer token + allowlist IP. PAS de check_session.php
  criteres.php       # liste blanche : critère → fragment SQL + validateur de type
  requete.php        # assemblage : jointures conditionnelles + WHERE + fenêtre
  cache.php          # cache de comptage (clé = hash des filtres normalisés)
  actions/
    comptage.php
    echantillon.php
    export_start.php
    export_statut.php
    export_fetch.php
  ../../../mcp_hellodata_var/     # HORS racine web
    jobs/            # état des jobs d'export
    exports/         # fichiers CSV produits
    cache/           # entrées de cache de comptage
```

`mcp_hellodata_var/` est **hors `DOCUMENT_ROOT`**. Aucun CSV n'est accessible
par URL directe ; seul `export_fetch.php` le streame, derrière le Bearer.
Le chemin exact est à confirmer à l'implémentation selon l'arborescence réelle
du compte Ecritel — c'est une **précondition à vérifier avant de coder**.

### 4.2 Le dédoublonnage passe en SQL

C'est la conséquence directe de D3 (pas de matérialisation). Le dédoublonnage
PHP actuel s'applique après coup, donc il ne peut pas être correct page par
page. MySQL est en **8.0.36-28** (vérifié le 2026-09-21), les fonctions fenêtre
sont disponibles :

```sql
SELECT <colonnes autorisées>
FROM (
  SELECT A.id_acheteur, A.id_source_a AS id_fiche, A.source_a AS source,
         A.siret_a, A.siren_a, <colonnes demandées>,
         ROW_NUMBER() OVER (
           PARTITION BY <clé de dédoublonnage>
           ORDER BY A.id_acheteur
         ) AS rn
  FROM acheteur A
    <jointures conditionnelles>
  WHERE A.id_acheteur != 0 AND A.bloquage_a = 0
    <fragments des critères validés>
) d
WHERE d.rn = 1
  AND d.id_acheteur > :cursor
ORDER BY d.id_acheteur
LIMIT :taille
```

Clé de partition selon `type_blocage` :

| `type_blocage` | `PARTITION BY` | Sémantique |
|---|---|---|
| 1 (défaut) | *(aucune partition, `rn` omis)* | Pas de dédoublonnage |
| 2, 3 | `LEFT(A.siret_a, 9)` | Une fiche par SIREN |
| 4, 5, 7, 8 | `A.siret_a` | Une fiche par SIRET |

Deux gains : le dédoublonnage devient **déterministe** (`ORDER BY id_acheteur`
dans la fenêtre, pas l'ordre d'arrivée), et la pagination se fait **par
curseur** — coût identique page 1 et page 40, là où `OFFSET 40000` relancerait
le scan complet. Un curseur ne saute ni ne duplique de lignes déjà vues quand
la base bouge entre deux appels.

### 4.3 Les critères de la v1

Une trentaine de critères métier, soit **46 champs** une fois comptées les
bornes de période et les opérateurs de comparaison.

| Famille | Critères exposés |
|---|---|
| Géo | `region`, `departement`, `commune`, `code_postal`, `pays` |
| Entreprise | `naf`, `effectif`, `annee_creation` + `annee_creation_operateur`, `tranche_ca`, `a_siret`, `a_site_web`, `statut_entreprise`, `forme_juridique` |
| Contact | `civilite`, `fonction`, `service`, `validite_email`, `a_mobile` |
| Consentement | `npai`, `desinscrit`, `email_correct`, `optin`, `ne_souhaite_pas_appel`, `radiee` |
| Activité DI | `nb_di_recues` + `nb_di_recues_operateur`, `nb_di_validees`, `di_date_debut`, `di_date_fin`, `anciennete_derniere_di` |
| Emailing | `nb_emailing_recus`, `nb_emailing_ouverts`, `nb_emailing_cliques`, `date_derniere_ouverture_debut/fin`, `date_dernier_clic_debut/fin`, `nb_bounces` |
| Rubrique | `rubrique_hp`, `rubrique_hd` |
| Fiche | `fiche_creation_debut/fin`, `fiche_maj_debut/fin` |
| Technique | `type_blocage` (mode de dédoublonnage, cf. § 4.2) |

`criteres.php` est une **liste blanche stricte**. Tout paramètre inconnu
provoque un refus explicite qui **renvoie la liste des critères connus** — le
LLM apprend le vocabulaire par l'erreur plutôt que d'inventer. Un paramètre
inconnu n'est **jamais** ignoré silencieusement.

Aucun SQL n'entre par la porte : le wrapper n'envoie que des filtres
structurés, validés en type et en domaine côté PHP.

### 4.4 Colonnes restituables

Dérivées de la table d'extraction de l'écran actuel :

`id_societe`, `id_acheteur`, `nom_commercial`, `raison_sociale`, `civilite`,
`nom`, `prenom`, `adresse`, `code_postal`, `ville`, `region`, `pays`, `siret`,
`effectif`, `site_web`, `statut`, `fonction`, `service`, `naf`,
`secteur_activite`, `annee_creation`, `date_creation_entreprise`,
`chiffre_affaires`, `forme_juridique`, `code_insee`, `validite_email`

**Colonnes sous condition de rôle** (équivalent du `$debloque_tel_mail` du
script actuel) : `email`, `telephone`, `telephone_md5`, `fax`.

Sans le niveau de rôle requis, ces colonnes sont **absentes du résultat** — pas
présentes et masquées après coup. Le moteur reçoit du wrapper un indicateur
dérivé du `min_role` du gateway ; il refuse la demande si une colonne
restreinte est demandée sans le droit.

### 4.5 Contrat HTTP

Enveloppe `{"code": 200, "response": {...}}` — identique à celle que
`internal/bddcatalog/client.go` sait déjà déballer (`unwrap()`).

| Action | Méthode | Entrée | Sortie |
|---|---|---|---|
| `comptage` | POST | filtres, `exact` (bool, défaut `false`) | `{count, exact, plafonne, duree_ms, depuis_cache}` |
| `echantillon` | POST | filtres, `colonnes[]`, `cursor`, `taille` | `{rows[], next_cursor, has_more}` |
| `export_start` | POST | filtres, `colonnes[]` | `{job_id}` |
| `export_statut` | GET | `job_id` | `{state, lignes_ecrites, handle?, erreur?}` |
| `export_fetch` | GET | `handle` | flux `text/csv` |

`state` ∈ `en_attente`, `en_cours`, `termine`, `echec`.

### 4.6 Comptage approché + cache (D7)

**Par défaut (`exact: false`)** : la requête est plafonnée à
`LIMIT 10001` sur la sous-requête dédoublonnée. Si 10 001 lignes sont
atteintes, la réponse est `{count: 10000, plafonne: true}` ; sinon
`{count: n, plafonne: false}`. Réponse en quelques secondes, suffisant pour
qu'un LLM affine un ciblage par itérations.

**Sur demande (`exact: true`)** : `COUNT(*)` complet sur la sous-requête
dédoublonnée. Lent par nature, budget de timeout dédié.

**Cache** : clé = hash SHA-256 des filtres normalisés (tri des clés,
normalisation des listes) + `exact` + niveau de rôle. TTL court, de l'ordre de
5 minutes, purge paresseuse à l'écriture. Le cache s'applique aux deux modes.
La réponse porte `depuis_cache` pour que le comportement reste lisible.

**Le niveau de rôle fait partie de la clé de cache** — sans ça, une réponse
calculée pour un rôle élevé pourrait être resservie à un rôle plus bas.

### 4.7 Export

`export_start` inscrit un job et rend la main immédiatement. Un worker écrit le
CSV **en flux** — requête non bufferisée, `fputcsv` ligne à ligne — sans jamais
accumuler de tableau en mémoire. Pas de `ini_set("memory_limit", -1)`.

Le fichier est écrit sous `mcp_hellodata_var/exports/` avec un nom à jeton
aléatoire. Le `handle` rendu au wrapper est ce jeton, pas un chemin.

Rétention : purge des exports et des jobs au-delà de 24 h, déclenchée
paresseusement à chaque `export_start`.

### 4.8 Erreurs

Le moteur ne reproduit **jamais** le `die(hellopro_mysql_error($sql, …))` du
script actuel. Les erreurs sont mappées en codes stables
(`critere_inconnu`, `valeur_invalide`, `colonne_interdite`, `timeout`,
`erreur_interne`) ; le message MySQL brut est journalisé côté serveur
uniquement et n'apparaît dans aucune réponse.

---

## 5. Le wrapper — `apps-microservices/mcp-hellodata-service/` (Go)

Calqué sur `mcp-leexi-service` : Go 1.24, **stdlib seule**, MCP JSON-RPC 2.0
sur SSE + streamable HTTP, `/health`, Dockerfile 2 étages
(builder → Alpine), port **8597**.

8597 et 8598 sont les seuls ports libres dans la plage MCP de
`docker-compose.yml` (8590–8596, 8599–8601, 8610, 8625, 8665 sont pris).

```
mcp-hellodata-service/
├── cmd/server/main.go
├── internal/
│   ├── config/config.go        # HELLODATA_BASE_URL, HELLODATA_TOKEN, timeouts
│   ├── mcp/types.go            # types JSON-RPC 2.0
│   ├── hellodata/
│   │   ├── client.go           # Bearer, unwrap de l'enveloppe, budget par endpoint
│   │   └── types.go            # DTO filtres / lignes / job
│   ├── tools/
│   │   ├── registry.go
│   │   ├── handler.go          # initialize, tools/list, tools/call
│   │   └── selection.go        # les 4 tools
│   ├── download/proxy.go       # GET /download/{handle} : streaming du CSV
│   └── transport/{sse,streamable_http,admin,scope}.go
├── Dockerfile
└── CLAUDE.md
```

Toutes les URL et le token viennent de variables d'environnement
(`.claude/rules/security.md` : aucune URL de service en dur).

---

## 6. Les 4 tools MCP

| Tool | Entrée | Sortie | Rôle |
|---|---|---|---|
| `hellodata_compter` | `filtres`, `exact` (défaut `false`) | `{count, exact, plafonne, depuis_cache}` | L'appel bon marché que le LLM répète pour affiner son ciblage |
| `hellodata_echantillon` | `filtres`, `colonnes[]`, `cursor`, `taille` (≤ **2000**, défaut 50) | `{rows[], next_cursor, has_more}` | Lecture paginée par curseur |
| `hellodata_export_csv` | `filtres`, `colonnes[]` | `{job_id}` | Démarre l'extraction complète. Explicite, jamais implicite |
| `hellodata_export_statut` | `job_id` | `{state, lignes, url?}` | `url` pointe le wrapper, jamais le BO |

**C'est là que vit le garde-fou de D1** : `compter` et `echantillon` ne
produisent rien de rapatriable en masse ; produire un fichier est un acte
séparé, nommé, et journalisé.

### 6.1 Proxy de téléchargement

`hellodata_export_statut` rend une URL du wrapper de la forme
`{WRAPPER_PUBLIC_URL}/download/{handle}`. Cette route :

1. valide le handle,
2. appelle `export_fetch` du moteur avec son propre Bearer,
3. streame la réponse au client.

Aucune URL du BO ne circule jamais. La route est soumise à la même
authentification que le reste du service, donc au `min_role` du gateway.

---

## 7. Sécurité et autorisation

| Surface | Mesure |
|---|---|
| Wrapper → moteur | Bearer token (`HELLODATA_TOKEN`), en variable d'environnement, jamais en dur. Allowlist IP côté Ecritel |
| Moteur | Pas de `check_session.php` : ce n'est pas une page BO. Le Bearer est la seule authentification |
| Injection SQL | Aucun SQL ne traverse le contrat. Liste blanche stricte dans `criteres.php`, requêtes préparées pour toutes les valeurs |
| Colonnes sensibles | `email`, `telephone`, `telephone_md5`, `fax` sous condition de rôle (§ 4.4) |
| Fichiers CSV | Hors racine web, nom à jeton, servis uniquement par endpoint authentifié, purge à 24 h |
| Cache | Le niveau de rôle fait partie de la clé (§ 4.6) |
| Fuite par message d'erreur | Codes stables, aucun SQL ni message MySQL dans les réponses (§ 4.8) |
| Accès LLM | Enregistrement du backend dans `mcp-gateway-service` avec `min_role` |

---

## 8. Budgets de timeout

Suivant la leçon déjà apprise par `bddcatalog` (ses endpoints `/count`
dépassent 30 s et ont dû recevoir un budget séparé de 60 s) :

| Endpoint | Budget wrapper | Justification |
|---|---|---|
| `comptage` (approché) | 20 s | Plafonné à 10 001 lignes |
| `comptage` (exact) | 120 s | `COUNT(*)` sur sous-requête dédoublonnée, 5,6 M lignes |
| `echantillon` | 30 s | Pagination par curseur, coût borné |
| `export_start` | 5 s | Asynchrone, rend un `job_id` |
| `export_statut` | 5 s | Lecture d'état |
| `export_fetch` | 10 min | Streaming d'un fichier volumineux |

Un dépassement est rendu comme un échec explicite avec le code `timeout`, pas
comme un résultat vide.

---

## 9. Tests

### 9.1 Côté Go (en CI)

- `internal/hellodata/client_test.go` — `httptest`, déballage de l'enveloppe,
  propagation des codes d'erreur, respect des budgets de timeout.
- `internal/tools/selection_test.go` — validation des arguments, plafond de
  2000 sur `taille`, rejet des colonnes restreintes sans le rôle.
- `internal/download/proxy_test.go` — handle invalide, streaming, absence de
  fuite de l'URL du moteur dans la réponse.

### 9.2 Côté PHP (local, hors CI puisque non tracké)

`criteres.php` et `requete.php` sont **purs** : filtres en entrée, fragment SQL
en sortie, sans base ni serveur. Ils sont donc testables par un script de test
local, livré à côté de la spec de déploiement. Cas à couvrir :

- chaque critère produit le fragment attendu ;
- un critère inconnu est refusé et la liste des critères connus est rendue ;
- les trois clés de partition de `type_blocage` (§ 4.2) ;
- une colonne restreinte demandée sans le droit est refusée ;
- le plafonnement à 10 001 du comptage approché.

---

## 10. Livraison et déploiement

| Composant | Suivi git | Déploiement |
|---|---|---|
| `mcp-hellodata-service/` (Go) | Tracké, PR normale | CI `ci_services_*` + CD `cd_build_push_*`, `docker-compose.yml` |
| Enregistrement dans le gateway | Tracké | Migration + configuration `min_role` |
| `/admin/mcp/hellodata/` (PHP) | **Non tracké** (D6) | Upload FTP manuel sur Ecritel, avec une spec `.md` de déploiement en PR, conformément à `site/CLAUDE.md` |

La spec `.md` de déploiement du PHP contiendra les fichiers complets, le
contexte, et les tests post-déploiement — c'est la procédure décrite dans
`site/CLAUDE.md` § « Procédure correcte pour modifier un fichier Ecritel ».

---

## 11. Hors périmètre de la v1

Explicitement **pas** dans cette version, pour que l'absence soit un choix et
non un oubli :

- La très large majorité des 545 paramètres de l'écran BO (D4).
  `/admin/mcp/hellodata/` n'est pas un miroir de cet écran et n'a pas
  vocation à le devenir.
- Les liaisons ET/OU entre familles (`liason1..7`) : la v1 combine tous les
  critères en `AND`.
- Les critères fournisseur (`if_*`) et opération emailing (`oe_*`).
- Le filtre profiling (`filtre-profiling`) et le comptage ventilé.
- La correction des CSV devinables existants dans
  `/admin/hellodata/fichiers_exports/` (§ 1.5) — constat signalé, chantier
  distinct.
- L'échappatoire `raw_params` : écartée, elle contournerait la liste blanche.

---

## 12. Préconditions à vérifier avant de coder

1. **Chemin hors racine web** sur le compte Ecritel pour
   `mcp_hellodata_var/` (§ 4.1). Si aucun chemin hors `DOCUMENT_ROOT` n'est
   accessible en écriture, replier sur un répertoire protégé par `.htaccess`
   `Deny from all` — et le vérifier réellement, pas le supposer.
2. **Joignabilité réseau** : le wrapper, hébergé côté RAG, doit pouvoir
   atteindre le BO Ecritel en HTTPS. À confirmer avant toute implémentation.
3. **Absence de `.htaccess`** imposant une authentification sur `/admin/` qui
   empêcherait le moteur de répondre à un Bearer.
4. **Correspondance `min_role` ↔ `$debloque_tel_mail`** : quel niveau de rôle
   du gateway équivaut au droit BO actuel sur téléphone et email.
