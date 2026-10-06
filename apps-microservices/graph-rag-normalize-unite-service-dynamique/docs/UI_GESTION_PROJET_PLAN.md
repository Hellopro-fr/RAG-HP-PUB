# Plan — Bloc « Normalisation dynamique » dans `gestion_projet`

Ajout d'un **onglet** dans le BO `gestion_projet` (`mvp-QC/gestion_projet/index_v2.php` + `api.php`)
pour **piloter manuellement** le workflow de normalisation dynamique : lancer le learner,
revoir/activer les unités apprises, recharger le moteur, requeue les messages DLQ.

> Cible : `BO/admin/repertoire_test/moulinettes_hosana/script_divers/mvp-QC/gestion_projet/`
> Conventions relevées : nav `<a class="tab-link" data-tab="X">`, panneaux `data-tab-content="X"`,
> JS `_api(action, params, cb)` → POST FormData vers `api.php` (`switch($action)`), toasts `_toast`,
> tâches `TaskTracker`/`_task`. Services exposés sous `https://api.hellopro.eu/<service>`.

---

## 1. Workflow piloté (le geste manuel, en 1 onglet)

```
[1] Lancer learner /run {limit:100}     → rapport (appris inactifs / à vérifier / erreurs)
[2] Revoir « À ACTIVER »                 → pour chaque unité : dimension + define proposés
[3] Activer une unité (ou tout)          → actif=1 sur ses lignes + reload moteur dynamique
[4] Requeue les messages DLQ             → /graphdlq-service/dlq/requeue {count, queue_name}
        ↳ le retry-processor re-normalise → Neo4j
```

## 2. Front — `index_v2.php`

### 2.1 Onglet
Ajouter dans la nav (après `auto-prix [08]`) :
```html
<a class="tab-link" data-tab="normalisation" href="#"><span>Normalisation</span> <span class="count">[09]</span></a>
```
Et un panneau `data-tab-content="normalisation"` contenant 5 sous-blocs (cartes `hop-*`) :

