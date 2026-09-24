# Rapport de bascule — `prix-extraction-devis`

> **Lot L3 · basculé le 2026-09-23 à 07:30 UTC (09:30 Paris)** · exécuté par le DevSecOps · validé techniquement le 23/09 après-midi sur tests réels ; **décision du lot jeudi 24/09 9h30** (LEAD + DSO).
> Ce rapport dit ce qui a changé, ce qui a été prouvé, et **comment vous accédez maintenant au service** pour le déboguer.

---

## 1. Avant / après

| | Avant (VM GPU) | Après (GKE) |
|---|---|---|
| Où il tourne | `rag-hp-pub-prix-extraction-devis-1`, Docker Compose, VM `vm-embedding-g2-std-24-use` | Déploiement `prix-extraction-devis`, namespace `apps-microservices`, cluster `matching-api-dev-k8s` |
| Réplicas | 1 | 1 |
| File consommée | `prix_devis_processing_queue` sur le broker prod `10.0.1.216` | **La même**, via `rabbitmq-internal.rabbitmq-v3.svc.cluster.local` (même broker) |
| Appels sortants | Gemini, `api.hellopro.fr` **et trois services gRPC de la VM** (embedding, reranking, database-recherche) | **Les mêmes** ; internet via la sortie Cloud NAT `35.233.35.8`, whitelistée chez ECRITEL |
| Fichier de suivi | Disque de la VM, relu par `qc-tracking-service` | `emptyDir` dans le pod **+ envoi HTTP** de chaque ligne à `qc-tracking-service` (VM, `10.11.0.2:8590`) |
| Image | — | `prix-extraction-devis:tracking-2026-09-23` |
| État du jumeau VM | `Up` | **`Exited`, conservé** — filet de rollback |
| Ce qui a changé côté code | — | **Uniquement le tracking** : `write_log` pousse aussi la ligne en HTTP (PR #818, `app/core/utils.py`). La logique métier n'a pas bougé |

**Ce qui a changé côté configuration** :

- secret `prix-extraction-devis-rabbitmq`, clé `rabbitmq-url` : broker dev → **prod** ; le service lit `HP_TOKEN` (empreinte `1d02693e`) et `GEMINI_API_KEY` (empreinte `36c842e3`) du secret partagé `platform-llm-hp-secrets`, identiques VM et GKE ;
- **correctif F-HP-MIG-012 du 23/09** : `EMBEDDING_SERVICE_URL=10.11.0.2:15052`, `RERANKING_SERVICE_URL=10.11.0.2:15053`, `DATABASE_SERVICE_URL=10.11.0.2:15054` (proxy TCP de la VM GPU). Sans ces variables, le code se rabat sur des noms Docker (`database-recherche-service:50054`…) qui n'existent pas sur GKE ;
- variables `TRACKING_API_URL`, `TRACKING_SERVICE`, `TRACKING_API_TOKEN` (secret `platform-tracking-secrets`) et volume `emptyDir` `/app/tracking` 512Mi (commit infra `6ee3a1f6`).

---

## 2. Ce qui a été prouvé — et ce qui ne l'est pas encore

| Preuve | Résultat |
|---|---|
| Parité des valeurs secrètes VM / GKE | ✅ empreintes SHA-256 identiques sur les clés lues (P0 et P1 du 23/09) |
| Le pod s'abonne à la file **prod** | ✅ 23/09 07:32:17 UTC : `consumers=1`, jumeau VM arrêté ; 0 erreur au démarrage |
| Traitement de bout en bout | ✅ après correctif : devis rejoué à 12:54 UTC → **41/41 succès, 43 lignes insérées** dans Milvus prod, 0 doublon. Premier essai à 12:40 en échec (gRPC introuvable), message parti en DLQ |
| Écritures Milvus du lot **une seule fois** | ✅ 101 lignes au-delà de la borne `467759069053297382`, 0 doublon, 0 lead réinséré |
| Tracking visible dans `qc-tracking-service` | ✅ 23/09, catégorie `2005786` |

---

## 3. Ce que vous devez savoir sur ce service

**Il dépend des services gRPC de la VM GPU** (modèles d'embedding, de reranking et la recherche en base). Ils restent sur la VM ; le pod les atteint par le proxy `10.11.0.2:15052-15054`. Si la VM GPU ou son proxy tombe, ce service échoue. Test depuis le pod :

```bash
kubectl -n apps-microservices exec deploy/prix-extraction-devis -- python -c \
  "import socket; [socket.create_connection(('10.11.0.2',p),timeout=3).close() for p in (15052,15053,15054)]; print('gRPC VM joignable')"
```

**Pas de fenêtre tarifaire** (Gemini).

**Il n'expose aucun port** : pas de `/health`, pas de `/metrics` (« option B »). Sa santé se lit dans ses logs et sur la file.

---

## 4. Comment vous accédez au service maintenant

**Ce qui ne marche plus** : `docker logs` sur la VM GPU montre des conteneurs **arrêtés**, figés à l'heure de la bascule. Tout ce qui vit est sur GKE.

### Logs — depuis la VM Manager ou votre poste (`kubectl`)

```bash
kubectl -n apps-microservices logs deploy/prix-extraction-devis --tail=200
kubectl -n apps-microservices logs deploy/prix-extraction-devis -f
kubectl -n apps-microservices get pods -l app=prix-extraction-devis
kubectl -n apps-microservices logs <nom-du-pod> --since=1h
```

⚠️ La ligne de connexion au broker contient le mot de passe (F-HP-SEC-021). Masquez avant tout partage :
`| sed -E 's#(amqp://[^:]+):[^@]*@#\1:***@#g'`

### Logs — console GCP (Cloud Logging)

```
resource.type="k8s_container"
resource.labels.namespace_name="apps-microservices"
resource.labels.container_name="prix-extraction-devis"
```

Ajoutez `textPayload:"<id catégorie ou message>"` pour suivre un traitement. Les lignes Python arrivent en sévérité `ERROR` (stderr) : filtrez par texte, pas par sévérité. Rétention 15 jours. Guide complet : [`../acces-logs-services-migres.md`](../acces-logs-services-migres.md).

### État, événements, shell

```bash
kubectl -n apps-microservices describe pod -l app=prix-extraction-devis | tail -30
kubectl -n apps-microservices exec -it deploy/prix-extraction-devis -- /bin/sh
```

### La file

```bash
POD=$(kubectl -n rabbitmq-v3 get pods -o name | head -1)
kubectl -n rabbitmq-v3 exec "$POD" -- rabbitmqctl list_queues name messages consumers | grep prix_devis_processing
```

`consumers=1` = nominal. `consumers=0` ou `messages` qui monte = le service ne traite plus.

### Le fichier de suivi (tracking)

Le service écrit toujours son fichier par message dans `/app/tracking` (volume `emptyDir`, perdu au redémarrage du pod) **et** pousse chaque ligne vers `qc-tracking-service`, resté sur la VM. L'UI de `qc-tracking-service` montre les fichiers comme avant (prouvé le 23/09 sur la catégorie `2005786`). Si un fichier manque, cherchez `Tracking push KO` dans les logs du pod (l'envoi ne bloque jamais le traitement, délai max 2 s).

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
| 12:40 | 1er devis réel : `database-recherche-service:50054: Domain name not found` → message en DLQ |
| 12:50 | `scale 0` (la file garde les messages), sonde du proxy depuis GKE : 15052/15053/15054 ouverts |
| 12:54 | 3 adresses gRPC posées, `scale 1`, devis rejoué : 41/41, 43 insertions |
| 13:05 | Manifestes alignés sur le cluster, `kubectl diff` sans écart (commit infra `448e0bbc`) |

---

## 6. Rollback de ce service

Retour sur la VM en ~2 minutes, **dans cet ordre** :

1. `kubectl -n apps-microservices scale deploy/prix-extraction-devis --replicas=0`
2. `kubectl -n apps-microservices wait --for=delete pod -l app=prix-extraction-devis --timeout=60s`
3. VM GPU : `docker start rag-hp-pub-prix-extraction-devis-1`
4. vérifier `consumers=1` sur `prix_devis_processing_queue`
5. repointer le secret sur le broker dev, puis `scale --replicas=1` (retour en shadow)

Un rollback du **lot** s'accompagne, si des écritures sont fausses, de la suppression dans `prix` des entités `id > 467759069053297382` (voir le rapport de `prix-milvus-processor`). Exécuté par le DevSecOps. Les devs signalent, ils ne rollbackent pas.

---

## 7. Points ouverts

| # | Constat | Pour qui |
|---|---|---|
| 1 | Le message du premier essai est resté dans `prix_devis_processing_queue_dlq` (1) : **rejouer ou purger, décision du dev** | Dev référent |
| 2 | **SIGTERM ignoré** à l'arrêt (`Exited 137`) : même défaut que L1/L2 (F-HP-DEV-006) | LEAD |
| 3 | **Back-merge de la PR #818 sur `features/poc`** : sans lui, une reconstruction depuis `poc` perd l'envoi du tracking | Dev |
| 4 | `prix-extraction-siteweb` et `prix-traitement` restent sur la VM (registre « Services qui restent sur la VM » du suivi) : ne pas les arrêter avec ce service | DevSecOps |
| 5 | Mot de passe du broker dans les logs au démarrage (F-HP-SEC-021) — masquer avant partage | Tous |
