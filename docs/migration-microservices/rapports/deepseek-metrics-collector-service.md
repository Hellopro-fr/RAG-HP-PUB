# Rapport de bascule — `deepseek-metrics-collector-service`

> **Lot L1-a · basculé le 2026-09-19 à 06:52 UTC (09:52 locales)** · exécuté par le DevSecOps · validation fonctionnelle **en attente du premier message réel** (lundi 21/09, dev référent).
> Ce rapport dit ce qui a changé, ce qui a été prouvé, et **comment vous accédez maintenant au service** pour le déboguer.

---

## 1. Avant / après

| | Avant (VM GPU) | Après (GKE) |
|---|---|---|
| Où il tourne | `rag-hp-pub-deepseek-metrics-collector-service-1`, Docker Compose, VM `vm-embedding-g2-std-24-use` | Déploiement `deepseek-metrics-collector-service`, namespace `apps-microservices`, cluster `matching-api-dev-k8s` |
| Réplicas | 1 | 1 |
| File consommée | `deepseek_metrics_queue` sur le broker prod `10.0.1.216` | **La même**, via le DNS in-cluster `rabbitmq-internal.rabbitmq-v3.svc.cluster.local` (c'est le même broker) |
| Cible de transfert | `https://www.hellopro.fr/partenaires_externes/graphrag/deepseek_metrics_collector.php` | **Identique** — via la sortie Cloud NAT `35.233.35.8`, whitelistée chez ECRITEL |
| État du jumeau VM | `Up` | **`Exited`, conservé** — c'est le filet de rollback, il n'est pas supprimé |
| Ce qui a changé côté code | — | **Rien.** Aucune ligne modifiée |

**Ce qui a changé côté configuration** (infrastructure, pas code) :

- le secret Kubernetes `deepseek-metrics-collector-service-rabbitmq`, clé `rabbitmq-url` : broker dev → broker **prod** ;
- la variable `DEEPSEEK_METRICS_COLLECTOR_URL` du déploiement : un placeholder shadow → la vraie URL du collecteur (manifeste corrigé dans le dépôt infra, commit `7a2e2514`).

---

## 2. Ce qui a été prouvé — et ce qui ne l'est pas encore

| Preuve | Résultat |
|---|---|
| Le pod GKE atteint le collecteur PHP derrière Imperva | ✅ `HEAD` → `405` Apache en 0,17 s depuis le cluster |
| Le pod GKE s'abonne à la file **prod** | ✅ `deepseek_metrics_queue  consumers=1` avec le jumeau VM arrêté — le seul candidat |
| Le rollback fonctionne | ✅ joué pour de vrai : **62 s** pour que la VM reprenne la file, 2 min pour tout remettre en shadow |
| La bascule est rejouable | ✅ rebasculé une seconde fois : **1 min 50 s** de l'arrêt VM à la preuve broker |
| **Le traitement de bout en bout sur un message réel** | ⬜ **Pas encore.** Trafic nul samedi (0 message, 0 en cours). Se validera sur le **premier message réel**, avec un dev, lundi matin |

Nous n'avons **pas** injecté de message de test : il aurait fini en écriture dans le collecteur de production.

---

## 3. Comment vous accédez au service maintenant

**Ce qui ne marche plus** : `docker logs rag-hp-pub-deepseek-metrics-collector-service-1` sur la VM GPU montre un conteneur **arrêté**. Ses logs sont figés au 19/09 09:51. Tout ce qui vit est sur GKE.

### Logs — depuis la VM Manager (ou un poste avec `kubectl` configuré)

```bash
# dernières lignes, puis suivi en direct
kubectl -n apps-microservices logs deploy/deepseek-metrics-collector-service --tail=200
kubectl -n apps-microservices logs deploy/deepseek-metrics-collector-service -f

# les 15 dernières minutes
kubectl -n apps-microservices logs deploy/deepseek-metrics-collector-service --since=15m
```

⚠️ **La ligne de connexion au broker contient le mot de passe en clair** (défaut applicatif connu, F-HP-SEC-021, correction prévue post-migration). Si vous copiez des logs dans un ticket ou un chat, masquez-le :

```bash
kubectl -n apps-microservices logs deploy/deepseek-metrics-collector-service --since=15m \
  | sed -E 's#(amqp://[^:]+):[^@]*@#\1:***@#g'
```

### Logs — depuis la console GCP (sans terminal)

Cloud Logging → Explorateur de journaux, requête :

```
resource.type="k8s_container"
resource.labels.namespace_name="apps-microservices"
resource.labels.container_name="deepseek-metrics-collector-service"
```

Historique conservé 30 jours, recherche plein texte, alertes possibles.

### État du pod

```bash
kubectl -n apps-microservices get pods -l app=deepseek-metrics-collector-service
kubectl -n apps-microservices describe pod -l app=deepseek-metrics-collector-service | tail -30   # événements, redémarrages
```

Un `RESTARTS` qui monte = le service plante et Kubernetes le relance (`restartPolicy=Always`). C'est l'équivalent d'un conteneur Docker en boucle de redémarrage.

### Ouvrir un shell dans le pod

```bash
kubectl -n apps-microservices exec -it deploy/deepseek-metrics-collector-service -- /bin/sh
```

Même image que sur la VM, mêmes chemins. Le shell est éphémère : rien de ce que vous y faites ne survit au redémarrage du pod — et c'est voulu.

### La file RabbitMQ

Le broker prod est **le même qu'avant** (`10.0.1.216`). L'interface de management n'est pas exposée en IP : passer par un port-forward depuis la VM Manager, puis un tunnel SSH vers votre poste.

```bash
# sur la VM Manager
kubectl -n rabbitmq-v3 port-forward svc/rabbitmq-ui 15672:15672
# puis http://localhost:15672 via votre tunnel SSH
```

Ou en ligne de commande, sans interface :

```bash
POD=$(kubectl -n rabbitmq-v3 get pods -o name | head -1)
kubectl -n rabbitmq-v3 exec "$POD" -- rabbitmqctl list_queues name messages consumers | grep deepseek
```

`consumers=1` sur `deepseek_metrics_queue` = le service est abonné. `messages` qui monte sans redescendre = il ne traite plus.

### Métriques

Ce service n'expose **pas** d'endpoint `/metrics` (consumer pur, « option B » : aucun port en écoute). La seule télémétrie est la file RabbitMQ et les logs.

---

## 4. Chronologie du 19/09 (heure locale, UTC+3)

| Heure | Geste |
|---|---|
| 09:17 | Mesure du trafic : 0 message, 0 en cours, CPU ≈ 0, aucun log depuis 15 min |
| 09:38 | Correction du manifeste (URL du collecteur), `kubectl apply`, pod shadow redéployé |
| **09:41:13** | **Arrêt du jumeau VM** (`docker stop`) — file à 0 consommateur |
| 09:43:44 | Secret repointé sur le broker prod, `rollout restart` |
| **09:44:16** | **`consumers=1` — GKE consomme la production** |
| 09:47:22 → 09:48:09 | **Rollback réel** : GKE à 0, VM redémarrée, VM réabonnée en **62 s** |
| 09:49:25 | GKE remis en shadow (secret dev), file toujours servie par la VM |
| 09:51:30 → 09:53:20 | **Rebascule** : arrêt VM → secret prod → rollout → `consumers=1` en **1 min 50** |
| 09:52:50 | Pod final `deepseek-metrics-collector-service-8967b8bb8-zxgr5` connecté |

---

## 5. Rollback de ce service

Si le service se comporte mal sur GKE, retour sur la VM en ~2 minutes, **dans cet ordre** :

1. `kubectl -n apps-microservices scale deploy/deepseek-metrics-collector-service --replicas=0` — libérer la file
2. sur la VM GPU : `docker start rag-hp-pub-deepseek-metrics-collector-service-1` — la VM se réabonne (7 s)
3. vérifier `consumers=1` sur `deepseek_metrics_queue`
4. repointer le secret sur le broker dev, puis `scale --replicas=1` — GKE redevient shadow

C'est le DevSecOps qui l'exécute. Les devs **signalent**, ils ne rollbackent pas.

---

## 6. Points ouverts

| # | Constat | Pour qui |
|---|---|---|
| 1 | **Validation fonctionnelle** à faire sur le premier message réel : le collecteur PHP reçoit-il bien les métriques, une seule fois ? | Dev référent, lundi 21/09 matin |
| 2 | **Le service ignore SIGTERM** : `docker stop` finit en `Exited (137)` (SIGKILL) même avec 30 s de grâce. Sans conséquence sur une file vide ; sur un service chargé, un message peut rester non acquitté et être requeué. À corriger côté code (`aio_pika` : fermer la connexion sur le signal) | LEAD |
| 3 | Un conteneur orphelin `df2145682135_rag-hp-pub-deepseek-metrics-collector-service-1` en état `Created` traîne sur la VM (ancienne recréation Compose). Inoffensif, à nettoyer hors fenêtre | DevSecOps |
| 4 | Le mot de passe du broker apparaît dans les logs au démarrage (F-HP-SEC-021) — masquer avant tout partage | Tous, en attendant le correctif |

## Validation — 22/09/2026 9h30

✅ **Lot L1 validé** : traitements réels confirmés par le dev le 21/09 (`deepseek-metrics-collector-service` : lignes `[SUCCESS]` / files consommées), 0 `Traceback`, 0 redémarrage sur la nuit du 21 au 22. Jumeaux VM `Exited` conservés jusqu'au **26/09**, puis retrait (`docker rm` + neutralisation dans `docker-compose.yml`).
