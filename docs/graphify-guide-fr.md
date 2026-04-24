# graphify — Guide d'équipe (Français)

Un graphe de connaissance persistant du monorepo, construit à partir du code (AST) et de la documentation (LLM). Survit aux sessions. Interrogeable depuis toute session Claude Code. Déjà intégré — aucune action requise pour en bénéficier passivement.

## Ce que vous obtenez aujourd'hui

**Un graphe unifié** à `graphify-out/`, commité sur `features/poc` :

- 1700 nœuds, ~3150 arêtes, 86 communautés
- Couvre : `libs/`, `protos/`, `tools/`, `model-optimizer/`, `docs/`, et `apps-microservices/crawler-service/`
- 10 liens cross-service explicites depuis les concepts crawler-service vers les concepts backbone (par ex. `crawler_capacity_counter --uses--> cache_service.py`, `crawler_archiving_gcs_fallback --shares_data_with--> tools_upload_daemon`) — c'est ce qui permet de répondre à « comment le crawler utilise Redis » en une seule requête.

Le dossier du graphe contient :

- `graph.html` — visualisation interactive, à ouvrir dans un navigateur
- `graph.json` — données brutes (consommées par la CLI + MCP)
- `GRAPH_REPORT.md` — rapport d'audit avec god nodes, surprises, questions suggérées
- `labels.json` — noms de communautés (tracké ; préservé entre les rebuilds)
- `memory/` — Q&A sauvegardées (auto-promues en nœuds au prochain update sémantique)

Local uniquement (gitignoré) : `cache/`, `manifest.json`, `cost.json`, `.needs_update`.

## Pourquoi l'utiliser

| Problème | Solution via le graphe |
|----------|------------------------|
| « Comment X atteint-il Y à travers les fichiers ? » | `graphify path "X" "Y"` — plus court chemin de dépendance avec tags de confiance |
| « Quel est le blast radius de modifier `Configuration` ? » | `graphify explain "Configuration"` — liste tous les consommateurs avec emplacement source |
| « Qui utilise cette fonction de librairie ? » | Traverse les arêtes `calls` / `uses` / `references` au lieu de greper 90 dossiers de services |
| Nouveau sur une section du codebase | `GRAPH_REPORT.md` montre les top-10 god nodes + structure des communautés en 5 minutes |
| Coût en tokens d'un scan brut | Le graphe compresse 59x vs lire le texte du corpus |

**Tag d'honnêteté sur chaque arête** :
- `EXTRACTED` — trouvé directement dans la source (import, appel de méthode via AST)
- `INFERRED` — le LLM a raisonné depuis le contexte (docs, patterns de données partagés)
- `AMBIGUOUS` — à vérifier

## Installation initiale (une fois par développeur)

```bash
# 1. Installer la CLI graphify
pip install graphifyy

# 2. Installer le hook post-commit scoppé (mises à jour autonomes, aucun coût LLM pour les changements code)
bash scripts/install-graphify-hook.sh
```

Vérifier :

```bash
graphify --version                # affiche une version
ls .git/hooks/post-commit         # hook présent après install
```

### Hook scoppé vs hook amont

La commande amont `graphify hook install` installe un hook post-commit qui appelle `_rebuild_code(Path("."))` — rescanne tout le répertoire de travail à chaque commit. Dans ce monorepo de 2129 fichiers, ça aspire `apps-microservices/` dans le graphe, fait exploser `graph.json` de ~20x et dérive silencieusement la portée du graphe à chaque commit. **Ne pas lancer `graphify hook install`.**

`scripts/install-graphify-hook.sh` installe un hook différent (`scripts/graphify-post-commit.sh`) qui délègue à `scripts/graphify_rebuild_scoped.py`. Le hook scoppé :

