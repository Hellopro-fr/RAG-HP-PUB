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
| D4 | Périmètre des critères | **Sous-ensemble curé**, pas les 545. Le moteur n'est explicitement **pas** un miroir de l'écran BO. Les critères retenus sont les **feuilles** de l'arbre de D9 |
| D5 | Livraison du CSV | **Le wrapper proxifie le téléchargement** : le moteur rend un handle, jamais une URL ; le lien vu par le LLM est une URL du wrapper |
| D6 | Emplacement git du PHP | **Non tracké**, spec `.md` seule, conformément à `site/CLAUDE.md`. Chemin serveur : `/admin/mcp/hellodata/` |
| D7 | Coût du comptage | **Comptage approché par défaut + cache court**, comptage exact sur demande |
| D8 | Service MCP | **Service séparé** `mcp-hellodata-service`, distinct du MCP `bdd` |
| D9 | Forme des filtres | **Arbre booléen imbriqué** (groupes ET / OU / NON contenant des sous-groupes et des feuilles), livré **en un seul appel** |
| D10 | Accès au service | Décidé **dans le wrapper**, sur l'e-mail et le rôle injectés par le gateway : `admin` OU présent dans une liste statique. `access_gate.go` n'est pas modifié ; `server_authorizations` n'est pas utilisé (§ 7.1) |
| D11 | Visibilité des outils | Le wrapper sert un `tools/list` **variable selon l'appelant** — liste vide pour un non-autorisé. Le gateway l'interroge par requête, sur le modèle du live-fetch Zoho (§ 7.2) |

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
    AND ( <prédicat compilé depuis l'arbre de filtres, § 4.3> )
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

### 4.3 Les filtres — un arbre booléen imbriqué

Le filtre n'est pas une liste plate de champs : c'est un **arbre**. Un groupe
englobe un sous-ensemble de conditions, qui peuvent elles-mêmes être des
groupes. L'arbre entier est livré **en un seul appel** ; il n'y a pas de
construction incrémentale sur plusieurs échanges, ce qui reste cohérent avec
l'absence de matérialisation (D3).

#### 4.3.1 Grammaire

Deux types de nœuds.

**Groupe** — un opérateur booléen et ses enfants :

```json
{ "operateur": "ET" | "OU" | "NON", "conditions": [ <nœud>, … ] }
```

**Feuille** — un critère de la liste blanche, un comparateur, une valeur :

```json
{ "critere": "region", "comparateur": "dans", "valeur": ["Bretagne", "Normandie"] }
```

Exemple complet :

```json
{
  "operateur": "ET",
  "conditions": [
    { "critere": "region", "comparateur": "dans", "valeur": ["Bretagne"] },
    { "critere": "effectif", "comparateur": ">=", "valeur": 10 },
    { "operateur": "OU", "conditions": [
        { "critere": "nb_di_recues",        "comparateur": ">=", "valeur": 3 },
        { "critere": "nb_emailing_ouverts", "comparateur": ">=", "valeur": 5 }
    ]},
    { "operateur": "NON", "conditions": [
        { "critere": "npai", "comparateur": "=", "valeur": true }
    ]}
  ]
}
```

Comparateurs autorisés, par type de critère :

| Type de critère | Comparateurs |
|---|---|
| Liste (région, NAF, rubrique, pays…) | `dans`, `pas_dans` |
| Numérique (effectif, compteurs) | `=`, `!=`, `<`, `<=`, `>`, `>=`, `entre` |
| Date / période | `avant`, `apres`, `entre` |
| Booléen (NPAI, optin, a_siret…) | `=` |
| Texte (nom commercial, raison sociale) | `contient`, `ne_contient_pas`, `commence_par` |

#### 4.3.2 Garde-fous structurels

Un LLM peut produire un arbre arbitrairement large ; le moteur le refuse
avant de compiler quoi que ce soit.

| Limite | Valeur | Raison |
|---|---|---|
| Profondeur maximale | 5 | Au-delà, l'arbre est illisible et le SQL explose |
| Nombre total de feuilles | 50 | Borne le coût de la requête compilée |
| Enfants par groupe | 1 à 20 | Un groupe vide n'a pas de sens |
| Enfants d'un `NON` | exactement 1 | `NON` est unaire ; un `NON` à deux enfants est ambigu |

Un dépassement est un refus explicite (`arbre_trop_complexe`), avec la limite
franchie nommée — pas une troncature silencieuse.

#### 4.3.3 Règle de composition — le piège des jointures

C'est la conséquence non évidente de l'imbrication, et elle commande
l'implémentation.

Aujourd'hui, les jointures du script BO sont **conditionnelles à la présence**
d'un critère : si un critère DI est posé, on joint `demande_information`. Cela
fonctionne parce que tous les critères sont combinés en `AND`. **Dès qu'un
critère apparaît sous un `OU` ou un `NON`, une `INNER JOIN` devient fausse** :
elle éliminerait des lignes qui auraient dû satisfaire l'autre branche.

Règle retenue :

1. **Toute feuille est un prédicat autonome.** Un critère portant sur une
   table liée s'exprime en sous-requête corrélée (`EXISTS`, `NOT EXISTS`, ou
   un scalaire `(SELECT COUNT(…) …)`), pas en jointure.
