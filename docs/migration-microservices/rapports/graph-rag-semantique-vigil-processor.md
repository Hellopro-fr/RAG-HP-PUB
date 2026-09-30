# Rapport de bascule — `graph-rag-semantique-vigil-processor`

> **Lot L5 · basculé le 2026-09-28 à 07:24 UTC (09:24 Paris)** · exécuté par le DevSecOps · pré-contrôle du dev reçu le 24/09 · validation sur le trafic réel ; **lot validé le 29/09 (GO LEAD)**.
> Ce rapport dit ce qui a changé, ce qui a été prouvé, et **comment vous accédez maintenant au service** pour le déboguer.

---

## 1. Avant / après

| | Avant (VM GPU) | Après (GKE) |
|---|---|---|
| Où il tourne | `rag-hp-pub-graph-rag-semantique-vigil-processor-1` à `-3`, Docker Compose, VM `vm-embedding-g2-std-24-use` | Déploiement `graph-rag-semantique-vigil-processor`, namespace `apps-microservices`, cluster `matching-api-dev-k8s` |
| Réplicas | 3 | **1**, ajustable sur la profondeur de la file |
| File consommée | `graph_rag_semantic_vigil_queue` sur le broker prod `10.0.1.216` | **La même**, via `rabbitmq-internal.rabbitmq-v3.svc.cluster.local` |
| Dépendances | services de la VM par leur nom Docker | milvus graph-rag `10.11.0.2:15055` + **API d'embedding HTTP** (le client gRPC `EMBEDDING_SERVICE_URL` est commenté dans le code) — les services gRPC graph-rag **restent sur la VM** (enabler `10.11.0.2`) |
| Écriture Neo4j | par le connecteur de la VM, vers le Neo4j GKE `10.0.1.218` | **Identique** : le processor n'a aucun accès direct à Neo4j |
| État des jumeaux VM | `Up` ×3 | **`Exited` ×3, conservés** — filet de rollback |
| Code monté depuis la VM | aucun | image seule |

**Ce qui a changé côté configuration** :

- secret `graph-rag-semantique-vigil-processor-rabbitmq`, clé `rabbitmq-url` : broker dev → **prod** (empreinte relue = secret prod des lots précédents) ;
- `EMBEDDING_API_URL` et `EMBEDDING_API_KEY` (`platform-embedding-secrets`) — **ajoutées le 25/09**.

---

## 2. Ce qui a été prouvé — et ce qui ne l'est pas encore

| Preuve | Résultat |
|---|---|
| Pré-contrôle du dev | ✅ 24/09 : aucune écriture disque ; variables complétées (`SPACY_SERVICE_URL`, embedding HTTP) ; rejouable sans dégât |
| Adresses gRPC | ✅ mappage haproxy vérifié le 25/09 (`15055` milvus `:50056`, `15056` connecteur `:50055`, `15057` normalize `:50057`, `15058` spaCy `:50058`) ; ports joignables depuis GKE |
| Abonnement à la file **prod** | ✅ 28/09 07:24 UTC : `consumers=1`, jumeaux arrêtés |
| Santé au démarrage | ✅ 0 redémarrage, 0 Traceback, 0 erreur |
| Point de retour Neo4j | ✅ instantané `neo4j-data-pre-l5-20260928` (28/09 07:19 UTC) |
| Traitement de bout en bout sur données réelles | ✅ trafic réel 28-29/09 (relevés midi, 17h et nuit : 0 redémarrage, 0 Traceback) et tests du dev OK — **GO L5 le 29/09** |

---

## 3. Ce que vous devez savoir sur ce service

Contrôle sémantique avant l'ETL. Ses « upsert » Milvus sont des insertions protégées par un test d'existence : **deux réplicas sur la même caractéristique au même instant peuvent créer une ligne en double dans Milvus** (pas dans Neo4j) — c'est pourquoi il reste à **1 réplica**.

---

## 4. Comment vous accédez au service maintenant

**Ce qui ne marche plus** : `docker logs` sur la VM GPU montre des conteneurs **arrêtés**, figés au 28/09 07:17 UTC. Tout ce qui vit est sur GKE.

### Logs — depuis la VM Manager ou votre poste (`kubectl`)

```bash
kubectl -n apps-microservices logs deploy/graph-rag-semantique-vigil-processor --tail=200
kubectl -n apps-microservices logs deploy/graph-rag-semantique-vigil-processor -f
kubectl -n apps-microservices get pods -l app=graph-rag-semantique-vigil-processor
```

