# crawler-service — apprentissage des préfixes non-HTML (R23 (2)) — design

> **BROUILLON** (2026-10-16). Conception validée section par section par l'user ; spec PAS encore auto-revue.
> Base jugée : `features/poc` @ `e57409aed`. ⚠ Les `fichier:ligne` ci-dessous viennent d'une carte d'agent
> (`C:\Users\USER\.claude\projects\D--DevHellopro-Workspaces-RAG-HP-PUB\memory\r23_carte_branches_2026-10-16.md`)
> et n'ont pas tous été relus : les re-dériver avant de retirer ce bandeau.
> Registre : R23 (`C:\Users\USER\.claude\projects\D--DevHellopro-Workspaces-RAG-HP-PUB\memory\ACTIONS.md`).
> Diagnostic : `project_crawler_image_url_timeout_retries.md` (même dossier).

## 1. Problème

Le crawl `3582-2480-1791970865` (marsaleix.fr) enfile des URLs image SANS extension
(`/image/_1AAAB…-equipment-equipmentPicture-apkwc`). Les filtres par extension
(`routes.ts:360-362`, `seedExtensionFilter.ts`) ne les voient pas. Une partie de ces URLs répond vite en
non-HTML (garde content-type), le reste expire à 90 s. Mesure du 2026-10-15 sur une fenêtre de 2 h :
1 205 reclaims sur 1 209 concernent `/image/`, 0 URL image sur 263 a réussi, et seulement 27 `Processing URL`.

Ces URLs arrivent par deux chemins. (b1) Elles sont **découvertes** : ancres lightbox des pages de liste,
`enqueueLinks` (`routes.ts:1114`). (b2) Elles sont **ré-amorcées** : la phase 2 de la MAJ relit toute la
`request_queue` précédente (`UrlConsolidator.ts:262-326` vers `main.ts:1615`).

Le plafond de retry `9de07a755` (R23 (1)) réduit le coût de 6 × 90 s à 3 × 90 s par URL, sans les exclure.

## 2. Décisions prises (user, 2026-10-16 — ne pas redemander)

| # | Décision | Écarté (motif) |
|---|---|---|
| D1 | Combinaison **E + B** | A : motif propre au site. C : le HEAD peut pendre aussi, +1 requête par URL. D : l'élément d'ancre n'est visible d'aucun point de filtre (Crawlee `enqueueLinks` ne passe que des href, sélecteur `a` par défaut) ⇒ il faudrait réécrire l'extraction de liens pour ne couvrir que b1 |
| D2 | B **persisté** d'un crawl au suivant | B en mémoire seulement : les URLs qui expirent, ré-amorcées en phase 2, repaieraient 3 × 90 s avant le réapprentissage |
| D3 | Clé = **hôte + dossier parent** du chemin | 1ᵉʳ segment : trop large, il mélange des sous-dossiers sans rapport |
| D4 | Révision par **sonde** | expiration (une MAJ sur deux repaie) ; aucune (une refonte du site ne serait jamais détectée) |
| D5 | E = URLs non-HTML **isolées**, dans le **même sidecar** que B | lecture du `pdf-*` précédent : sa présence dans l'archive restaurée n'est pas établie (l'archive partielle `crawler_manager.py:2051-2059` n'a pas d'entrée `pdf`), et le fichier compte 18 806 entrées sur marsaleix |

## 3. Composants

### 3.1 Module pur `crawler/src/nonHtmlPrefix.ts`

Patron : `facetCap.ts` (décisions pures, état passé en argument, sans I/O).

- `prefixKey(url): string | null` : `host + dirname(pathname)`. Requête et fragment sont ignorés. Rend `null`
  pour la racine `/`, qui n'est jamais apprise.
- État par clé : `{ nonHtml: number, sawHtml: boolean, probation?: { admitted: number, resolved: boolean } }`.
- `recordNonHtml(state, url)` : n'est appelée que pour une URL **sans** extension ignorée. Elle fait
  `nonHtml++`. Si la clé n'est pas bloquée, l'URL entre dans l'ensemble `isolated`, plafonné.
- `recordHtml(state, url)` : `sawHtml = true`. La clé est libérée pour tout le crawl.
- `decide(state, url, ctx)` : rend `allow | block | probe`.
  - `allow` si la clé est `null`, si l'URL est dans le **dataset principal précédent** (exemption absolue,
    voir § 5) ou si `sawHtml` est vrai.
  - `block` si `nonHtml ≥ K` et `!sawHtml`, ou si l'URL fait partie des isolées chargées.
  - Une clé en probation suit § 3.3.