1. Dérive la portée depuis `graphify-out/graph.json` — l'attribut `source_file` de chaque nœud est collecté en un ensemble de chemins dans le scope. `graph.json` est tracké, donc chaque coéquipier obtient la bonne portée juste après `git pull`. `manifest.json` est gitignoré volontairement (mtime-based, invalide après clone selon la convention amont) et n'est utilisé qu'en fallback.
2. Intersecte les fichiers modifiés du commit avec cette portée. Hors scope = ignoré silencieusement ; pas de reconstruction.
3. Pour les fichiers code dans le scope : ré-extrait l'AST uniquement sur ces fichiers, fusionne sur place, préserve les arêtes sémantiques + cross-links intactes. Zéro coût LLM.
4. Pour les fichiers doc/config dans le scope : touche `graphify-out/.needs_update` et rappelle de lancer `/graphify --update` depuis une session Claude Code (la ré-extraction sémantique a besoin du LLM).
5. Régénère `graph.json`, `graph.html`, `GRAPH_REPORT.md` en réutilisant les noms de communauté depuis `graphify-out/labels.json`.

C'est la voie autonome : commiter normalement, la backbone + tout service graphé reste à jour sans y penser. Si le hook échoue pour une raison quelconque, le commit réussit quand même — le hook est side-effect-only.

## Intégration automatique avec Claude Code

Déjà câblé :

- **`CLAUDE.md` racine** possède une section `## graphify` qui demande à Claude de consulter `GRAPH_REPORT.md` avant les questions d'architecture.
- **`.claude/settings.json`** possède un hook `PreToolUse` sur `Glob|Grep` qui injecte un rappel de consulter le graphe avant toute recherche brute.

Aucune action requise. Chaque session démarre graph-aware.

## Interroger le graphe manuellement

Quatre commandes slash dans toute session Claude Code :

```bash
/graphify query "Comment le DLQ archiver atteint-il Elasticsearch ?"
/graphify query "Qu'est-ce qui appelle get_embedding ?" --dfs
/graphify path "DLQArchiver" "get_elasticsearch_client"
/graphify explain "Configuration"
```

Modes :
- BFS (par défaut) — contexte large, « à quoi X est connecté »
- DFS (`--dfs`) — tracer une chaîne spécifique A→B
- `--budget 1500` — limiter les tokens de la réponse

Les réponses sont persistées dans `graphify-out/memory/` et promues en nœuds au prochain `--update`. Le graphe apprend de vos requêtes.

## Services actuellement dans le graphe

La source unique de vérité est `graphify-out/services-policy.yml` (tracké, lisible par machine, lu par le workflow CI coverage-check). Les tableaux ci-dessous sont le résumé pour humain ; les garder en phase avec le YAML lors de l'ajout d'un service.

### Dans le graphe (2)

