# Rapport de bascule — `document-database-qdrant-service`

> **Lot L4 · basculé le 2026-09-24 à 08:58 UTC (10:58 Paris)** · exécuté par le DevSecOps · pré-contrôle du LEAD reçu le 24/09 ; validation fonctionnelle **sur le trafic réel** (aucun test possible) ; décision du lot **vendredi 25/09 9h30**.
> Ce service **écrit dans Milvus prod**. Ce rapport dit ce qui a changé, ce qui a été prouvé, comment revenir en arrière sur les données, et **comment vous accédez maintenant au service**.

---

## 1. Avant / après

| | Avant (VM GPU) | Après (GKE) |
|---|---|---|
| Où il tourne | `rag-hp-pub-document-database-qdrant-service-1` à `-4`, Docker Compose, VM `vm-embedding-g2-std-24-use` | Déploiement `document-database-qdrant-service`, namespace `apps-microservices`, cluster `matching-api-dev-k8s` |
| Réplicas | 4 | **2** (palier 1 du 24/09), ajustable sur la profondeur de la file |
| File consommée | `insertion_document_queue` sur le broker prod `10.0.1.216` | **La même**, via `rabbitmq-internal.rabbitmq-v3.svc.cluster.local` (même broker) |
| Écriture | Milvus prod (`milvus-prod.hello.dev.private.com` → `10.0.1.51:19530`) : `document` (188 k) et `pjechanges` (199 k) | **La même base, les mêmes collections** |
| Coordination | garde de concurrence Milvus via Redis prod `10.0.1.220:6379` | **Le même Redis** (VM et GKE ont basculé ensemble, jamais à moitié) |
| État des jumeaux VM | `Up` ×4 | **`Exited` ×4, conservés** — filet de rollback |
| Code monté depuis la VM | aucun (vérifié le 24/09) | image seule |
| Ce qui a changé côté code | — | **Rien** |

