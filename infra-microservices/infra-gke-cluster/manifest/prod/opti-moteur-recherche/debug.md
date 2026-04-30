# debug.md — Historique incidents + dette technique

> Journal des bugs, erreurs, analyses, fix et leçons apprises pendant la migration Typesense + opti-moteur-front sur GKE.
> Voir aussi `etat_avancement.md` pour les risques actifs (Rxx) et `runbook.md` pour les procédures.

---

## Format d'une entrée incident

```
### #NNN — [Titre court] (Sprint Sx — date)

**Symptôme** : ...
**Hypothèses testées** : ...
**Diagnostic** : ...
**Fix appliqué** : ...
**Leçon apprise** : ...
**Référence** : runbook X / commit Y
```

Format dette technique :
```
### DTNNN — [Titre court]

**Constat** : ...
**Impact** : ...
**Mitigation actuelle** : ...
**Action future** : ...
**Owner** : ...
```

---

## 1. Incidents résolus

### #001 — `kubectl Unauthorized` au démarrage de S1 (2026-04-30)

**Symptôme** :
```
$ kubectl get svc -n milvus-prod -o wide
error: You must be logged in to the server (Unauthorized)
```

**Hypothèses testées** :
- Mauvais contexte kubectl → écarté (`kubectl config current-context` retournait le bon cluster)
- Tunnel SSH tombé → écarté (la commande `curl https://127.0.0.1:8443/healthz` n'a pas été testée mais l'erreur 401 vs timeout indique que la connectivité fonctionne)
- Token ADC expiré (~1 h TTL) → **confirmé**

**Diagnostic** : Le runbook `docs/runbooks/gke_kubectl_local.md` §9.3 documente précisément ce cas — token ADC OAuth d'1 h périmé.

**Fix appliqué** :
```bash
TOKEN=$(gcloud auth application-default print-access-token) && \
kubectl config set-credentials \
  gke_hellopro-rag-project_europe-west1-b_matching-api-dev-k8s \
  --token="$TOKEN"
```

**Leçon apprise** :
- Penser à l'expiration ADC dès qu'on voit `Unauthorized` (pas `Forbidden`)
- L'alias `gke-refresh` (cf. runbook §5) à mettre dans `~/.bashrc` pour gain de temps

**Référence** : `docs/runbooks/gke_kubectl_local.md` §9.3

---

### #004 — `curl` non disponible dans l'image `typesense/typesense:27.1` (S2 — 2026-04-30)

**Symptôme** :
```
$ kubectl exec typesense-0 -n moteur-recherche -- curl -sS http://localhost:8108/health
OCI runtime exec failed: ... exec: "curl": executable file not found in $PATH
```

**Diagnostic** : l'image `typesense/typesense:27.1` est minimale et n'inclut pas `curl`. Vérifié : `wget` également absent.

**Fix appliqué** : utiliser un **pod éphémère externe** (`curlimages/curl`) pour tous les tests HTTP impliquant Typesense :
```bash
kubectl run -n moteur-recherche --rm -i --restart=Never \
  --image=curlimages/curl \
  --env="API_KEY=$TYPESENSE_API_KEY" \
  tmp-test -- \
  sh -c 'curl -sS -X POST "http://typesense:8108/collections" \
    -H "X-TYPESENSE-API-KEY: $API_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"name\":\"_smoketest\",\"fields\":[{\"name\":\"id\",\"type\":\"string\"}]}"'
```

**Leçon apprise** :
- Ne jamais supposer la présence de `curl`/`wget` dans une image applicative
- Pour les smoketests réseau intra-cluster, **toujours** passer par un pod éphémère `curlimages/curl` (alpine + curl + sh, ~10 Mo)
- L'API key passée via `--env=API_KEY=$VAL` est visible dans `kubectl describe pod` le temps du test → acceptable pour test éphémère mais ne jamais utiliser en prod (Secret mount uniquement)

**Référence** : aucun. Note : Typesense tourne en **root** dans son container (vérifié via fichier créé dans /data). À durcir post-S2 si possible (DT à ouvrir).

---

### #003 — `kubectl get pods,pvc -w` ne fonctionne pas (2026-04-30)