- Sidecar : `serialize(state)` et `parse(json)`. Le parse est tolérant : absent ou corrompu ⇒ état vide ;
  `version` inconnue ⇒ ignoré.

### 3.2 Câblage

| Point | Fichier:ligne (à re-dériver) | Effet |
|---|---|---|
| Apprendre non-HTML | garde content-type `routes.ts:364-389` | `recordNonHtml`, puis log `Non-HTML prefix learned: <key> (n=…)` au passage du seuil |
| Apprendre HTML | requestHandler, page HTML traitée (après la garde) | `recordHtml` |
| Bloquer à l'enfilage (b1) | `transformRequestFunction`, à côté du facet cap `routes.ts:1244` | `return false` + `filtered_nonhtml++` |
| Bloquer en prenav (b3) | `preNavigationHooks`, à côté du facet cap `functions.ts:885` | `throw StaleVariantSkip` (comptage existant, non-erreur) |
| Bloquer au ré-amorçage (b2) | `seedPhase2`, à côté de `hasIgnoredExtensionForSeed` `main.ts:1573` | skip + `filtered_nonhtml++` |
| Charger | démarrage : sidecar du crawl précédent (MAJ, `path.resolve('..', previousId)/storage/datasets/<domaine>`, même résolution que `functions.ts:1267-1283`) **et** sidecar du crawl courant (reprise après OOM) | état initial ; les clés du précédent entrent en probation |
| Persister | à chaque clé apprise ou confirmée, et en fin de crawl, à côté de `__collapsed_urls.json` (`functions.ts:2034`) | `__nonhtml_prefixes.json` |

Compteur neuf : `filtered_nonhtml` dans `node_stats`.

Une URL bloquée n'entre plus dans la `request_queue`, donc la MAJ suivante ne la ré-amorce plus. C'est voulu.

### 3.3 Sonde (D4)

Une clé chargée depuis le sidecar est en probation : la 1ʳᵉ URL qui se présente passe (`probe`), les autres
sont bloquées.

| Issue de la sonde | Effet dans ce crawl | Persistée ? |
|---|---|---|
| non-HTML | clé confirmée, blocage normal | oui |
| HTML | `sawHtml`, clé libérée | non, elle sort du sidecar |
| timeout ou erreur | une sonde suivante passe, jusqu'à `NONHTML_PREFIX_PROBES` (3) au total | oui, si les 3 n'ont donné aucun signal |

Frontière à accepter : après une refonte qui rend la clé HTML, les URLs ré-amorcées sous cette clé et bloquées
avant la réponse de la sonde sont perdues pour ce crawl. Elles ne reviennent que si une page les relie (b1).

### 3.4 Sidecar `__nonhtml_prefixes.json`

```json
{ "version": 1,
  "prefixes": { "www.marsaleix.fr/image/": { "nonHtml": 217, "confirmedAt": "2026-10-16T10:00:00Z" } },
  "urls": ["https://…/telechargement?id=12"] }
```

- Emplacement : dossier du dataset principal, `storage/datasets/<domaine>/`, frère de `__collapsed_urls.json`.
  Il voyage donc par le même canal d'archive (`IncludeInArchive.DATASET`).
- Cycle de vie : calqué sur `__unjudged_urls.json` (`unjudgedUrls.ts`, créé après le `dropData` `main.ts:613`,
  écriture durable qui survit à une relance après OOM). **Vérifier en spec finale que le patron se transpose.**
- Invisible aux lecteurs du dataset :
  - BO `loadJsonFilesFromDirectory` saute tout nom qui commence par `_`
    (`BO/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/fonctions/fonctions_scrapping.php:5456`).
    PROD vérifiée le 2026-10-16 : la taille 494 757 o est celle du blob `1c411242`, distincte des blobs
    voisins, et ce blob porte la ligne.
  - Python `_count_files_in_dir` (`app/core/crawler_manager.py:155`) et `admin.py:307`.
  - Le chargeur TS du dataset précédent, qui saute `__*`.

## 4. Activation

