# Design — Workflow d'enrichissement de la doc des tables BDD (MCP)

> Date : 2026-06-05
> Statut : validé (brainstorming) — prêt pour writing-plans
> Repos concernés : `RAG-HP-PUB/apps-microservices/mcp-gateway-service` (control-plane, dashboard + import), `Hellopro/BO/admin/mcp_hp/` (data-plane PHP, consommateur)

## 1. Contexte & objectif

Le système MCP « Table BDD » expose des tables MySQL prod en lecture seule à un agent LLM, via 6 outils (`bdd_list_tables`, `bdd_describe_table`, `bdd_query_readonly`, `bdd_sample_data`, `bdd_search_columns`, `bdd_get_table_doc`). La qualité des réponses de l'agent dépend de la **doc métier** attachée à chaque table et champ dans le registre curaté du gateway (`bdd_used_tables` / `bdd_used_fields`), servie à l'agent par `bdd_get_table_doc`.

**Objectif** : un processus réutilisable où l'utilisateur crée une table dans le dashboard MCP, et cette conversation (qui a accès au code + aux outils MCP en lecture) produit une doc précise (description de la table + de chaque champ), appliquée en **un geste** via l'import JSON du dashboard.

**Contrainte clé établie** : le remplissage 100 % automatique (Claude écrivant directement dans le registre) **n'est pas possible** depuis cette session —
- l'écriture passe par `POST /api/v1/bdd/used/tables/import-doc`, **admin-gated** (login SSO hellopro.fr / JWT) ;
- les outils MCP disponibles sont **lecture seule** (aucun n'écrit dans le registre) ;
- `BDD_PUBLIC_API_TOKEN` n'ouvre que les endpoints publics en **lecture** (`/api/v1/public/bdd/*`).

Le plus proche d'automatique = Claude génère le fichier, l'utilisateur l'applique en un geste.

## 2. Rappel d'architecture (qui possède quoi)

- **Registre curaté** (`bdd_used_tables`/`bdd_used_fields`/`bdd_meta`, GORM, MySQL gateway) = source de la doc métier. Édité via l'API admin du gateway + le dashboard Vue `mcp-gateway-frontend/src/views/BDDTablesView.vue`.
- **Catalogue amont** (lecture seule, `BDD_CATALOG_BASE_URL`) = vérité sur le schéma réel (tables/colonnes/types existants). Le gateway le proxifie en lecture (`/api/v1/bdd/catalog/...`).
- **Plan données PHP** (`Hellopro/BO/admin/mcp_hp/`) = exécute les requêtes ; tire la doc du gateway via `/api/v1/public/bdd/schema-doc` (cache 300 s) et la liste des tables autorisées via `/api/v1/public/bdd/config` (cache 60 s).
- **Outils MCP `bdd_*`** = passent par le gateway ; lecture seule.

## 3. Le ritual réutilisable

**Unité = une table (approche A). Lot = plusieurs tables en un fichier (approche B).** Même gabarit JSON, jouable à 1 ou N tables.

1. **Créer la table** dans le dashboard (nom + `database_id` + champs). Optionnel techniquement (l'import upsert peut créer la table), mais recommandé pour vérifier les noms de colonnes côté UI et activer la table.
2. **Fournir le contexte** à Claude : nom de table + `database_id` (1/5/10) + (optionnel) colonnes ciblées + toute connaissance métier.
3. **Grounding** par Claude (cf. §5).
4. **Livraison** : un fichier doc-JSON (cf. §4) + un aperçu FR (tableau colonne → description) pour validation avant dépôt.
5. **Application** (cf. §8) : drag-drop dans « Importer JSON » (ou `curl` lancé par l'utilisateur). L'utilisateur colle le retour `{inserted, updated, errors}`. Toute colonne droppée (G3) → correction du nom → re-dépôt.

Lot : étapes 2–4 répétées, concaténées dans un seul fichier `{_meta, t1:{…}, t2:{…}}`, un seul dépôt.

## 4. Gabarit JSON (shape exacte acceptée par `import-doc`)

Vérifié sur `mcp-gateway-service/internal/api/bdd_handlers.go:967-1192` (handler `handleBDDUsedImportDoc`).

```json
{
  "_meta": {
    "description": "Doc globale de la base exposée au MCP (optionnel).",
    "usage": "Quand/comment l'agent doit interroger ces tables."
  },
  "<nom_table>": {
    "database_id": 1,
    "description": "Rôle métier de la table, en une-deux phrases.",
    "primary_key": "id",
    "default_order_by": "id DESC",
    "rows": null,
    "columns": {
      "id":         { "type": "int",          "desc": "Identifiant unique." },
      "id_societe": { "type": "int",          "desc": "FK → societe.id. ..." },
      "statut":     { "type": "enum",         "desc": "Valeurs: 0=..., 1=... ." }
    },
    "relations": [],
    "notes": ""
  }
}
```

Sémantique (vérifiée dans le handler) :

| Clé | Règle |
|-----|-------|
| `database_id` | `1`=edgb2b/BO (**défaut si omis ou 0**), `5`=hpdata, `10`=hellopro_ia. Toute autre valeur → erreur `database_id must be one of 1, 5, 10`. Doit matcher la DB de la table (cf. G1). |
| `columns` | Map `nom_colonne → {type, desc}`. Nom exact requis ; colonne hors catalogue amont = droppée + signalée (cf. G3). enum/set : mettre les valeurs réelles dans `desc` (cf. G6). |
| `_meta` | Optionnel ; upsert de la ligne singleton `bdd_meta` (doc globale servie par `bdd_get_table_doc` sans argument). |
| `rows` | `null` accepté (ou via le bouton `refresh-catalog` plus tard). |
| `primary_key` / `default_order_by` | Optionnels (string). |
| `relations` | `[]` ou `{}` ou structure libre (JSON). |
| `notes` | String libre, optionnel. |

Mapping `database_id` confirmé : `bdd_handlers.go:38-42` (`bddPublicDBKeyByID`).

## 5. Méthode de grounding (ordre, par table)

Source validée = **live MCP + code**.

1. **`bdd_describe_table`** → noms + types + clés/index exacts (structure live). Garantit des noms de colonnes qui matchent → évite G3.
2. **`bdd_sample_data`** → 5 lignes réelles → formats, unités, valeurs plausibles, colonnes FK-like.
3. **`bdd_query_readonly`** ad hoc si besoin : `SELECT <col>, COUNT(*) ... GROUP BY <col>` (énumérer enum + cardinalité), `MIN/MAX` (plages dates/montants).
4. **Grep code Hellopro** (`BO/`, `FRONT/`) sur le nom de table + colonnes clés → sens métier, qui écrit/lit, jointures (→ `relations`), pièges.
5. **`bdd_get_table_doc`** si la table est déjà documentée → ne pas contredire l'existant.

**Prérequis live** : les outils ne voient la table que si elle est **active dans le registre** (pull config gateway ~60 s). Donc : créer + activer la table, attendre ~1 min, puis demander à Claude. Sinon repli sur code + catalogue (moins fondé), ou l'utilisateur colle la liste des colonnes.

## 6. Gotchas (ce qui fait rater un import)

| # | Piège | Parade |
|---|-------|--------|
| G1 | `database_id` ≠ celui de la table → **ligne dupliquée** dans un autre bucket DB (l'upsert est keyé sur `(database_id, table_name)`) | Toujours le même DB (1/5/10) que la création |
| G2 | Update = **remplacement total du jeu de champs** (delete + reinsert dans `repo.Import`) | Le JSON liste **toutes** les colonnes à garder ; Claude sort toujours le set complet de `describe_table`. Colonnes omises = supprimées |
| G3 | Colonne absente du catalogue amont → **droppée + signalée** (`field X not in upstream catalog (skipped)`) | Noms exacts (grounding live) ; sinon refresh catalogue amont |
| G4 | Identifiant hors `^[a-zA-Z0-9_]{1,128}$` (`bddIdentRe`) | Validé avant émission |
| G5 | Corps > **1 MiB** (`bddImportMaxBody`) | Découper le lot en plusieurs fichiers |
| G6 | `enum`/`set` normalisés au mot-clé (type tronqué) | Mettre les valeurs réelles dans `desc` |
| G7 | Doc pas visible immédiatement côté agent | PHP re-pull config ~60 s / schema-doc ~300 s ; ou déclencher `generate_schema_doc_2.php?token=...` |

Comportement transactionnel : échecs par ligne collectés, transaction **non** annulée (un mauvais bloc table n'empêche pas les autres). Réponse : `{inserted, updated, errors[]}`.

## 7. Langue & ton des descriptions

Public = **le LLM** qui appellera les outils → **FR, concis, orienté requête**.
- **Champ** : sens métier + unité/format + valeurs enum + FK (table cible) + piège (nullable, flag soft-delete, TZ des dates).
- **Table** : rôle + grain (1 ligne = quoi) + relations clés + `default_order_by` utile.

## 8. Application (deux voies, au choix de l'utilisateur)

**Voie 1 — Drag-drop (simple, sûr)** : dashboard → onglet BDD → « Importer JSON » → glisser le fichier `.json` (modale `BDDTablesView.vue`, accepte `{tables:[...]}` export OU `{_meta, <table>:{...}}` doc).

**Voie 2 — `curl` (zéro UI, lancé par l'utilisateur)** : Claude fournit une commande prête ; l'utilisateur la lance via `! curl ...` avec **son** auth admin (reste chez lui). Marche en batch. Endpoint : `POST {GATEWAY}/api/v1/bdd/used/tables/import-doc`, corps = le fichier doc-JSON. L'auth est celle du dashboard admin (cookie `gw_session`, ou Bearer JWT) — **mécanisme exact à confirmer au moment de construire la commande**. Voie secondaire : la voie 1 (drag-drop) reste la recommandation par défaut.

Dans les deux cas, l'utilisateur renvoie le résultat `{inserted, updated, errors}` à Claude pour la boucle de correction.

## 9. Hors-scope (YAGNI)

- Écriture directe automatisée par Claude (impossible — §1). Pas de tentative de scripter un login admin.
- Pas de nouvel outil MCP d'écriture côté gateway/PHP.
- Pas de modification du code du gateway, du PHP, ou du dashboard. Ce design n'introduit **aucun changement de code** : il s'appuie sur les endpoints et formats existants.
- Génération en masse de la doc de tout le catalogue d'un coup : on procède table par table (ou petit lot) avec validation humaine.

## 10. Critères de succès

- Pour une table donnée, Claude produit un fichier doc-JSON **importable sans erreur** (0 colonne droppée) après au plus une boucle de correction.
- Les descriptions champ/table sont en FR, exactes (fondées sur structure live + données réelles + code), et utiles à un agent pour requêter.
- Le ritual est rejouable à l'identique pour chaque nouvelle table, à l'unité ou en lot.
- Aucun changement de code dans les trois composants ; uniquement de la donnée de registre.

## 11. Livrables (pour le plan)

1. Un **gabarit doc-JSON** réutilisable (fichier modèle versionné dans le repo, ou snippet dans un runbook).
2. Un **runbook** court : les étapes du ritual + les 7 gotchas + les deux voies d'application.
3. **Exécution de la première table** comme exemple concret de bout en bout (grounding → fichier → import → vérification via `bdd_get_table_doc`).
