# graphify — Guide d'équipe (Français)

Un graphe de connaissance persistant du monorepo, construit à partir du code (AST) et de la documentation (LLM). Survit aux sessions. Interrogeable depuis toute session Claude Code. Déjà intégré — aucune action requise pour en bénéficier passivement.

## Ce que vous obtenez aujourd'hui

Deux graphes préconstruits, commités sur `features/poc` :

| Graphe | Portée | Nœuds / Arêtes / Communautés | Emplacement |
|--------|--------|------------------------------|-------------|
| **Backbone** | `libs/`, `protos/`, `tools/`, `model-optimizer/`, `docs/` | 1240 / 2120 / 85 | `graphify-out/` |
| **crawler-service** | `apps-microservices/crawler-service/` | 491 / 1056 / 18 | `apps-microservices/crawler-service/graphify-out/` |

Chaque dossier de graphe contient :

- `graph.html` — visualisation interactive, à ouvrir dans un navigateur
- `graph.json` — données brutes (consommées par la CLI `graphify` et MCP)
- `GRAPH_REPORT.md` — rapport d'audit en texte clair avec god nodes, surprises, questions suggérées
- `memory/` — Q&A sauvegardées des requêtes passées (promues en nœuds au prochain `--update`)

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
pip install graphifyy
```

C'est tout. Rien à installer dans le repo. Vérifier :

```bash
graphify --version   # doit afficher une version
which graphify       # doit résoudre vers votre chemin pip install
```

### Pourquoi pas de git hooks ?

graphify propose un hook post-commit optionnel (`graphify hook install`) qui reconstruit le graphe après chaque commit. **Nous ne l'utilisons pas dans ce monorepo.**

**Raison** : le `_rebuild_code` du hook rescanne tout le répertoire de travail. Dans ce monorepo de 2129 fichiers, un seul commit sur la backbone extrait l'AST des 1790 fichiers code (incluant les 90+ services hors du scope backbone), faisant exploser le `graph.json` commité par ~20x et dérivant la portée du graphe hors de ses limites.

**Contournement** : utiliser `/graphify --update` depuis une session Claude Code. Cette commande lit le manifeste scoppé (`graphify-out/manifest.json`) et ré-extrait uniquement les fichiers modifiés dans le jeu d'extraction initial — pas de dérive de portée, même zéro coût LLM pour les changements code-only. Voir **Mettre à jour le graphe** plus bas.

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

## Étendre — grapher un nouveau service

```bash
cd apps-microservices/<service>
# Avoir un CLAUDE.md dans le service est recommandé pour une extraction de concepts plus riche
/graphify .
```

La sortie atterrit dans `apps-microservices/<service>/graphify-out/`. À commiter.

**Quand grapher un service :**

- ≥ 20 fichiers
- Développement actif / questions fréquentes
- État interne complexe (conditions de course, élection de leader, orchestration)

**Quand ignorer :**

- Wrapper FastAPI templaté (lire un service comme modèle, ignorer les autres)
- < 10 fichiers (un grep brut suffit)
- Service déprécié / mort

## Mettre à jour le graphe

Deux déclencheurs, par ordre de préférence :

1. **Toute modification dans le scope backbone** → lancer `/graphify --update` depuis une session Claude Code. Utilise une détection incrémentale basée sur le manifeste :
   - Changements code-only : ré-extraction AST des fichiers modifiés, **zéro coût LLM**, ~5-15s.
   - Changements doc / CLAUDE.md : ré-extraction sémantique (LLM) des docs modifiées seulement. Cache hits pour le reste. Coût proportionnel à ce qui a été édité.
2. **Reconstruction complète** → `/graphify .` depuis zéro. À éviter sauf changement structurel majeur — ré-extrait tout.

**Ne PAS lancer `graphify update .` en CLI** dans ce repo. La CLI invoque `_rebuild_code` qui rescanne tout le répertoire (pas de manifeste). Dans ce monorepo, ça aspire `apps-microservices/` et fait exploser le graphe. Toujours utiliser la slash command `/graphify --update` depuis une session Claude Code — elle passe par le skill qui lit d'abord le manifeste.

Le coût cumulé en tokens par run est tracé dans `graphify-out/cost.json` (gitignoré, local uniquement).

## Limitations à connaître

1. **La direction des arêtes peut être inversée**. Le graphe est non-orienté. Une arête `Configuration --uses--> MilvusCrud` signifie souvent l'inverse (CRUD utilise Configuration). Interpréter dans les deux sens.
2. **Les docstrings de tests gonflent les god nodes**. Exemple : `CrawlerManager` a 93 arêtes, dont certaines viennent de docstrings de `test_*.py` extraits en nœuds. Ignorer les voisins préfixés `test_` lors de l'inspection visuelle.
3. **Les arêtes INFERRED doivent être vérifiées** pour les décisions critiques. Lancer `graphify explain <node>` et grep pour confirmer avant de refactoriser un composant partagé.
4. **Les petits corpus ne bénéficient pas de la compression** (< 50k mots). La valeur du graphe est la clarté structurelle, pas les tokens.
5. **Cache miss au clone** — `cache/` est gitignoré. Le premier run après `git clone` ré-extrait tout. Les runs suivants sont instantanés.

## Structure des fichiers

```
graphify-out/                                  # graphe backbone
├── graph.html                                 # viz interactive
├── graph.json                                 # données brutes (entrée MCP/CLI)
├── GRAPH_REPORT.md                            # rapport d'audit
├── memory/                                    # Q&A sauvegardées (tracké)
├── cache/                                     # cache d'extraction local (gitignoré)
├── manifest.json                              # index mtime (gitignoré)
└── cost.json                                  # log de tokens (gitignoré)

apps-microservices/<service>/graphify-out/     # graphe par service
└── (même structure)
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
| `graphify update .` lancé et graphe explosé (10k+ nœuds) | Vous avez déclenché le piège du rebuild non-scoppé. `git checkout -- graphify-out/` pour restaurer. Utiliser `/graphify --update` depuis une session Claude Code à la place. |
| Un membre de l'équipe a installé les git hooks — graphe rempli d'`apps-microservices/` | `graphify hook uninstall`, `git checkout -- graphify-out/`. Hooks intentionnellement non utilisés dans ce repo — voir « Pourquoi pas de git hooks ? » ci-dessus. |
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
