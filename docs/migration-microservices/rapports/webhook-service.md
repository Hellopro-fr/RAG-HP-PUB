# Rapport de bascule — `webhook-service`

> **Lot L6 · basculé le 2026-09-29 à 11:23 UTC (13:23 Paris)** · exécuté par le DevSecOps · pré-contrôle vérifié par le DSO le 25/09 · **GO le 30/09** (256 appels `2xx`, 0 refus).
> Ce rapport dit ce qui a changé, ce qui a été prouvé, et **comment vous accédez maintenant au service** pour le déboguer.

---

## 1. Avant / après

| | Avant (VM GPU) | Après (GKE) |
|---|---|---|
| Où il tourne | `webhook-service` (seul conteneur VM sans préfixe `rag-hp-pub-`), Docker Compose, VM `vm-embedding-g2-std-24-use` | Déploiement `webhook-service`, namespace `apps-microservices`, cluster `matching-api-dev-k8s` |
| Réplicas | 1 | **1** |
| File consommée | `webhook_queue` sur le broker prod `10.0.1.216` | **La même**, via `rabbitmq-internal.rabbitmq-v3.svc.cluster.local` |
| Dépendances | services de la VM par leur nom Docker | **back-office PHP** `https://www.hellopro.fr/fichiers_communs_bo_front/rag/webhook/webhook_update_produit_scrapping.php` (appels HTTP signés HMAC, via Cloud NAT) |
| État des jumeaux VM | `Up` ×1 | **`Exited` ×1, conservés** — filet de rollback |
| Ce qui a changé côté code | — | **Rien** (image `shadow-2026-09-15`) |

**Ce qui a changé côté configuration** :

- secret `webhook-service-rabbitmq`, clé `rabbitmq-url` : broker dev → **prod** (empreinte relue) ;
- secret partagé `platform-llm-hp-secrets`, clé `key-webhook` : placeholder → **valeur réelle** (Secret Manager `platform-key-webhook`, empreinte `21387e2c` = conteneur VM) ;
- `WEBHOOK_UPDATE_PRODUIT_URL` = URL VM (commit infra `8dfe1afd`) — **indispensable** : sans elle, repli sur la table `CollectionWebhook` qui pointe `webhook.site`.

---

## 2. Ce qui a été prouvé — et ce qui ne l'est pas encore

| Preuve | Résultat |
|---|---|
| Pré-contrôle | ✅ vérifié par le DSO le 25/09 dans le code, les conteneurs VM et Secret Manager (réponses du dev le 28/09) |
| Joignabilité du back-office depuis GKE | ✅ 29/09 11:02 : `GET` sans signature → `405` (rien n'est traité côté PHP) |
| Abonnement à la file **prod** | ✅ 29/09 11:23 UTC : `consumers=1`, jumeau arrêté |
| Signature acceptée par le back-office | ✅ premiers appels réels 29/09 12:20 UTC : `200` au premier essai |
| Traitement de bout en bout sur données réelles | ✅ du 29/09 11:23 au 30/09 05:09 : 1 630 messages reçus, 815 ignorés (`mode` ≠ `update`), **256 appels `2xx`**, 0 `HTTP ≥ 400`, 0 échec définitif — **GO 30/09** |
| Rollback | ⬜ non joué (procédure identique aux lots précédents) |

---

## 3. Ce que vous devez savoir sur ce service

Il n'envoie que les messages `mode=update` et acquitte les autres sans rien faire (`app/messaging/consumer.py:157`). Il **regroupe** les produits : un appel HTTP par URL, dès 50 messages ou après 5 s (`WEBHOOK_BATCH_SIZE`, `WEBHOOK_BATCH_TIMEOUT_S`, `app/core/processor.py:15-16`) — reçus ≠ appels, c'est normal. **Aucune déduplication** et, après 3 échecs, le message est **supprimé sans file d'erreurs** (F-HP-DEV-007). **Ne jamais rejouer d'anciens messages** de `webhook_queue` : le produit pointerait vers des ID Milvus déjà supprimés. Pas de serveur de métriques ni de sonde (consumer pur) : santé lue dans les logs.

---

## 4. Comment vous accédez au service maintenant

**Ce qui ne marche plus** : `docker logs` sur la VM GPU montre des conteneurs **arrêtés**, figés au 29/09 vers 11:19 UTC. Tout ce qui vit est sur GKE.

### Logs — depuis la VM Manager ou votre poste (`kubectl`)

```bash
kubectl -n apps-microservices logs deploy/webhook-service --tail=200
kubectl -n apps-microservices logs deploy/webhook-service -f
kubectl -n apps-microservices get pods -l app=webhook-service
```



⚠️ Masquez les URLs de broker avant tout partage :
`| sed -E 's#(amqp://[^:]+):[^@]*@#\1:***@#g'`

### Logs — console GCP (Cloud Logging)

```
resource.type="k8s_container"
resource.labels.namespace_name="apps-microservices"
resource.labels.container_name="webhook-service"
```

Lignes Python en sévérité `ERROR` (stderr) : filtrez par texte. Guide : [`../acces-logs-services-migres.md`](../acces-logs-services-migres.md).

### État, shell, file

```bash
kubectl -n apps-microservices describe pod -l app=webhook-service | tail -30
kubectl -n apps-microservices exec -it deploy/webhook-service -- /bin/sh
POD=$(kubectl -n rabbitmq-v3 get pods -o name | head -1)
kubectl -n rabbitmq-v3 exec "$POD" -- rabbitmqctl list_queues name messages consumers | grep -E '^webhook_queue'
```

### Métriques

Aucun serveur de métriques ni sonde : le pod redémarre seul si le processus s'arrête (`restartPolicy: Always`). Santé lue dans les logs et sur la file.

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

1. `kubectl -n apps-microservices scale deploy/webhook-service --replicas=0`
2. `kubectl -n apps-microservices wait --for=delete pod -l app=webhook-service --timeout=60s` (jamais deux consommateurs en même temps)
3. VM GPU : `docker start webhook-service`
4. vérifier `consumers=1` sur `webhook_queue`
5. remettre le secret depuis `webhook-service-rabbitmq-prel6` et la **clé seule** `key-webhook` depuis `platform-llm-hp-secrets-prel6` (secret partagé : ne pas restaurer les autres clés), puis `scale --replicas=1` (retour en shadow)

**Données** : ce lot n'écrit dans aucune base. Les devs signalent, ils ne rollbackent pas.

---

## 7. Points ouverts

| # | Constat | Pour qui |
|---|---|---|
| 1 | Déduplication et file d'erreurs du webhook (F-HP-DEV-007), correctif après cutover | dev |
| 2 | **SIGTERM ignoré** à l'arrêt des conteneurs VM (`Exited (137)`, F-HP-DEV-006) | LEAD |
| 3 | Jumeaux VM conservés pendant la fenêtre de rollback, puis retrait | DevSecOps |
| 4 | Mot de passe du broker dans les logs au démarrage (F-HP-SEC-021) | Tous |
