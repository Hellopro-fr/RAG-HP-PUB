# Inventaire des services — état de migration et lot de bascule

> **Pour les développeurs.** Un service par ligne : son nom sur la VM, s'il est migré et où, le nom exact de son
> équivalent Cloud Run ou GKE, son lot de bascule, et ce qu'il faut savoir avant de le vérifier.
>
> Source : `docker-compose.yml` de la VM GPU (**117 services**), état live Cloud Run (31 services) et GKE
> (42 déploiements) relevé le 2026-09-17. Correspondance des URLs : [`correspondance-endpoints-vm-cloud.md`](correspondance-endpoints-vm-cloud.md).
> Variables d'environnement par service : [`env-migration-matrix.md`](env-migration-matrix.md).


> 📍 **Publié sur la branche `prod` le 2026-09-18** pour toute l'équipe — `git pull` pour la version à jour.
> Point d'entrée du dossier : [`README.md`](README.md) · procédure de vérification : [`guide-pre-check-service.md`](guide-pre-check-service.md).
> Ce document est **dérivé de l'état réel** (le `docker-compose.yml` de la VM et l'inventaire live du cloud), pas d'une intention.
> Les documents cités ici mais **absents de ce dossier** vivent côté DevSecOps (hors dépôt applicatif) — demande-les si tu en as besoin.
> **Une erreur trouvée est une remontée utile** : signale-la au Lead Dev plutôt que de contourner.

---

## Comment lire ce document

**Cherche ton service dans le sommaire ci-dessous**, il te renvoie à son lot. Le lot dit *quand* ta migration se joue
et *ce que tu as à vérifier*.

| Lot | Contenu | Quand | Ce que le dev doit faire |
|:--:|---|---|---|
| **P1** | Consumers asynchrones — 34 services | **J0, 19-20 sept** | **Rien.** Un consumer s'abonne à une queue, il n'a pas d'adresse. Aucune config à changer |
| **P2** | Cluster gateway B1 — 4 services | **J0** | Vérifier les tokens partagés entre gateway et satellites |
| **P3** | Always-on B3 — 3 services | **J0** | Vérifier les règles d'archivage DLQ avant la bascule |
| **P4** | API internes RAG déjà sur Cloud Run — 16 services | Vague 2, lot 1 | **Le vrai travail** : remplacer les URLs de conteneurs Docker en dur |
| **P5** | Serveurs MCP — 8 services | Vague 2, lot 2 | Vérifier les clés d'API et les quotas des services tiers |
| **P6** | Entrée publique `rag.hellopro.eu` — 1 service | Vague 2, lot 3 | Rien côté code, c'est du DNS et du LB |
| **P7** | Front `conseils.hellopro.fr` — 1 service | Vague 2, lot 4 | **Décision produit/SEO** avant toute technique |
| **P8** | Fronts SSO et compte — 5 services | Vague 2, lot 5 | Enregistrer les clients OAuth, vérifier les secrets de session |
| **P9** | Différés et à qualifier — 17 services | Vague 3 | Chaque cas a sa raison, voir le commentaire |
| **P10** | Restent sur la VM — 28 services | **Jamais** | Rien. GPU, bases locales, outillage |

**Total contrôlé : 34 + 4 + 3 + 16 + 8 + 1 + 1 + 5 + 17 + 28 = 117.**

> **Le message principal, si tu ne lis qu'une ligne** : au week-end du 19-20 septembre, **aucune adresse HTTP ne change**.
> Seuls les consumers de queues basculent, et eux n'ont pas d'adresse. Ton service ne bougera pas ce week-end.

---

## P1 — Consumers asynchrones · bascule J0 · **34 services**

Ces services consomment des queues RabbitMQ. Ils n'exposent aucun endpoint, personne ne les appelle : ils s'abonnent.
À J0 on arrête les conteneurs VM et les pods GKE prennent le relais sur le broker de production.

**Ce que tu as à faire : rien.** Aucune URL, aucun `.env` consommateur à modifier. Si ton service est ici, ta vérification
se limite à confirmer après la bascule que ta queue est bien dépilée.

