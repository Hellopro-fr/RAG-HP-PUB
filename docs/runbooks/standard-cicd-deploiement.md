# Standard CI/CD de déploiement — Cloud Run et GKE

> **Pour qui** : les devs qui ajoutent ou modifient un service, et les assistants (Claude Code ou autre) qui écrivent un pipeline à leur place.
> **But** : qu'un pipeline de déploiement s'écrive **sans l'équipe DevSecOps**, en copiant un modèle et en remplissant les champs. Tout ce qui est décrit ici est lu dans les workflows de la branche `prod` au 6/11/2026.
> **À lire avec** : [`guide-livraison-services-migres.md`](guide-livraison-services-migres.md) (quelle branche pour quel service).

## 1. Comment ça marche, en une page

```
PR vers prod ──► pr-gate-prod.yml (Trivy CRITICAL, bloquant) ──► merge
                                                                   │
            push sur prod, chemin apps-microservices/<service>/** │
                                                                   ▼
             deploy-<service>.yml  (wrapper, 1 par service)  ──► uses: deploy-cloud-run.yml   (Cloud Run)
             deploy-gke-<service>.yml                        ──► uses: deploy-gke-service.yml (GKE)
```

- **Un wrapper par service**, dans `.github/workflows/`. Il ne contient que le déclencheur et les paramètres du service. Toute la logique est dans **deux workflows réutilisables** qu'on ne modifie pas pour ajouter un service.
- Le wrapper se déclenche sur **`push` vers `prod`** quand le dossier du service ou le wrapper lui-même change, et à la main (**`workflow_dispatch`**, bouton *Run workflow*).
- L'authentification GCP passe par **Workload Identity Federation** (`vars.GCP_WIF_PROVIDER`, `vars.GCP_DEPLOYER_SA`) : **jamais de clé JSON**.
- L'image est taguée **`sha-<commit court>`** et poussée dans Artifact Registry (`<région>-docker.pkg.dev/<projet>/hellopro/<service>`). Jamais `latest`.
- Une modification de `libs/` **ne redéploie pas** les services qui en dépendent (sauf wrapper qui déclare ce chemin, comme `deploy-content-extractor-api-service.yml`). Il faut lancer les déploiements concernés à la main.
- **Slack** : chaque déploiement envoie une notification si le secret `SLACK_WEBHOOK_URL` existe ; sinon il passe silencieusement. GitHub envoie aussi un email à l'auteur du merge en cas d'échec.

## 2. La gate `pr-gate-prod.yml`

Déclencheur : `pull_request` vers `prod`. Un seul job bloquant : **Trivy sur le système de fichiers du dépôt entier** (`vuln`, `misconfig`, `secret`), sévérité `CRITICAL`, `--ignore-unfixed`, exceptions dans `.trivyignore.yaml`. Conséquences :

- une CVE critique **ailleurs** dans le dépôt bloque votre PR : corriger (ou documenter une exception dans `.trivyignore.yaml` avec justification) puis *Update branch* ;
- la gate ne construit pas d'image : le scan d'image a lieu dans le pipeline Cloud Run (§ 3) ; GKE n'a pas de scan d'image (dette tracée).

## 3. Le workflow réutilisable Cloud Run — `deploy-cloud-run.yml`

Quatre jobs : **build + scan + push**, **deploy**, **smoke test**, **rollback** (trafic remis sur la révision précédente si le smoke test échoue).

| Étape | Ce qui se passe |
|---|---|
| Build | `docker build` depuis `build_context` avec `dockerfile_path` ; tag `sha-<commit>` |
| Scan | `trivy image`, bloquant sur `trivy_severity_block` (`CRITICAL,HIGH` par défaut), `trivy_ignore_unfixed` ; **`trivy_disable_gate: true` rend le scan informatif** (à n'utiliser qu'avec une dette documentée) |
| Push | vers Artifact Registry **seulement si le scan passe** |
| Deploy | lecture de la révision précédente, puis `gcloud run deploy` avec les variables, les secrets (références Secret Manager), le VPC Connector, l'entrée, les ressources, la commande |
| Smoke test | 3 appels de `health_check_path` depuis le runner ; en cas d'échec, le job `rollback` remet le trafic sur la révision précédente. **Avec une entrée interne, le runner ne peut pas joindre le service : le smoke test est ignoré (`skipped`) et il n'y a pas de retour arrière automatique** — vérifier à la main depuis la VM (`v2a_verif_deploy.sh`) |

### Entrées (`with:`)