**Symptôme** :
```
$ kubectl get pods,pvc -n moteur-recherche -w
error: you may only specify a single resource type
```

**Diagnostic** : `kubectl` ne supporte le flag `-w` (watch) que pour **un seul type de ressource** à la fois. Limitation connue / by design.

**Fix appliqué** : utiliser **deux commandes** :
```bash
# Watch sur les pods (Ctrl+C une fois prêt)
kubectl get pods -n <ns> -w

# Vérif ponctuelle PVC (pas besoin de watch, le bind est rapide)
kubectl get pvc -n <ns>
```
Ou alternative pour suivre tout en parallèle : 2 terminaux distincts.

**Leçon apprise** : ne pas mélanger des types dans un `-w`. Pour le suivi multi-types, préférer un `kubectl get all,pvc -n <ns>` répété (sans `-w`) ou outil tiers (`k9s`).

**Référence** : aucun (limitation upstream)

---

### #002 — `jq: command not found` en post-vérification (2026-04-30)

**Symptôme** :
```
$ kubectl get ns moteur-recherche -o jsonpath='{.metadata.labels}' | jq .
bash: jq: command not found
```

**Diagnostic** : Git Bash sous Windows MINGW64 n'a pas `jq` installé par défaut.

**Fix appliqué** : remplacement des post-vérifs futures par `kubectl describe` ou `-o yaml` directement (pas de pipe externe).

**Leçon apprise** :
- Ne pas dépendre d'outils externes (`jq`, `yq`) dans les commandes proposées par défaut
- `kubectl describe <resource>` est lisible et suffisant 90 % du temps
- Pour les cas où JSON parsing est vraiment requis, `python -c "import json,sys; ..."` est une alternative cross-OS

**Référence** : aucun, ajustement convention équipe

---

## 2. Dette technique tracée (à traiter hors S0-S8)

### DT001 — Cluster GKE nommé `matching-api-dev-k8s` héberge la prod

**Constat** : Le cluster qui héberge Milvus prod, Qdrant, RabbitMQ et désormais `moteur-recherche` s'appelle `matching-api-dev-k8s`. Le suffixe `-dev` est trompeur.

**Impact** : Risque de confusion ops, scripts conditionnels mal écrits (`if env=dev`), erreurs de manipulation en se croyant en environnement non-prod.

**Mitigation actuelle** : Documenté dans `plan.md` §1, `runbook.md` §3 et ce fichier. Tous les manifests prod portent le label `environment=prod`.

**Action future** : Renommer en `matching-api-prod-k8s` (= recréation cluster, sprint majeur séparé).

**Owner** : DevSecOps + CTO

---

### DT002 — NetworkPolicy enforcement non actif (= R8)

**Constat** : Le cluster n'a ni le NetworkPolicy addon legacy (Calico), ni Dataplane V2 (Cilium). Vérification :
```bash
gcloud container clusters describe matching-api-dev-k8s \
  --zone europe-west1-b \
  --project hellopro-rag-project \
  --format="value(networkPolicy.enabled,networkConfig.datapathProvider)"
# → sortie vide
```

**Impact** : Les 5 NetworkPolicies appliquées dans `moteur-recherche` (S1) sont **stockées dans etcd mais non appliquées par le datapath**. Faux sentiment de sécurité L3/L4.

**Mitigation actuelle** :
- L'isolation réelle vient de l'architecture : Service `Internal LoadBalancer` (D18), API Gateway VM GPU = unique consommateur
- Les NetPol sont du code déclaratif valuable : prêtes à enforcer dès activation

**Action future** : Activer `NetworkPolicy` addon (option B = update cluster, redémarre les CNI nodes, à valider sur tous les workloads existants) OU recréer un cluster Dataplane V2 (option C, sprint majeur).

**Owner** : DevSecOps

---

### DT003 — VM GPU embedding en `us-east4` ↔ GKE en `europe-west1` (= R7)

**Constat** : VM `vm-embedding-g2-std-24-use` (IP `10.11.0.2`) hébergée en `us-east4-c` au lieu de `europe-west1-b`. Cause root : indisponibilité du quota GPU L4 sur `europe-west1` au moment du provisionnement.