| Nom sur la VM | Migré ? | Équivalent exact (GKE, ns `apps-microservices`) | Priorité | À savoir |
|---|:--:|---|:--:|---|
| `website-processor-service` | ✅ GKE | `website-processor-service` | P1 | 7 réplicas sur la VM — le plus gros consommateur du lot |
| `nettoyage-bruit-ocr-service` | ✅ GKE | `nettoyage-bruit-ocr-service` | P1 | Pas de `/metrics` sur 8530 → déployé sans sonde (F-HP-OBS-002) |
| `template-llm-service` | ✅ GKE | `template-llm-service` | P1 | ⚠️ **Se désabonne volontairement de sa queue entre 06h et 10h UTC** (heures pleines DeepSeek). Zéro consommateur sur `llm_templating_queue` à ces heures = **normal** |
| `embedding-service` | ✅ GKE | `embedding-service` | P1 | ⚠️ **À ne pas confondre** avec `api-embedding-service` (P4, HTTP). Celui-ci est un consumer, il appelle le GPU en gRPC |
| `deepseek-metrics-collector-service` | ✅ GKE | `deepseek-metrics-collector-service` | P1 | Forward HTTP sans base de données |
| `webhook-service` | ✅ GKE | `webhook-service` | P1 | Écrit vers le back-office PHP en HMAC. Seul conteneur VM **sans** le préfixe `rag-hp-pub-` |
| `devis-processor-service` | ✅ GKE | `devis-processor-service` | P1 | — |
| `echange-processor-service` | ✅ GKE | `echange-processor-service` | P1 | — |
| `product-processor-service` | ✅ GKE | `product-processor-service` | P1 | — |
| `prix-milvus-processor-service` | ✅ GKE | **`prix-milvus-processor`** | P1 | ⚠️ Le nom GKE **perd le suffixe `-service`** |
| `di-database-qdrant-service` | ✅ GKE | `di-database-qdrant-service` | P1 | ⚠️ **Écrit dans Milvus, pas dans Qdrant** — « qdrant » est un héritage abandonné |
| `document-database-qdrant-service` | ✅ GKE | `document-database-qdrant-service` | P1 | Idem — writer Milvus |
| `echange-database-qdrant-service` | ✅ GKE | `echange-database-qdrant-service` | P1 | Idem — writer Milvus |
| `product-database-qdrant-service` | ✅ GKE | `product-database-qdrant-service` | P1 | Idem — writer Milvus |
| `website-database-qdrant-service` | ✅ GKE | `website-database-qdrant-service` | P1 | Idem — writer Milvus |
| `graph-rag-produit-processor` | ✅ GKE | `graph-rag-produit-processor` | P1 | Appelle les backends gRPC du GPU via l'enabler |
| `graph-rag-etl-processor` | ✅ GKE | `graph-rag-etl-processor` | P1 | — |
| `graph-rag-categorie-processor` | ✅ GKE | `graph-rag-categorie-processor` | P1 | — |
| `graph-rag-fournisseur-processor` | ✅ GKE | `graph-rag-fournisseur-processor` | P1 | — |
| `graph-rag-llm-extractor-processor` | ✅ GKE | `graph-rag-llm-extractor-processor` | P1 | Sortie internet vers DeepSeek |
| `graph-rag-normalize-unite-processor` | ✅ GKE | `graph-rag-normalize-unite-processor` | P1 | — |
| `graph-rag-normalize-unite-retry-processor` | ✅ GKE | `graph-rag-normalize-unite-retry-processor` | P1 | — |
| `graph-rag-semantique-vigil-processor` | ✅ GKE | `graph-rag-semantique-vigil-processor` | P1 | — |
| `qc-caracterisation` | ✅ GKE | `qc-caracterisation` | P1 | Sortie internet : LLM + API HelloPro |
| `qc-enrichissement` | ✅ GKE | `qc-enrichissement` | P1 | Idem |
| `qc-equivalence` | ✅ GKE | `qc-equivalence` | P1 | Idem |
| `qc-generation-caracteristiques` | ✅ GKE | `qc-generation-caracteristiques` | P1 | Idem |
| `qc-generation-question1` | ✅ GKE | `qc-generation-question1` | P1 | Idem |
| `qc-generation-question2an` | ✅ GKE | `qc-generation-question2an` | P1 | Idem |
| `qc-generation-valeurs` | ✅ GKE | `qc-generation-valeurs` | P1 | Idem |
| `prix-caracterisation` | ✅ GKE | `prix-caracterisation` | P1 | Accès direct à Milvus (pymilvus), initialisé à la demande |
| `prix-extraction-devis` | ✅ GKE | `prix-extraction-devis` | P1 | — |
| `prix-extraction-message` | ✅ GKE | `prix-extraction-message` | P1 | — |
| `prix-extraction-produits` | ✅ GKE | `prix-extraction-produits` | P1 | — |

