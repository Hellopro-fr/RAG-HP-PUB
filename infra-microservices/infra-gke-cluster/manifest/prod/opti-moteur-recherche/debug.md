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

### #008 — Cloud Build sous SA dédié `cicd-opti-moteur-sa` : 5 pièges IAM en cascade (2026-05-22)

**Contexte** : premier build via le SA dédié `cicd-opti-moteur-sa` (impersonation depuis user `@hellopro.fr`), au lieu du SA admin `devops-infra-sa` utilisé jusqu'ici. Setup initial fait selon `update_image.md` §2.1 (3 rôles : `cloudbuild.builds.editor` + `artifactregistry.writer` + `storage.objectAdmin` conditionné). Build censé fonctionner — il a fallu **5 fixes successifs** pour aboutir.

**Symptôme initial** :
```
$ gcloud builds submit . --config=... --region=europe-west1 --substitutions=_TAG=$NEW_TAG
ERROR: (gcloud.builds.submit) The user is forbidden from accessing the bucket
[hellopro-rag-project_cloudbuild]. Please check your organization's policy or if
the user has the "serviceusage.services.use" permission.
```

**Diagnostic 5-étapes** :

| Étape | Symptôme observable | Cause root | Fix |
|---|---|---|---|
| 1 | `forbidden from accessing the bucket` + mention `serviceusage.services.use` | SA manque `roles/serviceusage.serviceUsageConsumer` (appel API GCP) | `gcloud projects add-iam-policy-binding ... --role=roles/serviceusage.serviceUsageConsumer` au niveau projet |
| 2 | Tentative `roles/storage.legacyBucketReader` au niveau projet → `ERROR: Role X is not supported for this resource` | C'est un rôle **bucket-level** uniquement | Grant directement au niveau bucket via `gcloud storage buckets add-iam-policy-binding gs://...` |
| 3 | Tentative création bucket → `HTTPError 409: The requested bucket name is not available` | Bucket existait déjà mais en multi-région `us` (créé par un build précédent admin). Filtre `grep` Git Bash MINGW64 ne l'avait pas remonté correctement | Vérifier via console GCP ou `gcloud storage buckets list --format=yaml` sans filtre. Décision : conserver le bucket `us` + utiliser `--gcs-source-staging-dir` |
| 4 | Après les fixes 1-3, build échoue à nouveau : `forbidden from accessing the bucket` (persistant) | `roles/storage.objectAdmin` n'inclut **PAS** `storage.buckets.get` (perm bucket-level absente). Cloud Build fait un `GET` sur le bucket avant upload | Ajouter `roles/storage.legacyBucketReader` au niveau bucket (contient `storage.buckets.get`) |
| 5 | Tarball upload OK (72 MiB), puis : `PERMISSION_DENIED: caller does not have permission to act as service account projects/.../<UNIQUE_ID>` | Cloud Build régional (`--region=europe-west1`) exécute les steps sous **Compute Engine default SA** (`<PROJECT_NUMBER>-compute@developer.gserviceaccount.com`). SA submitter doit avoir `actAs` dessus | `gcloud iam service-accounts add-iam-policy-binding ${PROJECT_NUMBER}-compute@... --role=roles/iam.serviceAccountUser` |

**Détours/fausses pistes** :
- Le filtre `gcloud projects get-iam-policy ... --filter="bindings.members:serviceAccount:..."` retourne vide en Git Bash MINGW64 (échappement du `:`). Fait croire à 5 minutes près que le SA n'a aucune binding → vérifier par `--format=yaml | grep cicd-opti-moteur-sa` à la place.
- Le message d'erreur `serviceusage.services.use` est **trompeur** : il apparaît dans plusieurs des 5 étapes alors que le rôle est déjà bien posé après l'étape 1. Le vrai problème est ailleurs (bucket perms à l'étape 4, actAs à l'étape 5).

**Fix appliqué** (récap, à appliquer dans cet ordre pour toute reproduction) :

1. **Vérifier bucket Cloud Build** (existence + région) ; créer en `europe-west1` si absent
2. **4 bindings PROJET** : `cloudbuild.builds.editor` + `artifactregistry.writer` + `storage.objectAdmin` (conditionné) + **`serviceusage.serviceUsageConsumer`**
3. **1 binding BUCKET** : `storage.legacyBucketReader` sur le bucket Cloud Build
4. **1 binding SA Compute** : `iam.serviceAccountUser` sur `<PROJECT_NUMBER>-compute@developer.gserviceaccount.com`
5. **Flag `--gcs-source-staging-dir=gs://<bucket>/source`** sur chaque `gcloud builds submit` (pour bucket existant hors région)

