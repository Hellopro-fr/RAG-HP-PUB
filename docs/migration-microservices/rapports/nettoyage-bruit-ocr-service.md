# Rapport de bascule — `nettoyage-bruit-ocr-service`

> **Lot L1-b · basculé le 2026-09-19 à 10:29 UTC (13:29 locales)** · exécuté par le DevSecOps · validation fonctionnelle **en attente du premier message réel** (lundi 21/09, dev référent).
> Ce rapport dit ce qui a changé, ce qui a été prouvé, et **comment vous accédez maintenant au service** pour le déboguer.

---

## 1. Avant / après

| | Avant (VM GPU) | Après (GKE) |
|---|---|---|
| Où il tourne | `rag-hp-pub-nettoyage-bruit-ocr-service-1` à `-5`, Docker Compose, VM `vm-embedding-g2-std-24-use` | Déploiement `nettoyage-bruit-ocr-service`, namespace `apps-microservices`, cluster `matching-api-dev-k8s` |
| Réplicas | 5 | **3** au départ — un pod GKE (500m CPU) vaut plusieurs conteneurs VM I/O-bound ; ajustable sur la profondeur de la file |
| File consommée | `nettoyage_bruit_ocr_queue` sur le broker prod `10.0.1.216` | **La même**, via `rabbitmq-internal.rabbitmq-v3.svc.cluster.local` (même broker) |
| LLM | `llm-service:50051` (conteneur voisin sur la VM) | `10.11.0.2:15051` — **le même service GPU de la VM**, atteint via l'enabler gRPC. Le GPU ne bouge pas |
| Code exécuté | ⚠️ le **checkout git de la VM** (`features/poc@33d62cbc`) via un bind-mount du dossier `app/` | L'image `shadow-2026-09-15` bâtie depuis `prod@4fe9ebaf` — **code `app/` et modules partagés vérifiés identiques** avant bascule |
| État des jumeaux VM | `Up` ×5 | **`Exited` ×5, conservés** — filet de rollback |
| Ce qui a changé côté code | — | **Rien** |

**Ce qui a changé côté configuration** : le secret `nettoyage-bruit-ocr-service-rabbitmq`, clé `rabbitmq-url`, broker dev → **prod**. C'est tout. Les quatre variables que le code lit (`RABBITMQ_URL`, `LLM_SERVICE_URL`, `LOG_LEVEL`, `DEEPSEEK_FENETRES_PLEINES`) ont les mêmes valeurs ou les mêmes défauts des deux côtés.

---

## 2. Ce qui a été prouvé — et ce qui ne l'est pas encore

