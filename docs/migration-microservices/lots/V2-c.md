# Lot V2-c — Bloc gateway B1 + B3 (ex-L7)

> **Vague 2 · lot 5/6** · risque **Fort** · **une journée dédiée, semaine du 12/10** (pas un vendredi).
> Procédure commune : [`../procedure-bascule-route-http.md`](../procedure-bascule-route-http.md) pour les routes ; ce lot a en plus ses gestes propres (ci-dessous) · plan : [`../plan-vague-2.md`](../plan-vague-2.md) § 3 V2-c et § 1bis · suivi : [`../suivi-vague-2.md`](../suivi-vague-2.md).
> Reprend l'ancien lot [`L7.md`](L7.md) (non joué le 25/09 : ces services basculent **avec leur trafic**). Priorités **P2 / P3** de l'[inventaire](../inventaire-services-migration-par-lot.md).

## Composition

| Service (nom `docker-compose`) | Cible (nom exact) | Aiguillage | Jumeau VM après bascule |
|---|---|---|---|
| `api-gateway-go-service` | GKE `api-gateway-go` | **vhost nginx VM `api.hellopro.eu`** → IP interne du Service GKE (décision 10) | **arrêté dans le même geste** (écrit seul au démarrage) |
| `mcp-gateway-service` | GKE `mcp-gateway-service` | **vhost nginx VM `mcp.hellopro.eu`** → IP interne GKE | **arrêté dans le même geste** (contrôle de santé toutes les 30 s, alertes Slack) |
| `mcp-zoho-service` | GKE `mcp-zoho-service` | ligne `mcp_servers` | arrêté |
| `mcp-google-templates-runner` | GKE `mcp-google-templates-runner` | URL côté `mcp-gateway` | arrêté |
| `graph-rag-api-admin-service` | GKE `graph-rag-api-admin-service` | route `SERVICE_GRAPHADMIN` | après observation |
| `graph-rag-dlq-manager-service` | GKE `graph-rag-dlq-manager` (sans `-service`) | route `SERVICE_GRAPHDLQ` | après observation |
| `image-comparison-service` | Cloud Run `image-comparison-service` | route `SERVICE_IMAGE_COMPARATOR` (aujourd'hui `reverse-proxy:8050/comparator`) | après observation |

**Hors lot** : `dlq-manager-service` **reste sur la VM** (décision 5, UP, restreint aux IP Hellopro) ; `api-catalog-service` reste sur la VM (la gateway GKE le joint par l'enabler).

## Ce qui bascule dans ce lot

- `api.hellopro.eu` et `mcp.hellopro.eu` : le **nginx de la VM** envoie vers GKE au lieu des conteneurs locaux (décision 10 : DNS inchangé pendant la vague).
- `gateway_db` (MySQL VM) devient la base d'une gateway **qui tourne sur GKE** (enabler `10.11.0.2:3307`) : migration de schéma au démarrage (`AutoMigrate`), jetons système.

## À savoir, service par service

Analyse de code complète du 25/09 : [`L7.md`](L7.md), section « Analyse du code (25/09) ».

| Service | Vigilance |
|---|---|
| `api-gateway-go` | `AutoMigrate` de 3 tables + INSERT de jetons au démarrage. Carte de services issue de `.env.url` (fichier local VM) → ConfigMap. `JWT_SECRET` identique. Défauts Docker à poser (`MYSQL_*`, `API_CATALOG_GRPC`, `ACCOUNT_BASE_URL`). |
| `mcp-gateway-service` | `AutoMigrate` de 36 tables ; contrôle de santé → `UPDATE mcp_servers` + Slack ; `MCP_GATEWAY_PORT=8592` ; `ENCRYPTION_KEY` partagée ; icônes sur le disque VM → stockage cible ; **pas de Service K8s** à ce jour. `account-service-backend` (VM) l'appelle → le repointer **avant** d'arrêter le jumeau. Commit `poc` seul du 30/09 → rapatriement. |
| `mcp-zoho-service` | Pas de Service K8s ; dépend de MySQL au démarrage. |
| `mcp-google-templates-runner` | Reçoit les comptes de service Google déchiffrés : un seul hôte à la fois. |
| `graph-rag-api-admin` | Écrit dans Neo4j sur appel : instantané Neo4j la veille. |
| `graph-rag-dlq-manager` | Endpoints sans authentification (F-HP-SEC-027) : jamais exposés hors cluster. |
| `image-comparison-service` | ⚠️ **Compteur Redis partagé** `comparator:running_count` à isoler, sinon collision avec la VM ; passe aujourd'hui par le `reverse-proxy` (sidecar nginx à prévoir). |

## Prérequis spécifiques au lot

- c.1 Version du code gateway VM = image GKE (le LEAD confirme) ; parité par empreinte de `ENCRYPTION_KEY`, `JWT_SECRET`, `GATEWAY_ADMIN_KEY`, `GOOGLE_TEMPLATES_RUNNER_ADMIN_TOKEN`, `ZOHO_GATEWAY_TOKEN`.
- c.2 Services K8s manquants, Service **interne** (IP `10.0.1.x`) pour `api.` et `mcp.`, ConfigMap `.env.url`, icônes, sidecar `/comparator` `/crawler`, défauts Docker posés.
- **0.22 Script de bascule nginx** d'un vhost (sauvegarde, `nginx -t`, `reload`, contrôle, retour arrière) : à écrire.
- Dump complet de `gateway_db` le matin (c.3), instantané Neo4j la veille.

## Ce qu'on attend du LEAD et des devs concernés

- LEAD : confirmation écrite de la version du code gateway (c.1).
- Devs gateway et MCP : parcours réels sur `api.hellopro.eu` et `mcp.hellopro.eu` après la bascule (c.7).

## Feuille de lot

| Étape | Heure | Résultat | Par |
|---|---|---|---|
| c.1 Parité version + jetons | | | DSO · LEAD |
| c.2 Manifestes (`kubectl diff` relu), pods prêts en shadow | | | DSO |
| Script nginx (0.22) prêt et relu | | | DSO |
| c.3 Dump `gateway_db` (taille vérifiée) | | | DSO |
| c.4 mcp-gateway, zoho, templates-runner, api-gateway-go sur la prod ; jumeaux arrêtés | | | DSO |
| c.5 vhosts nginx `api.` et `mcp.` → GKE | | | DSO |
| c.6 routes graph-rag admin / dlq, comparateur d'images | | | DSO |
| c.7 Tests fonctionnels gateway et MCP | | | devs |
| Relevé 17h / nuit | | | DSO |
| **Décision J+1 9h30** (rollback prêt : vhosts remis, `docker start` des jumeaux, dump si le schéma a divergé) | | | LEAD · DSO |
