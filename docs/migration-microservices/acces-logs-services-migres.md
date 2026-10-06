# Lire les logs d'un service migré — guide développeur

> Pour un service qui tourne sur GKE ou Cloud Run, `docker logs` sur la VM GPU ne montre plus rien d'utile : le
> conteneur VM est arrêté. Les logs sont dans **Cloud Logging**, lisibles depuis la console GCP ou depuis ton poste
> avec `gcloud`. Aucun accès à la VM Manager, aucun `kubectl` nécessaire pour lire des logs.
>
> **Depuis quand** : les logs des pods GKE ne sont collectés que depuis le **21/09/2026 14h21 (Paris)**. Avant cette
> date, il n'y a rien à trouver côté GKE (finding F-HP-OBS-004). Cloud Run était déjà collecté (revérifié le 05/10 : journal
> des requêtes et sortie de l'application, aucune exclusion FinOps sur Cloud Run). **Vague 2** : voir la section dédiée plus bas.

## Ce qu'il te faut

- Ton compte Google **hellopro.fr**, avec les rôles `Logs Viewer` et `Cloud Run Viewer` sur le projet
  `hellopro-rag-project`. Posés le 21/09 pour les 6 développeurs ayant l'accès SSH aux VM ; la liste est tenue par le
  DevSecOps (`Docs/DevSecOps/runbooks/iam_acces_humains.md`). Si la console dit « permission denied », demande-lui.
