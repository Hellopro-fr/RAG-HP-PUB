# Runbook — Enrichir la doc d'une table BDD (MCP)

> Procedure rejouable. Spec: `../specs/2026-06-05-bdd-doc-enrichment-workflow-design.md`. Gabarit: `bdd-doc-template.json`.
> Aucun changement de code. On edite uniquement la donnee du registre via l'import JSON du dashboard.

## Le ritual

Unite = une table (A). Lot = plusieurs tables dans un seul fichier `{_meta, t1:{...}, t2:{...}}` (B). Meme gabarit.

1. **Creer la table** dans le dashboard (nom + database_id + champs). Optionnel (l'import upsert cree la table) mais recommande: verifie les noms de colonnes + active la table.
2. **Donner le contexte** a Claude: nom de table + database_id (1/5/10) + colonnes ciblees (option) + connaissance metier.
3. **Grounding** par Claude (voir plus bas).
4. **Livraison**: fichier doc-JSON (copie du gabarit, rempli) + apercu FR (tableau colonne -> description) a valider.
5. **Application**: drag-drop dans "Importer JSON" (ou voie 2 curl). Coller le retour `{inserted, updated, errors}`. Colonne droppee (G3) -> corriger le nom -> re-deposer.

## Grounding (ordre, par table)

1. `bdd_describe_table` -> noms + types + cles exacts (evite G3).
2. `bdd_sample_data` -> 5 lignes reelles -> formats, unites, valeurs, colonnes FK-like.
3. `bdd_query_readonly` ad hoc: `SELECT <col>, COUNT(*) ... GROUP BY <col>` (enum + cardinalite), `MIN/MAX` (plages).
4. Grep code Hellopro (`BO/`, `FRONT/`) sur table + colonnes -> sens metier, qui ecrit/lit, jointures.
5. `bdd_get_table_doc` si deja documentee -> ne pas contredire.

**Prerequis live**: les outils ne voient la table que si elle est ACTIVE dans le registre (pull config gateway ~60 s). Creer + activer, attendre ~1 min, puis demander. Sinon repli code + catalogue.

## Langue & ton

Public = le LLM. FR, concis, oriente requete.
- Champ: sens metier + unite/format + valeurs enum + FK (table cible) + piege (nullable/soft-delete/TZ).
- Table: role + grain (1 ligne = quoi) + relations cles + default_order_by utile.

## Gotchas (ce qui fait rater un import)

| # | Piege | Parade |
|---|-------|--------|
| G1 | `database_id` != celui de la table -> ligne dupliquee (upsert keye sur (database_id, table_name)) | Meme DB (1/5/10) que la creation |
| G2 | Update = remplacement TOTAL du jeu de champs (delete + reinsert) | Le JSON liste TOUTES les colonnes a garder; omises = supprimees |
| G3 | Colonne hors catalogue amont -> droppee + signalee ("field X not in upstream catalog (skipped)") | Noms exacts (grounding live); sinon refresh catalogue amont |
| G4 | Identifiant hors `^[a-zA-Z0-9_]{1,128}$` | Verifier avant emission |
| G5 | Corps > 1 MiB | Decouper le lot en plusieurs fichiers |
| G6 | enum/set normalises au mot-cle (type tronque) | Mettre les valeurs reelles dans `desc` |
| G7 | Doc pas visible tout de suite cote agent | PHP re-pull config ~60 s / schema-doc ~300 s; ou declencher `generate_schema_doc_2.php?token=...` |

Transactionnel: echecs par ligne collectes, transaction NON annulee. Reponse: `{inserted, updated, errors[]}`.

## Application

**Voie 1 — drag-drop (defaut)**: dashboard -> onglet BDD -> "Importer JSON" -> glisser le `.json`. Accepte export `{tables:[...]}` ou doc `{_meta, <table>:{...}}`.

**Voie 2 — curl (lance par l'operateur)**: `! curl -X POST {GATEWAY}/api/v1/bdd/used/tables/import-doc -H "<auth admin: cookie gw_session ou Bearer JWT, a confirmer>" -H "Content-Type: application/json" --data-binary @mon-fichier.doc.json`. Le token reste chez l'operateur. Marche en batch.

Dans les deux cas: renvoyer `{inserted, updated, errors}` a Claude pour la boucle de correction.