2. **Exception d'optimisation** : un critère situé dans la chaîne `ET` de
   premier niveau — donc obligatoirement vrai pour toute ligne du résultat —
   peut être compilé en `INNER JOIN`. Le compilateur ne l'applique que là.
3. Toute jointure restante nécessaire à la projection des colonnes est une
   `LEFT JOIN`, jamais une `INNER JOIN`, pour ne pas filtrer implicitement.

Le coût de la règle 1 sur une table de 5,6 M lignes est réel et doit être
**mesuré**, pas supposé : c'est la précondition n° 5 du § 12.

#### 4.3.4 Les critères disponibles en feuille

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

`criteres.php` est une **liste blanche stricte**. Un `critere` inconnu en
feuille, un `comparateur` incompatible avec le type du critère, ou une valeur
hors domaine provoquent un refus explicite qui **renvoie la liste des critères
connus et leurs comparateurs** — le LLM apprend le vocabulaire par l'erreur
plutôt que d'inventer. Rien n'est **jamais** ignoré silencieusement.

Aucun SQL n'entre par la porte : le wrapper n'envoie qu'un arbre structuré,
dont chaque feuille est validée en critère, en comparateur et en domaine de
valeur côté PHP, et dont chaque valeur passe en requête préparée.

### 4.4 Colonnes restituables

Dérivées de la table d'extraction de l'écran actuel :

`id_societe`, `id_acheteur`, `nom_commercial`, `raison_sociale`, `civilite`,
`nom`, `prenom`, `adresse`, `code_postal`, `ville`, `region`, `pays`, `siret`,
`effectif`, `site_web`, `statut`, `fonction`, `service`, `naf`,
`secteur_activite`, `annee_creation`, `date_creation_entreprise`,
`chiffre_affaires`, `forme_juridique`, `code_insee`, `validite_email`

**Colonnes sous condition de rôle** (équivalent du `$debloque_tel_mail` du
script actuel) : `email`, `telephone`, `telephone_md5`, `fax`.

Sans le droit requis, ces colonnes sont **absentes du résultat** — pas
présentes et masquées après coup. Le moteur reçoit du wrapper un indicateur
explicite ; il refuse la demande si une colonne restreinte est demandée sans
le droit.

Tout utilisateur admis est soit `admin`, soit présent dans la liste statique
(§ 7.1). La distinction ne porte donc pas entre rôles élevés et rôles bas,
mais entre **admin** et **autorisé par liste** — et il reste à décider si ce
dernier y a droit. C'est la précondition n° 4 du § 12 ; tant qu'elle n'est
pas tranchée, le wrapper ne demande ces colonnes que pour un `admin`.

### 4.5 Contrat HTTP

Enveloppe `{"code": 200, "response": {...}}` — identique à celle que
`internal/bddcatalog/client.go` sait déjà déballer (`unwrap()`).

| Action | Méthode | Entrée | Sortie |
|---|---|---|---|
| `comptage` | POST | `filtre` (arbre), `exact` (bool, défaut `false`) | `{count, exact, plafonne, duree_ms, depuis_cache}` |
| `echantillon` | POST | `filtre` (arbre), `colonnes[]`, `cursor`, `taille` | `{rows[], next_cursor, has_more}` |
| `export_start` | POST | `filtre` (arbre), `colonnes[]` | `{job_id}` |
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

