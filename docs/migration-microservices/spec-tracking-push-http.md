# Tracking QC / prix après migration — spécification « push HTTP » (F-HP-MIG-010)

> **Pour** : Lead Dev et le dev qui prendra le ticket. **Demandeur** : DevSecOps. **Date** : 22/09/2026.
> **Pourquoi maintenant** : depuis la bascule des 7 QC sur GKE (22/09 12h48), leurs fichiers de tracking s'écrivent dans
> un `emptyDir` **à l'intérieur du pod**. L'interface <https://api.hellopro.eu/qc_tracking-service/> ne les voit plus,
> et des interfaces métier s'appuient sur ces données. Les 5 prix (lot L3) auront le même problème. Il faut rétablir le
> flux **avant L3**, sans créer d'infrastructure de stockage partagé.

## 0. État

**22/09 13h30 Paris : code écrit sur une branche depuis `prod`** (14 `utils.py`, `qc-tracking-service/main.py`), PR à relire par le LEAD. Aucun déploiement avant le GO L2 du 23/09 9h30 ; ordre § 5.

## 1. Ce qu'on garde, ce qu'on change

| Inchangé | Changé |
|---|---|
| L'interface `qc-tracking-service` (UI, endpoints `browse`/`file`/`search`/`download`), son URL, son disque VM, l'arborescence `service/année/mois/fichier` | Le **transport** : au lieu d'écrire sur un disque partagé, chaque service **envoie la ligne** au tracking-service, qui l'écrit à la même place |
| Le format des fichiers (texte, une ligne ajoutée à la fois) | `write_log()` dans les services : écriture locale **et** envoi HTTP si configuré |
| Le comportement sur la VM (services non migrés) : rien à faire, la variable n'est pas définie | Le tracking-service reçoit un `POST /api/append` protégé par jeton |

## 2. Côté services (QC ×8, prix ×6) — `app/core/utils.py`

La fonction `write_log(filepath, message)` est **identique dans les 8 QC** (même empreinte) et présente dans les 6 prix.
C'est la seule porte d'écriture du tracking (vérifié : aucun `open(...tracking...)` ailleurs).

```python
import os, json, logging, urllib.request   # stdlib uniquement : requests/httpx ne sont pas pinnés partout
logger = logging.getLogger(__name__)

TRACKING_API_URL   = os.environ.get("TRACKING_API_URL")     # ex. http://10.x.x.x:8590 (VM GPU, IP interne)
TRACKING_API_TOKEN = os.environ.get("TRACKING_API_TOKEN")   # même valeur que côté tracking-service
TRACKING_SERVICE   = os.environ.get("TRACKING_SERVICE")     # ex. "caracterisation" (clé de l'arborescence côté tracking-service)

def write_log(filepath: str, message: str):
    """Écrit une ligne de tracking en local et, si configuré, la pousse au tracking-service."""
    try:
        ensure_directory(os.path.dirname(filepath))
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(f"{message}\n")
    except Exception as e:
        logger.error(f"Erreur lors de l'écriture du log: {e}")
    if TRACKING_API_URL and TRACKING_SERVICE:
        try:
            rel = os.path.relpath(filepath, "tracking")      # "2026/09/2026-09-22-12-48-tracking-generation-1002121.txt"
            req = urllib.request.Request(f"{TRACKING_API_URL}/api/append", method="POST",
                data=json.dumps({"service": TRACKING_SERVICE, "path": rel, "line": message}).encode(),
                headers={"Content-Type": "application/json", "X-Tracking-Token": TRACKING_API_TOKEN or ""})
            with urllib.request.urlopen(req, timeout=2):
                pass
        except Exception as e:                                # jamais bloquant pour le pipeline
            logger.warning(f"Tracking push KO ({e.__class__.__name__}), ligne conservée en local")
```

Règles : **jamais d'exception remontée** au pipeline ; timeout court ; la ligne reste écrite en local (emptyDir) quoi qu'il
arrive. Pas de file d'attente ni de retry dans cette version : si le tracking-service est indisponible quelques secondes, les
lignes de cet intervalle manquent côté UI, et c'est accepté (le pipeline métier n'en dépend pas).

## 3. Côté `qc-tracking-service` — `main.py`