| Preuve | Résultat |
|---|---|
| Parité de configuration VM / GKE | ✅ 4 variables lues, identiques ou défauts identiques |
| Parité de code VM / GKE | ✅ `git diff prod@4fe9ebaf poc@33d62cbc -- app/` vide (seul le Dockerfile diffère : durcissement `apt upgrade` de l'image) |
| Le pod GKE s'abonne à la file **prod** | ✅ `consumers 0 → 1 → 3`, jumeaux VM arrêtés |
| Le pod gère la fenêtre tarifaire | ✅ log au démarrage : `heures creuses (moitié prix) : reabonnement` |
| **Traitement de bout en bout** (message réel → LLM GPU → publication) | ⬜ **Pas encore.** Trafic nul samedi. Se validera sur le premier message réel, lundi |

Pas de message de test injecté : il aurait déclenché un appel LLM de production et une publication en aval.

---

## 3. Ce que vous devez savoir sur ce service

**Il se désabonne volontairement de sa file entre 06h-10h et 01h-04h UTC** (09h-13h et 04h-07h locales) pour éviter le tarif double de DeepSeek — logique partagée (`libs/common-utils/…/fenetre_tarifaire.py`), la même sur la VM et sur GKE. Pendant ces plages, `consumers=0` et les messages **s'accumulent** : c'est nominal, pas une panne. Le réabonnement se fait tout seul dans la minute qui suit la fin de plage.

**Il n'expose aucun port** : pas de `/health`, pas de `/metrics` (« option B »). Sa santé se lit dans ses logs et sur la file.

---

## 4. Comment vous accédez au service maintenant

**Ce qui ne marche plus** : `docker logs rag-hp-pub-nettoyage-bruit-ocr-service-N` sur la VM montre des conteneurs **arrêtés**, figés au 19/09 13:27. Tout ce qui vit est sur GKE.

### Logs — depuis la VM Manager

```bash
# les 3 pods d'un coup, préfixés par leur nom
kubectl -n apps-microservices logs deploy/nettoyage-bruit-ocr-service --all-pods --prefix --tail=100
kubectl -n apps-microservices logs deploy/nettoyage-bruit-ocr-service --all-pods --prefix -f
# un pod précis
kubectl -n apps-microservices get pods -l app=nettoyage-bruit-ocr-service
kubectl -n apps-microservices logs <nom-du-pod> --since=1h
```

⚠️ La ligne de connexion au broker contient le mot de passe (F-HP-SEC-021). Masquez avant tout partage :
`| sed -E 's#(amqp://[^:]+):[^@]*@#\1:***@#g'`

### Logs — console GCP (Cloud Logging)

```
resource.type="k8s_container"
resource.labels.namespace_name="apps-microservices"
resource.labels.container_name="nettoyage-bruit-ocr-service"
```

Trois pods, donc trois flux : ajoutez `textPayload:"<id du message>"` pour suivre un traitement précis. ⚠️ Collecte GKE active **depuis le 21/09 14h21 Paris** seulement (F-HP-OBS-004) ; toutes les lignes apparaissent en sévérité `ERROR` (stderr Python) : filtrer par texte. Guide : [`../acces-logs-services-migres.md`](../acces-logs-services-migres.md).

### Shell dans un pod

```bash
kubectl -n apps-microservices exec -it deploy/nettoyage-bruit-ocr-service -- /bin/sh
```

### La file

```bash
POD=$(kubectl -n rabbitmq-v3 get pods -o name | head -1)
kubectl -n rabbitmq-v3 exec "$POD" -- rabbitmqctl list_queues name messages consumers | grep nettoyage
```

`consumers=3` hors plage tarifaire = nominal. `consumers=0` **dans** la plage = nominal. `messages` qui monte **hors** plage = le service ne traite plus.

### Tester le chemin GPU depuis le pod

```bash
kubectl -n apps-microservices exec deploy/nettoyage-bruit-ocr-service -- python -c \
  "import socket; s=socket.create_connection(('10.11.0.2',15051),timeout=3); print('gRPC GPU joignable'); s.close()"
```

---

## 5. Chronologie du 19/09 (UTC — la VM et les logs sont en UTC ; ajoutez 3 h pour l'heure locale)

| UTC | Geste |
|---|---|
| 06:17 | Mesure du trafic : 0 message, 5 conteneurs `Up`, `consumers=0` — **désabonnement volontaire** (plage 06h-10h), confirmé par les logs VM |
| 07:5x | Pré-flight : secret dérivé, hôte dev, parité env (4 variables), **parité code** prod@4fe9ebaf vs VM poc@33d62cbc |
| 10:25 | Fin de plage : `consumers=5`, la VM s'est réabonnée — porte d'entrée ouverte |
| **10:27:40** | **Arrêt des 5 jumeaux VM** (`Exited 137` ×5 — SIGTERM ignoré, F-HP-DEV-006) — `consumers=0` |
| 10:29:00 | Secret repointé sur le broker prod, `rollout restart` |
| **10:29:07** | Pod `nettoyage-bruit-ocr-service-6fb58f89fb-9c9ls` connecté, `heures creuses : reabonnement` — **`consumers=1`** |
| ~10:30 | Montée à 3 réplicas — **`consumers=3`** |

---

## 6. Rollback de ce service

Retour sur la VM en ~2 minutes, **dans cet ordre** :

1. `kubectl -n apps-microservices scale deploy/nettoyage-bruit-ocr-service --replicas=0`
2. VM GPU : `docker start rag-hp-pub-nettoyage-bruit-ocr-service-{1,2,3,4,5}`
3. vérifier `consumers=5` (hors plage tarifaire) sur `nettoyage_bruit_ocr_queue`
4. repointer le secret sur le broker dev, puis `scale --replicas=1`

Exécuté par le DevSecOps. Les devs signalent, ils ne rollbackent pas.

---

## 7. Points ouverts

| # | Constat | Pour qui |
|---|---|---|
| 1 | **Validation fonctionnelle** sur le premier message réel : OCR nettoyé, appel LLM GPU réussi, publication en aval, **une seule fois** | Dev référent, lundi 21/09 |
| 2 | **Réplicas** : 3 au départ contre 5 sur la VM. Surveiller la profondeur de `nettoyage_bruit_ocr_queue` **hors plage tarifaire** lundi ; si elle monte, passer à 4 ou 5 | DevSecOps |
| 3 | **SIGTERM ignoré** (`Exited 137` ×5) — confirmé sur un second service : la correction (F-HP-DEV-006) vaut pour toute la famille de consumers `aio_pika` | LEAD |
| 4 | **Code en bind-mount sur la VM** : tant que les jumeaux existent, un `git pull` sur la VM change le code qu'ils exécuteraient au redémarrage (rollback). Ne pas toucher au checkout VM pendant la fenêtre de rollback (7 jours) | DevSecOps |
| 5 | Mot de passe du broker dans les logs au démarrage (F-HP-SEC-021) — masquer avant partage | Tous |