`NONHTML_PREFIX_MODE` prend trois valeurs :
- `off` : défaut du build, aucun effet ;
- `shadow` : apprend, journalise `would block`, écrit le sidecar, ne bloque rien ;
- `on` : bloque.

Déploiement prévu en trois temps : build en `off`, puis la VM en `shadow` sur quelques MAJ (on y compte les
faux positifs, c'est-à-dire les clés apprises qui voient une page HTML ensuite), puis `on`.

Paramètres :

| Variable | Défaut | Rôle |
|---|---|---|
| `NONHTML_PREFIX_MIN` (K) | 5, provisoire, dérivé par rejeu (§ 6) | nombre de non-HTML avant blocage |
| `NONHTML_PREFIX_PROBES` | 3 | sondes par clé en probation |
| `NONHTML_ISOLATED_MAX` | 10 000 | plafond des URLs isolées |

⚠ Piège connu, déjà vu sur `resolveTimeoutMaxRetries("")` : une variable posée VIDE ne doit pas donner 0.
Il faut un parse explicite qui retombe sur le défaut.

## 5. Garde-fou côté BO (le consommateur le plus strict d'une absence)

Le BO désactive « URLs Milvus − URLs du dataset neuf », et seuls `__collapsed_urls.json` et
`__unjudged_urls.json` protègent de cette soustraction (`unjudgedUrls.ts:4-24`). Une URL image n'a jamais de
ligne dataset, donc la filtrer est neutre pour le BO. En revanche, une page produit bloquée à tort ferait
désactiver sa fiche.

**Exemption absolue** : une URL présente dans le dataset principal précédent n'est jamais bloquée, à aucun
des trois points. Source : l'ensemble dataset de la consolidation, ou la même lecture que le préchargement
`filterOnSeen` (`main.ts:741`). Conséquence : `previousTotal` n'est pas affecté.

## 6. Tests et mesure

- **Nouveau** fichier `crawler/src/nonHtmlPrefix.test.ts`. On n'étend aucun fichier existant : la suite
  509/509 sert d'oracle publié à R23 (1). Cas couverts :
  - clé (racine, hôte + dossier, requête et fragment) ;
  - seuil K, veto `sawHtml`, exemption dataset ;
  - automate de probation (non-HTML, HTML, timeout ×3) ;
  - plafond des isolées ;
  - parse tolérant ;
  - les trois modes.
- Câblage : un test par point de blocage. Patrons : `seedExtensionFilter.test.ts` pour b2, `facetCap.test.ts`
  pour b1 et b3.
- Caractérisation : en mode `off`, la suite existante reste à 509/509 **sans modification**.
- Rejeu pour dériver K : `pdf-*` et dataset principal des crawls stockés, fusionnés par `timestamp`, avec
  simulation de K = 1…10 ; on compte les faux positifs (clé apprise qui voit une page HTML ensuite).
  Prérequis : ajouter `"pdf": "pdf-"` à `_DATASET_PREFIXES` (`app/router/admin.py:225`), car l'API admin ne
  sert aujourd'hui que main, error, nfr et update. L'instrument est gratuit (données internes). À défaut,
  la mesure se fait en mode `shadow`.
- Preuve d'effet après déploiement (marsaleix, première MAJ en `on` après une MAJ en `shadow`) : 0
  `Navigation timed out` sur `/image/` une fois la clé chargée ou apprise, et `filtered_nonhtml` > 0. Cette
  sortie est impossible sans le correctif. Comparaison avec 27 `Processing URL` en 2 h (mesure du 2026-10-15).

## 7. Restes avant la spec finale

1. Re-dériver chaque `fichier:ligne` cité, sur la base de `git log e57409aed..features/poc -- apps-microservices/crawler-service`.
2. Lire `unjudgedUrls.ts` (écriture durable) et `main.ts:613` : le patron de cycle de vie se transpose-t-il ?
3. Trouver où l'ensemble « dataset précédent » est disponible aux trois points de blocage (consolidation,
   ou préchargement `filterOnSeen`).
4. Pin check (brainstorming, auto-revue § 5) : chercher les fichiers édités (`routes.ts`, `functions.ts`,
   `main.ts`, `admin.py`) dans les empreintes et golden files.
5. Auto-revue (placeholders, cohérence, ambiguïtés), retirer le bandeau BROUILLON, faire relire par l'user,
   puis `writing-plans`.