Résultat : build SUCCESS en **1m18s**, image `opti-moteur-front:v1.0.1-220526-prod` push en Artifact Registry.

**Leçons apprises** :
- **`roles/storage.objectAdmin` ne suffit pas pour Cloud Build** : il manque `storage.buckets.get`. Le compléter avec `storage.legacyBucketReader` au niveau **bucket** (pas projet).
- **`roles/serviceusage.serviceUsageConsumer` est obligatoire** pour tout SA qui appelle des APIs GCP (Cloud Build, Storage, etc.). Sans lui, message d'erreur trompeur lié à des permissions de stockage.
- **Cloud Build régional utilise le SA Compute par défaut** pour exécuter les steps. Le SA submitter doit avoir `iam.serviceAccountUser` sur ce SA, sinon erreur `actAs`. Piège classique des migrations vers builds régionaux post-2024.
- **Les rôles bucket-level (`legacyBucket*`) ne sont PAS grantables au niveau projet**. Erreur explicite mais trompeuse : `Role X is not supported for this resource`. Toujours utiliser `gcloud storage buckets add-iam-policy-binding` pour ces rôles.
- **Filtres `gcloud get-iam-policy --filter="bindings.members:serviceAccount:..."` cassent sous Git Bash MINGW64** (échappement du `:`). Préférer `--format=yaml | grep <SA_NAME>` pour les diagnostics rapides.
- **Le message d'erreur GCP n'indique pas toujours la vraie cause** : `forbidden from accessing the bucket` peut signifier soit perms manquantes, soit `actAs` manquant, soit bucket inexistant (GCP retourne `forbidden` au lieu de `not found` par convention sécurité).
- **Tous ces fixes documentés en détail dans `update_image.md` §11 + §2.1.A-E** pour réplication sur futurs projets / nouveaux SAs.

**Référence** : `update_image.md` §2 (setup complet) + §11 (historique leçons) + §4 Étape 1 (flag `--gcs-source-staging-dir`)

---

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

### #007 — Typesense OOMKilled pendant ingestion massive (DT010 matérialisée) (2026-05-13)

**Symptôme** : ~2h après stabilisation post-#006, l'ingestion devs reprend, atteint ~80%, puis **typesense-0 restart** (RESTARTS: 0 → 1).
- App `opti-moteur-front-wf89c` (stable 13j) restart aussi 2× durant le même évent
- App `opti-moteur-front-f2djv` passe de 8 → 9 restarts

**Diagnostic** :
```
kubectl describe pod typesense-0 :
  Last State:     Terminated
  Reason:         OOMKilled     ← kernel a tué le container
  Exit Code:      137           ← SIGKILL après OOM
  Started:        14:50:22
  Finished:       16:38:32      ← 1h48 stable avant explosion
```

**Confirmation OOM** :
- Logs `--previous` : opérations Raft log normales jusqu'au moment du kill, **pas d'erreur applicative**. Caractéristique d'un OOMKill (kernel tue brutalement, l'app n'a pas le temps de logger).
- RAM monitoring avant crash : montée progressive 9.6 Gi → ... → > 16 Gi (limit dépassée durant l'ingestion d'écriture massive).

**Effet collatéral — app `opti-moteur-front-wf89c` restart** :
```
Reason:    Error
Exit Code: 137 (SIGKILL via liveness probe fail)
Events:    Liveness probe failed: Get "http://10.0.131.88:8570/": context deadline exceeded
```
→ L'app a sa **liveness probe `/` qui timeout** (`context deadline exceeded`). Pourtant `/` est un endpoint léger (juste retour message). Cause : threads workers Uvicorn **bloqués sur des connexions HTTP Typesense down** (timeout HTTP côté embedding_client trop long ou inexistant). Quand Typesense crash, les requêtes en cours sont bloquées et l'app ne peut plus répondre à `/`.

**Root cause** : matérialisation de **DT010** (`limits.memory: 16Gi` insuffisant à pleine échelle). Estimation initiale post-#006 : 22 Gi à 3M docs. L'OOM est arrivé à ~1.5-1.8M docs en cours d'écriture intense (les writes consomment de la RAM additionnelle au-delà du dataset stocké).

**Fix appliqué** :

