# Rapport de bascule — `prix-milvus-processor`

> **Lot L3 · basculé le 2026-09-23 à 07:30 UTC (09:30 Paris)** · exécuté par le DevSecOps · validé techniquement le 23/09 après-midi sur tests réels ; **décision du lot jeudi 24/09 9h30** (LEAD + DSO).
> Ce service est **le premier écrivain Milvus de production** de la série. Ce rapport dit ce qui a changé, ce qui a été prouvé, comment revenir en arrière sur les données, et **comment vous accédez maintenant au service**.

---

## 1. Avant / après

| | Avant (VM GPU) | Après (GKE) |
|---|---|---|
| Où il tourne | `rag-hp-pub-prix-milvus-processor-service-1` à `-4`, Docker Compose, VM `vm-embedding-g2-std-24-use` | Déploiement **`prix-milvus-processor`** (sans `-service`), namespace `apps-microservices`, cluster `matching-api-dev-k8s` |
| Réplicas | 4 | **2** au départ (la moitié), ajustable sur la profondeur de la file |
| File consommée | `insertion_prix_queue` sur le broker prod `10.0.1.216` | **La même**, via `rabbitmq-internal.rabbitmq-v3.svc.cluster.local` (même broker) |
| Écriture | Milvus prod `10.0.1.51:19530`, collection `prix` (insertion seule, `id` INT64 auto-généré) | **La même base**, par `milvus-prod.hello.dev.private.com` (résout vers `10.0.1.51`) |
| Image | — | `prix-milvus-processor:shadow-2026-09-15` (pas de tracking fichier dans ce service) |
| État des jumeaux VM | `Up` ×4 | **`Exited` ×4, conservés** — filet de rollback |
| Ce qui a changé côté code | — | **Rien** |

**Ce qui a changé côté configuration** — secret **multi-clés** `prix-milvus-processor-secrets`, modifié clé par clé (`kubectl patch`, jamais recréé) :

- `rabbitmq-url` : broker dev → **prod** ;
- `zilliz-user` / `zilliz-password` : identifiants Milvus dev → **prod**, depuis Secret Manager `platform-zilliz-user` / `platform-zilliz-password` (empreintes `ec7955cf` / `7384d49e`, identiques à la VM) ;
- variable `ZILLIZ_URI` : `my-release-milvus.default.svc.cluster.local` (dev) → `milvus-prod.hello.dev.private.com` ; réplicas 1 → 2 (commit infra `448e0bbc`).

---

## 2. Ce qui a été prouvé — et ce qui ne l'est pas encore

| Preuve | Résultat |
|---|---|
| Milvus prod joignable depuis GKE | ✅ 23/09 P0 : DNS résolu, port 19530 ouvert depuis un pod |
| Le service voit la collection prod | ✅ 07:33 UTC : `prix` = 23 483 entités vues depuis les pods, 0 erreur au démarrage |
| Abonnement à la file **prod** | ✅ 07:32:17 UTC : `insertion_prix_queue` à `consumers=2`, jumeaux VM arrêtés |
| Écritures réelles | ✅ 23/09 après-midi : **101 lignes** insérées au-delà de la borne (28 venues de `prix-extraction-message`, 43 de `prix-extraction-devis`, 30 de `prix-extraction-siteweb` resté sur la VM) |
| Écritures **une seule fois** | ✅ 0 doublon, 0 lead réinséré sur les lignes `id > 467759069053297382` |
| Tenue sur la durée | ⬜ relevé de la nuit à faire jeudi 24/09 9h30 (file vide, pas de doublon au-delà de la borne) |

---

## 3. Ce que vous devez savoir sur ce service

**Tout ce qui entre dans `insertion_prix_queue` finit dans Milvus prod**, quelle que soit sa provenance : les extracteurs prix basculés sur GKE, mais aussi `prix-extraction-siteweb`, resté sur la VM, qui publie dans les mêmes files.

**Connexion Milvus à la demande** : le pod démarre même si Milvus est injoignable ; l'erreur n'apparaît qu'au premier message. Un pod `Running` ne prouve donc pas que l'écriture marche — lisez les logs après un message.

**Il expose un port** `8010` (métriques Prometheus), surveillé par des sondes `tcpSocket` : un pod qui ne répond plus sur 8010 est redémarré.

---

## 4. Comment vous accédez au service maintenant

**Ce qui ne marche plus** : `docker logs` sur la VM GPU montre des conteneurs **arrêtés**, figés à l'heure de la bascule. Tout ce qui vit est sur GKE.

### Logs — depuis la VM Manager ou votre poste (`kubectl`)

```bash
kubectl -n apps-microservices logs deploy/prix-milvus-processor --all-pods --prefix --tail=200
kubectl -n apps-microservices logs deploy/prix-milvus-processor --all-pods --prefix -f
kubectl -n apps-microservices get pods -l app=prix-milvus-processor
kubectl -n apps-microservices logs <nom-du-pod> --since=1h
```

