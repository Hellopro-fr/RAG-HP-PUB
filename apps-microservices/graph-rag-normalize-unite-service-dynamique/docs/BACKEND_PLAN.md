# Plan backend — `normalisation.php` (BO v2, racine PHP `Travail/BO/api/v2/`)

Plan d'implémentation du backend PHP qui sert les **2 services Python** :
`graph-rag-normalize-unite-service-dynamique` (lecture référentiel) et
`graph-rag-normalize-unite-learner` (lecture + écriture inactive + apprentissage + mail).

> Référence des payloads : [BO_V2_CONTRAT.md](apps-microservices/graph-rag-normalize-unite-service-dynamique/docs/BO_V2_CONTRAT.md).
> DDL des tables : [sql/01](apps-microservices/graph-rag-normalize-unite-service-dynamique/sql/01_referentiel_unite.sql), [sql/01b](apps-microservices/graph-rag-normalize-unite-service-dynamique/sql/01b_sanitisation_unite.sql), [sql/02](apps-microservices/graph-rag-normalize-unite-service-dynamique/sql/02_apprentissage_unite.sql).
> Seed initial : `python -m scripts.seed_referentiel_unite` → `sql/03_seed_referentiel.sql`.

---

## 0. Pré-requis SQL

> ⚠ **Base/connexion** : `normalisation.php` utilise `LINK_MYSQLI_ANNUAIRE_BO` (la même connexion
> que `action_prompt_chatgpt` et `caracterisation_produit_ia` dans le BO). Les tables `unite_*_ia`
> et `unite_apprentissage_ia` **doivent être créées sur CETTE base** (et non sur une autre). Si
> votre `LINK_MYSQLI_HELLOPRO_IA` pointe une base distincte, déplacer le lien dans `normalisation.php`
> ou créer les tables côté ANNUAIRE_BO. (Le commentaire « HELLOPRO_IA » des fichiers DDL est indicatif.)


1. Exécuter `sql/01_referentiel_unite.sql` (4 tables : `unite_definition_ia`, `unite_dimension_ia`, `label_dimension_ia`, `dimension_canonique_ia`).
2. Exécuter `sql/01b_sanitisation_unite.sql` (2 tables : `unite_preprocessing_ia`, `unite_reecriture_ia`).
3. Exécuter `sql/02_apprentissage_unite.sql` (`unite_apprentissage_ia`).
4. Charger le seed `sql/03_seed_referentiel.sql` (56 defines, 201 unités, 99 labels, 36 canoniques, 5 preprocessing, 76 réécritures).

> ⚠ **#5 — Seed = pré-requis DUR.** Le service dynamique **refuse de démarrer** si `referentiel/get`
> renvoie des sections cœur vides (fail-fast avec message explicite pointant ce seed). Charger
> l'étape 4 **avant** tout démarrage du service. (`referentiel/get` renvoie bien `code:200` même vide —
> c'est le service dynamique qui rejette, pas le BO.)
> ⚠ **#2 — Anti-doublon.** `unite_definition_ia.definition_udfi` et `label_dimension_ia.label_ldi`
> ont désormais une **clé UNIQUE** (cf. DDL) → le `save` fait un UPSERT, pas de lignes dupliquées au re-save.

## 1. Routage (convention BO v2)

- Nouveau handler `normalisation.php` ajouté à la **whitelist** d'`index.php` (anti-LFI), dispatch sur `{etape:"normalisation", field, action, data}`.
- Réponse standard BO : `{ "code": 200, "response": {...} }` (les clients Python lisent `response` quand `code==200`).
- Échappement de toute entrée via `hellopro_traitement_donnee_annuaire_bo()` (pas de prepared statements maison).
- Base : `HELLOPRO_IA`.

| field | action | Appelé par | Fonction PHP cible |
|---|---|---|---|
| `referentiel` | `get` | dynamique + learner | `get_referentiel_normalisation()` |
| `referentiel` | `save` | learner (+ seed) | `save_referentiel_normalisation()` |
| `apprentissage` | `get` | learner | `get_apprentissage_unite()` |
| `apprentissage` | `upsert` | learner | `upsert_apprentissage_unite()` |
| `learner` | `mail_recap` | learner (TODO) | `mail_recap_learner()` |
| `prompt`/`info`/`get` | — | learner | **réutiliser** l'endpoint prompt existant |