---

## P2 — Cluster gateway B1 · bascule J0 · **4 services**

Ces quatre-là forment un ensemble : ils partagent une base MySQL et des jetons d'administration. Ils basculent ensemble
ou pas du tout.

| Nom sur la VM | Migré ? | Équivalent exact | Priorité | À savoir |
|---|:--:|---|:--:|---|
| `api-gateway-go-service` | ✅ GKE | `api-gateway-go` | P2 | Service in-cluster sur 8500. L'entrée publique `api.hellopro.eu` ne bascule **qu'en P6** |
| `mcp-gateway-service` | ✅ GKE | `mcp-gateway-service` | P2 | ⚠️ **Pas de Service Kubernetes** à ce jour — à créer à J0, sinon `templates-runner` ne le résout pas |
| `mcp-zoho-service` | ✅ GKE | `mcp-zoho-service` | P2 | ⚠️ Même manque de Service. Dépend de MySQL au démarrage |
| `mcp-google-templates-runner` | ✅ GKE | `mcp-google-templates-runner` | P2 | Service in-cluster sur 8595 |

> **Ce que le dev doit vérifier** : `ENCRYPTION_KEY`, `GOOGLE_TEMPLATES_RUNNER_ADMIN_TOKEN` et `ZOHO_GATEWAY_TOKEN`
> doivent être **strictement identiques** entre la gateway et ses satellites. Une divergence casse la synchronisation
> et le déchiffrement, sans message clair.

---

## P3 — Always-on B3 · bascule J0 · **3 services**

| Nom sur la VM | Migré ? | Équivalent exact | Priorité | À savoir |
|---|:--:|---|:--:|---|
| `graph-rag-api-admin-service` | ✅ GKE | `graph-rag-api-admin-service` | P3 | Écrit dans Neo4j. ⚠️ **L'écriture n'a jamais été exercée en shadow** — validation par un message contrôlé à J0 |
| `graph-rag-dlq-manager-service` | ✅ GKE | **`graph-rag-dlq-manager`** | P3 | Le nom GKE perd le suffixe `-service` |
| `dlq-manager-service` | ✅ GKE | `dlq-manager-service` | P3 | ⚠️ **Boucle de fond d'auto-archivage destructive.** Le LEAD doit valider `dlq_auto_archive_rules` **avant** le câblage sur l'ES de production |

---

## P4 — API internes RAG · vague 2, lot 1 · **16 services**

Déjà déployés sur Cloud Run en shadow. Leur bascule ne change pas d'adresse publique — elle change **les adresses que
les autres services utilisent pour les appeler**.

**C'est ici que se trouve le vrai travail de développement.** Cherche dans ton code les URLs de la forme
`http://<nom-du-conteneur>:<port>` : elles disparaîtront. Deux pièges connus, documentés dans F-HP-DEV-005 —
quatre clients gRPC ont un défaut `:50051` erroné (les vrais ports sont 50055-50058), et `api-rest-milvus` appelle
`api-recherche` via `http://localhost` alors qu'il tourne déjà sur Cloud Run.

