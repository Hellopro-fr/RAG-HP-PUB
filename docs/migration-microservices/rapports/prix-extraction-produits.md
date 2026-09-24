# Rapport de bascule — `prix-extraction-produits`

> **Lot L3 · basculé le 2026-09-23 à 07:30 UTC (09:30 Paris)** · exécuté par le DevSecOps · validé techniquement le 23/09 après-midi sur tests réels ; **décision du lot jeudi 24/09 9h30** (LEAD + DSO).
> Ce rapport dit ce qui a changé, ce qui a été prouvé, et **comment vous accédez maintenant au service** pour le déboguer.

---

## 1. Avant / après

| | Avant (VM GPU) | Après (GKE) |
|---|---|---|
| Où il tourne | `rag-hp-pub-prix-extraction-produits-1`, Docker Compose, VM `vm-embedding-g2-std-24-use` | Déploiement `prix-extraction-produits`, namespace `apps-microservices`, cluster `matching-api-dev-k8s` |
| Réplicas | 1 | 1 |
| File consommée | `prix_produits_processing_queue` sur le broker prod `10.0.1.216` | **La même**, via `rabbitmq-internal.rabbitmq-v3.svc.cluster.local` (même broker) |
| Appels sortants | Gemini et `api.hellopro.fr` | **Les mêmes** ; internet via la sortie Cloud NAT `35.233.35.8`, whitelistée chez ECRITEL |
| Fichier de suivi | Disque de la VM, relu par `qc-tracking-service` | `emptyDir` dans le pod **+ envoi HTTP** de chaque ligne à `qc-tracking-service` (VM, `10.11.0.2:8590`) |
| Image | — | `prix-extraction-produits:tracking-2026-09-23` |
| État du jumeau VM | `Up` | **`Exited`, conservé** — filet de rollback |
| Ce qui a changé côté code | — | **Uniquement le tracking** : `write_log` pousse aussi la ligne en HTTP (PR #818, `app/core/utils.py`). La logique métier n'a pas bougé |

**Ce qui a changé côté configuration** :

- secret `prix-extraction-produits-rabbitmq`, clé `rabbitmq-url` : broker dev → **prod** ; le service lit `HP_TOKEN` (empreinte `1d02693e`) et `GEMINI_API_KEY` (empreinte `36c842e3`) du secret partagé `platform-llm-hp-secrets`, identiques VM et GKE ;
- **correctif F-HP-MIG-011 bis du 24/09** : le code force le provider LLM à `deepseek` (`app/core/prix_extractor.py:43`) ; `DEEPSEEK_API_KEY` manquait au manifeste → `CAT-2001065` en échec le 23/09 à 18:02 UTC (`Missing credentials`, message en DLQ). Clé ajoutée depuis `platform-llm-hp-secrets/deepseek-api-key` (empreinte `f1e15fed`, identique à la VM), commit infra `f73b9421` ;
- variables `TRACKING_API_URL`, `TRACKING_SERVICE`, `TRACKING_API_TOKEN` (secret `platform-tracking-secrets`) et volume `emptyDir` `/app/tracking` 512Mi (commit infra `6ee3a1f6`).

---

## 2. Ce qui a été prouvé — et ce qui ne l'est pas encore

| Preuve | Résultat |
|---|---|
| Parité des valeurs secrètes VM / GKE | ✅ empreintes SHA-256 identiques sur les clés lues (P0 et P1 du 23/09) |
| Le pod s'abonne à la file **prod** | ✅ 23/09 07:32:17 UTC : `consumers=1`, jumeau VM arrêté ; 0 erreur au démarrage |
| Traitement de bout en bout | ⬜ **Pas encore.** Le test du 23/09 n'a produit aucun message pour cette file (0 traité, 0 erreur). Se confirme sur le premier message réel |
| Écritures Milvus du lot **une seule fois** | ✅ 101 lignes au-delà de la borne `467759069053297382`, 0 doublon, 0 lead réinséré |
| Tracking visible dans `qc-tracking-service` | ✅ 23/09, catégorie `2005786` |

---

## 3. Ce que vous devez savoir sur ce service

**Il appelle DeepSeek**, pas Gemini (provider forcé dans le code), mais n'utilise pas la fenêtre tarifaire : `consumers=1` à toute heure.

**Il n'expose aucun port** : pas de `/health`, pas de `/metrics` (« option B »). Sa santé se lit dans ses logs et sur la file.

---

## 4. Comment vous accédez au service maintenant

**Ce qui ne marche plus** : `docker logs` sur la VM GPU montre des conteneurs **arrêtés**, figés à l'heure de la bascule. Tout ce qui vit est sur GKE.

### Logs — depuis la VM Manager ou votre poste (`kubectl`)

```bash
kubectl -n apps-microservices logs deploy/prix-extraction-produits --tail=200
kubectl -n apps-microservices logs deploy/prix-extraction-produits -f
kubectl -n apps-microservices get pods -l app=prix-extraction-produits
kubectl -n apps-microservices logs <nom-du-pod> --since=1h
```

⚠️ La ligne de connexion au broker contient le mot de passe (F-HP-SEC-021). Masquez avant tout partage :
`| sed -E 's#(amqp://[^:]+):[^@]*@#\1:***@#g'`

### Logs — console GCP (Cloud Logging)

```
resource.type="k8s_container"
resource.labels.namespace_name="apps-microservices"
resource.labels.container_name="prix-extraction-produits"
```

Ajoutez `textPayload:"<id catégorie ou message>"` pour suivre un traitement. Les lignes Python arrivent en sévérité `ERROR` (stderr) : filtrez par texte, pas par sévérité. Rétention 15 jours. Guide complet : [`../acces-logs-services-migres.md`](../acces-logs-services-migres.md).

### État, événements, shell

```bash
kubectl -n apps-microservices describe pod -l app=prix-extraction-produits | tail -30
kubectl -n apps-microservices exec -it deploy/prix-extraction-produits -- /bin/sh
```

### La file

```bash
POD=$(kubectl -n rabbitmq-v3 get pods -o name | head -1)
kubectl -n rabbitmq-v3 exec "$POD" -- rabbitmqctl list_queues name messages consumers | grep prix_produits_processing
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
| 13:05 | Manifestes alignés sur le cluster, `kubectl diff` sans écart (commit infra `448e0bbc`) |

---

## 6. Rollback de ce service

Retour sur la VM en ~2 minutes, **dans cet ordre** :

1. `kubectl -n apps-microservices scale deploy/prix-extraction-produits --replicas=0`
2. `kubectl -n apps-microservices wait --for=delete pod -l app=prix-extraction-produits --timeout=60s`
3. VM GPU : `docker start rag-hp-pub-prix-extraction-produits-1`
4. vérifier `consumers=1` sur `prix_produits_processing_queue`
5. repointer le secret sur le broker dev, puis `scale --replicas=1` (retour en shadow)

Un rollback du **lot** s'accompagne, si des écritures sont fausses, de la suppression dans `prix` des entités `id > 467759069053297382` (voir le rapport de `prix-milvus-processor`). Exécuté par le DevSecOps. Les devs signalent, ils ne rollbackent pas.

---

## 7. Points ouverts

| # | Constat | Pour qui |
|---|---|---|
| 0 | `CAT-2001065` en `prix_produits_processing_queue_dlq` (échec du 23/09 avant correctif) : **rejouer ou purger, décision du dev** | Dev référent |
| 1 | Premier traitement réel à confirmer : extraction publiée vers `prix_caracterisation_queue`, **une seule fois** | Dev référent |
| 2 | **SIGTERM ignoré** à l'arrêt (`Exited 137`) : même défaut que L1/L2 (F-HP-DEV-006) | LEAD |
| 3 | **Back-merge de la PR #818 sur `features/poc`** : sans lui, une reconstruction depuis `poc` perd l'envoi du tracking | Dev |
| 4 | `prix-extraction-siteweb` et `prix-traitement` restent sur la VM (registre « Services qui restent sur la VM » du suivi) : ne pas les arrêter avec ce service | DevSecOps |
| 5 | Mot de passe du broker dans les logs au démarrage (F-HP-SEC-021) — masquer avant partage | Tous |
