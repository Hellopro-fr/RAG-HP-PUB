# Guide d'equipe -- Claude Code sur RAG-HP-PUB

> **Version :** 2.0 | **Derniere mise a jour :** 2026-04-02
> **Public cible :** Tous les developpeurs du projet RAG-HP-PUB (juniors inclus)

---

## Table des matieres

1. [Introduction](#1-introduction)
2. [Demarrage rapide](#2-demarrage-rapide)
3. [Les commandes disponibles](#3-les-commandes-disponibles-commands)
4. [Les agents disponibles](#4-les-agents-disponibles-agents)
5. [Les regles](#5-les-regles-clauderules)
6. [Workflow quotidien standardise](#6-workflow-quotidien-standardise)
7. [Travail multi-services](#7-travail-multi-services)
8. [Services remote-only : les regles absolues](#8-services-remote-only--les-regles-absolues)
9. [Harmonisation de l'equipe](#9-harmonisation-de-lequipe)
10. [Maintenance du systeme CLAUDE.md](#10-maintenance-du-systeme-claudemd)
11. [Erreurs courantes a eviter](#11-erreurs-courantes-a-eviter)
12. [Astuces avancees](#12-astuces-avancees)
13. [Checklist pour les nouveaux membres](#13-checklist-pour-les-nouveaux-membres)
14. [Reference rapide (Cheat Sheet)](#14-reference-rapide-cheat-sheet)

---

## 1. Introduction

### Qu'est-ce que Claude Code ?

Claude Code est l'interface CLI officielle d'Anthropic pour interagir avec Claude directement depuis le terminal. Sur RAG-HP-PUB, il sert d'assistant de developpement integre : il connait l'architecture de nos 90+ microservices, respecte nos conventions de code, et s'adapte au contexte de chaque service grace a un systeme de memoire hierarchique.

### Le systeme de memoire

Claude Code charge automatiquement plusieurs couches de configuration au demarrage d'une session :

| Couche | Fichier | Portee | Contenu |
|--------|---------|--------|---------|
| Globale personnelle | `~/.claude/CLAUDE.md` | Tous les projets de l'utilisateur | Preferences personnelles (style, principes, langue) |
| Continuite de session | `~/.claude/primer.md` | Sessions successives | Etat du travail en cours, prochaine etape, blocages |
| Projet (racine) | `CLAUDE.md` (racine du repo) | Tout le repo RAG-HP-PUB | Architecture globale, carte des services, conventions |
| Service | `apps-microservices/<service>/CLAUDE.md` | Un microservice specifique | Stack technique, commandes, structure, dependances |
| Regles | `.claude/rules/*.md` | Tout le repo | Regles imperatives (modification de code, commits) |
| Agents | `.claude/agents/*.md` | Tout le repo | Sous-agents specialises (review, debug, docs) |
| Commandes | `.claude/commands/*.md` | Tout le repo | Commandes slash disponibles |

### Notre configuration

Le projet RAG-HP-PUB dispose de :
- **4 agents** : `code-reviewer`, `debugger`, `doc-writer`, `test-writer`
- **11 commandes** : `/commit-msg`, `/explain`, `/plan`, `/understand`, `/new-feature-claude-md`, `/new-service-claude-md`, `/update-claude-md`, `/pre-push`, `/investigate`, `/audit-feature`, `/review-task`
- **7 fichiers de regles** : `code-modification.md`, `commit-messages.md`, `security.md`, `language.md`, `impact-awareness.md`, `docker-security.md`, `config-freshness.md`
- **3 skills** : `/fastapi-service-scaffold`, `/rabbitmq-consumer-scaffold`, `/proto-sync`
- **1 hook** : `Stop` hook (auto-revue + rafraichissement CLAUDE.md apres chaque reponse)
- **Un systeme de CLAUDE.md** par service pour donner le contexte local a Claude

---

## 2. Demarrage rapide

### Premiere installation apres clonage du repo

```bash
# 1. Cloner le repo
git clone git@github.com:<org>/RAG-HP-PUB.git
cd RAG-HP-PUB

# 2. Installer Claude Code (si pas deja fait)
npm install -g @anthropic-ai/claude-code

# 3. Lancer Claude Code depuis la racine du projet
claude
```

Au lancement, Claude charge automatiquement :
- Le `CLAUDE.md` racine du projet
- Les fichiers dans `.claude/rules/`
- Les agents dans `.claude/agents/`
- Les commandes dans `.claude/commands/`
- Votre `~/.claude/CLAUDE.md` personnel (s'il existe)
- Votre `~/.claude/primer.md` (s'il existe)

### Configurer son `~/.claude/CLAUDE.md` personnel

Creez le fichier `~/.claude/CLAUDE.md` avec vos preferences. Exemple minimal recommande pour l'equipe :

```markdown
# Personal Preferences -- Global

## Code Philosophy
- Apply SOLID, DRY, KISS principles.
- Prefer composition over inheritance.
- Favor small, focused functions.

## Communication Style
- Be direct. Skip preamble.
- Flag uncertainty with **[UNCLEAR]** rather than guessing.

## Commit Messages
- Always generate in both English and French.
- Default format: Conventional Commits (feat/fix/refactor/docs/chore).

## Session Continuity
- Read @~/.claude/primer.md at session start if it exists.
- Before ending a session (or when I say "wrap up"), rewrite primer.md.
```

> **Important :** Ce fichier est personnel et n'est PAS commite dans le repo. Chacun peut y mettre ses preferences (langue de reponse, niveau de detail, etc.).

### Configurer `primer.md` pour la continuite de session

Creez `~/.claude/primer.md` avec cette structure initiale :

```markdown
# Session Primer

## Active Project
RAG-HP-PUB

## Last Session
- **Date:** --
- **Summary:** --

## Completed
- (nothing yet)

## Next Step
- (awaiting first task)

## Blockers
- (none)
```

Ce fichier est automatiquement mis a jour par Claude quand vous dites **"wrap up"** en fin de session. Il sera relu au demarrage de la session suivante pour reprendre la ou vous vous etiez arrete.

### Verifier que tout est charge

Lancez Claude Code et posez la question :

```
Quels agents, commandes et regles as-tu charges pour ce projet ?
```

Claude doit repondre avec la liste de nos 4 agents, 8 commandes et 4 fichiers de regles. Si un element manque, verifiez que le fichier existe dans `.claude/` et que sa syntaxe YAML front matter est correcte.

---

## 3. Les commandes disponibles (/commands)

Les commandes sont des raccourcis invoques avec `/` dans le chat. Elles declenchent un comportement precis et structure.

### 3.1 `/commit-msg` -- Generer un message de commit bilingue

**Quand l'utiliser :** Apres toute modification de fichier dans la session.

**Ce que fait la commande :** Analyse les changements de la session et genere un message Conventional Commits en anglais et en francais.

**Exemple :**
```
/commit-msg
```

**Resultat attendu :**
```
feat(graph-rag): add retry logic for Neo4j connection timeouts

- Add exponential backoff in database_connector.py
- Set max_retries to 3 with 2s base delay

---

feat(graph-rag): ajout de la logique de retry pour les timeouts Neo4j

- Ajout du backoff exponentiel dans database_connector.py
- Nombre max de tentatives : 3 avec delai de base de 2s
```

### 3.2 `/explain` -- Expliquer du code sans le modifier

**Quand l'utiliser :** Pour comprendre un service ou un fichier inconnu avant de le modifier.

**Ce que fait la commande :** Explique le code en langage clair, sans critique ni modification.

**Exemple :**
```
/explain apps-microservices/graph-rag-api-recherche-rust-service/src/main.rs
```

> **Regle :** Claude ne produit aucun code ni suggestion d'amelioration. Il termine par *"Is there a specific part you would like me to go deeper on?"*

### 3.3 `/plan` -- Planification interactive

**Quand l'utiliser :** Avant tout travail complexe touchant plusieurs fichiers ou services.

**Ce que fait la commande :** Claude reformule votre objectif, liste les etapes, et attend votre confirmation avant de coder.

**Exemple :**
```
/plan Ajouter un endpoint /health a api-gateway avec vérification de la connexion Redis
```

**Avec details de fichiers :**
```
/plan with file details Ajouter un endpoint /health a api-gateway avec vérification Redis
```

Claude affichera un tableau :

| Fichier | Action | Explication |
|---------|--------|-------------|
| `apps-microservices/api-gateway/src/routes/health.py` | CREATE | Nouveau endpoint /health |
| `apps-microservices/api-gateway/src/main.py` | UPDATE | Inclure le router health |

> **Regle :** Aucun code n'est genere tant que vous ne confirmez pas.

### 3.4 `/understand` -- Comprendre un contenu upload

**Quand l'utiliser :** Quand vous collez un log, un fichier de config, ou un document technique et voulez que Claude l'analyse avant d'agir.

**Exemple :**
```
/understand [collez ici un stack trace RabbitMQ]
```

Claude fournira :
- L'objectif du contenu
- Les composants cles
- Les patterns, dependances ou contraintes notables

### 3.5 `/new-feature-claude-md` -- Mettre a jour CLAUDE.md apres un ajout majeur

**Quand l'utiliser :** Apres l'ajout d'un module significatif a un service existant (ex : support WebSocket dans `api-gateway`, integration Stripe, nouveau dossier `jobs/`).

**Ne PAS utiliser pour :** Bug fixes, petits refactors, ajout d'un seul endpoint.

**Exemple :**
```
/new-feature-claude-md
```

Claude demandera :
1. Quel service ? (ex : `apps-microservices/api-gateway`)
2. Qu'est-ce qui a ete ajoute ? (ex : "Support WebSocket pour le streaming des reponses LLM")

Puis il proposera des modifications chirurgicales du `CLAUDE.md` du service.

### 3.6 `/new-service-claude-md` -- Generer le CLAUDE.md d'un nouveau service

**Quand l'utiliser :** A chaque creation d'un nouveau microservice dans `apps-microservices/`.

**Exemple :**
```
/new-service-claude-md
```

Claude demandera :
1. Nom du service (ex : `notification-service`)
2. Chemin (ex : `apps-microservices/notification-service/`)
3. S'execute localement ? Oui / Non

Il generera ensuite un `CLAUDE.md` conforme au template standard (stack, commandes, structure, dependances) et proposera de mettre a jour le `CLAUDE.md` racine.

> **Regle :** Le fichier genere ne depassera jamais 60 lignes. Les inconnues sont marquees `[TODO]`.

### 3.7 `/update-claude-md` -- Proposer des mises a jour chirurgicales

**Quand l'utiliser :** Trois cas :
- **(a)** Claude a fait une erreur que vous voulez empecher a l'avenir
- **(b)** Quelque chose a change dans le projet (nouvelle dependance, restructuration)
- **(c)** Vous voulez rescanner un service et rafraichir son CLAUDE.md

**Exemple :**
```
/update-claude-md
```

Claude vous demandera de choisir le scenario (a), (b) ou (c), puis proposera des modifications chirurgicales avec un apercu diff avant application.

### 3.8 `/pre-push` -- Verification pre-push

**Quand l'utiliser :** Avant de pousser du code vers le depot distant. Cette commande lance une checklist complete sur tous les services modifies.

**Ce que fait la commande :**
1. Identifie les fichiers modifies et les regroupe par service
2. Lance les verifications par langage :
   - **Python** : compilation syntaxique, imports, tests pytest (si existants)
   - **Rust** : `cargo check`, `cargo test` (si existants)
   - **TypeScript/Node.js** : lint et tests (si scripts existants dans package.json)
   - **Libs partagees** : verification + alerte sur l'impact downstream
3. Lance `@code-reviewer` sur tous les fichiers modifies
4. Affiche un tableau recapitulatif avec le statut de chaque service

**Exemple :**
```
/pre-push
```

**Resultat attendu :**
```
| Service              | Syntax | Tests | Review | Status |
|----------------------|--------|-------|--------|--------|
| api-gateway          | ✅     | ✅    | ✅     | OK     |
| graph-rag-etl        | ✅     | ⚠️    | ✅     | Warn   |

All checks passed. Safe to push.
```

> **Regle :** Si des tests manquent, la commande suggerera d'utiliser `@test-writer` pour en generer.

### 3.9 `/investigate` -- Verification factuelle basee sur les preuves

**Quand l'utiliser :** Pour verifier une affirmation sur le codebase (ex : "Tous les processors utilisent le DLQ", "Redis n'est utilise que par les crawlers").

**Exemple :**
```
/investigate Tous les services processor utilisent les headers DLQ
```

**Ce que fait la commande :**
1. Transforme l'affirmation en assertion testable.
2. Recherche exhaustivement dans tout le codebase (pas un echantillon).
3. Produit un verdict : **CONFIRMED**, **PARTIALLY TRUE**, **FALSE**, ou **INCONCLUSIVE** — avec preuves (fichier:ligne).

**Regle :** Lecture seule. Ne modifie aucun fichier.

### 3.10 `/audit-feature` -- Audit bout-en-bout d'une fonctionnalite

**Quand l'utiliser :** Pour tracer une fonctionnalite a travers tout le pipeline de microservices et auditer chaque service implique.

**Exemple :**
```
/audit-feature recherche produit
```

**Ce que fait la commande :**
1. Cartographie le flux de la fonctionnalite (API entree → file de messages → processeur → base de donnees → reponse).
2. Audite chaque service pour la qualite du code, la securite, la conformite Docker, la couverture de tests et la precision du CLAUDE.md.
3. Rapporte les problemes cross-service (schemas incoherents, propagation d'erreurs manquante).
4. Termine par : *"Would you like me to fix any of these findings?"*

### 3.11 `/review-task` -- Revue Tech Lead

**Quand l'utiliser :** Pour examiner le travail d'un developpeur ou auditer l'etat actuel d'un service.

**Exemple :**
```
/review-task apps-microservices/QC-tracking-service
```

**Ce que fait la commande :**
1. Lit l'etat complet du service (code, config, Dockerfile, tests, CLAUDE.md).
2. Si des changements de branche existent, analyse aussi le diff pour mettre en evidence ce qui a ete introduit.
3. Evalue selon 7 dimensions : qualite du code, securite, Docker, impact, couverture de tests, precision CLAUDE.md, criteres d'acceptation.
4. Produit un verdict : **APPROVED**, **CHANGES REQUESTED**, ou **BLOCKED**.

### 3.12 Skills (Scaffolding)

Les skills generent des structures de service completes en suivant les conventions du projet. Ils vivent dans `.claude/skills/`.

| Skill | Usage | Description |
|-------|-------|-------------|
| `/fastapi-service-scaffold` | `/fastapi-service-scaffold mon-service "Description"` | Generer un nouveau service FastAPI complet |
| `/rabbitmq-consumer-scaffold` | `/rabbitmq-consumer-scaffold mon-processor produits` | Generer un processeur RabbitMQ avec consumer, DLQ, metriques |
| `/proto-sync` | `/proto-sync` ou `/proto-sync embedding.proto` | Regenerer les stubs gRPC Python et verifier les changements cassants |

---

## 4. Les agents disponibles (@agents)

Les agents sont des sous-instances de Claude specialisees pour une tache. Ils utilisent le modele Sonnet (plus rapide, moins couteux) et ont acces a des outils restreints.

### 4.1 `@code-reviewer` -- Revue de code

**Role :** Analyser le code pour les violations SOLID/DRY/KISS, les failles de securite, les problemes de performance et la gestion d'erreurs.

**Outils :** Read, Glob, Grep (pas d'ecriture)

**Quand l'utiliser :**
- Avant de soumettre un PR
- Apres un refactor important
- Pour auditer un service inconnu

**Exemple :**
```
@code-reviewer Revois le fichier apps-microservices/api-gateway/src/routes/search.py
```

**Sortie :** Findings groupes par severite :
- 🔴 **Critical** -- Faille de securite, bug bloquant
- 🟡 **Warning** -- Violation de principe, code fragile
- 🔵 **Suggestion** -- Amelioration optionnelle

L'agent analyse selon **7 dimensions** : SOLID, DRY, KISS, securite, performance, gestion d'erreurs, et **conscience d'impact** (compromis, rayon d'impact sur les composants partages). Il effectue **plusieurs passes internes** avant de produire sa sortie — tous les findings sont reportes en une seule reponse.

> **Important :** L'agent ne genere JAMAIS de code corrige. Il termine par un **Resume d'impact** puis *"Would you like me to implement any of these suggested improvements?"*. Relancer l'agent sur du code inchange ne devrait pas produire de nouveaux findings.

### 4.2 `@debugger` -- Diagnostic d'erreurs

**Role :** Analyser les stack traces, logs d'erreur et bugs. Identifier la cause racine et proposer un correctif minimal.

**Outils :** Read, Bash, Glob, Grep

**Quand l'utiliser :**
- Quand un service crash et vous avez le stack trace
- Quand un test echoue sans raison evidente
- Quand un comportement est inattendu en production

**Exemple :**
```
@debugger Voici l'erreur du graph-rag-etl-processor :
ConnectionResetError: [Errno 104] Connection reset by peer
  File "apps-microservices/graph-rag-etl-processor/src/consumer.py", line 87, in process_message
    await channel.basic_ack(delivery_tag)
```

**Processus :**
1. Lit le fichier source concerne
2. Explique POURQUOI l'erreur survient
3. Produit un **plan de correction structure** : tableau des changements, analyse des compromis, verification du rayon d'impact
4. Demande : *"Does this fix plan look correct? Confirm to apply."*
5. Apres confirmation, applique tous les changements et verifie le correctif (py_compile, tests si disponibles)

### 4.3 `@doc-writer` -- Documentation du code

**Role :** Ajouter de la documentation (docstrings, JSDoc, commentaires inline) sans modifier le code executable.

**Outils :** Read, Write, Edit, Glob, Grep

**Quand l'utiliser :**
- Apres avoir termine une feature, avant le PR
- Sur des fichiers anciens sans documentation
- Pour les fonctions complexes avec de la logique non evidente

**Exemple :**
```
@doc-writer Documente le fichier apps-microservices/embedding-service/src/embedder.py
```

> **Regle absolue :** L'agent ne modifie JAMAIS le code executable. Il ajoute uniquement des commentaires et de la documentation. Le format suit les conventions du langage (docstrings Python, JSDoc pour TypeScript, `///` pour Rust).

### 4.4 `@test-writer` -- Generation de tests

**Role :** Generer des suites de tests pour tous les stacks du projet. Auto-detecte Python (pytest), Rust (cargo test), Node.js (Jest/Vitest), ou demande a l'utilisateur pour les stacks inconnus.

**Outils :** Read, Write, Edit, Glob, Grep

**Quand l'utiliser :**
- Quand un service n'a aucun test (69/91 services sont dans ce cas)
- Quand vous voulez augmenter la couverture de tests d'un service existant
- Quand `/pre-push` signale l'absence de tests pour un service modifie

**Exemple :**
```
@test-writer Genere des tests pour apps-microservices/QC-tracking-service/
```

**Processus :**
1. **Auto-detecte le stack** en lisant le repertoire du service :
   - `requirements.txt` / `pyproject.toml` → Python (pytest)
   - `Cargo.toml` → Rust (cargo test)
   - `package.json` → Node.js (Jest ou Vitest)
   - Inconnu → demande a l'utilisateur quel framework utiliser
2. Lit le code source du service (endpoints, schemas, logique metier)
3. Cherche les fichiers de test existants pour reutiliser les fixtures et patterns
4. Genere les fichiers de test adaptes au stack detecte

**Patterns de test Python :**
- `httpx.AsyncClient` pour les endpoints FastAPI
- Mock des dependances externes (RabbitMQ, gRPC, Milvus, Redis)
- `pytest.mark.asyncio` pour les tests async
- Nommage descriptif : `test_<action>_<condition>_<resultat_attendu>`

> **Regles absolues :**
> - Ne modifie JAMAIS le code source existant -- uniquement les fichiers de test
> - Ne genere JAMAIS de tests necessitant des connexions reelles aux BDD/queues
> - Apres generation, suggere la commande de lancement adaptee au stack detecte

### Quand NE PAS utiliser un agent

- **Ne pas utiliser `@code-reviewer`** pour de la simple comprehension de code -- utilisez `/explain` a la place.
- **Ne pas utiliser `@debugger`** si vous n'avez pas de message d'erreur concret -- posez votre question directement a Claude.
- **Ne pas utiliser `@doc-writer`** si vous voulez aussi refactorer le code -- faites le refactor d'abord, documentez ensuite.
- **Ne pas utiliser `@test-writer`** pour un seul test unitaire trivial -- ecrivez-le directement avec Claude.

---

## 5. Les regles (.claude/rules/)

### 5.1 `code-modification.md` -- Protocole de modification de code

Ce fichier impose un comportement de **patch tool** a Claude :

1. **Lire d'abord** -- Toujours lire le fichier depuis le disque avant de le modifier
2. **Diff minimal** -- Ne changer que ce que la tache requiert
3. **Preserver le formatage** -- Indentation, sauts de ligne, style d'origine
4. **Preserver les commentaires** -- Sauf s'ils deviennent factuellement incorrects
5. **Verifier apres** -- Lancer le typecheck/lint apres chaque modification

Chaque bloc de code est precede du chemin complet du fichier. Pour les modifications chirurgicales, seul le bloc modifie est affiche avec 3 lignes de contexte et `// ... existing code ...`.

> **Chemin :** `.claude/rules/code-modification.md`

### 5.2 `commit-messages.md` -- Protocole de messages de commit

Impose le format **Conventional Commits** bilingue (EN/FR) :

- Generation automatique apres toute modification de fichier
- Generation manuelle via `/commit-msg`
- Types : `feat:`, `fix:`, `refactor:`, `docs:`, `chore:`, `test:`
- Scope limite aux changements de la reponse en cours
- Ligne de sujet < 72 caracteres

> **Chemin :** `.claude/rules/commit-messages.md`

### 5.3 `security.md` -- Regles de securite

Impose les bonnes pratiques de securite pour tout le code du projet :

1. **Secrets et URLs** -- JAMAIS de valeurs en dur. Toutes les URLs de services et cles API doivent venir de variables d'environnement via Pydantic `BaseSettings`
2. **CORS** -- `allow_origins=["*"]` acceptable pour les services internes derriere le gateway. Les services publics (`api-gateway`, `api-html-recherche`) doivent restreindre les origines
3. **JWT et authentification** -- Les secrets JWT doivent etre en variable d'environnement, jamais de valeurs par defaut comme "changeme-jwt-secret"
4. **Validation des entrees** -- Utiliser les modeles Pydantic pour TOUTE validation. Assainir les donnees avant injection dans les prompts LLM (prevention d'injection de prompt)
5. **Logs** -- Les headers sensibles (`authorization`, `cookie`, `x-api-key`) doivent etre masques dans les logs

> **Chemin :** `.claude/rules/security.md`

### 5.4 `language.md` -- Regles de langue

Definit le comportement linguistique de Claude Code :

1. **Langue de reponse** -- Claude repond dans la meme langue que l'utilisateur (francais si l'utilisateur ecrit en francais, anglais si en anglais)
2. **Identifiants de code** -- Toujours en anglais, quelle que soit la langue de conversation
3. **Commentaires de code** -- Suivent la langue de conversation (commentaires en francais pour les utilisateurs francophones)
4. **Messages de commit** -- Toujours generes dans les DEUX langues (EN + FR)
5. **Fichiers CLAUDE.md** -- Rediges en anglais pour une meilleure adherence aux instructions

> **Chemin :** `.claude/rules/language.md`

### 5.5 `impact-awareness.md` -- Analyse des compromis et du rayon d'impact

Impose l'analyse des compromis AVANT toute modification de code :

1. **Analyse des compromis** -- Ce que le changement apporte vs ce qu'il coute (complexite, dependances, changements cassants)
2. **Vision globale** -- Comprendre le role du service dans le pipeline, verifier si le meme pattern existe dans d'autres services
3. **Rayon d'impact** -- Pour les composants partages (`libs/`, `protos/`, `docker-compose.yml`), lister tous les consommateurs en aval

> **Chemin :** `.claude/rules/impact-awareness.md`

### 5.6 `docker-security.md` -- Regles de securite Docker

Impose les bonnes pratiques Docker pour tous les Dockerfile et docker-compose.yml :

1. **Images de base** -- Toujours epingler les versions (pas de tag `latest`), pas d'images en fin de vie, preferer les variantes `-slim`
2. **Build** -- Utiliser `--no-cache-dir` sur pip install, builds multi-etapes, copier uniquement le necessaire
3. **Runtime** -- Pas d'utilisateur root, pas de secrets dans `ENV`, healthchecks obligatoires dans compose
4. **Patterns de vulnerabilite** -- Signaler `chmod 777`, `ADD` au lieu de `COPY`, `.dockerignore` manquant

> **Chemin :** `.claude/rules/docker-security.md`

### 5.7 `config-freshness.md` -- Fraicheur de la configuration

Assure que Claude Code travaille toujours avec la derniere version de la configuration `.claude/`, meme en milieu de conversation :

1. Relire les fichiers agent/commande avant de les invoquer
2. Apres creation ou modification d'un fichier `.claude/`, le traiter comme immediatement actif
3. En cas de conflit entre une version en contexte et le fichier sur disque, le fichier sur disque gagne

> **Chemin :** `.claude/rules/config-freshness.md`

### 5.8 `formatting.md` -- Conventions de formatage du code

Aucun formateur projet n'est impose pour le moment. Cette regle definit les conventions que Claude doit suivre :

1. **Python** : indentation 4 espaces, longueur de ligne 88 caracteres, guillemets doubles, ordre des imports (stdlib → third-party → libs → local)
2. **Rust** : defauts de rustfmt, longueur de ligne 100 caracteres, pas de `unwrap()` en production
3. **JS/TS** : indentation 2 espaces, points-virgules obligatoires, guillemets simples
4. **Universel** : Toujours respecter le style existant du fichier. Ne jamais reformater en dehors du scope du changement.

> **Chemin :** `.claude/rules/formatting.md`

### 5.9 `refactoring.md` -- Regles de refactoring

Gouverne quand et comment refactorer en toute securite :

1. **Quand** : Apres que le revieweur signale une duplication/violation SOLID, quand la meme logique existe dans 3+ services, ou sur demande explicite
2. **Quand NON** : Pendant un bug fix, pendant un ajout de feature, sans tests, ou sans demande
3. **Composants partages** : Toujours `/plan` d'abord, lister tous les consommateurs en aval, commiter les changements de lib separement
4. **Cibles connues** : centralisation du logging (75 services), duplication de config (45 services), standardisation de structure (15 services)

> **Chemin :** `.claude/rules/refactoring.md`

### Comment les regles sont chargees

Les fichiers dans `.claude/rules/` sont charges **automatiquement** par Claude Code au demarrage de chaque session. Vous n'avez rien a faire pour les activer -- elles s'appliquent a toutes les interactions dans le repo.

### Comment ajouter une nouvelle regle

Quand Claude fait une erreur repetitive, le workflow est :

1. **Diagnostiquer** l'erreur (ex : Claude reformate systematiquement les imports Python)
2. **Rediger la regle** dans un nouveau fichier `.claude/rules/<nom-regle>.md`
3. **Commiter** le fichier pour que toute l'equipe en beneficie

**Exemple concret :**

```bash
# Claude a reformate les imports dans embedding-service
# Diagnostic : il trie les imports par ordre alphabetique alors qu'on
# utilise des groupes separes (stdlib, third-party, local)

# 1. Creer la regle
cat > .claude/rules/python-imports.md << 'EOF'
# Python Import Ordering

## Rule
Never reorder Python imports. Preserve the existing grouping:
1. Standard library
2. Third-party packages
3. Local imports (from src.*, from libs.*)

Each group is separated by a blank line. Do not sort within groups.
EOF

# 2. Commiter
git add .claude/rules/python-imports.md
git commit -m "chore(rules): add Python import ordering rule"
```

Desormais, tous les membres de l'equipe beneficient de cette regle.

---

## 6. Workflow quotidien standardise

### Debut de session

```
# 1. Ouvrir le terminal dans le repo
cd ~/Workspaces/RAG-HP-PUB

# 2. Lancer Claude Code
claude

# 3. Claude lit automatiquement :
#    - CLAUDE.md racine
#    - .claude/rules/*
#    - ~/.claude/CLAUDE.md (personnel)
#    - ~/.claude/primer.md (continuite)
```

Si `primer.md` contient un etat de session precedente, Claude reprendra le contexte automatiquement. Verifiez avec :

```
Ou en etions-nous la derniere fois ?
```

### Pendant le travail

| Etape | Action |
|-------|--------|
| Avant de coder | `/plan` pour les taches complexes |
| Codage | Travailler en mode normal, Claude applique les regles automatiquement |
| Apres modification | `/commit-msg` pour generer le message de commit |
| Tests manquants | `@test-writer` pour generer des tests sur le service modifie |
| Avant push | `/pre-push` pour la checklist de verification complete |
| Avant PR | `@code-reviewer` sur les fichiers modifies |
| Documentation | `@doc-writer` sur les fichiers cles |
| Erreur rencontree | `@debugger` avec le stack trace |

### Fin de session

Dites simplement :

```
wrap up
```

Claude mettra a jour `~/.claude/primer.md` avec :
- Le projet actif
- Ce qui a ete fait
- La prochaine etape exacte
- Les blocages eventuels

### Mode Plan vs Mode Normal

| Situation | Mode |
|-----------|------|
| Ajout d'un endpoint a un service existant | Normal |
| Modification d'un fichier unique | Normal |
| Feature touchant 3+ fichiers | `/plan` d'abord |
| Travail cross-service (ex : proto + service + gateway) | `/plan with file details` |
| Refactor architectural | `/plan with file details` |

### Quand faire `/compact`

Claude Code a une fenetre de contexte limitee. Un indicateur de remplissage est affiche. Les seuils recommandes :

| Remplissage contexte | Action |
|----------------------|--------|
| < 50% | Continuez normalement |
| 50-65% | Lancez `/compact` pour resumer le contexte |
| > 65% | `/compact` imperatif, sinon risque de perte de coherence |
| > 80% | Terminez la session (`wrap up`), relancez Claude Code |

### Services remote-only

Pour les services qui ne tournent qu'en remote (voir section 8), le workflow est adapte :

```
# Verifications locales possibles (Rust)
cargo check --manifest-path apps-microservices/graph-rag-api-recherche-rust-service/Cargo.toml

# NE JAMAIS tenter de lancer le service
# NE JAMAIS tenter de se connecter aux BDD de production
```

---

## 7. Travail multi-services

### Architecture de reference

RAG-HP-PUB est compose de :
- **`apps-microservices/`** -- 90+ microservices (Python, Rust, Node.js, Go)
- **`libs/`** -- Bibliotheques partagees (`common-utils`, `grpc-stubs`, `rust-common-utils`)
- **`protos/`** -- Definitions gRPC (`protos/grpc_stubs/`)
- **`tools/`** -- Scripts utilitaires (`dlq_archiver.py`, `dlq_requeuer.py`, etc.)
- **`model-optimizer/`** -- Optimisation des modeles ML

### Quand utiliser les sous-agents en parallele

Pour les taches touchant a plusieurs services independants, utilisez des sous-agents :

```
Lance un sous-agent pour analyser la structure de graph-rag-etl-processor
et un autre pour analyser graph-rag-produit-processor.
Ensuite compare leurs patterns de consommation RabbitMQ.
```

Cas d'usage :
- Comparer les patterns d'erreur entre deux services
- Auditer la coherence des schemas gRPC entre producteur et consommateur
- Verifier que `libs/common-utils` est utilise de maniere consistante

### Travailler avec les bibliotheques partagees

Les libs partagees dans `libs/` sont importees par de nombreux services. Toute modification a un impact large.

**Procedure :**
1. `/plan with file details` avant toute modification de `libs/`
2. Identifier tous les services impactes avec Grep :
   ```
   Quels services importent depuis libs/common-utils ?
   ```
3. Verifier la compatibilite avec les services impactes
4. Tester localement ce qui peut l'etre (typecheck, unit tests)
5. Documenter le changement dans le CLAUDE.md de la lib

### Exemple concret : modification cross-service

**Scenario :** Ajouter un nouveau champ `confidence_score` a la reponse de recherche, ce qui touche :
- `protos/grpc_stubs/` -- Modifier le proto de recherche
- `apps-microservices/embedding-model-service/` -- Service gRPC en amont
- `apps-microservices/graph-rag-api-recherche-rust-service/` -- API Rust consommant le gRPC
- `apps-microservices/api-gateway/` -- Gateway exposant le resultat au client

```
/plan with file details

Ajouter un champ confidence_score (float, 0.0-1.0) a la reponse de
recherche. Le score est calcule par embedding-model-service et doit
traverser la chaine : embedding -> recherche-rust -> gateway -> client.
```

Claude listera tous les fichiers a modifier dans un tableau, avec l'ordre d'execution (proto d'abord, puis services en aval). Confirmez avant de commencer.

---

## 8. Services remote-only : les regles absolues

### Liste des services remote-only

La majorite des microservices Python/Rust ne fonctionnent qu'en environnement remote (serveur avec GPU, acces reseau aux bases de donnees). Cela inclut notamment :

**Services dependants du GPU :**
- `apps-microservices/embedding-model-service/` (gRPC port 50052)
- `apps-microservices/reranking-model-service/`
- `apps-microservices/llm-service/`
- `apps-microservices/ocr-service/`
- vllm-server, triton-server (infrastructure ML)

**Services dependants des bases de donnees distantes :**
- Tous les services `graph-rag-*` (Neo4j, Milvus)
- Tous les services `*-database-qdrant-service` (Qdrant)
- `apps-microservices/api-recherche-service/` (Milvus, Redis)
- `apps-microservices/database-service/` (Neo4j)
- `apps-microservices/database-recherche-service/` (Elasticsearch)

**Services dependants de RabbitMQ :**
- Tous les services `*-processor*` (consommateurs de messages)
- `apps-microservices/dlq-manager-service/`

### Ce que vous POUVEZ faire localement

| Action | Commande |
|--------|----------|
| Typecheck Python | [TODO: à compléter — outil de type-checking Python à définir par l'équipe] |
| Typecheck Rust | `cargo check --manifest-path apps-microservices/graph-rag-api-recherche-rust-service/Cargo.toml` |
| Tests unitaires (avec mocks) | `pytest apps-microservices/<service>/tests/unit/` |
| Lint | [TODO: a completer par l'equipe -- aucun linter standard configure] |
| Revue de code | `@code-reviewer` |
| Documentation | `@doc-writer` |
| Verifier les imports | `python -c "import ast; ast.parse(open('fichier.py').read())"` |

### Ce que vous NE POUVEZ PAS faire localement

- Lancer le service (`uvicorn`, `python main.py`, `cargo run`)
- Se connecter a Neo4j, Milvus, Qdrant, Redis, Elasticsearch
- Executer les tests d'integration
- Tester les consumers RabbitMQ
- Faire des appels gRPC reels entre services

### Commandes a NE JAMAIS executer localement

```bash
# NE JAMAIS FAIRE :
uvicorn apps-microservices/api-gateway/src/main:app --reload
python apps-microservices/graph-rag-etl-processor/src/main.py
docker-compose up  # (lance toute l'infrastructure)
cargo run --manifest-path apps-microservices/graph-rag-api-recherche-rust-service/Cargo.toml
```

> **Pourquoi ?** Ces commandes echoueront avec des erreurs de connexion aux BDD/services distants, ou tenteront de telecharger des modeles ML de plusieurs Go. Cela fait perdre du temps et peut corrompre l'etat local.

### Services qui fonctionnent localement

Ces services peuvent etre lances et testes en local :

- `apps-microservices/api-chatbot-html-service/` (Node.js, port 3000)
- `apps-microservices/nextjs-formulaire-hp/` (Next.js, port 3000, basePath: /formulaire)
- `apps-microservices/crawler-monitor-frontend/` (frontend)
- `apps-microservices/crawler-monitor-backend/` (backend)
- `apps-microservices/crawler-service/` (Crawlee)
- Bibliotheques dans `libs/` (tests unitaires)

---

## 9. Harmonisation de l'equipe

### Conventions de nommage par langage

| Langage | Fichiers | Variables/Fonctions | Classes | Constantes |
|---------|----------|---------------------|---------|------------|
| Python (FastAPI) | `snake_case.py` | `snake_case` | `PascalCase` | `UPPER_SNAKE_CASE` |
| Rust (Actix-web) | `snake_case.rs` | `snake_case` | `PascalCase` | `UPPER_SNAKE_CASE` |
| TypeScript (Next.js) | `kebab-case.ts` ou `PascalCase.tsx` | `camelCase` | `PascalCase` | `UPPER_SNAKE_CASE` |
| Go | `snake_case.go` | `camelCase` (prive), `PascalCase` (public) | `PascalCase` | `PascalCase` ou `UPPER_SNAKE_CASE` |
| Proto (gRPC) | `snake_case.proto` | `snake_case` (champs) | `PascalCase` (messages) | `UPPER_SNAKE_CASE` (enums) |

### Style de code par type de service

**Services Python (FastAPI) :**
- Routeur dans `src/routes/` ou `src/routers/`
- Modeles Pydantic pour la validation
- Async par defaut (`async def`)
- Gestion des erreurs avec `HTTPException`

**Service Rust (Actix-web) :**
- `graph-rag-api-recherche-rust-service` est le seul service Rust
- Modules dans `src/`, point d'entree `src/main.rs`
- Gestion d'erreurs avec `Result<T, E>` et types d'erreur personnalises

**Services Node.js/TypeScript :**
- Next.js pour les frontends (`nextjs-formulaire-hp`)
- Express pour les backends API (`crawler-monitor-backend`)
- Crawlee pour les crawlers (`crawler-service`)

### Conventions Git

**Branches :**
```
features/<nom-feature>     # Nouvelle fonctionnalite
fix/<nom-bug>              # Correction de bug
refactor/<description>     # Refactoring
chore/<description>        # Maintenance, CI/CD
```

**Commits :**
- Format : Conventional Commits
- Toujours bilingues (EN/FR)
- Scope : le service ou composant concerne
- Exemples :
  ```
  feat(api-gateway): add /health endpoint with Redis check
  fix(graph-rag-etl): handle RabbitMQ connection reset gracefully
  refactor(embedding-service): extract embedding logic into dedicated module
  docs(protos): update gRPC stub documentation
  chore(ci): add type-check step to Python service CI pipeline
  ```

**Pull Requests :**
- Titre court (< 70 caracteres)
- Description avec : resume des changements, plan de test, services impactes
- Utiliser `@code-reviewer` avant de soumettre
- Lier les issues le cas echeant

### CLAUDE.md projet vs CLAUDE.md personnel

| Aspect | Projet (`CLAUDE.md`, `.claude/`) | Personnel (`~/.claude/CLAUDE.md`) |
|--------|----------------------------------|-----------------------------------|
| Commite dans le repo | Oui | Non |
| Partage avec l'equipe | Oui | Non |
| Contenu | Architecture, conventions, carte services | Preferences personnelles, style |
| Modification | Via `/update-claude-md` ou `/new-feature-claude-md` | Libre, chacun gere le sien |
| Exemples | Ports des services, regles de modification | Langue preferee, niveau de detail |

---

## 10. Maintenance du systeme CLAUDE.md

### Quand mettre a jour

| Evenement | Action |
|-----------|--------|
| Nouveau microservice cree | `/new-service-claude-md` |
| Feature majeure ajoutee a un service | `/new-feature-claude-md` |
| Claude fait une erreur repetitive | `/update-claude-md` (scenario a) |
| Dependance ajoutee/retiree | `/update-claude-md` (scenario b) |
| Structure de dossier modifiee | `/update-claude-md` (scenario b) |
| Doute sur la fraicheur d'un CLAUDE.md | `/update-claude-md` (scenario c -- rescan) |

### Comment mettre a jour

**Regle d'or : modifications chirurgicales uniquement.** Ne jamais reecrire un CLAUDE.md entier sauf demande explicite.

```
/update-claude-md

> Claude : "What happened? Pick one:"
> (a) Claude made a mistake I want to prevent in the future.
> (b) Something changed in the project.
> (c) I just want you to rescan this service.

Repondre : (b)

> Claude : "What changed?"
Repondre : On a ajoute Redis comme cache dans api-recherche-service.

> Claude affiche un diff preview et demande confirmation.
```

### Commandes dediees

| Commande | Usage |
|----------|-------|
| `/new-service-claude-md` | Creer un CLAUDE.md pour un nouveau service |
| `/new-feature-claude-md` | Mettre a jour apres un ajout majeur |
| `/update-claude-md` | Mise a jour chirurgicale (erreur, changement, rescan) |

### Revue hebdomadaire recommandee

Chaque semaine (ex : lundi matin), un membre de l'equipe devrait :

1. Parcourir les PR de la semaine
2. Identifier les services ayant eu des changements structurels
3. Lancer `/update-claude-md` (scenario c) sur ces services
4. Commiter les mises a jour

> Cela garantit que Claude reste a jour et evite les hallucinations basees sur des informations obsoletes.

### La regle des 80 lignes

Chaque fichier CLAUDE.md doit rester **sous 80 lignes**. Si un fichier depasse ce seuil apres une mise a jour :

1. Identifier les sections les plus detaillees
2. Les extraire dans `.claude/rules/<service>-<aspect>.md`
3. Garder une reference dans le CLAUDE.md principal

Cela evite la surcharge de contexte au chargement.

---

## 11. Erreurs courantes a eviter

- ❌ **Lancer `docker-compose up` localement** -- L'infra complete (Neo4j, Milvus, Qdrant, RabbitMQ, Redis) requiert le serveur distant. Cela echouera ou surchargera votre machine.

- ❌ **Modifier `libs/common-utils` sans verifier les dependants** -- Cette lib est importee par des dizaines de services. Un changement naif peut casser la moitie de la plateforme. Toujours lancer `/plan` d'abord.

- ❌ **Oublier `/compact` quand le contexte atteint 50-65%** -- Claude perd en coherence au-dela de 65%. Vous obtiendrez des reponses incompletes ou contradictoires.

- ❌ **Ne pas dire `wrap up` en fin de session** -- Sans cela, `primer.md` n'est pas mis a jour et la prochaine session repart de zero.

- ❌ **Utiliser `@code-reviewer` pour faire corriger le code** -- L'agent de revue ne modifie rien. Il diagnostique. Utilisez Claude directement pour appliquer les corrections.

- ❌ **Ignorer les `[TODO]` dans les CLAUDE.md generes** -- Les informations non detectees automatiquement (ports, variables d'environnement, commandes de test) doivent etre completees manuellement.

- ❌ **Reecrire un CLAUDE.md entier au lieu d'une modification chirurgicale** -- Cela risque de supprimer des informations valides. Utilisez `/update-claude-md` qui fait des edits minimaux.

- ❌ **Ne pas commiter les fichiers `.claude/rules/`** -- Ces fichiers doivent etre partages avec l'equipe via Git. Un regle locale non commitee ne protege que vous.

- ❌ **Copier-coller un stack trace sans contexte** -- Quand vous utilisez `@debugger`, ajoutez toujours : quel service, quelle action declenchait, quel environnement (dev, staging, prod).

- ❌ **Travailler sur un service remote-only sans le savoir** -- Verifiez toujours le CLAUDE.md du service pour la mention "Remote-Only Service" avant de tenter de lancer quoi que ce soit.

---

## 12. Astuces avancees

### Mode Pipe

Claude Code peut recevoir de l'input par pipe pour des operations en batch :

```bash
# Generer la documentation de tous les fichiers Python d'un service
find apps-microservices/api-gateway/src -name "*.py" | claude "Documente chacun de ces fichiers"

# Analyser un log d'erreur directement depuis un fichier
cat /var/log/graph-rag-etl.log | claude "@debugger Analyse ces erreurs"
```

### Mode Agent (Agentic)

Pour les taches complexes, Claude peut enchainer plusieurs actions de maniere autonome :

```
Refactorise le consumer RabbitMQ dans graph-rag-etl-processor pour
utiliser le pattern retry avec backoff exponentiel. Utilise le meme
pattern que dans graph-rag-produit-processor si il existe.
```

Claude va :
1. Lire les deux services
2. Identifier le pattern existant
3. Appliquer le refactoring
4. Vérifier avec le linter/type-checker du projet

### Hooks (evenements automatiques)

Les hooks sont configures dans `.claude/settings.json`. Ils s'executent automatiquement en reponse a des evenements.

**Actuellement configure :**

| Evenement | Type | Description |
|-----------|------|-------------|
| `Stop` | `prompt` | Apres chaque reponse : (1) verifie si un CLAUDE.md necessite une mise a jour, (2) auto-revue du code modifie pour la qualite/securite/impact |

Cela signifie qu'apres chaque reponse ou du code a ete modifie, Claude Code verifie automatiquement son propre travail. Si des problemes sont trouves, il les rapporte et propose de les corriger.

**Comment ajouter un nouveau hook :** Editez `.claude/settings.json` et ajoutez des entrees sous la cle `hooks`. Types disponibles : `PreToolUse`, `PostToolUse`, `Stop`, `command`, `prompt`, `agent`.

### Plugin Superpowers

Le projet a le plugin `superpowers` installe au niveau projet. Il fournit 14 skills qui imposent un workflow de developpement structure : brainstorming avant le code, redaction de plans, TDD, orchestration de sous-agents, et verification avant toute declaration de completion.

**Quand utiliser superpowers vs. les commandes du projet :**

| Tache | Commande projet (legere) | Skill superpowers (lourde) |
|-------|--------------------------|----------------------------|
| Planifier une tache | `/plan` | `writing-plans` (spec multi-etapes avec revue formelle) |
| Debugger une erreur | `@debugger` | `systematic-debugging` (test d'hypotheses exhaustif) |
| Revoir du code | `@code-reviewer` | `requesting-code-review` (revue formelle avec portes de verification) |
| Ecrire des tests | `@test-writer` | `test-driven-development` (TDD strict red-green-refactor) |
| Executer un plan | Implementation directe | `executing-plans` (delegation aux sous-agents avec checkpoints) |

**Regle d'or :** Utilisez les commandes du projet pour les taches ciblees du quotidien. Utilisez les skills superpowers pour le travail complexe multi-etapes qui beneficie de portes de verification structurees.

### Pattern primer.md avance

Pour les projets a long terme, enrichissez votre `primer.md` avec des notes contextuelles :

```markdown
## Notes
- Le service graph-rag-etl-processor a un bug connu avec les messages > 1MB
  (issue #234). Contournement : truncation a 512KB dans le consumer.
- L'equipe migre progressivement de Milvus vers Qdrant.
  Nouveaux services doivent utiliser Qdrant.
- Convention recente : tous les nouveaux endpoints doivent retourner
  un champ "request_id" pour le tracing.
```

### Exploration de codebase avec sous-agents

Pour garder votre contexte principal propre lors de l'exploration :

```
Utilise un sous-agent pour cartographier toutes les connexions gRPC
entre les services dans apps-microservices/. Je veux savoir qui appelle
qui, via quels protos.
```

Le sous-agent explorera le code et rapportera ses resultats sans encombrer votre fenetre de contexte principale.

### Invocations rapides depuis le terminal

```bash
# Question rapide sans ouvrir une session
claude "Quel port utilise api-gateway ?"

# Generer un commit message pour les changements en cours
claude "/commit-msg"

# Revoir un fichier specifique
claude "@code-reviewer apps-microservices/prix-extraction-devis/src/extractor.py"
```

---

## 13. Checklist pour les nouveaux membres

Suivez ces etapes dans l'ordre lors de votre arrivee sur le projet :

- [ ] **1.** Installer Claude Code : `npm install -g @anthropic-ai/claude-code`
- [ ] **2.** Cloner le repo : `git clone git@github.com:<org>/RAG-HP-PUB.git`
- [ ] **3.** Creer votre fichier `~/.claude/CLAUDE.md` personnel (voir section 2)
- [ ] **4.** Creer votre fichier `~/.claude/primer.md` initial (voir section 2)
- [ ] **5.** Lancer `claude` depuis la racine du repo et verifier le chargement : `Quels agents, commandes et regles as-tu charges ?` (attendu : 4 agents, 11 commandes, 7 regles, 3 skills)
- [ ] **6.** Lire le CLAUDE.md racine du projet pour comprendre l'architecture globale
- [ ] **7.** Identifier les services sur lesquels vous allez travailler et lire leurs CLAUDE.md respectifs : `cat apps-microservices/<service>/CLAUDE.md`
- [ ] **8.** Faire un premier exercice avec `/explain` sur un fichier du service assigne
- [ ] **9.** Faire un premier exercice avec `/plan` pour une tache fictive sur votre service
- [ ] **10.** Lire les sections 6 (Workflow quotidien) et 8 (Remote-only) de ce guide
- [ ] **11.** Essayer `@test-writer` sur un service sans tests : `@test-writer Genere des tests pour apps-microservices/<service>/`
- [ ] **12.** Essayer `/pre-push` avant votre premier push
- [ ] **13.** Demander a un collegue de vous montrer le workflow `@code-reviewer` -> correction -> `/commit-msg` sur un changement reel

---

## 14. Reference rapide (Cheat Sheet)

### Commandes

| Commande | Description | Usage typique |
|----------|-------------|---------------|
| `/commit-msg` | Message de commit bilingue EN/FR | Apres chaque modification |
| `/explain` | Explication d'un fichier ou bloc de code | Comprendre un fichier inconnu |
| `/plan` | Planification interactive | Avant un travail complexe |
| `/understand` | Analyse de contenus multiples/sujets larges | Comprendre un log, un doc technique |
| `/new-feature-claude-md` | Maj CLAUDE.md apres feature majeure | Apres ajout d'un module |
| `/new-service-claude-md` | Generer CLAUDE.md nouveau service | A la creation d'un microservice |
| `/update-claude-md` | Modification chirurgicale CLAUDE.md | Erreur, changement, rescan |
| `/pre-push` | Checklist de verification pre-push | Avant chaque push |
| `/investigate` | Verification factuelle basee sur les preuves | Verifier des affirmations, auditer la conformite |
| `/audit-feature` | Audit bout-en-bout d'une fonctionnalite | Evaluation qualite d'une feature |
| `/review-task` | Revue Tech Lead (etat + diff, verdict) | Revue du travail d'un dev, audit de service |

### Agents

| Agent | Modele | Role | Restriction cle |
|-------|--------|------|-----------------|
| `@code-reviewer` | Sonnet | Revue qualite/securite/impact (exhaustive en un passage) | Ne modifie JAMAIS le code |
| `@debugger` | Sonnet | Diagnostic → plan de correction structure avec compromis → appliquer | Demande confirmation avant d'appliquer |
| `@doc-writer` | Sonnet | Ajout de documentation (anglais uniquement) | Ne modifie JAMAIS le code executable |
| `@test-writer` | Sonnet | Generation de tests multi-stack (Python/Rust/Node.js) | Ne modifie JAMAIS le code source |

### Regles

| Fichier | Chemin | Effet |
|---------|--------|-------|
| `code-modification.md` | `.claude/rules/` | Impose le protocole de patch minimal |
| `commit-messages.md` | `.claude/rules/` | Impose les Conventional Commits bilingues |
| `security.md` | `.claude/rules/` | Interdit les secrets/URLs en dur, impose Pydantic BaseSettings, CORS interne vs public |
| `language.md` | `.claude/rules/` | Reponse dans la langue de l'utilisateur, commits bilingues |
| `impact-awareness.md` | `.claude/rules/` | Analyse des compromis, vision globale, rayon d'impact sur composants partages |
| `docker-security.md` | `.claude/rules/` | Images epinglees, pas de root, healthchecks, pas de secrets dans ENV |
| `config-freshness.md` | `.claude/rules/` | Relire la config `.claude/` en cours de session avant utilisation |
| `formatting.md` | `.claude/rules/` | Style par stack — reference stack-detection.md, avec fallback pour stacks inconnus |
| `refactoring.md` | `.claude/rules/` | Quand/comment refactorer, regles de scope, cibles de duplication connues |
| `stack-detection.md` | `.claude/rules/` | Source unique pour la detection de stack. Toutes les regles dependantes du stack referencent ce fichier. |

### Raccourcis et seuils

| Action | Commande / Seuil |
|--------|-------------------|
| Compacter le contexte | `/compact` a 50-65% |
| Terminer une session | Dire `wrap up` |
| Annuler la derniere action | `Ctrl+Z` dans le terminal |
| Quitter Claude Code | `Ctrl+C` ou taper `/exit` |
| Limite CLAUDE.md | 80 lignes max par fichier |
| Limite CLAUDE.md nouveau service | 80 lignes max |
| Ligne de sujet commit | < 72 caracteres |

### Ports des services (reference)

| Service | Port(s) |
|---------|---------|
| `api-gateway` | 8500 (FastAPI), 8050 (Nginx) |
| `graph-rag-api-recherche-rust-service` | 8528, 8566 (Prometheus) |
| `embedding-model-service` | 50052 (gRPC), 8530 (Prometheus) |
| `QC-tracking-service` | 8590 |
| `crawler-service` | 8503 |
| `api-chatbot-html-service` | 3000 |
| `nextjs-formulaire-hp` | 3000 (basePath: /formulaire) |

### Bases de donnees

| Technologie | Usage |
|-------------|-------|
| Neo4j | Graphe de connaissances (relations produits, categories, fournisseurs) |
| Milvus | Recherche vectorielle (embeddings) |
| Qdrant | Recherche vectorielle (migration en cours depuis Milvus) |
| Redis | Cache |
| Elasticsearch | Recherche full-text (desactive par defaut) |
| RabbitMQ | Messagerie inter-services (pika/aio_pika) |

---

> **Mainteneur de ce guide :** [TODO: a completer par l'equipe]
> **Derniere revue :** 2026-03-25
> **Prochaine revue prevue :** [TODO: a completer par l'equipe]