**Impact** :
- Latence inter-régions ~90-100 ms RTT minimum à chaque appel embedding
- API Gateway HelloPro hébergée sur la même VM us-east4 → +100 ms RTT supplémentaires entre l'API Gateway et notre service GKE
- Coûts egress inter-régions ~0,01 $/Go
- Le SLO `< 200 ms P95` du moteur de recherche est **à la limite voire non atteignable** dans cette config

**Mitigation actuelle** :
- Migration GKE en l'état (cf. décision utilisateur : option (c) migration parallèle)
- Mesure de la latence réelle prévue en S6
- S8 dédié au rapatriement VM en `europe-west1`

**Action future** :
1. Ouvrir une demande de quota GPU L4 sur `europe-west1` auprès de GCP (formulaire console)
2. Une fois quota obtenu : snapshot disque VM us-east4 → recréation VM en `europe-west1` → switch DNS / IP côté API Gateway

**Owner** : DevSecOps + CTO (validation quota)

---

### DT004 — `EMBEDDING_SERVICE_URL` lue via `os.getenv()` au lieu de Pydantic `BaseSettings`

**Constat** : Dans `apps-microservices/opti-moteur-front/app/services/embedding_client.py:18`, la variable d'environnement `EMBEDDING_SERVICE_URL` est récupérée via `os.getenv()` direct, alors que toutes les autres settings du service passent par `app/core/credentials.py` (Pydantic `BaseSettings`). Inconsistant avec la règle `.claude/rules/security.md` du repo.

**Impact** :
- Inconsistance code, plus difficile à tester (pas de mock injection facile)
- Pas de validation de la valeur (URL malformée passe silencieusement)
- Hors-périmètre des warnings démarrage (pas de log "missing config")

**Mitigation actuelle** : aucune — fonctionne en l'état.

**Action future** : Ajouter dans `Settings` de `credentials.py` :
```python
EMBEDDING_SERVICE_URL: str = "http://rag-hp-pub-api-embedding-service-1:8555"
EMBEDDING_TIMEOUT: int = 10
```
Puis refactor `embedding_client.py` pour utiliser `from app.core.credentials import settings`.

**Owner** : Lead Dev métier (ticket à créer hors périmètre DevSecOps)

---

### DT005 — API key Typesense POC `hp_poc_2026` codée en dur dans `docker-compose.yaml`

**Constat** : Dans `apps-microservices/opti-moteur-front/docker-compose.yaml:26`, default API key = `hp_poc_2026`. Idem dans `app/core/credentials.py:20` (`TYPESENSE_API_KEY: str = "hp_poc_2026"`).

**Impact** : Risque de fuite de la clé (déjà committée). Si jamais quelqu'un déploie le compose tel quel en prod, accès Typesense compromis.

**Mitigation actuelle** : la prod GKE utilisera un Secret K8s avec une **nouvelle clé forte générée** (D19). L'ancienne clé `hp_poc_2026` reste valable uniquement sur le POC VM GPU et n'a aucune valeur en prod.

**Action future** :
- Au S2 : générer la nouvelle clé Typesense prod (256 bits min, base64), la stocker en Secret K8s
- Hors périmètre : supprimer le default `"hp_poc_2026"` de `credentials.py` (forcer ENV var)
- Hors périmètre : audit secrets-scanner sur le commit qui a posé cette valeur

**Owner** : DevSecOps (S2) + Lead Dev (refactor default)

---

### DT008 — Typesense tourne en `root` dans le container

**Constat** : vérifié via test fichier dans /data au S2 — `-rw-r--r-- 1 root 2000`. L'image officielle `typesense/typesense:27.1` exécute `typesense-server` en `root` par défaut, sans `USER` directive.

**Impact** : si exploit RCE dans Typesense, attaquant a un shell root dans le container. fsGroup=2000 limite l'impact côté volume mais pas côté process.

**Mitigation actuelle** : container isolé (NetworkPolicies + ClusterIP), pas d'accès host (`hostNetwork: false` par défaut), securityContext `fsGroup: 2000`. Surface réelle = limitée à l'API Typesense + corruption potentielle des données.

