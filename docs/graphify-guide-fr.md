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

1. Lit `graphify-out/manifest.json` — source unique de vérité pour la portée du graphe.
2. Intersecte les fichiers modifiés du commit avec le manifeste. Hors scope = ignoré silencieusement ; pas de reconstruction.
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

## Étendre — ajouter un service au graphe unifié

Nous avons choisi de faire grandir **un seul graphe unifié** plutôt qu'un graphe isolé par service. Raisons : les requêtes cross-service (par ex. « comment `<service>` utilise Redis ? ») exigent un graphe où les concepts du service et ceux de `libs/common-utils` sont dans le même espace de noms, liés par des arêtes cross. Des graphes séparés par service ne peuvent pas répondre aux questions cross-service sans couture manuelle.

**Pour ajouter un service** (exemple : `llm-service`) :

```bash
# Depuis la racine du repo — le répertoire de travail compte, il pointe vers graphify-out/
/graphify apps-microservices/llm-service --update
```

Le chemin `--update` du skill :

1. Lit le manifeste racine, remarque que les fichiers du service n'y sont pas.
2. Re-détecte le sous-répertoire du service (crawler-service à 37 fichiers a pris ~1 min bout à bout).
3. Dispatche un sous-agent sémantique pour ses docs (`CLAUDE.md`, `README.md`, `requirements.txt`). Peu de tokens LLM — compter moins de 0,10 $ par service.
4. Fusionne les nouveaux nœuds/arêtes dans `graphify-out/graph.json` et ajoute les fichiers au manifeste.

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

Après ajout d'un service, relire `GRAPH_REPORT.md` — les nouvelles communautés peuvent avoir besoin de noms dans `graphify-out/labels.json`. Mettre à jour et recommiter.

## Mettre à jour le graphe

Trois déclencheurs, par ordre de couverture :

1. **Changements code-only dans le scope** → **automatique** via le hook post-commit scoppé. Aucun coût LLM. Tourne en ~5-15s après le commit.
2. **Changements doc / CLAUDE.md dans le scope** → le hook touche `graphify-out/.needs_update` et affiche un rappel. Lancer ensuite `/graphify --update` depuis une session Claude Code quand c'est pratique. La ré-extraction sémantique est facturée LLM mais cache-aware, donc le coût est proportionnel aux éditions.
3. **Reconstruction complète** → `/graphify .` depuis zéro. À éviter sauf si le graphe est corrompu ou si la portée a changé drastiquement — ré-extrait tout.

**Ne PAS lancer `graphify update .` en CLI** dans ce repo. La CLI amont invoque `_rebuild_code` qui rescanne tout le répertoire (pas de manifeste). Dans ce monorepo, ça aspire `apps-microservices/` et fait exploser le graphe. Le hook scoppé et la slash command sont les voies supportées. Pour un rebuild AST à la demande sans commiter, appeler directement le script :

```bash
python scripts/graphify_rebuild_scoped.py path/to/file1.py path/to/file2.ts
```

Les arguments sont les fichiers modifiés — il respecte le manifeste et ne fait rien pour les chemins hors scope.

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
├── graphify_rebuild_scoped.py                 # rebuild AST scoppé (respect du manifeste)
├── test_graphify_rebuild_scoped.py            # tests unitaires du script ci-dessus
├── graphify-post-commit.sh                    # corps du hook post-commit
└── install-graphify-hook.sh                   # installeur (copie le hook vers .git/hooks/)
```

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
| Hook post-commit déclenché mais n'a rien fait | Soit aucun fichier modifié n'est dans le manifeste (attendu pour les commits `apps-microservices/`), soit graphify n'est pas installé sur votre Python. Vérifier avec `python -c "import graphify"`. |
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