⚠️ La ligne de connexion au broker contient le mot de passe (F-HP-SEC-021). Masquez avant tout partage :
`| sed -E 's#(amqp://[^:]+):[^@]*@#\1:***@#g'`

### Logs — console GCP (Cloud Logging)

```
resource.type="k8s_container"
resource.labels.namespace_name="apps-microservices"
resource.labels.container_name="prix-milvus-processor"
```

Ajoutez `textPayload:"<id catégorie ou message>"` pour suivre un traitement. Les lignes Python arrivent en sévérité `ERROR` (stderr) : filtrez par texte, pas par sévérité. Rétention 15 jours. Guide complet : [`../acces-logs-services-migres.md`](../acces-logs-services-migres.md).

### État, événements, shell

```bash
kubectl -n apps-microservices describe pod -l app=prix-milvus-processor | tail -30
kubectl -n apps-microservices exec -it deploy/prix-milvus-processor -- /bin/sh
```

### La file

```bash
POD=$(kubectl -n rabbitmq-v3 get pods -o name | head -1)
kubectl -n rabbitmq-v3 exec "$POD" -- rabbitmqctl list_queues name messages consumers | grep insertion_prix
```

`consumers=2` = nominal. `messages` qui monte = l'écriture Milvus ne suit plus.

### Métriques

```bash
kubectl -n apps-microservices port-forward deploy/prix-milvus-processor 8010:8010
# puis http://localhost:8010/metrics
```

### Compter ce que GKE a écrit (lecture seule)

Toute entité `id > 467759069053297382` dans `prix` a été insérée depuis la bascule. Le DevSecOps fait ce relevé depuis un conteneur jetable portant les mêmes variables `ZILLIZ_*` ; demandez-le plutôt que d'ouvrir une session sur Milvus prod.

---

## 5. Chronologie (UTC — Paris = UTC+2)

| UTC (23/09) | Geste |
|---|---|
| 06:58 | Référence Milvus prod : collection `prix` = 23 483 entités, `max id 467759069053297382` ; sauvegarde de la nuit `daily_20260923_020000` vérifiée |
| 07:20 | Pré-flight : 5 déploiements, 5 secrets broker, 8 conteneurs VM |
| **07:28:07 → 07:28:38** | **Arrêt des 8 jumeaux prix** (`Exited 137`) |
| 07:28:43 | Borne du rollback données relevée après l'arrêt : `max id` inchangé, 23 483 lignes |
| 07:30:40 → 07:31:28 | Secrets repointés (broker prod ; identifiants Milvus prod), `ZILLIZ_URI` prod, `rollout` des 5 déploiements |
| **07:32:17** | **5 files consommées — bascule du lot en ~4 min 10** |
| 12:27 → 13:12 | Tests réels du dev sur la catégorie `2005786` |
| 13:05 | Manifestes alignés sur le cluster, `kubectl diff` sans écart (commit infra `448e0bbc`) |
| 13:12 | 101 insertions constatées (message, devis, siteweb), 0 doublon |

---

## 6. Rollback de ce service — et des données

**Service** (~2 minutes, dans cet ordre) :

1. `kubectl -n apps-microservices scale deploy/prix-milvus-processor --replicas=0`
2. `kubectl -n apps-microservices wait --for=delete pod -l app=prix-milvus-processor --timeout=60s`
3. VM GPU : `docker start rag-hp-pub-prix-milvus-processor-service-{1,2,3,4}`
4. vérifier `consumers=4` sur `insertion_prix_queue`
5. remettre dans `prix-milvus-processor-secrets` le broker dev et les identifiants Milvus dev (`kubectl patch` clé par clé), `ZILLIZ_URI` sur `my-release-milvus.default.svc.cluster.local`, puis `scale --replicas=1` (retour en shadow)

**Données**, seulement si des écritures sont fausses ou en double : supprimer dans `prix` les entités **`id > 467759069053297382`** (depuis le 23/09 07:28 UTC, seul GKE écrit). Restauration complète possible depuis la sauvegarde `gs://milvus-cluster-data-backup/milvus-backups/daily/daily_20260923_020000`. Décision LEAD + DSO, exécution DSO.

Les devs signalent, ils ne rollbackent pas.

---

## 7. Points ouverts

| # | Constat | Pour qui |
|---|---|---|
| 1 | Relevé de nuit du 24/09 : file vide, lignes `id > borne` sans doublon | DevSecOps, jeu 24/09 9h30 |
| 2 | **Réplicas** : 2 contre 4 sur la VM. Surveiller `insertion_prix_queue` aux heures chargées ; passer à 3 ou 4 si elle monte | DevSecOps |
| 3 | La borne `467759069053297382` reste le point de retour des données tant que le lot n'est pas validé ; après validation, elle n'a plus d'usage | DevSecOps |
| 4 | **SIGTERM ignoré** à l'arrêt (`Exited 137` ×4) : F-HP-DEV-006 | LEAD |
| 5 | Mot de passe du broker dans les logs au démarrage (F-HP-SEC-021) — masquer avant partage | Tous |