**Action future** (post-S6) :
- Ajouter `securityContext.runAsNonRoot: true` + `runAsUser: <UID>` au pod (UID à déterminer en testant l'image)
- Ou builder un Dockerfile interne `typesense:27.1-nonroot` qui pose un USER
- Tester soigneusement : Typesense doit pouvoir écrire dans /data

**Owner** : DevSecOps

---

### DT007 — StorageClass `premium-rwo` en `reclaimPolicy: Delete`

**Constat** : aucune StorageClass disponible sur le cluster n'a `reclaimPolicy: Retain`. Tout `kubectl delete pvc` détruit le disque physique sous-jacent (risque perte de données).

**Impact** : si un opérateur supprime accidentellement le PVC `typesense-data-typesense-0`, l'index Typesense est définitivement perdu (sauf backup GCS).

**Mitigation actuelle** :
- Backup CronJob → GCS hebdo (S7)
- Procédure interne : interdiction de `kubectl delete pvc` manuel (warning à afficher dans runbook)
- StatefulSet protège déjà le PVC d'une suppression auto via `kubectl delete pod`

**Action future** : créer une SC dédiée `premium-rwo-retain` (clone de `premium-rwo` avec `reclaimPolicy: Retain`). Permettrait de migrer le PVC sans risque. Effort = 5 min de manifest + 1 redéploiement StatefulSet.

**Owner** : DevSecOps (post-S7)

---

### DT006 — `--enable-cors` activé sur Typesense en POC

**Constat** : Dans `apps-microservices/opti-moteur-front/docker-compose.yaml:27`, command Typesense contient `--enable-cors`. En prod, ce flag est dangereux : Typesense est joignable directement par un navigateur si une URL fuite.

**Impact** : Surface d'attaque côté navigateur si Typesense exposé.

**Mitigation actuelle** : architecture cible (D18) garde Typesense en `ClusterIP` interne (jamais exposé hors cluster), donc impact réel = 0.

**Action future** : ne PAS reproduire `--enable-cors` dans le manifest prod K8s (S2). CORS sera géré uniquement par `opti-moteur-front` via FastAPI middleware.

**Owner** : DevSecOps (S2)

---

## 3. Conventions / outillage poste DevSecOps

### Outils manquants identifiés (Git Bash Windows)
- `jq` — utiliser `kubectl describe` ou `-o yaml` à la place
- *(à compléter au fil des sprints)*

### Aliases recommandés (à ajouter dans `~/.bashrc`)

```bash
# Refresh token ADC + ré-injection kubeconfig (cf. runbook gke_kubectl_local.md §5)
alias gke-refresh='TOKEN=$(gcloud auth application-default print-access-token) && \
  kubectl config set-credentials gke_hellopro-rag-project_europe-west1-b_matching-api-dev-k8s --token="$TOKEN" && \
  echo "Token refreshed at $(date) — expires in ~1h"'

# Raccourcis namespace courant
alias kmr='kubectl -n moteur-recherche'
alias kmp='kubectl -n milvus-prod'
```

---

## 4. Index croisé des risques actifs (cf. `etat_avancement.md` §6)

| Risque | Lié à |
|---|---|
| R1 cluster `-dev` pour prod | DT001 |
| R2 SPOF embedding VM GPU | (architecturel, sera traité S8) |
| R3 push direct prod depuis branche feature | (à traiter S5 via GitHub Environment) |
| R4 re-ingestion 2,24 M produits longue | (hors périmètre — D16) |
| R5 API key POC ne doit pas fuiter | DT005 |
| R6 `--enable-cors` Typesense en POC | DT006 |
| R7 VM GPU us-east4 ↔ GKE europe-west1 | DT003 |
| R8 NetworkPolicy non enforced | DT002 |

---

## 5. Mises à jour

| Date | Auteur | Modification |
|---|---|---|
| 2026-04-28 | DevSecOps | Création initiale (R1-R6, DT001 + DT004 + DT005 + DT006) |
| 2026-04-30 | DevSecOps | #001 incident kubectl Unauthorized résolu |
| 2026-04-30 | DevSecOps | #002 incident jq missing résolu |
| 2026-04-30 | DevSecOps | DT002 ajoutée (NetPol non enforced — R8) |
| 2026-04-30 | DevSecOps | DT003 ajoutée (VM GPU us-east4 — R7) |