| Entrée | Obligatoire | Défaut | À retenir |
|---|---|---|---|
| `service_name` | oui | — | nom Cloud Run **et** nom de l'image |
| `dockerfile_path` | oui | — | relatif à la racine du dépôt |
| `build_context` | oui | — | **`.`** (racine) dès que le Dockerfile copie `libs/` ; sinon le dossier du service |
| `cloud_run_region` | non | `vars.GCP_REGION` | `europe-west1` |
| `ingress` | non | `internal` | **`internal-and-cloud-load-balancing`** pour un service appelé par la VM ou GKE ; `all` rouvre le service à Internet : interdit sans décision |
| `allow_unauthenticated` | non | `false` | `true` seulement avec une entrée interne |
| `cpu`, `memory` | non | `1`, `512Mi` | mémoire selon les imports (ex. `1Gi` avec pymilvus + grpc) |
| `min_instances`, `max_instances` | non | `0`, `10` | `min` à 1 seulement si trafic réel et démarrage à froid > 10 s ; `max` à 3 par défaut dans nos wrappers (coût) |
| `vpc_connector`, `vpc_egress` | non | vide, `private-ranges-only` | obligatoires si le service joint une IP interne (gRPC `10.11.0.2`, Milvus, Redis) ; `all-traffic` seulement pour sortir par l'IP NAT fixe |
| `container_port` | non | `8080` | le port du `CMD` du Dockerfile |
| `health_check_path` | non | `/health` | une route qui répond 200 **sans** backend |
| `env_vars_json` | non | `{}` | variables non sensibles ; **`SERVICE_NAME` = nom VM** (les serveurs gRPC priorisent par nom) ; jamais `PORT`, `K_SERVICE`, `K_REVISION`, `K_CONFIGURATION` (réservés) |
| `secret_env_vars_json` | non | `{}` | `"VARIABLE": "nom-du-secret:latest"` ; le compte `cloudrun-services` doit avoir accès **secret par secret** |
| `container_command`, `container_args` | non | vides | pour remplacer une commande calibrée VM (ex. `gunicorn -w 8` → `-w 2`) ; `container_args` séparés par des virgules |
| `startup_cpu_boost` | non | `false` | `true` pour les services Python lourds |
| `request_timeout` | non | 300 s | ne pas l'allonger sans vérifier que les requêtes **terminent** (recherche, 15/10) |
| `trivy_*` | non | voir plus haut | — |

Secret : `slack_webhook_url: ${{ secrets.SLACK_WEBHOOK_URL }}`.

### Modèle de wrapper Cloud Run

Fichier `.github/workflows/deploy-<service>.yml`. Remplacer `<service>` par le nom du dossier (sans le suffixe quand il diffère du nom Cloud Run, voir le tableau du guide).

```yaml
name: 'Deploy — <service>'

# <Une ligne : ce que fait le service, son port, ses dépendances (gRPC enabler, Milvus, Redis, LLM externe).>
# <Décisions qui ne doivent pas changer : entrée interne, min_instances, gate Trivy et pourquoi.>

on:
  push:
    branches:
      - prod
    paths:
      - 'apps-microservices/<service>/**'
      - '.github/workflows/deploy-<service>.yml'
  workflow_dispatch:
    inputs:
      cloud_run_region:
        description: 'Région Cloud Run (override)'
        required: false
        type: string
        default: 'europe-west1'

permissions:
  id-token: write
  contents: read

jobs:
  deploy:
    name: 'Deploy <service>'
    uses: ./.github/workflows/deploy-cloud-run.yml
    with:
      service_name: <service>
      dockerfile_path: apps-microservices/<service>/Dockerfile
      build_context: .
      cloud_run_region: ${{ github.event.inputs.cloud_run_region || 'europe-west1' }}
      ingress: internal-and-cloud-load-balancing
      allow_unauthenticated: true
      cpu: '1'
      memory: '1Gi'
      min_instances: 0
      max_instances: 3
      container_port: <port du CMD>
      startup_cpu_boost: true
      health_check_path: /health
      vpc_connector: vpc-access-connector
      vpc_egress: private-ranges-only
      env_vars_json: |
        {
          "SERVICE_NAME": "<nom du service sur la VM>",
          "EMBEDDING_SERVICE_URL": "10.11.0.2:15052"
        }
      secret_env_vars_json: |
        {
          "GEMINI_API_KEY": "platform-gemini-api-key:latest"
        }
    secrets:
      slack_webhook_url: ${{ secrets.SLACK_WEBHOOK_URL }}
```