```python
import os, secrets
from fastapi import Header, HTTPException
from pydantic import BaseModel

TRACKING_API_TOKEN = os.environ.get("TRACKING_API_TOKEN", "")
# service → sous-dossier de TRACKING_BASE_PATH (= les montages actuels du docker-compose)
SERVICE_DIRS = {
    "question1": "question1", "question2aN": "question2aN", "caracteristiques": "caracteristiques",
    "valeurs": "valeurs", "enrichissement": "enrichissement", "equivalence": "equivalence",
    "caracterisation": "caracterisation", "fabricant-reference": "fabricant-reference",
    "prix-extraction-produits": "prix-extraction-produits",  # + les autres prix, même logique
}

class AppendBody(BaseModel):
    service: str
    path: str      # relatif : "2026/09/xxx.txt"
    line: str

@app.post("/api/append")
def append_line(body: AppendBody, x_tracking_token: str = Header(default="")):
    if not TRACKING_API_TOKEN or not secrets.compare_digest(x_tracking_token, TRACKING_API_TOKEN):
        raise HTTPException(status_code=401)
    sub = SERVICE_DIRS.get(body.service)
    if sub is None:
        raise HTTPException(status_code=400, detail="service inconnu")
    safe_path = os.path.normpath(body.path).lstrip("/\\")
    full_path = os.path.join(TRACKING_BASE_PATH, sub, safe_path)
    base = os.path.abspath(os.path.join(TRACKING_BASE_PATH, sub))
    if not os.path.abspath(full_path).startswith(base) or ".." in safe_path:
        raise HTTPException(status_code=400, detail="chemin invalide")
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "a", encoding="utf-8") as f:
        f.write(body.line + "\n")
    return {"ok": True}
```

Le contrôle de chemin reprend celui déjà en place sur `browse`/`file`. Le jeton est comparé en temps constant.

## 4. Configuration

| Où | Variable | Valeur | Source |
|---|---|---|---|
| Tracking-service (VM, `docker-compose.yml`) | `TRACKING_API_TOKEN` | jeton fort (32+ car.) | nouveau secret SM `platform-tracking-api-token`, recopié dans le `.env` VM |
| 7 QC GKE (manifestes `22-deployment.yaml`) | `TRACKING_API_URL` | `http://<IP interne VM GPU>:8590` | valeur en clair (pas un secret) |
| | `TRACKING_API_TOKEN` | idem | `secretKeyRef` → secret K8s `platform-tracking-secrets` / `api-token` (reseedé depuis SM, **empreinte vérifiée** = règle F-HP-MIG-009) |
| | `TRACKING_SERVICE` | `caracterisation`, `enrichissement`, `equivalence`, `caracteristiques`, `question1`, `question2aN`, `valeurs` | clé du tableau § 3 |
| 5 prix GKE (avant L3) | idem | clés `prix-…` | idem |

Réseau : GKE → VM GPU `:8590` passe déjà par `allow-intra-lan` (à confirmer par une sonde `curl` depuis un pod avant la
mise en service). Le tracking-service publie `0.0.0.0:8590` sur la VM.

## 5. Ordre de mise en service (hors fenêtre de bascule)

