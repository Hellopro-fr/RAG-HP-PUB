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