Exemple complet et commenté : [`deploy-prix-traitement.yml`](../../.github/workflows/deploy-prix-traitement.yml). Pour un serveur MCP derrière `mcp-proxy` (Node + Python) : [`deploy-mcp-semrush-service.yml`](../../.github/workflows/deploy-mcp-semrush-service.yml) (santé sur `/status`).

## 4. Le workflow réutilisable GKE — `deploy-gke-service.yml`

Un seul job : build sur le runner, push dans Artifact Registry (tag `sha-<commit>`), identifiants `kubectl` par **Connect Gateway**, puis **`kubectl set image`** sur le Deployment existant (les variables, sondes et secrets du manifeste sont préservés), attente du rollout (180 s), **`rollout undo`** automatique si le rollout échoue, vérification de l'image en place, résumé et Slack.

Ce workflow **ne crée pas** le Deployment : le manifeste (`RAG-HP-PUB-infra/infra-microservices/manifest/…`) doit exister et avoir été appliqué une première fois. Le compte `github-deployer` a besoin du RBAC namespacé `github-deployer-gke-set-image` dans le namespace cible (`manifest/cicd/github-deployer-rbac.yaml`).

### Entrées (`with:`)

| Entrée | Obligatoire | Défaut | À retenir |
|---|---|---|---|
| `service_name` | oui | — | nom de l'image dans Artifact Registry |
| `dockerfile` | oui | — | relatif à la racine |
| `build_context` | non | `.` | racine : les Dockerfiles des consumers copient `libs/` |
| `deployment` | oui | — | nom du Deployment Kubernetes |
| `container` | oui | — | nom du conteneur dans le Deployment (souvent le même) |
| `namespace` | non | `apps-microservices` | `moteur-recherche` pour opti-moteur-front |
| `cluster` | non | `matching-api-dev-k8s` | membership de la flotte |

Secret : `slack_webhook_url`.

### Modèle de wrapper GKE (consumer RabbitMQ)

```yaml
name: 'Deploy GKE — <service>'

# <Une ligne : consumer de quelle file, migré quand, modèle suivi.>

on:
  push:
    branches: [prod]
    paths:
      - 'apps-microservices/<dossier>/**'
      - '.github/workflows/deploy-gke-<service>.yml'
  workflow_dispatch: {}

permissions:
  id-token: write
  contents: read

jobs:
  deploy:
    uses: ./.github/workflows/deploy-gke-service.yml
    with:
      service_name: <service>
      dockerfile: apps-microservices/<dossier>/Dockerfile
      build_context: .
      deployment: <service>
      container: <service>
      namespace: apps-microservices
    secrets:
      slack_webhook_url: ${{ secrets.SLACK_WEBHOOK_URL }}
```

Exemple : [`deploy-gke-qc-equivalence.yml`](../../.github/workflows/deploy-gke-qc-equivalence.yml). Attention au nom du dossier, qui peut différer du nom du service (`QC-equivalence` → `qc-equivalence`, `product-processor-service` → `product-processor`).

### Variante avec approbation de production

Pour un service GKE qui sert directement du trafic, on peut imposer une **approbation manuelle** avant le déploiement : un job `approval` rattaché à l'environnement GitHub `production` (relecteurs requis réglés dans *Settings → Environments*), puis le job `deploy` avec `needs: approval`, et une `concurrency` pour ne jamais lancer deux déploiements en parallèle. Modèle : [`deploy-gke-opti-moteur-front.yml`](../../.github/workflows/deploy-gke-opti-moteur-front.yml) (ticket 007).

```yaml
concurrency:
  group: deploy-gke-<service>
  cancel-in-progress: false

jobs:
  approval:
    name: 'Approbation production'
    runs-on: ubuntu-latest
    environment: production
    steps:
      - run: echo "Deploiement <service> approuve (commit ${GITHUB_SHA::7})"

  deploy:
    needs: approval
    uses: ./.github/workflows/deploy-gke-service.yml
    with: …
```

## 5. Ajouter un pipeline à un nouveau service : check-list

