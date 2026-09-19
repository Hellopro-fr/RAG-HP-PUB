# Rapport de bascule — `<nom-du-service>`

> **Lot L<n> · basculé le <aaaa-mm-jj> à <hh:mm> UTC (<hh:mm> locales)** · exécuté par le DevSecOps · validation fonctionnelle **<faite le … par … / en attente de …>**.
> Ce rapport dit ce qui a changé, ce qui a été prouvé, et **comment vous accédez maintenant au service** pour le déboguer.

> Un rapport par service migré, rédigé à la clôture de sa bascule, avant le lot suivant. Modèle : [`deepseek-metrics-collector-service.md`](deepseek-metrics-collector-service.md).

---

## 1. Avant / après

| | Avant (VM GPU) | Après (Cloud Run / GKE) |
|---|---|---|
| Où il tourne | `rag-hp-pub-<service>-<n>`, Docker Compose, VM `vm-embedding-g2-std-24-use` | Déploiement `<nom-exact>`, namespace `apps-microservices` — **ou** service Cloud Run `<nom-exact>` |
| Réplicas | <n> | <n> |
| File(s) consommée(s) / endpoint | `<queue>` sur le broker prod `10.0.1.216` — ou `http://<conteneur>:<port>` | `<queue>` via `rabbitmq-internal.rabbitmq-v3.svc.cluster.local` — ou `https://<svc>-xqksdwdiga-ew.a.run.app` |
| Données (Milvus, Neo4j, Redis, ES, MySQL) | <instances utilisées> | <instances prod câblées> |
| État du jumeau VM | `Up` | **`Exited`, conservé** (filet de rollback) — ou `Up` si le jumeau sert encore une entrée publique (L7) |
| Ce qui a changé côté code | — | **Rien** — ou <fichier:ligne> si un correctif était nécessaire |

**Ce qui a changé côté configuration** : <secrets repointés (clé par clé), variables modifiées, cibles corrigées — avec le commit infra>.

---

## 2. Ce qui a été prouvé — et ce qui ne l'est pas encore

| Preuve | Résultat |
|---|---|
| Joignabilité des cibles depuis le cloud | ✅ / ⬜ <comment> |
| Abonnement à la file prod (ou réponse de l'endpoint) | ✅ / ⬜ <consumers=…, jumeau VM arrêté> |
| Rollback | ✅ joué / ⬜ non joué — <durée> |
| Écritures : présentes **une seule fois** | ✅ / ⬜ <message contrôlé, cible vérifiée> |
| Traitement de bout en bout sur données réelles | ✅ / ⬜ <par qui, quand> |

---

## 3. Comment vous accédez au service maintenant

**Ce qui ne marche plus** : `docker logs` sur la VM GPU montre un conteneur arrêté. Tout ce qui vit est sur le cloud.

### Logs — depuis la VM Manager

```bash
kubectl -n apps-microservices logs deploy/<nom-exact> --tail=200
kubectl -n apps-microservices logs deploy/<nom-exact> -f
# Cloud Run :
gcloud run services logs read <nom-exact> --region europe-west1 --project hellopro-rag-project --limit 200
```

⚠️ Masquer les URLs de broker avant tout partage : `| sed -E 's#(amqp://[^:]+):[^@]*@#\1:***@#g'`.

### Logs — console GCP

Cloud Logging → Explorateur de journaux :

```
resource.type="k8s_container"
resource.labels.namespace_name="apps-microservices"
resource.labels.container_name="<nom-exact>"
```

(Cloud Run : `resource.type="cloud_run_revision"` et `resource.labels.service_name="<nom-exact>"`.)

### État, événements, shell

```bash
kubectl -n apps-microservices get pods -l app=<nom-exact>
kubectl -n apps-microservices describe pod -l app=<nom-exact> | tail -30
kubectl -n apps-microservices exec -it deploy/<nom-exact> -- /bin/sh
```

### La file RabbitMQ (consumers)

```bash
POD=$(kubectl -n rabbitmq-v3 get pods -o name | head -1)
kubectl -n rabbitmq-v3 exec "$POD" -- rabbitmqctl list_queues name messages consumers | grep <motif>
```

⚠️ Si le service appelle DeepSeek, il **se désabonne volontairement** entre 06h-10h et 01h-04h UTC (09h-13h et 04h-07h locales) : `consumers=0` à ces heures est normal.

### Métriques

<`/metrics` sur le port … — ou « aucun, consumer pur (option B) »>

---

## 4. Chronologie (heure locale, UTC+3)

| Heure | Geste |
|---|---|
| | Mesure du trafic |
| | Arrêt du jumeau VM |
| | Secrets / variables repointés, rollout |
| | Preuve broker / endpoint |
| | Montée en réplicas |
| | Validation fonctionnelle |

---

## 5. Rollback de ce service

1. `kubectl -n apps-microservices scale deploy/<nom-exact> --replicas=0`
2. VM GPU : `docker start <conteneur(s)>`
3. vérifier `consumers ≥ 1` (ou l'endpoint VM)
4. repointer les secrets sur la dev, `scale --replicas=<n>`

Exécuté par le DevSecOps. Les devs signalent, ils ne rollbackent pas.

---

## 6. Points ouverts

| # | Constat | Pour qui |
|---|---|---|
| | | |
