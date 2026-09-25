# Rapport de bascule — `website-processor-service`

> **Lot L4 · basculé le 2026-09-24 à 08:58 UTC (10:58 Paris)** · exécuté par le DevSecOps · pré-contrôle du LEAD reçu le 24/09 ; validation sur le trafic réel ; **lot validé le 25/09 (GO LEAD)** après une nuit de production (≈ 33 000 produits traités, files et DLQ à 0, 0 redémarrage).
> Ce rapport dit ce qui a changé, ce qui a été prouvé, et **comment vous accédez maintenant au service** pour le déboguer.

---

## 1. Avant / après

| | Avant (VM GPU) | Après (GKE) |
|---|---|---|
| Où il tourne | `rag-hp-pub-website-processor-service-1` à `-7`, Docker Compose, VM `vm-embedding-g2-std-24-use` | Déploiement `website-processor-service`, namespace `apps-microservices`, cluster `matching-api-dev-k8s` |
| Réplicas | 7 | **1** (palier 1 du 24/09), ajustable sur la profondeur de la file |
| File consommée | `website_processing_queue` sur le broker prod `10.0.1.216` | **La même**, via `rabbitmq-internal.rabbitmq-v3.svc.cluster.local` (même broker) |
| Sortie | `processed_data_exchange` / `data.ready_for_templating` (vers `template-llm-service`, resté sur la VM jusqu'à L6) | **Identique** |
| État des jumeaux VM | `Up` ×7 | **`Exited` ×7, conservés** — filet de rollback |
| Code monté depuis la VM | aucun (vérifié le 24/09) | image seule |
| Ce qui a changé côté code | — | **Rien** |

**Ce qui a changé côté configuration** : secret `website-processor-secrets`, clés `rabbitmq-url` et `redis-url`, valeurs dev → **prod** (Secret Manager `platform-rabbitmq-url`, réécrite en DNS interne, et `platform-redis-url`). Chaque clé posée a été relue par empreinte ; empreintes identiques à celles des conteneurs VM.

---

## 2. Ce qui a été prouvé — et ce qui ne l'est pas encore

| Preuve | Résultat |
|---|---|
| Pré-contrôle du dev | ✅ 24/09 : aucune écriture disque, seules les variables connues, double traitement sans dégât |
| Parité des valeurs VM / GKE | ✅ empreintes identiques (broker, Redis) |
| Abonnement à la file **prod** | ✅ 24/09 08:58 UTC : `consumers=1`, jumeaux VM arrêtés |
| Santé depuis la bascule | ✅ pods `Running`, 0 redémarrage, 0 Traceback, 0 erreur |
| Traitement de bout en bout sur données réelles | ✅ trafic réel 24-25/09 : files et DLQ à 0, 0 redémarrage ; seules erreurs = coupures `pika` préexistantes, reprises |

---

## 3. Ce que vous devez savoir sur ce service

**Le plus gros consumer du lot** (7 conteneurs sur la VM). Il utilise **Redis prod** (`10.0.1.220:6379`) en plus du broker. Laissé à **1 réplica** : sa file était vide à la bascule et la mémoire du cluster est serrée ; on monte (jusqu'à 4) sur constat de backlog.

**Il ne touche pas Milvus.** Il prépare la donnée et la publie sur `processed_data_exchange` / `data.ready_for_templating` (vers `template-llm-service`, resté sur la VM jusqu'à L6). La suite de la chaîne passe donc par la VM puis revient sur GKE (les écrivains du lot) : un message peut traverser GKE → VM → GKE, via le même broker.

---

## 4. Comment vous accédez au service maintenant

**Ce qui ne marche plus** : `docker logs` sur la VM GPU montre des conteneurs **arrêtés**, figés au 24/09 08:46 UTC. Tout ce qui vit est sur GKE.

### Logs — depuis la VM Manager ou votre poste (`kubectl`)

```bash
kubectl -n apps-microservices logs deploy/website-processor-service --tail=200
kubectl -n apps-microservices logs deploy/website-processor-service -f
kubectl -n apps-microservices get pods -l app=website-processor-service
kubectl -n apps-microservices logs <nom-du-pod> --since=1h
```

⚠️ Les URL du broker et de Redis contiennent un mot de passe. Masquez avant tout partage :
`| sed -E 's#(amqp://[^:]+):[^@]*@#\1:***@#g; s#(redis://[^@]*):[^@]*@#\1:***@#g'`

### Logs — console GCP (Cloud Logging)

```
resource.type="k8s_container"
resource.labels.namespace_name="apps-microservices"
resource.labels.container_name="website-processor-service"
```

Ajoutez `textPayload:"<identifiant>"` pour suivre un traitement. Les lignes Python arrivent en sévérité `ERROR` (stderr) : filtrez par texte, pas par sévérité. Rétention 15 jours. Guide : [`../acces-logs-services-migres.md`](../acces-logs-services-migres.md).

### État, événements, shell

```bash
kubectl -n apps-microservices describe pod -l app=website-processor-service | tail -30
kubectl -n apps-microservices exec -it deploy/website-processor-service -- /bin/sh
```

### La file

```bash
POD=$(kubectl -n rabbitmq-v3 get pods -o name | head -1)
kubectl -n rabbitmq-v3 exec "$POD" -- rabbitmqctl list_queues name messages consumers | grep -w website_processing_queue
```

`consumers` = nombre de réplicas = nominal. `messages` qui monte durablement = le service ne suit plus.

### Métriques

Le service expose `/metrics` (Prometheus) sur le port **8530**, surveillé par des sondes `tcpSocket` :

```bash
kubectl -n apps-microservices port-forward deploy/website-processor-service 8530:8530   # puis http://localhost:8530/metrics
```

---

## 5. Chronologie (UTC — Paris = UTC+2)

| UTC (24/09) | Geste |
|---|---|
| 07:59 | Pré-flight : 9 déploiements `1/1`, clés des secrets conformes, URL broker prod identique au secret L3 |
| 08:44:28 | Photo du broker : files du lot à 0 message |
| **08:45:35 → 08:46:08** | **Arrêt des 39 conteneurs VM du lot** (33 s) |
| 08:46:29 → 08:50:39 | **Sauvegarde Milvus à la demande `daily_20260924_084629`**, VM arrêtée, avant toute écriture GKE |
| 08:53:03 → 08:57:42 | Garde-fous d'empreintes, copies `<secret>-prel4`, patch des 9 secrets (chaque clé relue), `ZILLIZ_URI` prod sur les 5 écrivains, rollout |
| **08:58:00** | **9 files consommées — bascule du lot en ~12 min 25** (dont 4 min 10 de sauvegarde) |
| 09:01 → 09:02:28 | Palier 1 : 8 déploiements à 2 réplicas, 0 `Pending` ; `website-processor-service` laissé à 1 (file vide, mémoire du cluster serrée) |

---

## 6. Rollback de ce service

Retour sur la VM en ~2 minutes, **dans cet ordre** (le lot entier se rollbacke d'un bloc, pas service par service, sauf décision contraire) :

1. `kubectl -n apps-microservices scale deploy/website-processor-service --replicas=0`
2. `kubectl -n apps-microservices wait --for=delete pod -l app=website-processor-service --timeout=60s`
3. VM GPU : `docker start rag-hp-pub-website-processor-service-1 rag-hp-pub-website-processor-service-2 rag-hp-pub-website-processor-service-3 rag-hp-pub-website-processor-service-4 rag-hp-pub-website-processor-service-5 rag-hp-pub-website-processor-service-6 rag-hp-pub-website-processor-service-7`
4. vérifier `consumers=7` sur sa file
5. remettre les secrets depuis leur copie `<secret>-prel4` (valeurs shadow d'avant la bascule), puis `scale --replicas=1` (retour en shadow)

Exécuté par le DevSecOps. Les devs signalent, ils ne rollbackent pas.

---

## 7. Points ouverts

| # | Constat | Pour qui |
|---|---|---|
| 1 | **Validation sur le trafic réel** (aucun test possible) : le référent confirme sur les données du jour que la donnée est présente, une seule fois, ancienne version bien remplacée | Dev référent · DSO |
| 2 | Réplicas : 1 contre 7 sur la VM. Surveiller `website_processing_queue` ; monter à 2 puis 4 si elle accumule | DevSecOps |
| 3 | **SIGTERM ignoré** à l'arrêt des conteneurs VM (même défaut que L1-L3, F-HP-DEV-006) | LEAD |
| 4 | Jumeaux VM conservés pendant la fenêtre de rollback, puis retrait (`docker rm` + neutralisation dans `docker-compose.yml`) | DevSecOps |
| 5 | Mot de passe du broker (et de Redis) dans les logs au démarrage (F-HP-SEC-021) — masquer avant partage | Tous |