**Ce qui a changé côté configuration** — secret multi-clés `document-database-qdrant-secrets`, modifié clé par clé (`kubectl patch`, jamais recréé ; copie d'avant bascule `document-database-qdrant-secrets-prel4`) :

- `rabbitmq-url` : broker dev → **prod** (Secret Manager `platform-rabbitmq-url`, réécrite en DNS interne) ;
- `redis-url` : Redis dev → **prod** (`platform-redis-url`) ;
- `zilliz-user` / `zilliz-password` : identifiants Milvus dev → **prod** (`platform-zilliz-user` / `platform-zilliz-password`) ;
- variable `ZILLIZ_URI` : `my-release-milvus.default.svc.cluster.local` (dev) → **`milvus-prod.hello.dev.private.com`**.

Toutes les empreintes posées ont été relues et sont identiques à celles des conteneurs VM.

---

## 2. Ce qui a été prouvé — et ce qui ne l'est pas encore

| Preuve | Résultat |
|---|---|
| Pré-contrôle du dev | ✅ 24/09 : aucune écriture disque, seules `RABBITMQ_URL`/`REDIS_URL`/`ZILLIZ_*`, **double traitement : résultat identique, sans doublon ni perte** |
| Milvus prod, Redis prod et broker joignables depuis GKE | ✅ sondes TCP du 24/09 |
| `RECREATE_COLLECTIONS` (suppression de collection au démarrage) | ✅ codé à `False` dans `common_utils`, jamais surchargé |
| Abonnement à la file **prod** | ✅ 24/09 08:58 UTC : `consumers=1`, jumeaux arrêtés ; 2 après le palier 1 |
| `ZILLIZ_URI` effectif dans les pods | ✅ `milvus-prod.hello.dev.private.com` |
| Santé depuis la bascule | ✅ 0 redémarrage, 0 Traceback, 0 erreur |
| Point de retour données | ✅ sauvegarde `daily_20260924_084629` (VM arrêtée, avant la 1re écriture GKE) |
| Écritures réelles justes et **une seule fois** | ⬜ validation sur le trafic réel : relevés 24/09 après-midi et 25/09 9h30 (deltas d'entités, échantillon d'identifiants) |

---

## 3. Ce que vous devez savoir sur ce service

**Il ne fait pas qu'insérer** : il `update_document` (chemin principal), insertion document et pièces jointes. Un rollback données ne peut donc pas se limiter à « supprimer ce qui a été ajouté » ; il passe par la restauration de la sauvegarde.

**Tout ce qui arrive dans `insertion_document_queue` finit dans Milvus prod**, quelle que soit sa provenance : la file est alimentée par `embedding-service`, resté sur la VM jusqu'à L6.

**Connexion Milvus à la demande** : un pod `Running` ne prouve pas que l'écriture marche ; lisez les logs après un message.

---

## 4. Comment vous accédez au service maintenant

**Ce qui ne marche plus** : `docker logs` sur la VM GPU montre des conteneurs **arrêtés**, figés au 24/09 08:46 UTC. Tout ce qui vit est sur GKE.

### Logs — depuis la VM Manager ou votre poste (`kubectl`)

```bash
kubectl -n apps-microservices logs deploy/document-database-qdrant-service --all-pods --prefix --tail=200
kubectl -n apps-microservices logs deploy/document-database-qdrant-service --all-pods --prefix -f
kubectl -n apps-microservices get pods -l app=document-database-qdrant-service
kubectl -n apps-microservices logs <nom-du-pod> --since=1h
```

⚠️ Les URL du broker et de Redis contiennent un mot de passe. Masquez avant tout partage :
`| sed -E 's#(amqp://[^:]+):[^@]*@#\1:***@#g; s#(redis://[^@]*):[^@]*@#\1:***@#g'`

### Logs — console GCP (Cloud Logging)

```
resource.type="k8s_container"
resource.labels.namespace_name="apps-microservices"
resource.labels.container_name="document-database-qdrant-service"
```

Ajoutez `textPayload:"<identifiant>"` pour suivre un traitement. Les lignes Python arrivent en sévérité `ERROR` (stderr) : filtrez par texte, pas par sévérité. Rétention 15 jours. Guide : [`../acces-logs-services-migres.md`](../acces-logs-services-migres.md).

### État, événements, shell

```bash
kubectl -n apps-microservices describe pod -l app=document-database-qdrant-service | tail -30
kubectl -n apps-microservices exec -it deploy/document-database-qdrant-service -- /bin/sh
```

### La file

```bash
POD=$(kubectl -n rabbitmq-v3 get pods -o name | head -1)
kubectl -n rabbitmq-v3 exec "$POD" -- rabbitmqctl list_queues name messages consumers | grep -w insertion_document_queue
```

`consumers` = nombre de réplicas = nominal. `messages` qui monte durablement = le service ne suit plus.

### Métriques

Le service expose `/metrics` (Prometheus) sur le port **8530**, surveillé par des sondes `tcpSocket` :

```bash
kubectl -n apps-microservices port-forward deploy/document-database-qdrant-service 8530:8530   # puis http://localhost:8530/metrics
```

### Vérifier une écriture dans Milvus (lecture seule)

Le DevSecOps fait les relevés Milvus prod depuis un pod qui porte déjà les identifiants (jamais depuis un poste). Donnez-lui l'identifiant métier (URL, `id_produit`, id échange, id document, id devis) : il vérifie la présence, l'unicité et la date d'insertion.

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

1. `kubectl -n apps-microservices scale deploy/document-database-qdrant-service --replicas=0`
2. `kubectl -n apps-microservices wait --for=delete pod -l app=document-database-qdrant-service --timeout=60s`
3. VM GPU : `docker start rag-hp-pub-document-database-qdrant-service-1 rag-hp-pub-document-database-qdrant-service-2 rag-hp-pub-document-database-qdrant-service-3 rag-hp-pub-document-database-qdrant-service-4`
4. vérifier `consumers=4` sur sa file
5. remettre les secrets depuis leur copie `<secret>-prel4` (valeurs shadow d'avant la bascule), `ZILLIZ_URI` sur `my-release-milvus.default.svc.cluster.local`, puis `scale --replicas=1` (retour en shadow)

**Données** : si des écritures sont fausses, restauration des collections concernées depuis la sauvegarde **`daily_20260924_084629`**, prise VM arrêtée, juste avant la première écriture GKE. Décision LEAD + DSO, exécution DSO.

Exécuté par le DevSecOps. Les devs signalent, ils ne rollbackent pas.

---

## 7. Points ouverts

| # | Constat | Pour qui |
|---|---|---|
| 1 | **Validation sur le trafic réel** (aucun test possible) : le référent confirme sur les données du jour que la donnée est présente, une seule fois, ancienne version bien remplacée | Dev référent · DSO |
| 2 | Réplicas : 2 contre 4 sur la VM. Surveiller `insertion_document_queue` aux heures chargées ; passer à 3 ou 4 si elle accumule (mémoire du cluster à vérifier avant) | DevSecOps |
| 3 | **SIGTERM ignoré** à l'arrêt des conteneurs VM (même défaut que L1-L3, F-HP-DEV-006) | LEAD |
| 4 | Jumeaux VM conservés pendant la fenêtre de rollback, puis retrait (`docker rm` + neutralisation dans `docker-compose.yml`) | DevSecOps |
| 5 | Mot de passe du broker (et de Redis) dans les logs au démarrage (F-HP-SEC-021) — masquer avant partage | Tous |
