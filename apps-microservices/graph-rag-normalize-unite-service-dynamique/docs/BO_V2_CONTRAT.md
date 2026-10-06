# Contrat BO v2 — `normalisation.php` (à implémenter racine PHP `BO/api/v2/`)

Le service dynamique (et le futur learner) lisent/écrivent le référentiel d'unités
**via BO v2** (règle projet : CRUD en PHP, logique en Python). Ce document spécifie
les endpoints attendus. Routeur webhook standard : `{etape, field, action, data}`,
handler `normalisation.php` whitelisté dans `index.php`.

Tables cibles (HELLOPRO_IA) : voir `sql/01_referentiel_unite.sql` et `sql/02_apprentissage_unite.sql`.

---

## 1. `referentiel/get` — lecture (consommé par le service dynamique)

Requête :
```json
{ "etape": "normalisation", "field": "referentiel", "action": "get" }
```

Réponse (filtrer `actif=1`, trier comme indiqué) :
```json
{
  "definitions": [
    { "definition": "KW = 1000 * watt", "ordre": 36 }
  ],
  "unite_dimension": [
    { "unite": "kg", "dimension": "mass" }
  ],
  "label_dimension": [
    { "label": "capacité d'accueil", "dimension": "count", "priorite": 5 }
  ],
  "dimension_canonique": [
    { "dimension": "mass", "unite_canonique": "kilogram" }
  ],
  "preprocessing": [
    { "type": "nfkc", "phase": "pre_snapshot", "pattern": null, "remplacement": "", "ordre": 0 },
    { "type": "regex_sub", "phase": "pre_snapshot", "pattern": "\\s*\\([^)]*\\)\\s*$", "remplacement": "", "ordre": 1 },
    { "type": "str_replace", "phase": "post_snapshot", "pattern": "³", "remplacement": "3", "ordre": 3 }
  ],
  "reecriture": [
    { "unite_source": "m3/h", "kind": "rewrite", "value": "m**3 / hour" },
    { "unite_source": "%", "kind": "bypass", "value": "count" }
  ]
}
```
- `definitions` : `ORDER BY ordre_udfi ASC` (dépendances entre define).
- `label_dimension` : `ORDER BY priorite_ldi ASC` (spécifique avant générique).
- `preprocessing` : `ORDER BY ordre_upi ASC` (transforms universels, phase pré/post-snapshot).
- `reecriture` : map exacte ; `kind` ∈ {`rewrite` (→ expr pint), `bypass` (→ unité canonique directe)}.
- `unite` toujours en **minuscules**.
- Le Python re-trie défensivement, mais le tri SQL doit être correct.
- **Hors périmètre BO** : la désambiguïsation contextuelle (nm / t/min / G) reste codée
  en dur côté service (`_STATIC_DISAMBIGUATIONS`) — pas de table ni d'endpoint associés.

---

## 2. `referentiel/save` — écriture (seed + learner)

Deux formes acceptées.

**(a) Mono-table** (seed) :
```json
{ "etape": "normalisation", "field": "referentiel", "action": "save",
  "data": { "table": "unite_dimension",  // unite_definition|unite_dimension|label_dimension|dimension_canonique|preprocessing|reecriture
            "rows": [ { "unite": "kilogrammes", "dimension": "mass", "est_auto": 0, "actif": 1, "origine": "seed" } ] } }
```

**(b) Multi-tables ATOMIQUE** (learner — #4) :
```json
{ "etape": "normalisation", "field": "referentiel", "action": "save",
  "data": { "tables": [
      { "table": "unite_dimension",     "rows": [ {"unite":"quintal","dimension":"mass","est_auto":1,"confiance":0.9,"statut_revue":1,"actif":0,"origine":"learner"} ] },
      { "table": "unite_definition",    "rows": [ {"definition":"quintal = 100 * kilogram","ordre":9000,"est_auto":1,"confiance":0.9,"statut_revue":1,"actif":0,"origine":"learner"} ] }
  ] } }
```
- **Forme (b) DOIT être transactionnelle** : `BEGIN` … insert de toutes les tables … `COMMIT` ; sur toute erreur `ROLLBACK` (zéro ligne écrite) → le learner peut rejouer sans créer de doublon ni de ligne orpheline (mapping unité→dimension sans canonique).
- INSERT (ou UPSERT sur clé naturelle : `unite_udi`, `dimension_dci`).
- `statut_revue=1` ⇒ forcer `actif=0` (en attente d'activation humaine).
- Réponse : `{ "saved": <n>, "erreur": false }` (ou `erreur: "..."`).
- ⚠ Les flags `est_auto/confiance/statut_revue/actif/origine` sont envoyés sur **toutes** les tables (y compris `unite_definition`, `reecriture`) — ces colonnes doivent exister sur chaque table (cf. DDL).

---

## 3. `apprentissage/get` — dédup learner

Requête :
```json
{ "etape": "normalisation", "field": "apprentissage", "action": "get",
  "data": { "unite": "quintal", "label_context": "poids" } }
```
Réponse : la ligne `_uai` (`statut`, `confiance`, `nb_occurrences`, **`nb_requeue`**, `payload_llm`) ou `null`.

---

## 4. `apprentissage/upsert` — claim atomique learner

Requête :
```json
{ "etape": "normalisation", "field": "apprentissage", "action": "upsert",
  "data": {
    "unite": "quintal", "label_context": "poids",
    "statut": "processing", "confiance": null, "payload_llm": null,
    "raison_rejet": null, "nb_requeue": null
  } }
```
- `INSERT ... ON DUPLICATE KEY UPDATE nb_occurrences_uai = nb_occurrences_uai + 1`,
  + mise à jour `statut`/`confiance`/`payload_llm`/`raison_rejet`/`nb_requeue` si fournis
  (`nb_requeue` est positionné explicitement par le learner, pas auto-incrémenté).
- Doit indiquer si l'appelant est le **premier** (claim) pour éviter 2 workers LLM sur la
  même unité. Réponse : `{ "claimed": true|false, "statut": "...", "nb_occurrences": <n>, "nb_requeue": <n> }`.

---

## 5. `prompt/info/get` — prompt learner (BDD)

Requête : `{ "etape": "prompt", "field": "info", "action": "get", "data": { "id_prompt": "<id>" } }`
Réponse : `{ "contenu_prompt": "...", "temperature": 0.1, ... }` (table `action_prompt_chatgpt`).
Placeholders attendus dans le prompt : `{label}`, `{unite}`, `{valeur}`,
`{dimensions_existantes}`, `{unites_canoniques}`.

---

## Note d'implémentation

- Échappement via `hellopro_traitement_donnee_annuaire_bo()` (pas de prepared statements maison).
- Aucune logique de normalisation côté PHP : le PHP ne fait que du CRUD sur les 5 tables.
- Après tout `referentiel/save`, le learner appelle `POST /admin/reload` du service dynamique
  pour rendre l'apprentissage effectif immédiatement (sans attendre le TTL).