⚠️ La ligne de connexion au broker contient le mot de passe (F-HP-SEC-021). Masquez avant tout partage :
`| sed -E 's#(amqp://[^:]+):[^@]*@#\1:***@#g'`

### Logs — console GCP (Cloud Logging)

```
resource.type="k8s_container"
resource.labels.namespace_name="apps-microservices"
resource.labels.container_name="graph-rag-semantique-vigil-processor"
```

Lignes Python en sévérité `ERROR` (stderr) : filtrez par texte. Rétention 15 jours. Guide : [`../acces-logs-services-migres.md`](../acces-logs-services-migres.md).

### État, shell, file

```bash
kubectl -n apps-microservices describe pod -l app=graph-rag-semantique-vigil-processor | tail -30
kubectl -n apps-microservices exec -it deploy/graph-rag-semantique-vigil-processor -- /bin/sh
POD=$(kubectl -n rabbitmq-v3 get pods -o name | head -1)
kubectl -n rabbitmq-v3 exec "$POD" -- rabbitmqctl list_queues name messages consumers | grep -w graph_rag_semantic_vigil_queue
```

### Métriques

Le service expose `/metrics` (Prometheus) sur le port **8563**, surveillé par des sondes `tcpSocket` :

```bash
kubectl -n apps-microservices port-forward deploy/graph-rag-semantique-vigil-processor 8563:8563   # puis http://localhost:8563/metrics
```

---

## 5. Chronologie (UTC — Paris = UTC+2)

| UTC (28/09) | Geste |
|---|---|
| 07:11 | Pré-flight : 8 déploiements `1/1`, secrets conformes, URL broker prod identique au secret des lots précédents, variables LLM / spaCy / embedding en place |
| 07:16:34 | Photo du broker (DLQ préexistantes : `llm_extraction` 11, `normalization_manual` 5) |
| **07:16:43 → 07:17:16** | **Arrêt des 30 conteneurs VM du lot** (33 s) ; services gRPC graph-rag de la VM non touchés |
| 07:17:55 → 07:19:09 | **Instantané du disque Neo4j** `neo4j-data-pre-l5-20260928` |
| 07:21:05 → 07:24:03 | Garde-fou broker, copies `<secret>-prel5`, patch des 8 secrets (relus), rollout |
| **07:24:06** | **8 files consommées — bascule en ~7 min 23** |
| 07:28 → 07:30 | Palier 1 : `produit`, `etl`, `llm-extractor`, `normalize-unite-retry` à 2 réplicas |

---

## 6. Rollback de ce service

Le lot se rollbacke d'un bloc, dans cet ordre :

1. `kubectl -n apps-microservices scale deploy/graph-rag-semantique-vigil-processor --replicas=0`
2. `kubectl -n apps-microservices wait --for=delete pod -l app=graph-rag-semantique-vigil-processor --timeout=60s`
3. VM GPU : `docker start rag-hp-pub-graph-rag-semantique-vigil-processor-1 rag-hp-pub-graph-rag-semantique-vigil-processor-2 rag-hp-pub-graph-rag-semantique-vigil-processor-3`
4. vérifier `consumers=3` sur `graph_rag_semantic_vigil_queue`
5. remettre le secret depuis `graph-rag-semantique-vigil-processor-rabbitmq-prel5`, puis `scale --replicas=1` (retour en shadow)

**Données** : si le graphe est faussé, restauration du disque Neo4j depuis `neo4j-data-pre-l5-20260928` (décision LEAD + DSO, exécution DSO). Les devs signalent, ils ne rollbackent pas.

---

## 7. Points ouverts

| # | Constat | Pour qui |
|---|---|---|
| 1 | ✅ Validé sur le trafic réel le 29/09 (GO LEAD) | — |
| 2 | **SIGTERM ignoré** à l'arrêt des conteneurs VM (F-HP-DEV-006) | LEAD |
| 2 bis | Nuit du 28 au 29/09 : 16 % de timeouts sur l'API d'embedding au pic 18h-20h UTC (5 % sur la VM) ; en cas d'échec, le nœud n'est pas indexé dans Milvus graph-rag, sans trace (F-HP-DEV-008), correctif après cutover | dev |
| 3 | Jumeaux VM conservés pendant la fenêtre de rollback, puis retrait | DevSecOps |
| 4 | Mot de passe du broker dans les logs au démarrage (F-HP-SEC-021) | Tous |