| Nom sur la VM | Migré ? | Équivalent exact (Cloud Run) | Priorité | À savoir |
|---|:--:|---|:--:|---|
| `api-recherche-service` | ✅ CR | `api-recherche` | P4 | Cœur du moteur RAG. Appelle le GPU en gRPC via l'enabler |
| `api-classification-service` | ✅ CR | `api-classification` | P4 | Enabler 4 ports |
| `api-chat-llm-service` | ✅ CR | `api-chat-llm` | P4 | Sortie internet vers le LLM |
| `api-embedding-service` | ✅ CR | `api-embedding-service` | P4 | ⚠️ **À ne pas confondre** avec `embedding-service` (P1, consumer) |
| `api-ingestion-service` | ✅ CR | `api-ingestion` | P4 | Publie dans RabbitMQ |
| `api-rest-milvus-service` | ✅ CR | `api-rest-milvus` | P4 | Accès à Milvus via le connecteur VPC. ⚠️ Contient un appel `localhost` à corriger |
| `optimize-service` | ✅ CR | `optimize-service` | P4 | LLM en gRPC |
| `prix-traitement` | ✅ CR | `prix-traitement` | P4 | Service HTTP — **ne pas l'arrêter** avec les consumers prix |
| `content-extractor-api-service` | ✅ CR | `content-extractor-api-service` | P4 | Premier service migré du projet |
| `api-comparaison-texte-service` | ✅ CR | `api-comparaison-texte` | P4 | — |
| `api-detection-langue-fr-service` | ✅ CR | `api-detection-langue-fr` | P4 | Embarque Chromium — mémoire 2 Gi, `--no-sandbox` |
| `image-comparison-service` | ✅ CR | `image-comparison-service` | P4 | ⚠️ **Compteur Redis partagé** `comparator:running_count` à isoler, sinon collision avec la VM |
| `graph-rag-api-recherche-service` | ✅ CR | `graph-rag-api-recherche-service` | P4 | — |
| `graph-rag-api-recherche-optim-service` | ✅ CR | `graph-rag-api-recherche-optim-service` | P4 | — |
| `graph-rag-api-recherche-rust-service` | ✅ CR | `graph-rag-api-recherche-rust-service` | P4 | Implémentation Rust. Sortie vers ECRITEL en IP NAT statique |
| `crawler-monitor-backend` | ✅ CR | `crawler-monitor-backend` | P4 | Go, ingress interne. Son front est en P8 |

> **Service Cloud Run sans équivalent sur la VM** : `api-question-caracteristique` existe dans le code
> (`apps-microservices/api-question-caracteristique`) et tourne sur Cloud Run, mais **n'est pas déclaré dans le
> `docker-compose.yml`**. À qualifier avec le LEAD : service nouveau, ou ancien retiré du compose ?

---

## P5 — Serveurs MCP · vague 2, lot 2 · **8 services**

| Nom sur la VM | Migré ? | Équivalent exact (Cloud Run) | Priorité | À savoir |
|---|:--:|---|:--:|---|
| `mcp-api-recherche-service` | ✅ CR | `mcp-api-recherche-service` | P5 | MCP interne, s'appuie sur `api-recherche` |
| `mcp-classification-produit-service` | ✅ CR | `mcp-classification-produit-service` | P5 | Go |
| `mcp-google-analytics-service` | ✅ CR | `mcp-google-analytics-service` | P5 | Clé de compte de service montée en fichier |
| `mcp-google-analytics-minisite-service` | ✅ CR | `mcp-google-analytics-minisite-service` | P5 | Réutilise le Dockerfile d'analytics |
| `mcp-google-search-console-service` | ✅ CR | `mcp-google-search-console-service` | P5 | Idem clé SA |
| `mcp-semrush-service` | ✅ CR | `mcp-semrush-service` | P5 | Node 22 + Python via `mcp-proxy`. Santé sur `/status`, pas `/health` |
| `mcp-ringover-service` | ✅ CR | `mcp-ringover-service` | P5 | API tierce |
| `mcp-leexi-service` | ✅ CR | `mcp-leexi-service` | P5 | API tierce |

> **Ce que le dev doit vérifier** : les clés d'API des services tiers sont bien en Secret Manager, et les quotas
> supportent l'appel depuis une nouvelle IP de sortie (`35.233.35.8`).

---

## P6 — Entrée publique `rag.hellopro.eu` · vague 2, lot 3 · **1 service**