- Pour la ligne de commande : [`gcloud` installé](https://cloud.google.com/sdk/docs/install) sur ton poste, puis une fois :

```bash
gcloud auth login                                  # ouvre le navigateur, compte hellopro.fr
gcloud config set project hellopro-rag-project
```

## Trouver le nom à mettre dans le filtre

Le nom sur la VM (celui de `docker-compose.yml`) n'est pas toujours celui du cloud. Les tables ci-dessous sont
générées depuis [`inventaire-services-migration-par-lot.md`](inventaire-services-migration-par-lot.md) et
[`suivi-bascule-par-lots.md`](suivi-bascule-par-lots.md). Deux colonnes comptent :

- **Filtre** : la valeur exacte à coller dans `resource.labels.container_name=` (GKE) ou `resource.labels.service_name=` (Cloud Run).
- **État** : `PROD` = le service traite le trafic de production sur le cloud, ses logs sont ceux qui comptent.
  `shadow` = déployé sur le cloud mais **la production est encore sur la VM** : ses logs cloud ne montrent que des
  tests ou du vide, regarde `docker logs` sur la VM.

### Services GKE (consumers RabbitMQ) — `resource.type="k8s_container"`, namespace `apps-microservices`

| Nom sur la VM | **Filtre** (`container_name`) | État |
|---|---|:--:|
| `api-gateway-go-service` | `api-gateway-go` | shadow |
| `deepseek-metrics-collector-service` | `deepseek-metrics-collector-service` | **PROD** |
| `devis-processor-service` | `devis-processor-service` | shadow |
| `di-database-qdrant-service` | `di-database-qdrant-service` | shadow |
| `dlq-manager-service` | `dlq-manager-service` | shadow |
| `document-database-qdrant-service` | `document-database-qdrant-service` | shadow |
| `echange-database-qdrant-service` | `echange-database-qdrant-service` | shadow |
| `echange-processor-service` | `echange-processor-service` | shadow |
| `embedding-service` | `embedding-service` | shadow |
| `graph-rag-api-admin-service` | `graph-rag-api-admin-service` | shadow |
| `graph-rag-categorie-processor` | `graph-rag-categorie-processor` | shadow |
| `graph-rag-dlq-manager-service` | `graph-rag-dlq-manager` | shadow |
| `graph-rag-etl-processor` | `graph-rag-etl-processor` | shadow |
| `graph-rag-fournisseur-processor` | `graph-rag-fournisseur-processor` | shadow |
| `graph-rag-llm-extractor-processor` | `graph-rag-llm-extractor-processor` | shadow |
| `graph-rag-normalize-unite-processor` | `graph-rag-normalize-unite-processor` | shadow |
| `graph-rag-normalize-unite-retry-processor` | `graph-rag-normalize-unite-retry-processor` | shadow |
| `graph-rag-produit-processor` | `graph-rag-produit-processor` | shadow |
| `graph-rag-semantique-vigil-processor` | `graph-rag-semantique-vigil-processor` | shadow |
| `mcp-gateway-service` | `mcp-gateway-service` | shadow |
| `mcp-google-templates-runner` | `mcp-google-templates-runner` | shadow |
| `mcp-zoho-service` | `mcp-zoho-service` | shadow |
| `nettoyage-bruit-ocr-service` | `nettoyage-bruit-ocr-service` | **PROD** |
| `prix-caracterisation` | `prix-caracterisation` | shadow |
| `prix-extraction-devis` | `prix-extraction-devis` | shadow |
| `prix-extraction-message` | `prix-extraction-message` | shadow |
| `prix-extraction-produits` | `prix-extraction-produits` | shadow |
| `prix-milvus-processor-service` | `prix-milvus-processor` | shadow |
| `product-database-qdrant-service` | `product-database-qdrant-service` | shadow |
| `product-processor-service` | `product-processor-service` | shadow |
| `qc-caracterisation` | `qc-caracterisation` | shadow |
| `qc-enrichissement` | `qc-enrichissement` | shadow |
| `qc-equivalence` | `qc-equivalence` | shadow |
| `qc-generation-caracteristiques` | `qc-generation-caracteristiques` | shadow |
| `qc-generation-question1` | `qc-generation-question1` | shadow |
| `qc-generation-question2an` | `qc-generation-question2an` | shadow |
| `qc-generation-valeurs` | `qc-generation-valeurs` | shadow |
| `template-llm-service` | `template-llm-service` | shadow |
| `webhook-service` | `webhook-service` | shadow |
| `website-database-qdrant-service` | `website-database-qdrant-service` | shadow |
| `website-processor-service` | `website-processor-service` | shadow |

### Services Cloud Run (API, MCP, fronts) — `resource.type="cloud_run_revision"`, région `europe-west1`

| Nom sur la VM | **Filtre** (`service_name`) | État |
|---|---|:--:|
| `account-service-backend` | `account-service-backend` | shadow |
| `account-service-frontend` | `account-service-frontend` | shadow |
| `api-chat-llm-service` | `api-chat-llm` | shadow |
| `api-classification-service` | `api-classification` | shadow |
| `api-comparaison-texte-service` | `api-comparaison-texte` | **PROD** (route gateway, 05/10) |
| `api-detection-langue-fr-service` | `api-detection-langue-fr` | shadow |
| `api-embedding-service` | `api-embedding-service` | shadow |
| `api-html-recherche-service` | `api-html-recherche` | shadow |
| `api-ingestion-service` | `api-ingestion` | shadow |
| `api-recherche-service` | `api-recherche` | shadow |
| `api-rest-milvus-service` | `api-rest-milvus` | shadow |
| `content-extractor-api-service` | `content-extractor-api-service` | shadow |
| `crawler-monitor-backend` | `crawler-monitor-backend` | shadow |
| `graph-rag-api-recherche-optim-service` | `graph-rag-api-recherche-optim-service` | shadow |
| `graph-rag-api-recherche-rust-service` | `graph-rag-api-recherche-rust-service` | shadow |
| `graph-rag-api-recherche-service` | `graph-rag-api-recherche-service` | shadow |
| `image-comparison-service` | `image-comparison-service` | shadow |
| `mcp-api-recherche-service` | `mcp-api-recherche-service` | shadow |
| `mcp-classification-produit-service` | `mcp-classification-produit-service` | shadow |
| `mcp-google-analytics-minisite-service` | `mcp-google-analytics-minisite-service` | shadow |
| `mcp-google-analytics-service` | `mcp-google-analytics-service` | shadow |
| `mcp-google-search-console-service` | `mcp-google-search-console-service` | shadow |
| `mcp-leexi-service` | `mcp-leexi-service` | shadow |
| `mcp-neo4j-service` | `mcp-neo4j-service` | shadow |
| `mcp-ringover-service` | `mcp-ringover-service` | shadow |
| `mcp-semrush-service` | `mcp-semrush-service` | shadow |
| `nextjs-conseils-hp` | `nextjs-conseils-hp` | shadow |
| `nextjs-formulaire-hp` | `nextjs-formulaire-hp` | shadow |
| `optimize-service` | `optimize-service` | shadow |
| `prix-traitement` | `prix-traitement` | shadow |

Les services absents de ces tables ne sont pas migrés : `docker logs` sur la VM, comme avant.

> ⚠️ **Piège vu le 21/09** : `gcloud run services logs read nettoyage-bruit-ocr-service` ne rend rien, et c'est normal :
> ce service est sur **GKE**. `gcloud run …` ne sert qu'aux services de la table Cloud Run. Pour GKE, c'est `gcloud logging read`
> avec `resource.type="k8s_container"`, ou la console.

## Vague 2 — vérifier un service HTTP basculé sur Cloud Run, et lire ses logs

> Ajouté le 05/10 avec la première route basculée (`SERVICE_COMPARAISON_TEXTE`). Procédure de bascule :
> [`procedure-bascule-route-http.md`](procedure-bascule-route-http.md) · état des services : [`suivi-vague-2.md`](suivi-vague-2.md) § 0bis.

En vague 2, ton service HTTP **existe deux fois** : le jumeau sur la VM (resté allumé, c'est le repli) et le service
Cloud Run. Après la bascule de sa route, les appels qui passent par la gateway (`api.hellopro.eu`) vont sur Cloud Run ;
les appels **directs** entre conteneurs de la VM (par exemple `crawler-service` → content-extractor) vont toujours sur le
jumeau. Avant de chercher un bug, regarde donc **où** est arrivée la requête.

### Deux journaux par service Cloud Run

| Journal | Ce qu'il contient | Comment le reconnaître |
|---|---|---|
| **Requêtes** (`run.googleapis.com/requests`) | une ligne par requête HTTP reçue : méthode, code, URL, latence — écrite par Cloud Run, même si ton code ne logue rien | `GET 200 https://api-comparaison-texte-xqksdwdiga-ew.a.run.app/openapi.json` |
| **Application** (`run.googleapis.com/stdout`, `stderr`) | ce que ton code écrit (uvicorn, `logging`, `print`) | `INFO: 169.254.169.126:38440 - "GET /api/v1/health HTTP/1.1" 200 OK` |

L'adresse `169.254.x.x` est le frontal de Google, pas l'appelant réel : pour savoir **qui** a appelé, regarde les logs de
la gateway sur la VM (elle reste sur la VM jusqu'à V2-c).

### Lire les logs

**Le plus simple, depuis ton poste** (marche aussi sous Git Bash) :

```bash
gcloud run services logs read api-comparaison-texte --region europe-west1 --project hellopro-rag-project --limit 100
```

**Console** : Cloud Run → le service → onglet **Logs** ; ou Logs Explorer avec :

```
resource.type="cloud_run_revision"
resource.labels.service_name="api-comparaison-texte"
```

Ajoute `httpRequest.status>=500` pour les erreurs serveur, `logName:"run.googleapis.com%2Frequests"` pour ne garder que
les requêtes, `logName:"stdout" OR logName:"stderr"` pour ne garder que ton code.

> ⚠️ **Sous Windows (Git Bash, PowerShell)**, `gcloud logging read` avec un filtre entre guillemets, ou un `--format`
> avec des parenthèses (`value(...)`, `table(...)`), est **mal transmis par `gcloud.cmd`** : 0 ligne, ou une erreur
> `… was unexpected at this time`. Ce n'est pas l'absence de logs (constaté le 05/10). Utilise
> `gcloud run services logs read`, la console, ou **Cloud Shell** (icône `>_` de la console) pour les filtres avancés.

### Vérifier que le service reçoit bien ses requêtes

| Question | Où regarder |
|---|---|
| Ma requête est-elle arrivée sur Cloud Run ? | journal des requêtes (ci-dessus), à l'heure de ton test |
| … ou sur le jumeau VM ? | `docker logs -t --since 10m <conteneur>` sur la VM (accès SSH) : si ta requête y est, la route n'a pas (encore) basculé — la gateway relit sa table toutes les 15 min, le DevSecOps peut forcer un rescan |
| Combien d'appels, combien d'erreurs ? | Cloud Run → le service → onglet **Métriques** : nombre de requêtes par classe de code (2xx, 4xx, 5xx), latence, instances (rôle `monitoring.viewer`, posé le 06/10 pour les 13 comptes devs) |
| Quelle révision sert le trafic ? | Cloud Run → le service → onglet **Révisions** (ou `gcloud run services describe <service> --region europe-west1 --format=json`) |

### Ce qu'on attend de toi après la bascule de ton service

1. Joue le parcours décrit dans la fiche du lot (`lots/V2-a1.md`…) et écris **OK / KO** dans le canal de bascule.
2. Un KO : envoie l'heure du test et, si possible, le lien « Share » de la requête Logs Explorer. **Ne corrige pas en
   direct** : le DevSecOps remet la route sur la VM en une minute, on analyse ensuite.
3. Après validation, tes correctifs pour ce service partent dans `prod` (PR, gate, CD) — plus par `features/poc`.

## Option 1 — la console (le plus simple)

1. Ouvre **Logs Explorer** : <https://console.cloud.google.com/logs/query?project=hellopro-rag-project>
2. Colle une requête, par exemple pour un service GKE :

```
resource.type="k8s_container"
resource.labels.namespace_name="apps-microservices"
resource.labels.container_name="nettoyage-bruit-ocr-service"
```

   ou pour un service Cloud Run :

```
resource.type="cloud_run_revision"
resource.labels.service_name="api-recherche"
```

3. Choisis la plage de temps en haut à droite (par défaut 1 h ; conservation **15 jours** (rétention du bucket `_Default`)).
4. **Run query**. Les lignes récentes sont en bas ; **Stream logs** pour suivre en direct.

Variantes utiles, à ajouter à la requête (une par ligne = ET logique) :

| Besoin | Ligne à ajouter |
|---|---|
| Tous les QC d'un coup | `resource.labels.container_name=~"^qc-"` (à la place de la ligne `container_name=`) |
| Retrouver un identifiant (catégorie, produit, fiche) | `textPayload:"1002121"` (plein texte, guillemets obligatoires) |
| Les vraies erreurs d'un service Python | `textPayload=~"ERROR|Traceback|Exception|❌"` — **pas** `severity>=ERROR`, voir la note sévérité |
| Un pod précis | `resource.labels.pod_name="qc-caracterisation-f674d9b9d-6sr7b"` |
| Cloud Run : requêtes HTTP en erreur | `resource.type="cloud_run_revision"` `httpRequest.status>=500` |
| Cloud Run : une révision précise | `resource.labels.revision_name="api-recherche-00012-abc"` |
| Cloud Run : les logs de démarrage (crash au boot) | `resource.type="cloud_run_revision"` `textPayload=~"Traceback|Error|listening|Uvicorn|gunicorn"` |

Astuce : **Save query** pour garder « mes QC en erreur » sous la main, et **Share link** pour envoyer la vue exacte
(filtre + plage) au DevSecOps quand tu remontes un problème.

### Note sévérité — à lire une fois

La sévérité affichée dépend du **flux**, pas du niveau Python. Les services en `logging.basicConfig()` (les QC, par exemple)
écrivent sur **stderr** → tout en **`ERROR`**, même un `INFO - En attente sur la file`. Les services qui passent par
`setup_logging()` de `common-utils` (nettoyage-bruit-ocr, les processors…) écrivent sur **stdout** → tout en **`INFO`**, même un
`logger.error`. Dans les deux cas : filtre par **texte** (`ERROR`, `Traceback`, `❌`), jamais par `severity`, jusqu'au chantier
logs JSON (F-HP-OBS-005). Cloud Run est mieux
loti : les requêtes HTTP ont une vraie sévérité, seuls les logs applicatifs stderr ont le même défaut.

## Option 2 — depuis ton poste, en ligne de commande

```bash
# GKE : dernières 30 min d'un service, plus récent en dernier
gcloud logging read \
  'resource.type="k8s_container" resource.labels.namespace_name="apps-microservices" resource.labels.container_name="nettoyage-bruit-ocr-service"' \
  --freshness=30m --order=asc --format='value(timestamp,textPayload)'

# GKE : les vraies erreurs de tous les QC sur 6 h
gcloud logging read \
  'resource.type="k8s_container" resource.labels.namespace_name="apps-microservices" resource.labels.container_name=~"^qc-" textPayload=~"ERROR|Traceback|❌"' \
  --freshness=6h --order=asc --format='value(timestamp,resource.labels.container_name,textPayload)'

# Cloud Run : les 100 dernières lignes d'un service (équivalent de docker logs --tail)
gcloud run services logs read api-recherche --region europe-west1 --limit 100

# Cloud Run : les requêtes en 5xx sur 1 h
gcloud logging read \
  'resource.type="cloud_run_revision" resource.labels.service_name="api-recherche" httpRequest.status>=500' \
  --freshness=1h --format='value(timestamp,httpRequest.status,httpRequest.requestUrl)'

# Cloud Run : quelle révision sert le trafic, et depuis quand (utile après un déploiement)
gcloud run services describe api-recherche --region europe-west1 --format=json | grep -E '"(latestReadyRevisionName|percent|revisionName)"'

# suivre en direct (équivalent de docker logs -f) — composant beta à installer une fois : gcloud components install beta
gcloud beta logging tail \
  'resource.type="k8s_container" resource.labels.namespace_name="apps-microservices" resource.labels.container_name="nettoyage-bruit-ocr-service"' \
  --format='value(timestamp,textPayload)'
```

`--freshness` accepte `10m`, `2h`, `3d`. Sans `--order=asc`, le plus récent sort en premier.

> **Si une commande `gcloud` rend une sortie vide alors que la console montre des lignes** : vérifie `gcloud config list` ;
> avec `accessibility/screen_reader = True`, les formateurs `value(...)`, `yaml(...)`, `table(...)` peuvent ne rien afficher
> (vu le 21/09). Corrige avec `gcloud config set accessibility/screen_reader false`, ou utilise `--format=json`.

## Ce qui change par rapport à la VM

| Avant (VM) | Maintenant (GKE / Cloud Run) |
|---|---|
| `docker logs rag-hp-pub-qc-caracterisation-1` puis `-2` | une seule requête, tous les pods du service ; le pod est dans `resource.labels.pod_name` |
| Fichiers de suivi `/app/tracking` lus par `qc-tracking-service` | **plus de fichier** pour les services migrés (décision Lead Dev du 21/09) : l'information est dans les logs du pod |
| Logs perdus au `docker rm` | conservés 15 jours quoi qu'il arrive au pod |
| Heure locale de la VM (UTC) | horodatage UTC dans Logging ; la console affiche dans **ton** fuseau (réglable en haut à droite) |
| `print()` visible dans `docker logs` | collecté aussi, en sévérité `INFO` (depuis le 21/09 soir : le namespace `apps-microservices` est épargné par les exclusions FinOps, seul le bruit `/health` est jeté). Loggue quand même avec `logging`, pas `print` |

## Quatre règles

1. **Ne recopie pas une ligne de log qui contient une URL avec identifiants** (`amqp://user:motdepasse@…`) dans Slack
   ou un ticket : masque le mot de passe. Certains services l'affichent encore au démarrage (F-HP-SEC-021, en cours).
2. Un comportement anormal sur un service `PROD` : **remonte-le au DevSecOps avant de corriger**, avec le lien
   « Share » de ta requête. Pendant la fenêtre d'observation d'un lot, un rollback se joue en une minute.
3. Un `consumers=0` ou un silence entre **01h-04h et 06h-10h UTC** sur `nettoyage-bruit-ocr`, `qc-caracterisation`,
   `template-llm`, `qc-fabricant-reference` est **normal** : ces services se désabonnent volontairement pendant les
   heures pleines DeepSeek ([`architecture-apres-migration.md`](architecture-apres-migration.md), § 10.4).
4. **Les logs coûtent** (ingestion facturée au-delà de 50 GiB/mois). Pas de log par ligne de boucle, pas de dump de
   payload complet en INFO. Le volume est suivi par le DevSecOps ; un service trop bavard sera ramené à `WARNING`.

## Voir les pods (console GKE ou `kubectl`) — ouvert le 22/09

Les 13 comptes de la liste ont la lecture du cluster (rôles `container.viewer`, `container.clusterViewer`, `gkehub.gatewayReader`, et un RoleBinding `view` sur `apps-microservices`). Aucun secret n'est lisible, aucune écriture possible.

- **Console** : <https://console.cloud.google.com/kubernetes/workload/overview?project=hellopro-rag-project> → filtre namespace `apps-microservices`. Onglet **Logs** d'un pod = la même chose que Logs Explorer.
- **`kubectl` depuis ton poste** (une fois) :

```bash
gcloud components install gke-gcloud-auth-plugin
gcloud container fleet memberships get-credentials matching-api-dev-k8s --project hellopro-rag-project   # Connect Gateway, cluster à endpoint privé
kubectl get pods -n apps-microservices
kubectl logs -n apps-microservices deploy/qc-caracterisation --since=1h -f          # équivalent de docker logs -f
```

`kubectl exec`, `delete`, `edit` : refusés, c'est voulu.

## Pour aller plus loin (sur demande au DevSecOps)

- `kubectl exec` (shell dans un pod) : droits supplémentaires, au cas par cas.
- Un tableau de bord Logs par chaîne (QC, prix, graph-rag).
- Logs JSON structurés côté code (F-HP-OBS-005) pour retrouver une vraie sévérité et pouvoir filtrer `severity>=ERROR`.