1. **Tracking-service** : code § 3, jeton dans `.env` VM, `docker compose build qc-tracking-service && docker compose up -d qc-tracking-service` (🟠 VM, service HTTP sans consumer : coupure de quelques secondes de l'UI). Test : `curl -X POST …/api/append` avec et sans jeton → 200 / 401 ; fichier apparu dans `/mnt/data/docker/images/…/qc-caracterisation/2026/09/test.txt` ; le supprimer.
2. **Un QC pilote** (`qc-enrichissement`) : code § 2, image rebuild (Cloud Build, tag `tracking-push-<date>`), manifeste avec les 3 variables, `kubectl set image` + `rollout status` (🟡 : le pod se réabonne en quelques secondes, aucun message perdu). Preuve : un message réel → fichier visible dans l'UI.
3. Les 6 autres QC, un par un, même geste.
4. Les 5 prix avant L3, même geste sur les manifestes (avec l'`emptyDir`, F-HP-MIG-008).

Repli à chaque étape : retirer `TRACKING_API_URL` du manifeste (les services reviennent à l'écriture locale seule).

## 5bis. Cartes d'exécution (23/09, après le GO L2 de 9h30 et le merge de la PR)

Ordre et niveaux : 0 🟢 · 1 🔴 (secrets) · 2 🟠 (VM) · 3 🟢 · 4 🟡 (shadow) · 5 🟠 (prod, un QC à la fois) · 6 🟡.
Rien ne se joue pendant une fenêtre de bascule ; le tracking-service est le premier, les QC en prod les derniers.

### 0 — Prérequis (🟢)

```bash
cd /h/Works/Hellopro/account-pro/RAG-HP-PUB && git branch --show-current && git pull --ff-only origin prod   # prod, contient la PR
git log --oneline -3 -- apps-microservices/QC-tracking-service/main.py                                     # le commit "feat(tracking)" est là
gcloud --configuration=default compute instances describe vm-embedding-g2-std-24-use --zone us-east4-c --project hellopro-rag-project --format=json | grep -m1 '"networkIP"'
```

L'IP interne relevée = `<IP_VM>` dans les cartes suivantes.

### 1 — Jeton : Secret Manager → secret K8s → `.env` VM (🔴, jamais affiché)

```bash
gcloud config configurations activate default
P=hellopro-rag-project
TF=$(mktemp /tmp/trk.XXXXXX); chmod 600 "$TF"; openssl rand -hex 32 | tr -d '\r\n' > "$TF"           # 64 caractères
gcloud secrets create platform-tracking-api-token --project $P --replication-policy=automatic --data-file="$TF" \
  --labels=service=platform,usage=tracking-push 2>/dev/null || gcloud secrets versions add platform-tracking-api-token --project $P --data-file="$TF"
gcloud secrets add-iam-policy-binding platform-tracking-api-token --project $P \
  --member="serviceAccount:cloudrun-services@hellopro-rag-project.iam.gserviceaccount.com" --role=roles/secretmanager.secretAccessor >/dev/null
# secret K8s (nouveau) — clé api-token
PF=$(mktemp /tmp/trk-k8s.XXXXXX); chmod 600 "$PF"; printf '{"stringData":{"api-token":"%s"}}' "$(cat "$TF")" > "$PF"
gcloud config configurations activate kubectl-local
kubectl create secret generic platform-tracking-secrets -n apps-microservices --from-literal=api-token=placeholder
kubectl patch secret platform-tracking-secrets -n apps-microservices --type merge --patch-file "$PF"
kubectl label secret platform-tracking-secrets -n apps-microservices app.kubernetes.io/managed-by=manifest environment=prod owner=devsecops cost-center=ia-rag
# empreinte de référence (à comparer côté VM)
sha256sum < "$TF" | cut -c1-16
# .env VM : copie du fichier temporaire puis ajout de la ligne, sans jamais l'afficher
gcloud --configuration=default compute scp "$TF" vm-embedding-g2-std-24-use:/tmp/trk.token --zone us-east4-c --project hellopro-rag-project --tunnel-through-iap
rm -f "$TF" "$PF"
```

```bash
# --- VM GPU, devhp, ~/RAG-HP-PUB
grep -c '^TRACKING_API_TOKEN=' .env                                           # 0 attendu
printf 'TRACKING_API_TOKEN=%s\n' "$(tr -d '\r\n' < /tmp/trk.token)" >> .env && shred -u /tmp/trk.token
grep -E '^TRACKING_API_TOKEN=' .env | cut -d= -f2- | tr -d '\r\n' | sha256sum | cut -c1-16     # = empreinte K8s
```

### 2 — Tracking-service sur la VM : image depuis `prod`, sans toucher au checkout `features/poc` (🟠)

```bash
# --- VM GPU, devhp
[ -d ~/RAG-HP-PUB-prod ] || git clone --branch prod --depth 1 git@github.com:Hellopro-fr/RAG-HP-PUB.git ~/RAG-HP-PUB-prod
cd ~/RAG-HP-PUB-prod && git pull --ff-only && git log --oneline -1
docker build -t rag-hp-pub-qc-tracking-service:tracking-push -f apps-microservices/QC-tracking-service/Dockerfile .
docker tag rag-hp-pub-qc-tracking-service:tracking-push rag-hp-pub-qc-tracking-service:latest      # nom attendu par le compose
# variable d'env : via docker-compose.override.yml (déjà hors dépôt, F-HP-IaC-004), pas de modification du compose poc
cd ~/RAG-HP-PUB && cp docker-compose.override.yml /tmp/override.bak.$(date +%s)
python3 - <<'EOF'
import yaml,io
p='docker-compose.override.yml'; d=yaml.safe_load(io.open(p)) or {}
svc=d.setdefault('services',{}).setdefault('qc-tracking-service',{}); env=svc.setdefault('environment',[])
if isinstance(env,dict): env['TRACKING_API_TOKEN']='${TRACKING_API_TOKEN}'
elif 'TRACKING_API_TOKEN=${TRACKING_API_TOKEN}' not in env: env.append('TRACKING_API_TOKEN=${TRACKING_API_TOKEN}')
io.open(p,'w').write(yaml.safe_dump(d,sort_keys=False)); print('override MAJ')
EOF
docker compose config qc-tracking-service | grep -A3 'environment' | grep -c TRACKING_API_TOKEN     # 1
docker compose up -d --no-build --force-recreate qc-tracking-service && sleep 5 && docker ps --format '{{.Names}}\t{{.Status}}\t{{.Image}}' | grep tracking
# tests : 401 sans jeton, 200 avec, fichier créé puis supprimé
curl -s -o /dev/null -w '%{http_code}\n' -X POST http://127.0.0.1:8590/api/append -H 'Content-Type: application/json' -d '{"service":"caracterisation","path":"2026/09/zz-test.txt","line":"test"}'
curl -s -o /dev/null -w '%{http_code}\n' -X POST http://127.0.0.1:8590/api/append -H "X-Tracking-Token: $(grep -E '^TRACKING_API_TOKEN=' .env | cut -d= -f2- | tr -d '\r\n')" -H 'Content-Type: application/json' -d '{"service":"caracterisation","path":"2026/09/zz-test.txt","line":"test"}'
ls -la /mnt/data/docker/images/generation-question-caracteristiques/qc-caracterisation/2026/09/zz-test.txt && rm -f /mnt/data/docker/images/generation-question-caracteristiques/qc-caracterisation/2026/09/zz-test.txt
```

Repli : `docker compose up -d --no-build --force-recreate qc-tracking-service` après `docker tag <ancienne image> …:latest` (l'ancienne image reste dans `docker images`), et restauration de l'override depuis `/tmp/override.bak.*`.

### 3 — Réseau GKE → VM :8590 (🟢)

```bash
kubectl run trk-probe --image=curlimages/curl:8.10.1 --restart=Never -n apps-microservices -- curl -s -o /dev/null -w '%{http_code}\n' http://<IP_VM>:8590/
sleep 15; kubectl logs trk-probe -n apps-microservices; kubectl delete pod trk-probe -n apps-microservices --wait=false      # 200 attendu
```

### 4 — Images QC + prix depuis `prod`, en shadow d'abord (🟡)

```bash
# poste — build des 11 images (script du 15/09, tag daté), REPO = checkout prod propre
cd /c/Users/ANTHONNY/AppData/Local/Temp/claude/h--Works-Hellopro-account-pro/336fc722-f419-428e-a7c6-fd1a65d18dbe/scratchpad/cutover-rebuild
gcloud config configurations activate default
TAG=tracking-2026-09-23 ONLY="QC-caracterisation QC-enrichissement QC-equivalence QC-generation-caracteristiques QC-generation-question1 QC-generation-question2aN QC-generation-valeurs prix-caracterisation prix-extraction-devis prix-extraction-message prix-extraction-produits" bash gke-rebuild-j0.sh build
TAG=tracking-2026-09-23 bash gke-rebuild-j0.sh wait
# manifestes : image :tracking-2026-09-23 + 3 variables (script scratchpad/patch_tracking_env.py, IP_VM en argument), commit infra
# prix (shadow) : apply + rollout — zéro impact prod
gcloud config configurations activate kubectl-local
for d in prix-caracterisation prix-extraction-devis prix-extraction-message prix-extraction-produits; do kubectl apply -f <infra>/manifest/apps/$d/22-deployment.yaml -n apps-microservices && kubectl rollout status deploy/$d -n apps-microservices --timeout=180s; done
```

### 5 — QC en prod, un par un, hors fenêtre de bascule (🟠)

```bash
for d in qc-enrichissement qc-equivalence qc-generation-caracteristiques qc-generation-question1 qc-generation-question2an qc-generation-valeurs qc-caracterisation; do
  D=$(ls -d <infra>/manifest/apps/QC-* | grep -i "/${d/qc-/QC-}$" )   # dossier QC-… correspondant
  kubectl apply -f "$D/22-deployment.yaml" -n apps-microservices && kubectl rollout status deploy/$d -n apps-microservices --timeout=180s
  kubectl exec -n rabbitmq-v3 $(kubectl get pods -n rabbitmq-v3 -o name | head -1) -- rabbitmqctl list_queues -q name messages consumers | grep -E "^qc_.*\s" | grep -vE '_dlq|_retry'
done
```

Chaque rollout = quelques secondes sans consommateur sur la file du service (messages conservés). Preuve finale : un message réel → fichier visible dans <https://api.hellopro.eu/qc_tracking-service/> sous le dossier du service.

### 6 — Repli

Retirer `TRACKING_API_URL` du manifeste concerné et ré-appliquer : le service revient à l'écriture locale seule, sans rebuild.

## 6. Ce qui n'est pas dans cette version

- Pas de reprise des lignes écrites entre le 22/09 12h48 et la mise en service (elles sont dans les `emptyDir` des pods
  actuels : le DevSecOps peut les récupérer une fois par `kubectl cp` si un métier les réclame ; un redémarrage de pod les perd).
- Pas de tampon local en cas d'indisponibilité du tracking-service.
- Pas de migration du tracking-service lui-même vers GKE : elle exigerait un volume RWX (Filestore ~200 $/mois ou GCS
  FUSE + Workload Identity). À revoir après la série, avec le durcissement WI.

## 7. Point de sécurité à traiter en même temps (F-HP-SEC-024, à confirmer)

`qc-tracking-service` expose `POST /api/delete-files` **sans authentification** dans le code. Si la route
`api.hellopro.eu/qc_tracking-service/` n'ajoute pas d'authentification devant (nginx / Apache), n'importe qui connaissant
l'URL peut effacer des fichiers de tracking. À vérifier sur la configuration du reverse proxy ; le jeton du § 3 peut couvrir
aussi cet endpoint à peu de frais.
