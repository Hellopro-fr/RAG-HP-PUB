# Rapport de bascule — `embedding-service`

> **Lot L6 · basculé le 2026-09-29 à 11:23 UTC (13:23 Paris)** · exécuté par le DevSecOps · pré-contrôle vérifié par le DSO le 25/09 · **GO le 30/09**, réserve **levée le 01/10** (nuit à 4 réplicas : file à 0, 0 deadline).
> Ce rapport dit ce qui a changé, ce qui a été prouvé, et **comment vous accédez maintenant au service** pour le déboguer.

---

## 1. Avant / après

| | Avant (VM GPU) | Après (GKE) |
|---|---|---|
| Où il tourne | `rag-hp-pub-embedding-service-1` à `-4`, Docker Compose, VM `vm-embedding-g2-std-24-use` | Déploiement `embedding-service`, namespace `apps-microservices`, cluster `matching-api-dev-k8s` |
| Réplicas | 4 | **4** (parité VM, depuis le 30/09 05:15 UTC ; 1 au départ) |
| File consommée | `embedding_queue` sur le broker prod `10.0.1.216` | **La même**, via `rabbitmq-internal.rabbitmq-v3.svc.cluster.local` |
| Dépendances | services de la VM par leur nom Docker | serveur d'embedding GPU de la VM en gRPC, `10.11.0.2:15052` (`EMBEDDING_SERVICE_URL`, enabler haproxy → `embedding-model-service:50052`) |
| État des jumeaux VM | `Up` ×4 | **`Exited` ×4, conservés** — filet de rollback |
| Ce qui a changé côté code | — | **Rien** (image `shadow-2026-09-15`) |

**Ce qui a changé côté configuration** :

- secret `embedding-service-rabbitmq`, clé `rabbitmq-url` : broker dev → **prod** (empreinte relue) ;
- `PROCESS_TIMEOUT=360` (valeur VM, commit infra `e97e2f65`) : doit rester supérieur à `GRPC_TIMEOUT` (300 par défaut) ;
- volume `emptyDir` `/logs` borné à 1 Gi (commit `baba9927`) : la classe partagée `common_utils` y écrit `embeddings.log` et `temps_embedding.log` ;
- `replicas: 4` (commit `00897696`).

---

## 2. Ce qui a été prouvé — et ce qui ne l'est pas encore

| Preuve | Résultat |
|---|---|
| Pré-contrôle | ✅ vérifié par le DSO le 25/09 dans le code, les conteneurs VM et Secret Manager (réponses du dev le 28/09) |
| Abonnement à la file **prod** | ✅ 29/09 11:23 UTC : `consumers=1`, jumeaux arrêtés ; `consumers=4` depuis le 30/09 05:15 |
| Santé | ✅ 0 redémarrage ; 0 Traceback jusqu'au pic nocturne |
| Traitement de bout en bout sur données réelles | ⚠️ nuit du 29 au 30/09 : **11 662 messages en attente** à 1 réplica (290 deadlines gRPC 02h-05h UTC, aucun message perdu) ; à 4 réplicas, file vidée en 14 min, 0 deadline. **Nuit du 30/09 au 01/10 à 4 réplicas : file à 0, 0 `DEADLINE_EXCEEDED` en 24 h sur les 4 pods → réserve levée le 01/10** |
| Rollback | ⬜ non joué (procédure identique aux lots précédents) |

---

## 3. Ce que vous devez savoir sur ce service

Il calcule les vecteurs des textes publiés sur `embedding_queue` en appelant le serveur d'embedding GPU de la VM, puis publie le résultat. **Capacité** : `PREFETCH_COUNT=2` messages en vol par réplica ; un appel qui dépasse `GRPC_TIMEOUT` (300 s) bloque son créneau pendant 5 minutes avant de partir en retry (`app/messaging/consumer.py:16-22`). Le serveur GPU sature au lot nocturne (02h-05h UTC) — c'était déjà le cas sur la VM (530 lignes de deadline à 03h le 29/09) : **ne pas descendre sous 4 réplicas** sans mesure. Retry puis DLQ `embedding_queue_dlq` après `MAX_RETRIES` : un message en échec n'est pas perdu.

Sur la VM, le code était **monté depuis le checkout** (`/home/devhp/RAG-HP-PUB/apps-microservices/embedding-service/app`) ; parité vérifiée avec la source de l'image GKE. Pas de `git pull` sur la VM tant que les jumeaux existent.

---

## 4. Comment vous accédez au service maintenant

**Ce qui ne marche plus** : `docker logs` sur la VM GPU montre des conteneurs **arrêtés**, figés au 29/09 vers 11:19 UTC. Tout ce qui vit est sur GKE.