**Cache** : clé = hash SHA-256 de la **forme canonique de l'arbre de
filtres** (tri des clés d'objet, tri des enfants d'un `ET` ou d'un `OU` —
commutatifs — tri et dédoublonnage des valeurs de liste, `NON` laissé en
place car unaire) + `exact` + niveau de rôle. La canonicalisation garantit
que deux arbres sémantiquement identiques écrits dans un ordre différent par
le LLM touchent la même entrée de cache. TTL court, de l'ordre de
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
│   ├── acces/
│   │   ├── liste.go            # chargement + normalisation de HELLODATA_ALLOWED_EMAILS
│   │   └── autorise.go         # Autorise(email, role) : admin OU liste (§ 7.1)
│   ├── filtre/
│   │   ├── arbre.go            # types du filtre imbriqué, parsing JSON
│   │   └── valide.go           # bornes structurelles (profondeur, feuilles, arité)
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

**Le contrôle d'accès vit ici** (§ 7.1) : le wrapper lit
`X-End-User-Email` et `X-End-User-Role` sur chaque requête et décide seul.
Le gateway ne fait qu'injecter l'identité et poser une barrière de rôle
minimale. C'est aussi ici que `tools/list` devient variable selon
l'appelant (§ 7.2).

Variables d'environnement propres au service :

| Variable | Rôle |
|---|---|
| `HELLODATA_BASE_URL` | URL du moteur `/admin/mcp/hellodata/` |
| `HELLODATA_TOKEN` | Bearer présenté au moteur |
| `HELLODATA_ALLOWED_EMAILS` | Liste statique d'autorisés, en plus des `admin` (§ 7.1) |
| `HELLODATA_PUBLIC_URL` | Base des liens `/download/{handle}` rendus au LLM |

Le wrapper valide **la structure** de l'arbre (profondeur, nombre de
feuilles, arité — § 4.3.2) pour rejeter tôt et donner un message utile au
LLM. Il ne valide **pas** les critères eux-mêmes : la liste blanche reste
côté moteur, en un seul endroit. Un wrapper qui dupliquerait la liste
divergerait d'elle.

---

## 6. Les 4 tools MCP

| Tool | Entrée | Sortie | Rôle |
|---|---|---|---|
| `hellodata_compter` | `filtre` (arbre), `exact` (défaut `false`) | `{count, exact, plafonne, depuis_cache}` | L'appel bon marché que le LLM répète pour affiner son ciblage |
| `hellodata_echantillon` | `filtre` (arbre), `colonnes[]`, `cursor`, `taille` (≤ **2000**, défaut 50) | `{rows[], next_cursor, has_more}` | Lecture paginée par curseur |
| `hellodata_export_csv` | `filtre` (arbre), `colonnes[]` | `{job_id}` | Démarre l'extraction complète. Explicite, jamais implicite |
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

### 7.1 Accès au service — décidé dans le wrapper (D10)

**Règle** : seuls les utilisateurs de rôle `admin` et ceux dont l'adresse
figure dans une liste statique peuvent utiliser `mcp-hellodata-service`. La
décision est prise **par le wrapper**, à partir de l'identité que le gateway
lui transmet.

#### Pourquoi pas dans le gateway

Deux leviers du gateway ont été écartés, chacun pour une raison propre.

**`server_authorizations`** ne signifie pas « peut atteindre ce serveur ».
Elle n'est lue qu'à un endroit, `internal/gateway/scoped_gateway.go:507`,
dans le chemin d'**injection des en-têtes de filtrage** : une ligne y fait
échapper un utilisateur au filtrage, elle ne lui ouvre aucune porte
(`internal/db/models.go:627` : « grants full *unfiltered* access »). La
détourner lui donnerait un second sens, contradictoire sur les backends
réellement filtrés (`leexi`, `ringover`, `bdd`).

**Élargir `GateAllowsEmail`** aurait concentré la décision en un seul
endroit, mais au prix de modifier un prédicat fail-closed sur ses cinq
points d'appel (`scoped_gateway.go` 285, 423, 874, 908 et
`FilterServersByGate`) — exactement la surface où les commits `e53e07df`,
`bf44e7f0` et `58f13bf9` viennent de corriger des oublis. Ce risque est
évité entièrement.