| Sous-bloc | Contenu | Action JS |
|---|---|---|
| **A. Run learner** | input `limit` (défaut 100) + bouton « Lancer l'apprentissage » + zone rapport (compteurs : drainés / uniques / appris / à vérifier / erreurs) | `runLearner()` → `_api('norm_learner_run', {limit})` |
| **B. À activer** | tableau des unités `pending_activation` (unité, dimension, `pint_define`/réécriture, confiance, valeur d'exemple) + bouton « Activer » par ligne + « Activer tout » | `activateUnit(unite,label)` / `activateAll()` → `_api('norm_activate_unit', …)` |
| **C. À vérifier** | tableau lecture seule `erreur_verification` (unité, raison) — décision humaine (corriger en base / ignorer) | `loadNormalisation()` (chargement) |
| **D. Moteur** | compteurs référentiel (actives / en attente / rejetées) + bouton « Recharger le moteur » | `reloadEngine()` → `_api('norm_dynamic_reload', {})` |
| **E. DLQ & requeue** | compteur `graph_rag_normalization_manual_dlq` + input `count` + bouton « Requeue » | `requeueDlq(count)` → `_api('norm_dlq_requeue', {count, queue_name})` |

### 2.2 JS (inline, même style que `auto-prix`)
- `loadNormalisation()` : `_api('norm_get_state', {})` → remplit B (à activer), C (à vérifier), D (compteurs), E (compte DLQ).
- `runLearner()` : `_task('learner run')` → `norm_learner_run` → affiche le rapport puis `loadNormalisation()`.
- `activateUnit/activateAll` : `norm_activate_unit` → toast + `loadNormalisation()`.
- `reloadEngine` / `requeueDlq` : toasts.
- Activer le chargement à l'ouverture de l'onglet (hook sur le tab-switch existant, comme `auto-prix`).

## 3. Backend — `api.php` du gestion_projet (nouvelles `case`)

URLs de services (nouvelles constantes, sur le modèle `INGESTION_API_URL`) :
```php
define('NORMALIZE_LEARNER_URL', 'https://api.hellopro.eu/normalize-unite-learner');
define('NORMALIZE_DYNAMIC_URL', 'https://api.hellopro.eu/normalize-unite-service-dynamique');
define('GRAPHDLQ_URL',          'https://api.hellopro.eu/graphdlq-service');
```

| `action` | Rôle | Implémentation |
|---|---|---|
| `norm_learner_run` | lance un run | `curl POST {NORMALIZE_LEARNER_URL}/run` body `{limit}` → renvoie `report` |
| `norm_get_state` | état pour l'UI | SELECT `unite_apprentissage_ia` (groupé par statut) → listes `pending_activation` (+ payload_llm pour dimension/define) et `erreur_verification` ; compteurs référentiel (`actif=1` vs `statut_revue=1`) ; + `norm_dlq_count` |
| `norm_activate_unit` | active une unité | appelle BO v2 `normalisation/referentiel/activate` (cf. §4) puis `curl POST {NORMALIZE_DYNAMIC_URL}/admin/reload` |
| `norm_dynamic_reload` | recharge le moteur | `curl POST {NORMALIZE_DYNAMIC_URL}/admin/reload` (header `x-reload-token` si configuré) |
| `norm_dlq_count` | compte DLQ | `curl GET {GRAPHDLQ_URL}/dlq/queues` → message_count de `graph_rag_normalization_manual_dlq` |
| `norm_dlq_requeue` | requeue N | `curl POST {GRAPHDLQ_URL}/dlq/requeue` body `{queue_name:'graph_rag_normalization_manual_dlq', count}` |

> `norm_get_state` peut lire la BDD en direct (api.php a déjà les connexions `LINK_MYSQLI_*`), ou
> déléguer à un nouvel endpoint BO v2 `normalisation/etat/get`. **Reco** : lecture directe ici
> (lecture seule), écriture (activation) déléguée au BO v2 (transaction).

## 4. Backend BO v2 — nouvelle action `normalisation/referentiel/activate`

Ajouter à [normalisation.php](C:/Users/Admin/Desktop/Travail_hp/Travail/BO/api/v2/normalisation.php) :
`traitement_normalisation('referentiel','activate', {unite, label_context})` → `activate_unite_apprise()` :
1. lit `unite_apprentissage_ia.payload_llm_uai` pour `(unite,label_context)` (la proposition validée).
2. **transaction** : `UPDATE … SET actif=…=1` sur les lignes `origine='learner'` correspondantes :
   - `unite_dimension_ia` WHERE `unite_udi = <unite>`
   - `unite_definition_ia` WHERE `definition_udfi = <payload.pint_define>` (si présent)
   - `unite_reecriture_ia` WHERE `unite_source_uri = <unite>` (si réécriture)
   - `dimension_canonique_ia` WHERE `dimension_dci = <payload.dimension>` (si nouvelle dimension)
   - `label_dimension_ia` WHERE `label_ldi = <payload.label_to_dimension>` (si label)
3. `UPDATE unite_apprentissage_ia SET statut_uai='learned'` pour cette unité.
4. retourne `{ "active": <n_lignes>, "erreur": false }`.

> L'activation flippe `actif=1` (et `statut_revue=0`) — c'est le seul moment où une unité apprise
> devient vivante. Le `payload_llm` (déjà stocké à l'apprentissage) porte les clés à cibler.
> Whitelister la nouvelle action ; pas de nouvelle table.

## 5. Points d'attention
- **Sécurité** : réutiliser le `check_session.php` déjà en tête d'`api.php` ; restreindre l'onglet (le bloc `$ALLOWED_USERS` commenté peut être réactivé).
- **Idempotence activation** : flipper `actif=1` est idempotent (re-activer ne casse rien). Le reload qui suit rend l'unité effective.
- **Ordre** : activer **avant** de requeue (sinon le retry re-échoue). L'UI doit guider cet ordre (étapes numérotées A→E).
- **Reload obligatoire** après activation : sans `/admin/reload`, le moteur garde l'ancien référentiel (jusqu'au TTL).
- **Timeouts curl** : un `learner /run` peut durer (LLM × N unités) → `CURLOPT_TIMEOUT` élevé (ex. 600) sur `norm_learner_run`, comme les autres lancements longs.
- **Base DB** : `norm_get_state` lit les tables `unite_*_ia`/`unite_apprentissage_ia` sur le **même lien** que `normalisation.php` (`LINK_MYSQLI_ANNUAIRE_BO`).

## 6. Checklist d'implémentation
1. Constantes URL dans `api.php` (§3).
2. `case` `norm_get_state` + `norm_dlq_count` (lecture) → tester l'affichage.
3. `case` `norm_learner_run`, `norm_dynamic_reload`, `norm_dlq_requeue` (curl).
4. BO v2 : action `normalisation/referentiel/activate` (§4) + `case` `norm_activate_unit`.
5. Front : onglet + 5 sous-blocs + JS (§2), chargement au tab-switch.
6. Test bout-en-bout manuel : run → activer → reload → requeue → vérifier Neo4j.

## 7. Hors périmètre (pour plus tard)
- Le mode **semi-automatique** (le learner active + reload + requeue tout seul) — ce bloc reste **manuel** (l'humain décide l'activation). Le bloc le prépare (boutons « Activer tout »).
- Édition fine du référentiel (CRUD unité par unité) — non couvert ; seulement activation des propositions du learner.