1. **Cible** : Cloud Run pour un service HTTP ou MCP sans état ; GKE pour un consumer RabbitMQ (`start_consuming` bloquant, pas de HTTP) ou un service always-on. En cas de doute, lire le `CMD` du Dockerfile et le démarrage du code (dépendances fatales : MySQL, SSO, fichiers montés).
2. **Dockerfile** : contexte racine si le code importe `libs/` ; port fixé dans le `CMD` ; pas de `latest` ; image de base scannée (une CVE `HIGH` bloque le push Cloud Run).
3. **Secrets** : créés dans Secret Manager (`platform-*` pour les secrets partagés, `<service>-*` sinon), accès donné à `cloudrun-services` secret par secret ; **jamais de valeur dans le wrapper**, seulement `nom:latest`.
4. **Variables** : noms identiques à ceux de la VM ; `SERVICE_NAME` = nom VM ; pas de variable réservée Cloud Run.
5. **Réseau** : VPC Connector + `private-ranges-only` si une IP interne est appelée ; entrée `internal-and-cloud-load-balancing` par défaut ; `all` interdit sans décision écrite.
6. **GKE** : manifeste du Deployment créé et appliqué (secret du broker **DEV** pour un shadow, prod seulement à la bascule), probe sur une route sans backend ou `tcpSocket`, RBAC `github-deployer` dans le namespace.
7. **Wrapper** : copier le modèle, remplir, vérifier que les chemins `paths:` sont exactement le dossier du service et le wrapper.
8. **Premier lancement** : *Run workflow* (`workflow_dispatch`) depuis `prod` après le merge ; lire le résumé du job (image, révision, smoke test ou rollout) ; sur Cloud Run, vérifier l'entrée interne (Internet → 404, VM → 200).
9. **Déclarer le service** : ligne dans l'[inventaire](../migration-microservices/inventaire-services-migration-par-lot.md), tableau du [guide de livraison](guide-livraison-services-migres.md), et dossier ajouté au garde-fou `guard-migrated-services-poc.yml` (branche `features/poc`) si la production du service quitte la VM.
10. **Attention** : ajouter un wrapper **déclenche un déploiement** au merge. Pour un lot de wrappers, prendre un état avant et après (`gke_lot_etat.sh` pour GKE).

## 6. Retour arrière

| Cible | Automatique | Manuel |
|---|---|---|
| Cloud Run | smoke test en échec → trafic remis sur la révision précédente (pas de smoke test, donc pas de retour automatique, sur une entrée interne) | `gcloud run services update-traffic <service> --to-revisions <révision>=100` ; la révision précédente est affichée dans le journal du job |
| GKE | rollout en échec (180 s) → `kubectl rollout undo` | `kubectl rollout undo deployment/<service> -n apps-microservices` ; ou `set image` sur le tag `sha-` précédent |

Un retour arrière de **route** (la VM reprend le trafic d'un service Cloud Run) est un geste de migration, pas de CD : voir `bascule_route.sh revert` et la note de décision du 15/10 sur la recherche.

## 7. Ce qui est interdit ou à ne pas faire

- `ingress: all` ou `allUsers` sur un service interne (F-HP-SEC-030) ; `allow_unauthenticated: true` sans entrée interne.
- Une valeur de secret, une clé JSON de compte de service, ou `.env` dans le dépôt ou le wrapper.
- `trivy_disable_gate: true` sans commentaire qui nomme la dette et la date.
- Modifier `deploy-cloud-run.yml` ou `deploy-gke-service.yml` pour un seul service : passer par une entrée ou ouvrir une discussion avec DevSecOps.
- Un wrapper pour un service **dont la production reste sur la VM** sans le dire dans son en-tête : il ne déploierait qu'une copie de test, et une livraison par `prod` ne toucherait pas la production (18 wrappers sont dans ce cas au 6/11, listés dans l'[état global](../migration-microservices/etat-global-migration-2026-11-06.md) § 5.1).
- Livrer un service migré par `features/poc` : le garde-fou prévient, mais rien ne part en production.

## 8. Variables et secrets du dépôt (réglés une fois, par DevSecOps)

| Nom | Type | Rôle |
|---|---|---|
| `GCP_PROJECT_ID`, `GCP_REGION` | variables | projet et région |
| `GCP_WIF_PROVIDER`, `GCP_DEPLOYER_SA` | variables | fédération d'identité et compte `github-deployer` |
| `SLACK_WEBHOOK_URL` | secret | notifications (optionnel) ; migration vers Teams prévue |
| environnement `production` | réglage | relecteurs requis pour la variante avec approbation |

Les actions tierces sont **épinglées par SHA** (`actions/checkout@11bd719…` v4.2.2, `google-github-actions/auth@8254fb7…` v2.1.10, `setup-gcloud@f099058…` v2.1.4) : reprendre ces lignes telles quelles, ne jamais inventer un SHA.