Le pattern retenu **existe déjà** : `mcp-zoho-service` autorise en aval sur
`X-End-User-Email`, injecté par `injectZohoIdentity`
(`scoped_gateway.go:811`).

#### Ce que le gateway injecte

Un `case` supplémentaire dans le `switch` de `requestHeadersFor` — un
dispatch, pas un prédicat de sécurité :

| En-tête | Source | Absent quand |
|---|---|---|
| `X-End-User-Email` | `scopetoken.EndUserEmailFromContext(ctx)` | Sonde de santé, découverte, token de scope, `client_credentials` |
| `X-End-User-Role` | `gatewayUsers.GetByEmail(email).Role` | Idem, plus toute résolution en échec |

**`X-End-User-Role` doit être fail-closed à l'émission** : dépôt non câblé,
erreur SQL, e-mail sans ligne dans `gateway_users` — on n'envoie pas
d'en-tête de rôle. On n'envoie **jamais** une valeur par défaut, parce que
côté wrapper une valeur par défaut deviendrait un rôle effectif.

#### Ce que le wrapper décide

```go
// Autorise si le rôle est admin, ou si l'adresse figure dans la liste.
// Toute absence refuse : un appel sans identité n'est pas un appel interne
// de confiance, c'est un appel dont on ignore l'auteur.
func (a *Acces) Autorise(email, role string) bool {
    if email == "" {
        return false
    }
    if role == roleAdmin {
        return true
    }
    _, ok := a.autorises[normaliseEmail(email)]
    return ok
}
```

`normaliseEmail` applique `strings.ToLower` + `strings.TrimSpace`, et la même
normalisation s'applique au chargement de la liste — une différence de casse
ne doit pas produire un refus silencieux.

Rôle admin : la constante est `admin` (`internal/auth/role.go`, niveau 3 ;
les autres sont `readonly` = 2 et `configonly` = 1). Le wrapper compare à
l'égalité stricte plutôt qu'à un niveau : il ne reçoit pas la table des
niveaux et n'a pas à la dupliquer. Un rôle inconnu n'est donc pas admin.

Configuration, **côté `mcp-hellodata-service`** :

| Variable | Rôle |
|---|---|
| `HELLODATA_ALLOWED_EMAILS` | Adresses séparées par des virgules, autorisées en plus des `admin`. Lue une fois au démarrage, normalisée. Vide ou absente = seuls les `admin` passent |

**Les adresses ne sont pas écrites dans le code** : `Hellopro-fr/RAG-HP-PUB`
est un dépôt **public** ; une adresse commitée resterait dans l'historique
même après suppression. Seule la mécanique vit dans le source.

#### `min_role = readonly` reste nécessaire

Le gateway n'est pas déchargé de tout. `min_role` reste posé à `readonly`,
pour une raison précise : `GateAllows` refuse quand aucun e-mail n'est sur le
contexte, ce qui n'arrive que sur le chemin OAuth2 bearer. Les **tokens de
scope et les grants `client_credentials` sont ainsi exclus du service**,
puisqu'ils ne portent jamais d'identité — et un service qui exporte des
e-mails et des téléphones d'acheteurs n'a rien à faire derrière une
authentification sans utilisateur.

Avec `min_role` vide, ces chemins passeraient et le wrapper devrait les
refuser lui-même. Deux barrières valent mieux qu'une lorsque la seconde est
déjà écrite et testée.

#### La frontière réseau devient la garantie

Déplacer la décision dans le wrapper rend l'autorisation **aussi solide que
l'isolation réseau**. Si quoi que ce soit d'autre que le gateway peut joindre
`mcp-hellodata-service:8597`, `X-End-User-Role: admin` est forgeable et la
liste ne vaut rien.

C'est l'exposition que `mcp-zoho-service` accepte déjà, mais le rayon
d'impact n'est pas le même : ici l'appelant obtient un export CSV de
coordonnées d'acheteurs. Trois exigences, non négociables :