| Service | Ajouté | Pourquoi |
|---------|--------|----------|
| `apps-microservices/crawler-service` | 2026-04-24 | Node.js + Python, machine à états complexe, cluster récent de corrections (relance OOM, élection de leader, staging d'archives). |
| `apps-microservices/graph-rag-api-recherche-rust-service` | 2026-04-24 | Rust (Actix-web / tonic). Récupération centrale. Stack unique ; cross-links vers les clients gRPC de libs/rust-common-utils et vers les providers LLM Python. |

### Hors graphe (89)

Regroupés par raison. Voir `graphify-out/services-policy.yml` pour la liste complète avec détails par service.

| Code raison | Signification | Nombre |
|-------------|---------------|-------:|
| `too_small` | < 10 fichiers et pas de CLAUDE.md riche. Un grep brut suffit. | 11 |
| `frontend` | Frontend Next.js / React, toolchain séparée. | 5 |
| `debug_variant` | Variante debug ou test d'un autre service. | 1 |
| `template_scaffold` | Template servant à scaffolder de nouveaux services, pas un service vivant. | 1 |
| `templated_wrapper` | Wrapper FastAPI / processor suivant un pattern commun ; grapher une référence, ignorer les frères. | 63 |
| `candidate_deferred` | Service large / unique qui vaudrait la peine d'être graphé, pas prioritaire. Promouvoir quand une requête cross-service fait émerger le besoin. | 8 |

Avant de lancer `/graphify <path> --update`, vérifier que le service n'est pas déjà dans une de ces listes :

```bash
python scripts/graphify_check_service.py apps-microservices/<name>
```

Le script lit la policy et affiche un verdict. Il renvoie non-zéro uniquement quand le chemin est totalement absent de la policy — c'est le signal qu'il faut le classifier.

## Étendre — ajouter un service au graphe unifié

Nous avons choisi de faire grandir **un seul graphe unifié** plutôt qu'un graphe isolé par service. Les requêtes cross-service (par ex. « comment `<service>` utilise Redis ? ») exigent un graphe où les concepts du service et ceux de `libs/common-utils` vivent dans le même espace de noms, liés par des arêtes cross. Des graphes séparés par service ne peuvent pas répondre aux questions cross-service sans couture manuelle.

### Checklist (faire les quatre étapes dans un seul commit)

1. **Mettre à jour la policy.** Déplacer le service depuis `not_graphed:` (ou l'ajouter) vers `graphed:` dans `graphify-out/services-policy.yml`. Inclure `added_at` et une ligne de justification.

2. **Fusionner le service dans le graphe.** Depuis la racine du repo :

    ```bash
    /graphify apps-microservices/<service> --update
    ```

    Le chemin `--update` du skill :
    1. Lit la portée du graphe racine (depuis `graph.json`), remarque que les fichiers du service n'y sont pas.
    2. Re-détecte le sous-répertoire du service (crawler-service à 37 fichiers a pris ~1 min bout à bout).
    3. Dispatche un sous-agent sémantique pour ses docs (`CLAUDE.md`, `README.md`, `requirements.txt`). Peu de tokens LLM — compter moins de 0,10 $ par service.
    4. Fusionne les nouveaux nœuds/arêtes dans `graphify-out/graph.json` et ajoute les fichiers au manifeste.

    Appliquer ensuite les deux pièges connus après la fin du sous-agent (IDs cross-link inventés + re-labellisation des communautés — recettes dans la section « Pièges lors de la fusion d'un service »).

3. **Mettre à jour le workflow CI de rebuild.** Ajouter le path glob du nouveau service au filtre `paths:` de `.github/workflows/graphify-auto-rebuild.yml`. Oublier cette étape est silencieux : le service est dans `graph.json` mais ses commits ne déclencheront plus de rebuild CI, donc le graphe se périme peu à peu dès que quelqu'un édite ce service sur `main` / `features/poc`.

4. **Mettre à jour le tableau « Dans le graphe » et le tableau de comptage** sous « Hors graphe » de ce guide. Reporter la même mise à jour dans le guide anglais.

### Que se passe-t-il si un dev crée un nouveau service et oublie de le classifier ?

Il ne peut pas merger. Le workflow CI `.github/workflows/graphify-coverage-check.yml` scanne `apps-microservices/*` à chaque PR qui touche cette arborescence ou le fichier de policy, et fait échouer le build si un répertoire est absent de `graphify-out/services-policy.yml`. La PR reste rouge jusqu'à ce que le dev choisisse une des deux voies :

- **Le grapher** → suivre la checklist quatre étapes ci-dessus (policy + `/graphify --update` + paths workflow + tableaux du guide).
- **L'ignorer** → ajouter une entrée dans `not_graphed:` avec un code raison (`too_small`, `frontend`, `debug_variant`, `template_scaffold`, `templated_wrapper`, ou `candidate_deferred`) et un `details` optionnel.

L'une ou l'autre des voies débloque la PR. Le coverage-check passe à la réexécution.

Si un dev est incertain, le défaut conservateur est `candidate_deferred` avec un court `details` expliquant « en attente de revue ». Le service est sorti du graphe mais signalé pour reconsidération.

Après la fusion, tout nouveau concept du `CLAUDE.md` du service qui référence des modules backbone est extrait automatiquement en cross-link (même mécanisme qui a produit les 10 arêtes crawler → libs/tools existantes).

Si le CLAUDE.md du service est maigre, les cross-links le seront aussi — investir dans l'écriture du CLAUDE.md d'abord, grapher ensuite.

**Quand ajouter un service :**

- ≥ 20 fichiers
- Développement actif / questions fréquentes
- État interne non trivial (conditions de course, élection de leader, orchestration, logique métier)

**Quand ignorer :**

- Wrapper FastAPI templaté (lire un service comme modèle, ignorer les autres)
- < 10 fichiers (un grep brut suffit)
- Service déprécié / mort

### Pièges à anticiper lors de la fusion d'un service (à lire avant d'en ajouter un)

Les deux services fusionnés à ce jour (`crawler-service`, `graph-rag-api-recherche-rust-service`) ont tous les deux rencontré les deux mêmes écueils. Les anticiper.

**1. IDs cibles de cross-links inventés.** Le sous-agent sémantique invente des IDs courts et intuitifs pour les concepts backbone (par ex. `cache_service_redisclient`, `embedding.rs`, `libs_common_utils`) au lieu d'utiliser les IDs de nœuds réels (par ex. `cache_service_py`, `libs_rust_common_utils_src_grpc_clients_embedding_rs`, `common_utils_lib`). Les IDs inventés produisent des arêtes cross-links pendantes qui font échouer silencieusement les requêtes.

Contournement — greper le graphe existant pour chaque concept que le sous-agent tente de lier, construire un dict de remap, réécrire les arêtes avant fusion :

```python
import json
sem = json.loads(open('.graphify_<svc>_semantic.json').read())
REMAP = {
    'cache_service_redisclient': 'cache_service_py',
    'embedding.rs': 'libs_rust_common_utils_src_grpc_clients_embedding_rs',
    'libs_common_utils': 'common_utils_lib',
    # ...
}
for e in sem['edges']:
    if e['source'] in REMAP: e['source'] = REMAP[e['source']]
    if e['target'] in REMAP: e['target'] = REMAP[e['target']]
```

Tenir une liste de remap à jour dans ce document. Pré-amorcer le prompt du sous-agent avec une liste d'IDs de nœuds backbone connus pour réduire les inventions — le prompt utilisé pour `graph-rag-api-recherche-rust-service` les liste explicitement et a fait passer le taux d'invention de 10/10 à 6/16.

**2. Le re-clustering mélange les labels.** Chaque fusion relance le clustering. La communauté `c0` peut devenir `c4`, `c7` peut devenir `c1`, etc. Les labels dans `graphify-out/labels.json` sont clés par ID de communauté — après une fusion, ils pointent vers la *nouvelle* communauté à cet ID, qui traite probablement d'un autre sujet.

Contournement — après chaque fusion, régénérer un échantillon par communauté et re-labelliser :

```bash
# dump les 4 premiers labels de nœud par communauté pour cross-check
python -c "import json, os; d=json.loads(open('graphify-out/graph.json').read()); \
  from collections import defaultdict; c=defaultdict(list); \
  [c[n.get('community')].append(n['label']) for n in d['nodes'] if n.get('community') is not None]; \
  [print(f'c{k} ({len(v)}): {v[:4]}') for k,v in sorted(c.items(), key=lambda x:-len(x[1]))[:30]]"
```

Comparer à `labels.json`, réécrire où faux, commiter la mise à jour des labels avec la mise à jour du graphe.

À terme, les labels devraient être dérivés du contenu des communautés (top-N labels de nœuds) plutôt qu'assignés manuellement, pour survivre au re-clustering gratuitement. Pas rentable tant qu'on ne rencontre pas ce problème plusieurs fois de plus.

## Mettre à jour le graphe

Quatre déclencheurs, par ordre de couverture :

1. **Tout push backbone vers `main` ou `features/poc`** → **automatique** via le workflow CI à `.github/workflows/graphify-auto-rebuild.yml`. Seules ces deux branches déclenchent la CI — ce sont les branches d'intégration déployées ; les autres branches feature dépendent du hook local pour ne pas brûler des minutes CI sur du travail exploratoire. GitHub Actions lance le rebuild scoppé sur un runner éphémère (graphify installé là, pas chez nous) et commit les `graph.json` / `graph.html` / `GRAPH_REPORT.md` mis à jour sur la même branche avec `[skip graphify]` dans le message pour casser la boucle. Couvre le cas « serveur consume-only » — un agent serveur qui commit du code mais n'a pas graphify installé dépend entièrement de la CI pour la fraîcheur du graphe. Durée ~1 min par rebuild. Gratuit sur repos publics ; quelques centaines de minutes/mois sur privés.
2. **Changements code-only dans le scope, en local** → **automatique** via le hook post-commit scoppé (si installé avec `bash scripts/install-graphify-hook.sh`). Aucun coût LLM. Tourne en ~5-15s après le commit. Redondant avec la CI mais utile pour avoir le `graph.json` local frais avant le prochain push.
3. **Changements doc / CLAUDE.md dans le scope** → le hook local (et la CI) ne peuvent rafraîchir que l'AST ; la ré-extraction sémantique a besoin du LLM. CI / hook touchent `graphify-out/.needs_update` et loggent un rappel. Lancer ensuite `/graphify --update` depuis une session Claude Code quand pratique. Coût proportionnel à ce qui a été édité grâce au cache sémantique.
4. **Reconstruction complète** → `/graphify .` depuis zéro. À éviter sauf si le graphe est corrompu ou si la portée a changé drastiquement — ré-extrait tout.

**Ne PAS lancer `graphify update .` en CLI** dans ce repo. La CLI amont invoque `_rebuild_code` qui rescanne tout le répertoire (pas de manifeste). Dans ce monorepo, ça aspire `apps-microservices/` et fait exploser le graphe. Le hook scoppé et la slash command sont les voies supportées. Pour un rebuild AST à la demande sans commiter, appeler directement le script :

```bash
python scripts/graphify_rebuild_scoped.py path/to/file1.py path/to/file2.ts
```

Les arguments sont les fichiers modifiés — il respecte la portée du graphe et ne fait rien pour les chemins hors scope.

Le coût cumulé en tokens par run est tracé dans `graphify-out/cost.json` (gitignoré, local uniquement).

## Limitations à connaître

1. **La direction des arêtes peut être inversée**. Le graphe est non-orienté. Une arête `Configuration --uses--> MilvusCrud` signifie souvent l'inverse (CRUD utilise Configuration). Interpréter dans les deux sens.
2. **Les docstrings de tests gonflent les god nodes**. Exemple : `CrawlerManager` a 93 arêtes, dont certaines viennent de docstrings de `test_*.py` extraits en nœuds. Ignorer les voisins préfixés `test_` lors de l'inspection visuelle.
3. **Les arêtes INFERRED doivent être vérifiées** pour les décisions critiques. Lancer `graphify explain <node>` et grep pour confirmer avant de refactoriser un composant partagé.
4. **Les petits corpus ne bénéficient pas de la compression** (< 50k mots). La valeur du graphe est la clarté structurelle, pas les tokens.
5. **Cache miss au clone** — `cache/` est gitignoré. Le premier run après `git clone` ré-extrait tout. Les runs suivants sont instantanés.

## Structure des fichiers

```
graphify-out/                                  # graphe unifié (backbone + services graphés)
├── graph.html                                 # viz interactive
├── graph.json                                 # données brutes (entrée MCP/CLI)
├── GRAPH_REPORT.md                            # rapport d'audit
├── labels.json                                # noms de communautés (tracké)
├── memory/                                    # Q&A sauvegardées (tracké, promues en nœuds au prochain update)
├── cache/                                     # cache d'extraction local (gitignoré)
├── manifest.json                              # index mtime (gitignoré)
├── cost.json                                  # log de tokens (gitignoré)
└── .needs_update                              # flag écrit par le hook sur changements doc (gitignoré)

scripts/
├── graphify_rebuild_scoped.py                 # rebuild AST scoppé (respect de la portée du graphe)
├── test_graphify_rebuild_scoped.py            # tests unitaires du script ci-dessus
├── graphify-post-commit.sh                    # corps du hook post-commit
└── install-graphify-hook.sh                   # installeur (copie le hook vers .git/hooks/)

.github/workflows/
└── graphify-auto-rebuild.yml                  # rebuild autonome CI sur push
```

## Qui reconstruit le graphe, quand

Trois voies indépendantes maintiennent le graphe à jour. Idempotentes et sûres à exécuter ensemble.

| Déclencheur | Où ça tourne | Ce qui est rafraîchi | Coût |
|-------------|--------------|----------------------|------|
| `git push` vers `main` ou `features/poc` touchant des fichiers dans le scope | Runner GitHub Actions | AST code + régénération HTML / rapport, commit sur la même branche | ~1 min CI par push, free tier |
| `git commit` sur une machine avec le hook scoppé installé | Machine locale | Idem CI, mais instantané et visible localement avant push | ~5-15 s |
| `/graphify --update` depuis une session Claude Code | Machine locale | Ré-extraction sémantique (LLM) des docs / CLAUDE.md modifiés | Tokens LLM proportionnels aux docs édités |

Les participants « consume-only » — typiquement un agent serveur qui édite du code mais n'a pas graphify installé — dépendent **uniquement de la CI**. Ils commit, push, pull ; le graphe est maintenu sans qu'ils lancent jamais graphify. Les machines de dev bénéficient des trois voies et ne sont jamais le goulot.

## Optionnel : serveur MCP pour requêtes agent en direct

Exposer `graph.json` comme serveur MCP stdio pour que d'autres agents interrogent sans passer par du texte :

```bash
python -m graphify.serve graphify-out/graph.json
```

Configurer dans `claude_desktop_config.json` de Claude Desktop :

```json
{
  "mcpServers": {
    "graphify-backbone": {
      "command": "python",
      "args": ["-m", "graphify.serve", "/chemin/absolu/vers/graphify-out/graph.json"]
    }
  }
}
```

Expose les outils : `query_graph`, `get_node`, `get_neighbors`, `get_community`, `god_nodes`, `graph_stats`, `shortest_path`.

## Dépannage

| Symptôme | Correction |
|----------|-----------|
| `graphify: command not found` | `pip install graphifyy` |
| `graphify update .` lancé et graphe explosé (10k+ nœuds) | Vous avez déclenché le piège du rebuild non-scoppé. `git checkout -- graphify-out/` pour restaurer. Utiliser `/graphify --update` depuis une session Claude Code, ou `python scripts/graphify_rebuild_scoped.py <fichiers>` directement. |
| Équipier a lancé `graphify hook install` par erreur | `graphify hook uninstall` puis réinstaller le nôtre : `bash scripts/install-graphify-hook.sh`. `git checkout -- graphify-out/` si le graphe a été pollué. |
| Hook post-commit déclenché mais n'a rien fait | Soit aucun fichier modifié n'est dans la portée du graphe (attendu pour les commits `apps-microservices/` sur services non-graphés), soit graphify n'est pas installé sur votre Python. Vérifier avec `python -c "import graphify"`. |
| Sortie du hook mentionne `.needs_update` | Un doc/CLAUDE.md du scope a changé. La ré-extraction sémantique a besoin du LLM ; lancer `/graphify --update` dans une session Claude Code quand pratique. |
| Nouveau service ajouté mais ses nœuds ne sont pas dans le graphe | Vous avez lancé `/graphify <service-path>` sans `--update`. Utiliser le flag update pour qu'il fusionne dans le graphe racine au lieu d'en créer un isolé. |
| Scroll vertical cassé sur PowerShell 5.1 | Utiliser Windows Terminal, ou désinstaller `graspologic` : `pip uninstall graspologic` |
| Direction d'arête fausse | Inhérent au graphe non-orienté ; interpréter bidirectionnellement ou reconstruire avec `--directed` |
| Exclure un fichier de l'extraction | Créer `.graphifyignore` à la racine du repo (même syntaxe que `.gitignore`) |

## Quand NE PAS utiliser graphify

- Correction rapide d'un bug dans un fichier que vous connaissez
- Questions non-architecturales (« comment fonctionne la compréhension de liste Python ? »)
- Petits scripts (< 10 fichiers) où un grep suffit

## Pour aller plus loin

- Documentation amont : https://github.com/safishamsi/graphify
- Section `## graphify` du `CLAUDE.md` racine — règles condensées pour les assistants IA
- `GRAPH_REPORT.md` de chaque dossier de graphe — état actuel du graphe