## 2. `referentiel/get` — lecture (filtre `actif=1`, tri)

`SELECT` sur les 6 tables (uniquement `actif=1`), **mappage colonne → clé de section** attendue par le loader Python :

```sql
-- definitions       (ORDER BY ordre_udfi ASC)
SELECT definition_udfi AS definition, ordre_udfi AS ordre
  FROM unite_definition_ia    WHERE actif_udfi=1 ORDER BY ordre_udfi;
-- unite_dimension
SELECT unite_udi AS unite, dimension_udi AS dimension
  FROM unite_dimension_ia     WHERE actif_udi=1;
-- label_dimension   (ORDER BY priorite_ldi ASC — spécifique avant générique)
SELECT label_ldi AS label, dimension_ldi AS dimension, priorite_ldi AS priorite
  FROM label_dimension_ia     WHERE actif_ldi=1 ORDER BY priorite_ldi;
-- dimension_canonique
SELECT dimension_dci AS dimension, unite_canonique_dci AS unite_canonique
  FROM dimension_canonique_ia WHERE actif_dci=1;
-- preprocessing     (ORDER BY ordre_upi ASC)
SELECT type_upi AS type, phase_upi AS phase, pattern_upi AS pattern,
       remplacement_upi AS remplacement, ordre_upi AS ordre
  FROM unite_preprocessing_ia WHERE actif_upi=1 ORDER BY ordre_upi;
-- reecriture
SELECT unite_source_uri AS unite_source, kind_uri AS kind, value_uri AS value
  FROM unite_reecriture_ia    WHERE actif_uri=1;
```

Réponse :
```json
{ "code":200, "response": {
  "definitions":[...], "unite_dimension":[...], "label_dimension":[...],
  "dimension_canonique":[...], "preprocessing":[...], "reecriture":[...] } }
```
> ⚠ Seuls les `actif=1` sortent → une unité apprise par le learner (`actif=0`) reste **invisible** du moteur tant qu'un humain ne l'a pas activée. C'est le garde-fou « activation manuelle ».

## 3. `referentiel/save` — écriture (mono + multi-tables atomique)

Deux formes (cf. contrat) :
- **(a) mono-table** : `data:{table, rows[]}` (utilisé par le seed).
- **(b) multi-tables ATOMIQUE** : `data:{tables:[{table, rows[]}, ...]}` (utilisé par le learner).

Mappage identifiant `table` (envoyé par Python) → table SQL + colonnes :

| `table` (payload) | table SQL | colonnes valeur |
|---|---|---|
| `unite_dimension` | `unite_dimension_ia` | `unite_udi, dimension_udi` |
| `dimension_canonique` | `dimension_canonique_ia` | `dimension_dci, unite_canonique_dci` |
| `unite_definition` | `unite_definition_ia` | `definition_udfi, ordre_udfi` |
| `reecriture` | `unite_reecriture_ia` | `unite_source_uri, kind_uri, value_uri` |
| `label_dimension` | `label_dimension_ia` | `label_ldi, dimension_ldi, priorite_ldi` |
| `preprocessing` | `unite_preprocessing_ia` | `type_upi, phase_upi, pattern_upi, remplacement_upi, ordre_upi` |

Flags communs sur **chaque** ligne : `est_auto_*`, `confiance_*`, `statut_revue_*`, `actif_*`, `origine_*` (présents sur les 6 tables).

**Transaction (forme b)** :
```
BEGIN;
  -- pour chaque {table, rows} : INSERT ... (UPSERT sur clé naturelle : unite_udi, dimension_dci,
  --   unite_source_uri, definition_udfi, label_ldi — anti-doublon #2). `preprocessing` non saveable (seed-only).
COMMIT;   -- sur erreur : ROLLBACK (rien écrit) → le learner rejoue sans doublon ni ligne orpheline
```
Réponse : `{ "code":200, "response": { "saved": <n>, "erreur": false } }` (ou `"erreur":"..."`).

## 4. `apprentissage/get`