| Nom sur la VM | Migré ? | Équivalent exact (Cloud Run) | Priorité | À savoir |
|---|:--:|---|:--:|---|
| `api-html-recherche-service` | ✅ CR | `api-html-recherche` | P6 | Le service est déjà sur Cloud Run ; c'est **l'entrée publique** qui bascule en P6, via le LB et Cloud Armor |

> Les entrées `api.hellopro.eu` (`api-gateway-go`) et `mcp.hellopro.eu` (`mcp-gateway`) basculent au même moment,
> mais ces deux services sont sur **GKE** et le module de LB actuel ne gère que les NEG serverless : il faudra des
> NEG zonaux ou un Ingress GKE. Travail d'infrastructure, rien à faire côté code.

---

## P7 — Front `conseils.hellopro.fr` · vague 2, lot 4 · **1 service**

| Nom sur la VM | Migré ? | Équivalent exact (Cloud Run) | Priorité | À savoir |
|---|:--:|---|:--:|---|
| `nextjs-conseils-hp` | ✅ CR | `nextjs-conseils-hp` | P7 | ⚠️ **Décision produit et SEO avant toute technique** : le service remplace *progressivement* les pages PHP. Basculer tout le sous-domaine casserait les URLs non encore migrées |

---

## P8 — Fronts SSO et compte · vague 2, lot 5 · **5 services**

Ces cinq-là dépendent de l'authentification unique portée par `account-service`. Ils forment aussi un ensemble.

| Nom sur la VM | Migré ? | Équivalent exact | Priorité | À savoir |
|---|:--:|---|:--:|---|
| `account-service-backend` | ✅ CR (shadow) | `account-service-backend` | P8 | Porte le SSO. Bascule avant ses clients |
| `account-service-frontend` | ✅ CR (shadow) | `account-service-frontend` | P8 | — |
| `redis-client-frontend` | ❌ non migré | *(à créer)* | P8 | SSO via la librairie `@hellopro/auth` → **contexte de build = racine du dépôt** |
| `crawler-monitor-frontend` | ❌ non migré | *(à créer)* | P8 | Idem. Son back-end est déjà en P4 |
| `mcp-gateway-frontend` | ❌ non migré | *(à créer)* | P8 | Idem |

> **Ce que le dev doit préparer** : enregistrer les clients OAuth sur `account-service`, et fournir
> `SESSION_SECRET`, `JWT_SECRET`, `ACCOUNT_*`, `ADMIN_EMAILS`. La librairie échoue au démarrage si l'environnement
> est incomplet — ce n'est pas une dégradation, c'est un refus de démarrer.

---

## P9 — Différés et à qualifier · vague 3 · **17 services**

Chacun pour une raison précise. Aucun n'est oublié, tous demandent une décision.

