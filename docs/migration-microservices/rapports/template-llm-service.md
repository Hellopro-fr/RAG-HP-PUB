# Rapport de bascule — `template-llm-service`

> **Lot L6 · basculé le 2026-09-29 à 11:23 UTC (13:23 Paris)** · exécuté par le DevSecOps · pré-contrôle vérifié par le DSO le 25/09 · **GO le 30/09** (trafic réel de nuit).
> Ce rapport dit ce qui a changé, ce qui a été prouvé, et **comment vous accédez maintenant au service** pour le déboguer.

---

## 1. Avant / après

| | Avant (VM GPU) | Après (GKE) |
|---|---|---|
| Où il tourne | `rag-hp-pub-template-llm-service-1` à `-4`, Docker Compose, VM `vm-embedding-g2-std-24-use` | Déploiement `template-llm-service`, namespace `apps-microservices`, cluster `matching-api-dev-k8s` |
| Réplicas | 4 | **1** (file restée à 0 la nuit du 29 au 30/09) |
| File consommée | `llm_templating_queue` sur le broker prod `10.0.1.216` | **La même**, via `rabbitmq-internal.rabbitmq-v3.svc.cluster.local` |
| Dépendances | services de la VM par leur nom Docker | service LLM de la VM en gRPC, `10.11.0.2:15051` (`LLM_SERVICE_URL`) ; tokenizer téléchargé depuis Hugging Face au démarrage (via Cloud NAT) |
| État des jumeaux VM | `Up` ×4 | **`Exited` ×4, conservés** — filet de rollback |
| Ce qui a changé côté code | — | **Rien** (image `shadow-2026-09-15`) |

**Ce qui a changé côté configuration** :

- secret `template-llm-service-rabbitmq`, clé `rabbitmq-url` : broker dev → **prod** (empreinte relue) ;
- aucune autre variable modifiée (`LLM_SERVICE_URL` posée en shadow).

---

## 2. Ce qui a été prouvé — et ce qui ne l'est pas encore

| Preuve | Résultat |
|---|---|
| Pré-contrôle | ✅ vérifié par le DSO le 25/09 dans le code, les conteneurs VM et Secret Manager (réponses du dev le 28/09) |
| Abonnement à la file **prod** | ✅ 29/09 11:23 UTC : `consumers=1`, jumeaux arrêtés |
| Santé | ✅ 0 redémarrage, 0 Traceback |
| Traitement de bout en bout sur données réelles | ✅ nuit du 29 au 30/09 : 13 439 lignes de traitement, 0 erreur, file à 0 le matin — **GO 30/09** |
| Rollback | ⬜ non joué (procédure identique aux lots précédents) |

---

## 3. Ce que vous devez savoir sur ce service

Il met en forme des contenus (articles, pages) via le service LLM de la VM et publie vers `processed_data_exchange`. **Fenêtre tarifaire DeepSeek** : il se **désabonne volontairement** aux heures pleines et se réabonne aux heures creuses (log « réabonnement à llm_templating_queue ») — `consumers=0` à ces heures est normal. Au démarrage, `AutoTokenizer.from_pretrained("deepseek-ai/DeepSeek-R1")` télécharge le tokenizer (cache éphémère du pod) : un redémarrage dépend de l'accès sortant à Hugging Face. Le dossier `recovery_data` créé au démarrage n'est jamais écrit.

À 1 réplica contre 4 sur la VM : suffisant sur la première nuit ; **monter à 2 au premier backlog durable** (leçon `embedding-service`).

---

## 4. Comment vous accédez au service maintenant

**Ce qui ne marche plus** : `docker logs` sur la VM GPU montre des conteneurs **arrêtés**, figés au 29/09 vers 11:19 UTC. Tout ce qui vit est sur GKE.

### Logs — depuis la VM Manager ou votre poste (`kubectl`)

```bash
kubectl -n apps-microservices logs deploy/template-llm-service --tail=200
kubectl -n apps-microservices logs deploy/template-llm-service -f
kubectl -n apps-microservices get pods -l app=template-llm-service
```



⚠️ Masquez les URLs de broker avant tout partage :
`| sed -E 's#(amqp://[^:]+):[^@]*@#\1:***@#g'`

### Logs — console GCP (Cloud Logging)

```
resource.type="k8s_container"
resource.labels.namespace_name="apps-microservices"
resource.labels.container_name="template-llm-service"
```

Lignes Python en sévérité `ERROR` (stderr) : filtrez par texte. Guide : [`../acces-logs-services-migres.md`](../acces-logs-services-migres.md).

### État, shell, file

```bash
kubectl -n apps-microservices describe pod -l app=template-llm-service | tail -30
kubectl -n apps-microservices exec -it deploy/template-llm-service -- /bin/sh
POD=$(kubectl -n rabbitmq-v3 get pods -o name | head -1)
kubectl -n rabbitmq-v3 exec "$POD" -- rabbitmqctl list_queues name messages consumers | grep -E '^llm_templating_queue'
```

### Métriques

Le service expose `/metrics` (Prometheus) sur le port **8530**, surveillé par des sondes `tcpSocket` :

```bash
kubectl -n apps-microservices port-forward deploy/template-llm-service 8530:8530   # puis http://localhost:8530/metrics
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

1. `kubectl -n apps-microservices scale deploy/template-llm-service --replicas=0`
2. `kubectl -n apps-microservices wait --for=delete pod -l app=template-llm-service --timeout=60s` (jamais deux consommateurs en même temps)
3. VM GPU : `docker start rag-hp-pub-template-llm-service-1 rag-hp-pub-template-llm-service-2 rag-hp-pub-template-llm-service-3 rag-hp-pub-template-llm-service-4`
4. vérifier `consumers=4` sur `llm_templating_queue`
5. remettre le secret depuis `template-llm-service-rabbitmq-prel6`, puis `scale --replicas=1` (retour en shadow)

**Données** : ce lot n'écrit dans aucune base. Les devs signalent, ils ne rollbackent pas.

---

## 7. Points ouverts

| # | Constat | Pour qui |
|---|---|---|
| 1 | Surveiller `llm_templating_queue` sur les prochains lots nocturnes ; monter à 2 au premier backlog durable | DSO |
| 2 | **SIGTERM ignoré** à l'arrêt des conteneurs VM (`Exited (137)`, F-HP-DEV-006) | LEAD |
| 3 | Jumeaux VM conservés pendant la fenêtre de rollback, puis retrait | DevSecOps |
| 4 | Mot de passe du broker dans les logs au démarrage (F-HP-SEC-021) | Tous |