`data:{unite, label_context}` (label_context peut être `""`).
```sql
SELECT statut_uai AS statut, confiance_uai AS confiance,
       nb_occurrences_uai AS nb_occurrences, nb_requeue_uai AS nb_requeue,
       payload_llm_uai AS payload_llm, raison_rejet_uai AS raison_rejet
  FROM unite_apprentissage_ia
 WHERE unite_uai = ? AND label_context_uai = ? LIMIT 1;
```
Réponse : la ligne, ou `null` (`response: null` ⇒ le learner traite comme « non vu »).

## 5. `apprentissage/upsert` (claim atomique)

`data:{unite, label_context, statut, confiance?, payload_llm?, raison_rejet?, nb_requeue?}`.
```sql
INSERT INTO unite_apprentissage_ia (unite_uai, label_context_uai, statut_uai, confiance_uai, payload_llm_uai, raison_rejet_uai, nb_requeue_uai)
VALUES (?,?,?,?,?,?, COALESCE(?,0))
ON DUPLICATE KEY UPDATE
  nb_occurrences_uai = nb_occurrences_uai + 1,
  statut_uai   = VALUES(statut_uai),
  confiance_uai= COALESCE(VALUES(confiance_uai), confiance_uai),
  payload_llm_uai = COALESCE(VALUES(payload_llm_uai), payload_llm_uai),
  raison_rejet_uai= VALUES(raison_rejet_uai),
  nb_requeue_uai  = COALESCE(VALUES(nb_requeue_uai), nb_requeue_uai);
```
Statuts utilisés par le learner : `pending_activation` (Gate 1 OK, inactif) / `erreur_verification` (Gate 1 NOK). Réponse : `{ "claimed": <bool>, "statut": "...", "nb_occurrences": <n> }`.
> Le `nb_requeue` n'est PAS utilisé en mode batch manuel (conservé pour compat).

## 6. `learner/mail_recap` — mail récap ✅ IMPLÉMENTÉ

`data:{report}` (rapport JSON du run). `mail_recap_learner()` formate un mail HTML (3 tableaux :
🟢 à activer avec dimension/define proposés, 🟠 à vérifier, 🔴 erreurs service + `type`, compteurs +
rappel des gestes manuels) et l'envoie via `envoyer_mail_scripts($objet,'',"script@hellopro.fr",$html,1)`.
Réponse : `{ "envoye": true }`.
> Côté Python : l'appel reste en **TODO** dans [batch.py](apps-microservices/graph-rag-normalize-unite-learner/app/core/batch.py) (à décommenter quand on veut déclencher le mail) ; le rapport `pending_activation` est déjà **enrichi** (`dimension`/`pint_define`/`reecriture`/`confiance`).

## 7. `prompt/info/get`

Le learner charge son prompt LLM depuis `action_prompt_chatgpt` via `data:{id_prompt}` → `{contenu_prompt, temperature}`. **Réutiliser** l'endpoint prompt existant du BO s'il existe (placeholders attendus : `{label}`, `{unite}`, `{valeur}`, `{dimensions_existantes}`, `{unites_canoniques}`). Insérer la ligne du prompt learner et renseigner `PROMPT_LEARNER_ID`.

---

## 8. Checklist d'implémentation (ordre conseillé)

1. **SQL** : exécuter les DDL (§0.1-3) + seed (§0.4).
2. **prompt** : insérer le prompt learner dans `action_prompt_chatgpt`, noter l'`id` → `PROMPT_LEARNER_ID`.
3. `normalisation.php` + whitelist `index.php`.
4. `referentiel/get` (§2) → tester depuis le **service dynamique** (doit booter, `counts()` non vides).
5. `referentiel/save` (§3, transaction) + `apprentissage/{get,upsert}` (§4-5) → tester un `/run` du **learner** (save inactif + statuts).
6. `learner/mail_recap` (§6) → décommenter le TODO côté Python.
7. **Activation** (geste humain) : passer `actif=1` sur les lignes apprises validées + `POST /admin/reload` du service dynamique ; puis **requeue** des messages via `dlq-manager /dlq/requeue`.

## 9. Sécurité / conventions
- Échappement systématique (`hellopro_traitement_donnee_annuaire_bo()`), `referentiel/save` réservé (auth Bearer `HP_TOKEN` déjà envoyé par les 2 services).
- `actif=0 + statut_revue=1` forcés sur tout ce qui vient du learner (jamais d'activation auto côté BO).
- Tri SQL conforme (`ordre`, `priorite`) — l'ordre porte la sémantique (cf. FLUX.md).
