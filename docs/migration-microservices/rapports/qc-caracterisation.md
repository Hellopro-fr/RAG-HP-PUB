# Rapport de bascule — `qc-caracterisation`

> **Lot L2 · basculé le 2026-09-22 à 10:48 UTC (12:48 Paris)**, après une première tentative le 21/09 annulée par rollback · exécuté par le DevSecOps · **validé le 23/09 à 7h20 Paris** par le LEAD et le dev, sur traitements réels.
> Ce rapport dit ce qui a changé, ce qui a été prouvé, et **comment vous accédez maintenant au service** pour le déboguer.

---

## 1. Avant / après

| | Avant (VM GPU) | Après (GKE) |
|---|---|---|
| Où il tourne | `rag-hp-pub-qc-caracterisation-1` et `-2`, Docker Compose, VM `vm-embedding-g2-std-24-use` | Déploiement `qc-caracterisation`, namespace `apps-microservices`, cluster `matching-api-dev-k8s` |
| Réplicas | 2 | **1** au départ (≈ la moitié), ajustable sur la profondeur de la file |
| File(s) consommée(s) | `qc_caracterisation_queue` et `qc_caracterisation_bo_queue` sur le broker prod `10.0.1.216` | **Les mêmes**, via `rabbitmq-internal.rabbitmq-v3.svc.cluster.local` (même broker) |
| Appels sortants | DeepSeek et `api.hellopro.fr` depuis l'IP de la VM | **Les mêmes**, via la sortie Cloud NAT `35.233.35.8`, whitelistée chez ECRITEL |
| Fichier de suivi | Disque de la VM, relu par `qc-tracking-service` | `emptyDir` dans le pod **+ envoi HTTP** de chaque ligne à `qc-tracking-service` (VM, `10.11.0.2:8590`) |
| Image | — | `qc-caracterisation:tracking-2026-09-23` depuis le 23/09 06:10-06:29 UTC (avant : `shadow-2026-09-15`) |
| État des jumeaux VM | `Up` ×2 | **`Exited` ×2, conservés** — filet de rollback |
| Ce qui a changé côté code | — | **Uniquement le tracking** : `write_log` pousse aussi la ligne en HTTP (PR #818, `app/core/utils.py`). La logique métier n'a pas bougé |

**Ce qui a changé côté configuration** :

- secret `qc-caracterisation-rabbitmq`, clé `rabbitmq-url` : broker dev → **prod** (seule clé repointée à la bascule) ;
- secret partagé `platform-llm-hp-secrets` : ses placeholders d'origine remplacés le 21/09 par les vraies valeurs (cause du rollback du 21/09, F-HP-MIG-009). Le service lit `HP_TOKEN` (empreinte `1d02693e`) et `DEEPSEEK_API_KEY` (empreinte `f1e15fed`), identiques VM et GKE ;
- variables `TRACKING_API_URL`, `TRACKING_SERVICE`, `TRACKING_API_TOKEN` (secret `platform-tracking-secrets`) et volume `emptyDir` `/app/tracking` 512Mi — commits infra `90ba9e0b` et `6ee3a1f6`.

---

## 2. Ce qui a été prouvé — et ce qui ne l'est pas encore

| Preuve | Résultat |
|---|---|
| Parité des valeurs secrètes VM / GKE | ✅ 22/09 10:41 UTC : empreintes SHA-256 identiques sur les clés lues (seul `RABBITMQ_URL` diffère avant bascule, attendu) |
| Le pod s'abonne à la file **prod** | ✅ 22/09 10:48:17 UTC : 2 files, chacune à `consumers=1`, jumeaux VM arrêtés |
| `api.hellopro.fr` répond 200 depuis GKE | ✅ sonde authentifiée depuis un pod le 21/09 après correctif, puis trafic réel (voir ligne suivante) |
| Traitement de bout en bout | ✅ 22/09 12:30 UTC, test dev sur la catégorie `1002121` (celle qui échouait le 21/09) : 16 × HTTP 200 sur `api.hellopro.fr`, DeepSeek 200, « ✅ Pipeline terminé » en 4 min. Nuit du 22 au 23/09 : **223 × HTTP 200**, 0 × 400, 0 traceback, 0 redémarrage |
| Tracking visible dans `qc-tracking-service` | ✅ 23/09 12:04 UTC, test dev QC `1002121` : fichier visible dans l'UI `qc-tracking-service` |

---

## 3. Ce que vous devez savoir sur ce service

**Il se désabonne volontairement de ses files entre 01h-04h et 06h-10h UTC** (03h-06h et 08h-12h Paris) pour éviter le tarif plein de DeepSeek — logique partagée `libs/common-utils/…/fenetre_tarifaire.py`, identique sur la VM et sur GKE. Pendant ces plages, `consumers=0` et les messages **s'accumulent** : c'est nominal. Le réabonnement se fait seul dans la minute qui suit la fin de plage. Surchargeable par `DEEPSEEK_FENETRES_PLEINES`.

**Deux files** : `qc_caracterisation_queue` et `qc_caracterisation_bo_queue` (circuit back-office). Les deux sont consommées par le même pod.

**Il n'expose aucun port** : pas de `/health`, pas de `/metrics` (« option B »). Sa santé se lit dans ses logs et sur la file.

---

## 4. Comment vous accédez au service maintenant

**Ce qui ne marche plus** : `docker logs` sur la VM GPU montre des conteneurs **arrêtés**, figés à l'heure de la bascule. Tout ce qui vit est sur GKE.

### Logs — depuis la VM Manager ou votre poste (`kubectl`)

```bash
kubectl -n apps-microservices logs deploy/qc-caracterisation --tail=200
kubectl -n apps-microservices logs deploy/qc-caracterisation -f
kubectl -n apps-microservices get pods -l app=qc-caracterisation
kubectl -n apps-microservices logs <nom-du-pod> --since=1h
```

⚠️ La ligne de connexion au broker contient le mot de passe (F-HP-SEC-021). Masquez avant tout partage :
`| sed -E 's#(amqp://[^:]+):[^@]*@#\1:***@#g'`

### Logs — console GCP (Cloud Logging)

```
resource.type="k8s_container"
resource.labels.namespace_name="apps-microservices"
resource.labels.container_name="qc-caracterisation"
```

Ajoutez `textPayload:"<id catégorie ou message>"` pour suivre un traitement. Les lignes Python arrivent en sévérité `ERROR` (stderr) : filtrez par texte, pas par sévérité. Rétention 15 jours. Guide complet : [`../acces-logs-services-migres.md`](../acces-logs-services-migres.md).

### État, événements, shell

```bash
kubectl -n apps-microservices describe pod -l app=qc-caracterisation | tail -30
kubectl -n apps-microservices exec -it deploy/qc-caracterisation -- /bin/sh
```

### La file

```bash
POD=$(kubectl -n rabbitmq-v3 get pods -o name | head -1)
kubectl -n rabbitmq-v3 exec "$POD" -- rabbitmqctl list_queues name messages consumers | grep qc_caracterisation
```

`consumers=1` hors plage tarifaire = nominal ; `consumers=0` **dans** la plage = nominal ; `messages` qui monte **hors** plage = le service ne traite plus.

### Le fichier de suivi (tracking)

Le service écrit toujours son fichier par message dans `/app/tracking` (volume `emptyDir`, perdu au redémarrage du pod) **et** pousse chaque ligne vers `qc-tracking-service`, resté sur la VM. Pour vous, rien ne change : l'UI de `qc-tracking-service` montre les fichiers comme avant. Si un fichier manque dans l'UI, cherchez `Tracking push KO` dans les logs du pod (l'envoi ne bloque jamais le traitement, délai max 2 s).

---

## 5. Chronologie (UTC — Paris = UTC+2)

| Date / heure UTC | Geste |
|---|---|
| 21/09 11:37 → 11:40 | 1re bascule : jumeaux arrêtés, secret repointé, file reprise en 2 min 39 |
| 21/09 12:32 → 12:37 | 1er message réel : `HTTP 400` sur `api.hellopro.fr` (secret partagé en placeholders) |
| 21/09 12:56 → 12:58 | **Rollback** : pods à 0, jumeaux VM relancés, la VM reprend |
| 21/09 après-midi | Secret partagé reseedé depuis Secret Manager, sonde 200 depuis GKE |
| 22/09 10:41 → 10:44 | Pré-flight du rejeu, dont parité des empreintes secrètes VM = GKE |
| **22/09 10:45:05 → 10:45:36** | **Arrêt des 14 jumeaux QC** (`Exited 137`) |
| 22/09 10:47:32 → 10:48:11 | Secret `qc-caracterisation-rabbitmq` repointé sur la prod, `rollout` |
| **22/09 10:48:17** | **2 files, chacune à `consumers=1` — bascule du lot en 3 min 12** |
| 22/09 12:30 → 12:34 | Test dev sur la catégorie `1002121` : 16 × 200, pipeline terminé |
| 23/09 06:10 → 06:29 | Passage à l'image `tracking-2026-09-23` (envoi du tracking à `qc-tracking-service`) |
| 23/09 07:22 | **GO du lot** (LEAD + dev) après une nuit propre |

---

## 6. Rollback de ce service

Retour sur la VM en ~2 minutes, **dans cet ordre** :

1. `kubectl -n apps-microservices scale deploy/qc-caracterisation --replicas=0`
2. `kubectl -n apps-microservices wait --for=delete pod -l app=qc-caracterisation --timeout=60s` — sans cette attente, les deux côtés consomment en même temps quelques secondes (21/09)
3. VM GPU : `docker start rag-hp-pub-qc-caracterisation-1 rag-hp-pub-qc-caracterisation-2`
4. vérifier `consumers=2` sur chacune des deux files (hors plage tarifaire)
5. repointer le secret sur le broker dev, puis `scale --replicas=1` (retour en shadow)

Sur la VM, le tracking reprend son chemin d'origine (disque de la VM). Exécuté par le DevSecOps. Les devs signalent, ils ne rollbackent pas.

---

## 7. Points ouverts

| # | Constat | Pour qui |
|---|---|---|
| 1 | Confirmation écrite du référent sur le test `1002121` (données bien arrivées côté HelloPro, une seule fois) | Dev référent |
| 2 | **Réplicas** : 1 contre 2 sur la VM. Surveiller la profondeur de `qc_caracterisation_queue` et `qc_caracterisation_bo_queue` hors plage tarifaire ; passer à 2 si elle monte | DevSecOps |
| 3 | **SIGTERM ignoré** à l'arrêt (`Exited 137` ×14 sur le lot) : même défaut que L1 (F-HP-DEV-006), famille `aio_pika` | LEAD |
| 4 | **Back-merge de la PR #818 sur `features/poc`** : sans lui, une reconstruction depuis `poc` perd l'envoi du tracking | Dev |
| 5 | Jumeaux VM conservés pendant la fenêtre de rollback, puis retrait (`docker rm` + neutralisation dans `docker-compose.yml`) à planifier comme pour L1 | DevSecOps |
| 6 | Mot de passe du broker dans les logs au démarrage (F-HP-SEC-021) — masquer avant partage | Tous |