1. **`expose:` et jamais `ports:`** dans `docker-compose.yml`
   (`.claude/rules/docker-security.md` l'impose déjà) — le service n'est
   joignable que depuis le réseau Docker interne.
2. **Aucune identité = refus.** L'absence de `X-End-User-Email` n'est pas
   « appel interne, donc de confiance ». Seul `/health` répond sans
   identité, et il ne renvoie aucune donnée métier.
3. **Journaliser l'adresse sur chaque appel accepté**, en particulier sur
   `hellodata_export_csv`. C'est la seule trace qui existera, puisque la
   liste statique n'en fournit aucune.

#### Caractère provisoire assumé

La liste est statique par choix, pour ne pas construire une gestion dynamique
avant d'en avoir le besoin. Les deux coûts à connaître : modifier la liste
demande un redémarrage du wrapper, et il n'existe aucun écran
d'administration pour ces accès. Le jour où l'un des deux manque, c'est le
signal qu'il faut une vraie table — pas un signal qu'il fallait la faire
d'emblée.

### 7.2 Visibilité des outils — `tools/list` variable (D11)

**Contrainte mécanique à connaître** : un tool MCP ne peut pas masquer ses
voisins. Le `tools/list` du gateway est servi depuis son registre, peuplé par
le health-checker, et filtré par requête **uniquement** sur `min_role`
(`gatedOutIDs`, `scoped_gateway.go:282`). Un outil de diagnostic qui
répondrait « tu n'as pas accès » laisserait les autres outils listés, et rien
n'empêcherait le LLM de les appeler.

Le masquage réel passe donc par le seul mécanisme qui existe : **le gateway
interroge le backend à chaque `tools/list`**, comme il le fait déjà pour Zoho
(`scoped_gateway.go:363`, live-fetch avec repli sur le cache en cas
d'échec).

La pré-vérification est donc le `tools/list` du wrapper lui-même :

| Appelant | Réponse du wrapper |
|---|---|
| `admin`, ou adresse dans la liste | Les 4 tools |
| Identité connue mais non autorisée | **Liste vide** |
| Aucune identité | **Liste vide** |

Conséquences à assumer :

- **Un second cas particulier dans le gateway**, à côté de celui de Zoho.
  C'est le prix du masquage ; il est explicitement moins cher que d'élargir
  le prédicat d'accès, mais il n'est pas nul.
- **Un aller-retour par `tools/list`.** Le repli du chemin Zoho — servir le
  cache quand le live-fetch échoue — doit ici se replier sur **la liste
  vide**, pas sur le cache : un backend injoignable ne doit pas rendre les
  outils visibles à tout le monde. C'est une divergence délibérée d'avec
  Zoho, et elle doit être écrite en commentaire à côté du code.
- **Un non-autorisé ne voit rien**, donc son LLM n'invente pas d'explication
  sur un outil qu'il ne peut pas appeler.

Un appel direct à `tools/call` sur un outil non listé reste refusé par
`Autorise` (§ 7.1) : le masquage est du confort, pas la barrière.

### 7.3 Surfaces

| Surface | Mesure |
|---|---|
| Wrapper → moteur | Bearer token (`HELLODATA_TOKEN`), en variable d'environnement, jamais en dur. Allowlist IP côté Ecritel |
| Moteur | Pas de `check_session.php` : ce n'est pas une page BO. Le Bearer est la seule authentification |
| Injection SQL | Aucun SQL ne traverse le contrat. Liste blanche stricte dans `criteres.php`, requêtes préparées pour toutes les valeurs |
| Colonnes sensibles | `email`, `telephone`, `telephone_md5`, `fax` sous condition de rôle (§ 4.4) |
| Fichiers CSV | Hors racine web, nom à jeton, servis uniquement par endpoint authentifié, purge à 24 h |
| Cache | Le niveau de rôle fait partie de la clé (§ 4.6) |
| Fuite par message d'erreur | Codes stables, aucun SQL ni message MySQL dans les réponses (§ 4.8) |
| Accès LLM | Décidé dans le wrapper sur `X-End-User-Email` + `X-End-User-Role` : `admin` OU liste statique (§ 7.1) |
| Isolation du wrapper | `expose:` et jamais `ports:`. La liste ne vaut que ce que vaut la frontière réseau (§ 7.1) |
| Appel sans identité | Refusé. Seul `/health` répond sans identité, et sans donnée métier (§ 7.1) |
| Chemins sans utilisateur | `min_role = readonly` exclut tokens de scope et `client_credentials`, qui ne portent pas d'e-mail (§ 7.1) |
| Visibilité des outils | `tools/list` variable servi par le wrapper ; repli sur liste vide, jamais sur le cache (§ 7.2) |
| Arbre de filtres | Profondeur, nombre de feuilles et arité bornés avant compilation (§ 4.3.2) |

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
- `internal/acces/autorise_test.go` — le test central de cette v1 :
  - un `admin` passe ; un `readonly` absent de la liste est refusé ; le même
    `readonly` **présent** dans la liste passe ;
  - e-mail vide, rôle vide, en-têtes absents : refus dans les trois cas.
    L'absence d'identité ne vaut **jamais** confiance ;
  - un rôle inconnu (`""`, `Admin`, `superadmin`) n'est pas `admin` —
    comparaison stricte, pas de niveau ;
  - casse et espaces : `  A@Hellopro.FR ` correspond à `a@hellopro.fr`,
    dans les deux sens de normalisation ;
  - `HELLODATA_ALLOWED_EMAILS` vide ou absente : seuls les `admin` passent,
    et c'est le contrôle positif qui prouve que le test de refus ne passe
    pas par accident.
- `internal/tools/liste_test.go` — `tools/list` rend les 4 outils à un
  autorisé, **une liste vide** à un non-autorisé, et une liste vide en
  l'absence d'identité.
- `internal/filtre/valide_test.go` — arbre au-delà de la profondeur 5, plus
  de 50 feuilles, groupe vide, `NON` à deux enfants : chacun refusé avec la
  limite nommée. Et un arbre valide de profondeur 5 accepté, pour que le test
  d'absence ait un contrôle positif.
- `internal/tools/selection_test.go` — validation des arguments, plafond de
  2000 sur `taille`, rejet des colonnes restreintes sans le rôle.
- `internal/download/proxy_test.go` — handle invalide, streaming, absence de
  fuite de l'URL du moteur dans la réponse.

### 9.2 Côté gateway (en CI)

`access_gate.go` n'est **pas** modifié, donc aucun test de prédicat à
reprendre. Restent l'injection d'identité et le `tools/list` variable :

- `requestHeadersFor` pose `X-End-User-Email` **et** `X-End-User-Role` pour
  le backend hellodata, et **ne les pose pas** pour les autres backends —
  un test par branche, sur le modèle de
  `TestRequestHeadersFor_BDDFilterIgnoredForNonBDDBackend` ;
- **fail-closed à l'émission** : dépôt `gatewayUsers` non câblé, erreur de
  résolution, e-mail sans ligne dans `gateway_users` — aucun en-tête de rôle
  n'est envoyé. Jamais de valeur par défaut ;
- un token de scope n'atteint pas le backend (`min_role = readonly`, pas
  d'e-mail sur le contexte) — l'invariant reste celui de
  `TestScopeTokenPathLeavesEndUserEmailUnset` ;
- **le repli du live-fetch `tools/list` est la liste vide, pas le cache** :
  backend injoignable ⇒ aucun outil visible. C'est la divergence délibérée
  d'avec le chemin Zoho (§ 7.2), et elle mérite son propre test parce que
  copier le repli Zoho serait l'erreur naturelle.

### 9.3 Côté PHP (local, hors CI puisque non tracké)

`criteres.php` et `requete.php` sont **purs** : filtres en entrée, fragment SQL
en sortie, sans base ni serveur. Ils sont donc testables par un script de test
local, livré à côté de la spec de déploiement. Cas à couvrir :

- chaque critère produit le fragment attendu, pour chaque comparateur
  autorisé de son type ;
- un critère inconnu, un comparateur incompatible et une valeur hors domaine
  sont refusés, et la liste des critères connus est rendue ;
- **compilation de l'arbre** : un `OU` contenant un critère sur table liée
  produit une sous-requête corrélée, pas une `INNER JOIN` (§ 4.3.3) — c'est
  le test qui protège la correction sémantique du nesting ;
- un `NON` produit bien la négation, y compris sur un groupe entier ;
- un critère seul dans la chaîne `ET` de premier niveau peut emprunter le
  chemin `INNER JOIN`, et le résultat est identique à sa forme en
  sous-requête (test d'équivalence) ;
- la forme canonique de l'arbre est stable : deux arbres identiques à l'ordre
  près produisent la même clé de cache (§ 4.6) ;
- les trois clés de partition de `type_blocage` (§ 4.2) ;
- une colonne restreinte demandée sans le droit est refusée ;
- le plafonnement à 10 001 du comptage approché.

---

## 10. Livraison et déploiement

| Composant | Suivi git | Déploiement |
|---|---|---|
| `mcp-hellodata-service/` (Go) | Tracké, PR normale | CI `ci_services_*` + CD `cd_build_push_*`, `docker-compose.yml` |
| Enregistrement dans le gateway | Tracké, PR normale | Configuration `min_role = readonly` (§ 7.1) |
| Injection d'identité + `tools/list` variable | Tracké, PR normale | Un `case` dans `requestHeadersFor` et un cas de live-fetch dans le chemin `tools/list`, tous deux dans `scoped_gateway.go`. `access_gate.go` **n'est pas touché**. PR distincte de celle du service, pour être relue seule |
| `HELLODATA_ALLOWED_EMAILS` | **Jamais** dans git | Variable d'environnement de déploiement de `mcp-hellodata-service`. Le dépôt est public ; aucune adresse ne doit apparaître dans un fichier tracké, y compris un `.env.example` |
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
- La reproduction fidèle de la sémantique des `liason1..7` de l'écran BO.
  La v1 offre un arbre ET / OU / NON générique (§ 4.3), qui est **plus**
  expressif sur la forme, mais ne prétend pas reproduire le comportement
  exact des sept liaisons de l'écran.
- Les critères fournisseur (`if_*`) et opération emailing (`oe_*`).
- Le filtre profiling (`filtre-profiling`) et le comptage ventilé.
- La correction des CSV devinables existants dans
  `/admin/hellodata/fichiers_exports/` (§ 1.5) — constat signalé, chantier
  distinct.
- L'échappatoire `raw_params` : écartée, elle contournerait la liste blanche.
- Toute gestion **dynamique** des autorisations : table dédiée, écran
  d'administration, trace d'audit des accès. La v1 s'en tient à la liste
  statique du § 7.1, avec les deux limites que cela implique — redémarrage
  pour modifier, et aucune trace d'audit.
- Tout usage de `server_authorizations`, et toute modification de
  `access_gate.go` : ce design ne touche ni l'une ni l'autre (§ 7.1).
- Un outil de diagnostic d'accès exposé au LLM. Il ne masquerait rien
  (§ 7.2) et dupliquerait une information que la liste vide de `tools/list`
  transmet déjà.

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
4. **Correspondance droit d'accès ↔ `$debloque_tel_mail`** : l'équivalent du
   droit BO actuel sur téléphone et email. Avec l'accès décidé dans le
   wrapper (§ 7.1), la question est : un utilisateur admis **par la liste
   statique** a-t-il droit à ces colonnes, ou seul un `admin` ? Si la réponse
   diffère d'un membre à l'autre de la liste, alors une liste plate ne suffit
   plus et il faut une seconde liste — ou la table que le § 11 écarte.
5. **Coût réel des sous-requêtes corrélées** (§ 4.3.3) sur `acheteur`
   (5,6 M lignes). À mesurer sur un arbre représentatif — un `OU` entre deux
   critères sur tables liées — avant de figer la règle de composition. Si le
   coût est prohibitif, l'alternative est de restreindre les critères sur
   tables liées à la chaîne `ET` de premier niveau et de le documenter comme
   une limite du moteur, plutôt que de livrer une requête qui ne revient pas.
6. **Isolation réseau réelle de `mcp-hellodata-service`** en production.
   C'est devenu **la** garantie du modèle d'accès (§ 7.1) : si un autre
   composant que le gateway peut joindre le port 8597, `X-End-User-Role:
   admin` est forgeable et la liste ne protège rien. À vérifier sur le
   déploiement réel, pas seulement dans `docker-compose.yml`.
7. **Où sont injectées les variables d'environnement en production**, pour y
   poser `HELLODATA_ALLOWED_EMAILS` sans qu'elle transite par un fichier
   tracké. Le dépôt étant public, c'est une vérification à faire avant la
   première mise en service, pas après.
8. **Comportement du live-fetch `tools/list`** quand le backend est lent :
   vérifier que le budget de cette sonde est court et qu'un dépassement
   donne bien une liste vide, sans pénaliser le `tools/list` des autres
   backends agrégés dans la même réponse.