| Nom sur la VM | Migré ? | Équivalent exact | Priorité | Pourquoi il attend |
|---|:--:|---|:--:|---|
| `nextjs-formulaire-hp` | ✅ CR (shadow) | `nextjs-formulaire-hp` | P9 | **Migration Next 14 → 15 requise** (CVE). Handoff Lead Dev rédigé |
| `mcp-neo4j-service` | ✅ CR (shadow) | `mcp-neo4j-service` | P9 | CVE `fastmcp` **non corrigeable en l'état** : l'upstream `mcp-neo4j-cypher` plafonne `fastmcp<2.14`. VEX + veille |
| `prix-extraction-siteweb` | ❌ non migré | *(à créer, GKE)* | P9 | Embarque `api-recherche` : 14 champs de configuration à fournir en réel |
| `image-download-service` | ❌ non migré | *(à décider)* | P9 | Hybride HTTP + consumer, écritures lourdes sur NFS. Décision d'architecture : découpler, ou maintenir sur la VM |
| `image-cdn-service` | ❌ non migré | *(à décider)* | P9 | Nginx de service de fichiers — chantier stockage à part |
| `api-transcription-service` | ❌ non migré | — | P9 | Code de développement, pas de version de production |
| `api-chatbot-service` | ❌ non migré | — | P9 | Dormant — à confirmer avec le LEAD avant toute décision |
| `crawler-service` | ❌ non migré | — | P9 | Exposé via `reverse-proxy` sur `/crawler`. Son monitoring est migré, pas lui |
| `milvus-collection-duplicator` | ❌ non migré | — | P9 | Outil d'exploitation, pas un service applicatif |
| `qc-tracking-service` | ❌ non migré | — | P9 | Hors périmètre de la migration des consumers — **ne pas l'arrêter** à J0 |
| `qc-fabricant-reference` | ❌ non migré | **aucun** | P9 | ⚠️ **Aucun équivalent GKE.** L'arrêter laisserait sa queue sans personne. Exclu de la liste d'arrêt J0 |
| `document-echange-processor-service` | ❌ non migré | **aucun** | P9 | ⚠️ Même situation — exclu de la liste d'arrêt J0 |
| `api-gateway-service` | ❌ non migré | — | P9 | Gateway FastAPI historique, remplacée par `api-gateway-go`. À qualifier : encore utilisée ? |
| `api-catalog-service` | ❌ non migré | — | P9 | Alimente la table de routage de la gateway. À traiter avec `api-gateway-go` |
| `api-model-service` | ❌ non migré | — | P9 | À qualifier avec le LEAD |
| `api-recherche-test-modification` | ❌ non migré | — | P9 | Bac à sable bâti sur le Dockerfile d'`api-recherche` — ne pas migrer |
| `graph-rag-api-recherche-service-debug` | ❌ non migré | — | P9 | Instance de débogage. Candidate à la suppression plutôt qu'à la migration |

---

## P10 — Restent sur la VM · **28 services**

Rien à faire, ni maintenant ni plus tard. La VM GPU n'est pas décommissionnée.

| Catégorie | Services | Pourquoi ils restent |
|---|---|---|
| **Inférence GPU** (8) | `model-builder`, `vllm-server`, `triton-server`, `llm-service`, `embedding-model-service`, `reranking-model-service`, `database-recherche-service`, `deepseek-ocr` | Ils utilisent les deux cartes L4. La VM existe pour eux |
| **Backends gRPC graph-rag** (4) | `graph-rag-database-connector-service`, `graph-rag-milvus-service`, `graph-rag-normalize-unite-service`, `graph-rag-spacy-service` | Joignables depuis Cloud Run et GKE via l'enabler `10.11.0.2:15055-15058`. Dispositif **pérenne** |
| **Bases et observabilité locales** (8) | `elasticsearch`, `init-elasticsearch`, `kibana`, `mysql`, `neo4j`, `prometheus`, `grafana`, `phpmyadmin` | Instances locales de la VM. Les équivalents de production sont sur GKE |
| **Réseau local** (5) | `reverse-proxy`, `api-classification-lb`, `api-rest-milvus-lb`, `nextjs-conseils-hp-lb`, `nextjs-formulaire-hp-lb` | Répartiteurs nginx internes à la VM. Sans objet sur Cloud Run |
| **Outillage DLQ** (3) | `dlq-archiver-host`, `dlq-archiver-client`, `dlq-requeuer-tool` | Outils d'exploitation, lancés à la demande |

---

## Ce qu'on attend de toi avant la bascule de ton lot

1. **Trouve ton service dans le tableau** et note son lot.
2. **Si tu es en P1** — rien à faire. Vérifie seulement, après J0, que ta queue est dépilée.
3. **Si tu es en P4 ou au-delà** — cherche dans ton code les URLs `http://<conteneur>:<port>` et les ports gRPC en dur.
   C'est ce qui cassera. La table de correspondance des adresses est dans
   [`correspondance-endpoints-vm-cloud.md`](correspondance-endpoints-vm-cloud.md).
4. **Signale toute erreur de ce tableau.** Il a été construit à partir du `docker-compose.yml` et de l'état live ;
   si ton service fait quelque chose que la colonne « à savoir » ignore, c'est exactement ce qu'on veut apprendre
   **avant** la bascule, pas pendant.
5. **Les cases « à qualifier » de P9 attendent une réponse du LEAD.** Si l'un de ces services est le tien, dis-nous
   s'il est encore utilisé.