1. **Patch `requests` et `limits` du StatefulSet** :
   ```bash
   kubectl patch statefulset typesense -n moteur-recherche --type=json \
     -p='[
       {"op": "replace", "path": "/spec/template/spec/containers/0/resources/limits/memory", "value": "32Gi"},
       {"op": "replace", "path": "/spec/template/spec/containers/0/resources/requests/memory", "value": "12Gi"}
     ]'
   ```
   - `limits.memory: 16Gi → 32Gi` (double, marge confortable pour 3M docs cible)
   - `requests.memory: 8Gi → 12Gi` (réservation augmentée → QoS améliorée, moins de risque eviction)
2. **Recreate pod** : `kubectl delete pod typesense-0` (le pod en cours de re-boot a l'ancienne config 16Gi, doit être recréé)
3. **Sync manifest committé** : `manifests/12-typesense-statefulset.yaml` mis à jour avec les nouvelles valeurs + commentaires explicatifs.

**Vérification cluster** :
- Cluster total : 128 Gi RAM, bridé 60% utilisation (D17). Libre : ~51 Gi avant patch.
- Après patch Typesense (12 Gi reservés au lieu de 8 Gi) : ~47 Gi libres. OK.

**Leçons apprises** :
- **Mesurer RAM réelle pendant ingestion intense, pas juste après load idle**. Les writes Typesense consomment de la RAM transient (queue, batch, in-flight indexing).
- **DT ouverte = signal réel**. DT010 prédisait l'OOM, c'est arrivé. Ne pas la dépriorier.
- **Liveness probe d'une app dépendant d'un service externe doit utiliser un endpoint sans cascade** (ce qu'on a fait avec `/` vs `/health`). MAIS l'app doit aussi avoir des **timeouts HTTP courts** sur ses dépendances externes (Typesense, Milvus) pour ne pas bloquer ses workers. À ouvrir comme DT (DT011).
- **Pour les workloads stateful avec long boot** (cf. #006), un OOM = downtime de **30+ min** de réchargement. Sizing préventif > réactif.

**Référence** : commit fix `manifests/12-typesense-statefulset.yaml` (resources) + patch direct StatefulSet (2026-05-13)

---

### #006 — Typesense CrashLoopBackOff après ingestion massive — liveness probe trop agressive (2026-05-13)

**Symptôme** :
```
pod/typesense-0   0/1   CrashLoopBackOff   16+ restarts en 13d
```
Stable depuis le déploiement initial (2026-04-30) → soudainement CrashLoop le 2026-05-13. Restarts d'environ toutes les ~2 minutes.

**Diagnostic** :
1. `kubectl describe pod typesense-0` :
   - `Exit Code: 0` (pas crash kernel/OOM)
   - `Reason: Completed`
   - `Started: 14:27:42 → Finished: 14:29:41` (vie de **2 min précises**)
   - Events : `Container typesense failed liveness probe, will be restarted` + `Readiness probe failed: HTTP probe failed with statuscode: 503`

2. `kubectl logs --previous` :
   - Démarrage normal : Raft init, snapshot load, `Loading collection produits_prod`
   - Chargement progressif : 49k → 81k → 114k → **130k docs** atteints
   - Puis BRUSQUEMENT : `Stopping Typesense server...` + `SIGINT was installed with 1`
   - Shutdown propre puis `Bye.`

3. **Timeline qui matche les seuils probes** :
   - Liveness probe : `initialDelaySeconds: 30s` + `failureThreshold: 3` × `periodSeconds: 30s` = **kill à T+120s (2 min) précises**
   - Or, chargement collection prend > 2 min après ingestion progressive par les devs

**Root cause** : la liveness probe (héritée du déploiement initial à index vide) est devenue **trop agressive** une fois la collection peuplée. Le pod n'a jamais le temps d'atteindre `Ready` avant que K8s ne le tue → boucle infinie.

**Cause indirecte** : pendant ces 13 jours, les devs ont ingéré ~1,33 M produits (vs ~0 au déploiement S2). Boot time est passé de < 10s à ~24 min (snapshot load + index in-memory build).

**Fix appliqué** :

1. Ajout d'un **`startupProbe`** dans `12-typesense-statefulset.yaml` :
   ```yaml
   startupProbe:
     httpGet: { path: /health, port: 8108 }
     initialDelaySeconds: 10
     periodSeconds: 10
     timeoutSeconds: 5
     failureThreshold: 540   # 1h30 de budget de boot (initial 60 = 10 min, trop court)
   livenessProbe:
     # initialDelaySeconds retiré — startupProbe gère le bootstrap
     periodSeconds: 30
     failureThreshold: 3
   readinessProbe:
     # initialDelaySeconds retiré — idem
     periodSeconds: 10
     failureThreshold: 3
   ```

2. **Recreate du pod** (`kubectl delete pod typesense-0`) pour que le StatefulSet applique le nouveau template (Generation 2).

3. **Patch failureThreshold** initialement `60` (10 min) → `540` (1h30) après détection que le chargement dépasse 30 min sur 1,33M docs.

**Résultat post-fix** :
- Pod boot complet en **24 minutes** (chargement) + **~5 min** (Raft WAL catch-up) = **~30 min total**
- `RESTARTS: 0` (compteur stable)
- Pod passe à `Running 1/1` après catch-up Raft (< 1000 lagging entries)

**Leçons apprises** :
- **Stateful workloads avec long boot doivent utiliser `startupProbe`** (K8s ≥ 1.16). Ne **jamais** s'appuyer uniquement sur `initialDelaySeconds` de la livenessProbe — ce dernier est fixe et ne s'adapte pas à la croissance des données.
- **Le boot time scale avec la taille des données**. Une probe correcte au déploiement initial (vide) devient une bombe à retardement à mesure que les data s'accumulent.
- **Toujours sizer le `failureThreshold` du startupProbe avec ample marge** (5-10× le temps de boot estimé). Coût d'une marge trop large = négligeable. Coût d'une marge trop courte = downtime entier.
- **`Exit Code: 0` + `Reason: Completed`** = signal que K8s a délibérément arrêté le container (SIGTERM puis SIGKILL si grace period dépassée). Différent d'un crash applicatif (Exit Code 1, 137=OOM, 139=segfault).
- **`kubectl describe pod` + logs `--previous`** restent les 2 commandes les plus puissantes pour diagnostiquer un CrashLoopBackOff.

**Référence** : commit fix `manifests/12-typesense-statefulset.yaml` + patch `failureThreshold` (2026-05-13)

---

### #005 — Cloud Build échoue (build step 0) avec build context = racine super-repo (S3 — 2026-04-30)

**Symptôme** :
```
Creating temporary archive of 4270 file(s) totalling 975.3 MiB before compression.
Uploading tarball of [.] to [gs://...]
BUILD FAILURE: Build step failure: build step 0 "gcr.io/cloud-builders/docker" failed
```

**Hypothèses testées** :
1. Mauvais SA Cloud Build → écarté (build a démarré, donc auth OK)
2. Quota Artifact Registry → écarté (pas atteint)
3. **Build context = `account-pro/` au lieu de `RAG-HP-PUB/`** → **confirmé**

**Diagnostic** : le Dockerfile fait `COPY apps-microservices/opti-moteur-front/requirements.txt`. Ce chemin existe relatif à `RAG-HP-PUB/`, pas à `account-pro/` (super-repo qui contient `RAG-HP-PUB/` parmi d'autres choses). Lancer `gcloud builds submit .` depuis `account-pro/` envoie un contexte où `apps-microservices/` n'est pas à la racine → COPY échoue.

**Fix appliqué** :
1. **Modifier `cloudbuild.yaml`** : `--file=apps-microservices/opti-moteur-front/Dockerfile` (sans préfixe `RAG-HP-PUB/`)
2. **Lancer depuis `RAG-HP-PUB/`** :
   ```bash
   cd /h/Works/Hellopro/account-pro/RAG-HP-PUB
   gcloud builds submit . \
     --config=apps-microservices/opti-moteur-front/cloudbuild.yaml \
     --project=hellopro-rag-project --region=europe-west1 \
     --substitutions=_TAG=v1.0.0-prod
   ```
3. **Créer `.gcloudignore`** à la racine de `RAG-HP-PUB/` pour exclure les autres services + `.git` + node_modules → upload ~975 MiB → quelques Mo

**Leçon apprise** :
- Toujours aligner build context et chemins du Dockerfile (vérifier les `COPY` avant de lancer)
- `.gcloudignore` obligatoire dès le 1er build pour éviter d'envoyer 975 MiB de bruit (.git seul peut faire des centaines de Mo)
- Pour un mono-repo : 1 service = 1 `.gcloudignore` adapté qui n'inclut que le strict nécessaire

**Référence** : commit fix `cloudbuild.yaml` + ajout `.gcloudignore` (2026-04-30)

**Erreur en cascade découverte au 2ème run** : la 1ʳᵉ version du `.gcloudignore` utilisait le pattern `apps-microservices/*` + `!apps-microservices/opti-moteur-front/`. Mais d'après la doc gitignore : *"It is not possible to re-include a file if a parent directory of that file is excluded"*. → `apps-microservices/*` excluait le **dir** `opti-moteur-front`, et `!apps-microservices/opti-moteur-front/` ne ré-incluait que l'entrée du dir mais **pas son contenu** (dont `requirements.txt`). Résultat : le tarball uploadait le dir vide → COPY échoue.

**Pattern canonique correct** (exclure tout, ré-inclure parent + cible + contenu via `/**`, puis ré-exclure subdirs inutiles) :
```
*
!apps-microservices/
!apps-microservices/opti-moteur-front/
!apps-microservices/opti-moteur-front/**
apps-microservices/opti-moteur-front/local/
apps-microservices/opti-moteur-front/tests/
... (re-exclusions specifiques)
```

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

### DT009 — Downtime de restart Typesense = ~30 min (1,33M docs)

**Constat** : suite à l'incident #006, mesuré qu'un restart pod Typesense = **24 min de chargement collection + ~5 min de catch-up Raft WAL = ~30 min indisponibilité service recherche**. À 3M docs (objectif catalogue complet), estimation **~55 min**.

**Impact** :
- Tout incident node (eviction, autoscaling, maintenance GKE) = 30-55 min downtime recherche
- Tout deploy avec changement template StatefulSet = idem
- SLA recherche dégradé

**Mitigation actuelle** :
- Front PHP a un fallback Solr (cf. `hypothese_option.md` §II — architecture 2 couches)
- Couche 1 (Solr) gère les 40 premiers produits, Typesense est appelé en pages 2-4 en AJAX
- → utilisateurs ne sont pas bloqués, juste la pagination 2+ est dégradée pendant le restart

**Action future** (post-S7) :
- **Snapshots Typesense + restore plus rapide** : `POST /operations/snapshot` (déjà prévu en S7 backup). Restore from snapshot peut être plus rapide qu'un re-load complet from Raft logs si le snapshot est récent.
- **Cluster mode Typesense** (3+ replicas, élection leader) : élimine le downtime de restart mais nécessite Typesense Cloud Enterprise (licence payante) OU configuration manuelle complexe.
- **Augmenter RAM/CPU** : peut réduire le temps d'indexation in-memory (à mesurer).
- **Workload isolation** : déplacer Typesense sur un node pool dédié avec garanties d'isolation.

**Owner** : DevSecOps + CTO

---

### DT010 — Marge RAM 16Gi limit potentiellement courte à pleine échelle

**Constat** : pendant l'incident #006, RAM observée jusqu'à **9.6 Gi** sur 1,33M docs (catch-up en cours). Estimation à 3M docs : **~22 Gi** (linéaire vecteurs CamemBERT 1024 dims × 4 bytes + structures BM25 + métadonnées + RAM système Typesense).

**Impact si dépassement 16Gi** : OOMKilled → restart → 30-55 min downtime supplémentaire (cf. DT009).

**Mitigation actuelle** : `limits.memory: 16Gi` suffit pour 1,33M docs avec marge.

**Action future** :
- Surveiller `kubectl top pod typesense-0` après stabilisation Ready
- Si > 12Gi à 1,33M docs → augmenter `limits.memory` à 24Gi (cluster a 51Gi libres, OK)
- Si la collection est étendue à 3M docs (objectif final), passer à `limits.memory: 32Gi` préventivement
- Considérer `node pool` avec node `c2-standard-16` (64Gi/node) pour héberger Typesense isolément

**Owner** : DevSecOps (surveillance + ajustement S7 ou hors-sprint)

---

### DT011 — App `opti-moteur-front` se fait killer par sa liveness quand Typesense est down (timeout HTTP non borné)

**Constat** : pendant l'incident #007, l'app `opti-moteur-front-wf89c` (stable 13j) a fait 2 restarts en quelques minutes. Cause :
- Liveness probe `/` timeout `context deadline exceeded` (alors que `/` est un endpoint léger)
- → threads workers Uvicorn bloqués sur des connexions HTTP Typesense qui ne répondent plus (Typesense en OOMKill)
- → l'app ne peut plus servir `/` dans le délai de la liveness (5s)
- → K8s kill l'app

**Impact** : effet cascade — chaque crash Typesense (OOM, OOM noisy neighbor, eviction) provoque restart inutile des apps consommatrices. Augmente la fenêtre de downtime utilisateur.

**Cause technique** : pas de timeout HTTP strict côté client Typesense dans le code app. Le `requests.get(...)` par défaut n'a pas de timeout → si Typesense ne répond pas, le worker Uvicorn est bloqué indéfiniment.

**Mitigation actuelle** : aucune — le pattern liveness `/` léger ne suffit pas si l'app entière est en deadlock sur ses workers.

**Action future** :
- Côté code app (`apps-microservices/opti-moteur-front/app/core/typesense_client.py` + `embedding_client.py`) : ajouter `timeout=(2, 5)` (connect, read) sur tous les `requests.get/post`. Mieux : un circuit breaker (lib `tenacity` ou `pybreaker`) pour fail fast.
- Côté Deployment K8s : augmenter `livenessProbe.timeoutSeconds` de 5 → 10 (palliatif court terme, pas une solution).
- À ouvrir comme ticket pour Lead Dev métier (hors périmètre DevSecOps strict mais à orchestrer).

**Owner** : Lead Dev métier (code app) + DevSecOps (ticket de coordination)

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

### DT012 — Compute Engine default SA `806625052144-compute@...` a `roles/editor` (sur-permissivité)

**Constat** : Audit IAM du 2026-05-26 — le SA Compute par défaut a `roles/editor` au niveau projet `hellopro-rag-project`. Ce rôle est très large (création/suppression de la plupart des ressources). CIS Benchmark GCP §1.4 recommande de retirer ce rôle des SAs par défaut.

**Impact** : Si un pod compromis utilise le metadata server pour récupérer un token Compute SA (mode GCE_METADATA legacy actuel), l'attaquant a `editor` sur le projet entier. À ce jour pas d'usage actif détecté (audit logs Admin vides), mais Data Access Audit Logs sont **OFF** (cf. DT014) donc impossible de garantir 100%.

**Mitigation actuelle** : Aucune. La surface d'attaque est limitée par le fait que les pods détectés n'utilisent pas activement ce SA (ils utilisent leurs propres clés JSON ou n'appellent pas GCP). Mais ce n'est pas une mitigation contrôlée.

**Action future** : Retirer `roles/editor` du SA Compute **après** la migration WI (DT014) — une fois qu'on aura activé Data Access Audit Logs et confirmé que rien ne dépend du Compute SA. Remplacer si besoin par rôles minimaux (ex: `roles/logging.logWriter`, `roles/monitoring.metricWriter`).

**Owner** : DevSecOps (consolidation avec DT014)

---

### DT013 — `opti-moteur-data-sa` utilise une clé JSON (pattern milvus-backup)

**Constat** : Pour résoudre le ticket dev "volume `/app/app/data` partagé" (2026-05-26, ticket T2 opti-moteur-front), on a opté pour le pattern **(η) milvus-backup** : SA GCP `opti-moteur-data-sa` scopé au bucket `hellopro-rag-opti-moteur-data` + clé JSON exportée + Secret K8s + InitContainer qui télécharge `idf_nom_produit.json` au boot du pod. Choix justifié par :
- Pas de coût supplémentaire (vs node pool dédié WI estimé ~60 $/mo)
- Pas d'impact sur les workloads prod existants (vs migration WI cluster-wide risquée — audit incomplet, Data Access Audit Logs OFF)
- Pattern **déjà utilisé** dans le cluster (`milvus-backup-daily`/`milvus-backup-sa`), aucune nouvelle dette pattern

**Impact** : Si la clé JSON fuite (commit accidentel, accès Secret K8s par opérateur non autorisé), accès **strictement limité** au bucket dédié de 20 MB. Pas de blast radius cross-projet.

**Mitigation actuelle** :
- Permissions strictement scopées (`roles/storage.objectAdmin` sur 1 bucket uniquement, pas project-level)
- Clé jamais en Git (Secret K8s créé via `--from-file` puis fichier local supprimé immédiatement)
- RBAC K8s `moteur-recherche` limite l'accès au Secret

**Action future** : Migrer vers Workload Identity quand DT014 sera traité (annoter K8s SA `opti-moteur-sa` → SA GCP, supprimer le Secret JSON, supprimer la clé JSON exportée). Migration co-orchestrée avec celle de `milvus-backup-sa` (même chantier).

**Owner** : DevSecOps (à consolider dans le sprint DT014)

---

### DT014 — Chantier conjoint : rightsizing node pool + activation Workload Identity

**Constat** : 3 problèmes liés qui doivent être traités ensemble :

1. **Cluster surdimensionné CPU, sous-dimensionné RAM** : 1 node pool de 4× `c2-standard-8` (32 vCPU / 128 Gi). Usage observé : ~2 cores moyen (6% CPU), ~100 Gi RAM (78%). Les machines `c2-*` sont compute-optimized — inadaptées au profil mémoire-intensif du cluster (Milvus, Typesense, etc.).
2. **Workload Identity non activé** sur le cluster — pattern moderne K8s/GCP impossible (pas d'annotation `iam.gke.io/gcp-service-account` sur les K8s SAs).
3. **Multiplication des clés JSON** : `milvus-backup-sa` (existant) + `opti-moteur-data-sa` (créé 2026-05-26 via DT013) + futurs services nécessitant GCP. Chaque clé = anti-pattern sécurité + rotation manuelle à prévoir.

**Impact (multi-axe)** :
- **FinOps** : économie estimée 30-40% sur les nodes en passant de `c2-standard-8` (~230 $/mo/node) à des machines memory-optimized équivalentes (ex: `n2-highmem-4` 4 vCPU / 32 Gi ~155 $/mo, ou `n2d-highmem-4` AMD ~140 $/mo). Sur 4 nodes : économie ~300-360 $/mo.
- **Sécurité** : surface d'attaque clés JSON qui croît avec chaque nouveau service GCP.
- **Hygiène architecture** : pattern moderne K8s ne peut pas être adopté tant que WI n'est pas activé.

**Mitigation actuelle** : Aucune. Configuration stable, supportable à court terme.

**Action future — sprint dédié S9 (ou ultérieur)** : *"Cluster rightsizing + WI activation"*

1. Activer **Data Access Audit Logs** sur Storage / Compute pendant **14 jours minimum** avant tout chantier
2. Audit complet workloads : qui appelle GCP, comment (env var, volume Secret, metadata legacy)
3. Choix nouveau machine type — recommandation initiale : `n2-highmem-4` ou `n2d-highmem-4` (à valider via load test)
4. Création **nouveau node pool** avec `--workload-metadata=GKE_METADATA` et machine type ciblé
5. Activation cluster-level WI : `gcloud container clusters update --workload-pool=hellopro-rag-project.svc.id.goog`
6. Activation addon GCS Fuse CSI (au passage, ouvre la voie au refactor de DT013 vers volume WI natif)
7. Migration workloads progressive : `kubectl cordon` ancien node → `kubectl drain` → reschedule sur nouveau pool. Un workload à la fois, validation par check.
8. Migration des SAs clé JSON vers WI :
   - `milvus-backup-sa` → annotation WI
   - `opti-moteur-data-sa` → annotation WI (DT013)
   - Supprimer les clés JSON exportées + Secrets correspondants
9. Retirer `roles/editor` du Compute SA (DT012)
10. Suppression ancien node pool

**Économie attendue** : ~300-360 $/mo (CSV) + gain sécurité (élimination des clés JSON + bénéfice transversal pour futurs services GCP) + alignement architecture moderne K8s.

**Dépendances** : Aucune urgence opérationnelle, à planifier post-stabilisation S6/S7 (validation prod opti-moteur-recherche + backup/observabilité).

**Owner** : DevSecOps + CTO

**Référence** : ce DT englobe le débat (α) vs (β) vs (A') du ticket T2 opti-moteur-front (session 2026-05-26). La solution court-terme (η) a été retenue pour ne pas bloquer le ticket dev, mais elle s'inscrit dans la trajectoire de DT014.

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
| 2026-05-13 | DevSecOps | Incident #006 (Typesense CrashLoopBackOff) résolu via startupProbe (failureThreshold=540) |
| 2026-05-13 | DevSecOps | DT009 ajoutée (downtime restart Typesense ~30 min sur 1,33M docs) |
| 2026-05-13 | DevSecOps | DT010 ajoutée (RAM 16Gi limit à surveiller à pleine échelle 3M docs) |
| 2026-05-13 | DevSecOps | **Incident #007** (OOMKill Typesense matérialisation DT010) — fix : limits 32Gi + requests 12Gi |
| 2026-05-13 | DevSecOps | DT011 ajoutée (app `opti-moteur-front` worker deadlock quand Typesense down → liveness fail) |
| 2026-05-22 | DevSecOps | **Incident #008** (Cloud Build sous SA dédié — 5 pièges IAM en cascade) — fixes : 4 rôles projet + 1 rôle bucket + 1 rôle SA Compute + flag `--gcs-source-staging-dir`. Doc complète dans `update_image.md` §2 + §11. Image `v1.0.1-220526-prod` push OK + rollout GKE OK + smoketests OK. |
| 2026-05-26 | DevSecOps | **Tickets dev A + B reçus** : (A) bump RAM opti-moteur-front limits 1Gi → 2Gi (timeouts tâches lourdes) ; (B) "volume RWX partagé entre 2 pods" pour `idf_nom_produit.json` (~20 MB) |
| 2026-05-26 | DevSecOps + Utilisateur | **Ticket A appliqué ✅** : manifest `22-opti-moteur-deployment.yaml` patché (`requests=1Gi, limits=2Gi`), rollout zéro-downtime, 2 pods Running, vérif `kubectl get pods ... resources` OK |
| 2026-05-26 | DevSecOps + Utilisateur | **Drift Git↔cluster détecté** sur l'image (LIVE `v1.0.1-220526-prod` créé par `kubectl set image` lors d'#008, manifest Git resté à `v1.0.0-prod`). `kubectl apply` a régressé l'image. Fix : alignement manifest Git → `v1.0.1-220526-prod` + re-apply. **Leçon** : éviter `kubectl set image` (Option A `update_image.md`), toujours préférer Option B (modif YAML + apply). |
| 2026-05-26 | DevSecOps | **Audit cluster pour Ticket B (volume RWX)** : exigence "no extra cost + no prod impact". 7 vérifications préalables (node pools, audit logs, mapping pods/nodes, env GOOGLE_APPLICATION_CREDENTIALS, images, configs, cluster describe). Résultats principaux : 1 seul node pool (4× c2-standard-8 partagé entre tous workloads), Data Access Audit Logs OFF (constat dans IAM policy), 0 pod détecté avec env GOOGLE_APPLICATION_CREDENTIALS direct (les pods qui utilisent GCP le font via volume Secret monté + chemin direct, ex: milvus-backup), 0 image SDK suspecte. |
| 2026-05-26 | DevSecOps | **Re-orientation Ticket B** : option (α) WI cluster-wide écartée à court terme (audit incomplet + 1 seul node pool = trop risqué pour Milvus prod). Option node pool dédié (~60 $/mo) écartée pour FinOps. Choix final : **pattern (η) milvus-backup** = SA scoped + clé JSON + Secret K8s + InitContainer download GCS au boot. |
| 2026-05-26 | DevSecOps | **3 DT ouvertes** : DT012 (Compute SA `roles/editor` overprivileged), DT013 (clé JSON `opti-moteur-data-sa` — anti-pattern à migrer WI), DT014 (chantier conjoint long-terme `Cluster rightsizing + WI activation` — économie estimée 300-360 $/mo + élimination clés JSON + ouvre pattern moderne K8s). |
| 2026-05-26 | Utilisateur (apply) | **Ticket B / T2 implémentation (η) ✅** : bucket `gs://hellopro-rag-opti-moteur-data` (europe-west1), SA `opti-moteur-data-sa` + IAM scoped bucket-level, clé JSON générée (user, pas devops-infra-sa qui n'a pas la perm `keys.create`), Secret K8s `opti-moteur-data-sa-key` créé + labels FinOps, clé JSON locale supprimée + impersonation unset. |
| 2026-05-26 | Utilisateur (apply) | **Manifest deployment étendu** : `initContainers.fetch-idf` (image `cloud-sdk:slim`, gcloud storage cp depuis GCS, tolérant fichier absent) + `volumes` (Secret + emptyDir) + `volumeMounts` sur InitContainer ET container app (post-clarif dev : code app écrit GCS via `/admin/compute-idf`). Env vars `GOOGLE_APPLICATION_CREDENTIALS`/`GCS_IDF_BUCKET`/`GCS_IDF_OBJECT` exposées au container app. |
| 2026-05-26 | Utilisateur + DevSecOps | **Ticket B / T2 ✅ Smoketests** : InitContainer s'exécute auth OK (WARN fichier absent en GCS = normal, cron dev pas encore lancé), main container voit le mount + env vars + Python lit la clé JSON et identifie le bon SA + projet. App `/health` cascade Typesense+Milvus OK, `/` OK. **Communication dev envoyée** avec bucket/SA/env/exemple SDK Python à intégrer dans `/admin/compute-idf` et `/admin/reload-idf`. |
| 2026-05-26 | DevSecOps + Utilisateur | **Incident auth gcloud/kubectl en cours de session** : ADC user ne contenait pas le claim `email` (seulement `azp/aud` numeric ID) → user perçu comme `117897935407743956877` par K8s → Forbidden. Fix : re-run `gcloud auth application-default login` (scopes manquants). **Leçon** : pour kubectl on utilise `gcloud auth application-default print-access-token` (token user direct, pas SA via impersonation). Pour gcloud admin GCP on utilise `gcloud auth print-access-token` sous impersonation `devops-infra-sa`. Documenté dans `gcp_authentication.md` (rewrite). |