### Logs — depuis la VM Manager ou votre poste (`kubectl`)

```bash
kubectl -n apps-microservices logs -l app=embedding-service --prefix --tail=200
kubectl -n apps-microservices logs -l app=embedding-service --prefix -f
kubectl -n apps-microservices get pods -l app=embedding-service
```

⚠️ Avec plusieurs réplicas, `kubectl logs deploy/embedding-service` ne lit **qu'un** pod : utilisez `-l app=embedding-service --prefix`.

⚠️ Masquez les URLs de broker avant tout partage :
`| sed -E 's#(amqp://[^:]+):[^@]*@#\1:***@#g'`

### Logs — console GCP (Cloud Logging)

```
resource.type="k8s_container"
resource.labels.namespace_name="apps-microservices"
resource.labels.container_name="embedding-service"
```

Lignes Python en sévérité `ERROR` (stderr) : filtrez par texte. Guide : [`../acces-logs-services-migres.md`](../acces-logs-services-migres.md).

### État, shell, file

```bash
kubectl -n apps-microservices describe pod -l app=embedding-service | tail -30
kubectl -n apps-microservices exec -it deploy/embedding-service -- /bin/sh
POD=$(kubectl -n rabbitmq-v3 get pods -o name | head -1)
kubectl -n rabbitmq-v3 exec "$POD" -- rabbitmqctl list_queues name messages consumers | grep -E '^embedding_queue'
```

### Métriques

Le service expose `/metrics` (Prometheus) sur le port **8530**, surveillé par des sondes `tcpSocket` :

```bash
kubectl -n apps-microservices port-forward deploy/embedding-service 8530:8530   # puis http://localhost:8530/metrics
```

---

## 5. Chronologie (UTC — Paris = UTC+2)

| UTC | Geste |
|---|---|
| 29/09 11:02 | Pré-flight : 3 déploiements `1/1`, 4 secrets conformes, URL broker prod identique aux lots précédents, `platform-key-webhook` = valeur VM (`21387e2c`), sonde `GET` vers l'URL du webhook → `405` (joignable) |
| 11:08:53 | Photo du broker (124 files) |
| **~11:19** | **Arrêt des 9 conteneurs VM du lot** (`Exited (137)`) ; files du lot `embedding_queue`, `llm_templating_queue`, `webhook_queue`, toutes à 0 message |
| 11:20:15 → 11:23:14 | Garde-fous, copies `<secret>-prel6` ×4, patch des 3 secrets broker et de `key-webhook` (relus), `WEBHOOK_UPDATE_PRODUIT_URL`, rollouts |
| **11:23:58** | **3 files consommées — bascule en ~4 min 30** |
| 12:20 → 12:23 | Première rafale réelle après 57 min de creux : 7 webhooks `200` au premier essai |
| 15:26 | Relevé de 17h : 0 restart, 0 erreur ; 197 appels webhook `2xx` |
| 30/09 05:09 | Relevé de nuit : **`embedding_queue` à 11 662 messages** (1 réplica), deadlines gRPC 02h-05h UTC ; template-llm et webhook propres |
| 05:15 → 05:29 | `embedding-service` 1 → 4 (parité VM) ; file vidée, 0 deadline |
| 30/09 matin | **GO L6** (embedding sous réserve de la nuit suivante) |

---

## 6. Rollback de ce service

1. `kubectl -n apps-microservices scale deploy/embedding-service --replicas=0`
2. `kubectl -n apps-microservices wait --for=delete pod -l app=embedding-service --timeout=60s` (jamais deux consommateurs en même temps)
3. VM GPU : `docker start rag-hp-pub-embedding-service-1 rag-hp-pub-embedding-service-2 rag-hp-pub-embedding-service-3 rag-hp-pub-embedding-service-4`
4. vérifier `consumers=4` sur `embedding_queue`
5. remettre le secret depuis `embedding-service-rabbitmq-prel6`, puis `scale --replicas=1` (retour en shadow)

**Données** : ce lot n'écrit dans aucune base. Les devs signalent, ils ne rollbackent pas.

---

## 7. Points ouverts

| # | Constat | Pour qui |
|---|---|---|
| 1 | ✅ Réserve levée le 01/10 (0 deadline, file à 0) ; ne pas descendre sous 4 réplicas sans mesure | DSO |
| 2 | **SIGTERM ignoré** à l'arrêt des conteneurs VM (`Exited (137)`, F-HP-DEV-006) | LEAD |
| 3 | Jumeaux VM conservés pendant la fenêtre de rollback, puis retrait | DevSecOps |
| 4 | Mot de passe du broker dans les logs au démarrage (F-HP-SEC-021) | Tous |
