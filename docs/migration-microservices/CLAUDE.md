# CLAUDE.md — Migration des microservices (contexte pour l'assistant)

> Lis ce fichier avant d'aider un développeur sur le pré-contrôle de migration.
> Les trois documents de référence sont dans ce même dossier ; ne réponds pas de mémoire, ouvre-les.

## Ce qui se passe

~80 services quittent la **VM GPU** (Docker Compose, ~155 conteneurs, `docker-compose.yml` à la racine du dépôt)
pour **Cloud Run** (europe-west1) et **GKE** (cluster `matching-api-dev-k8s`, namespace `apps-microservices`).
Les services concernés tournent déjà en double sur le cloud depuis juillet-août **sans recevoir de trafic** — le
*shadow*. La bascule leur donne les données de production et arrête leurs jumeaux VM.

Le GPU et ses dépendants **restent sur la VM**, définitivement.

## Ton rôle ici

Aider le développeur à faire le **pré-contrôle de son service** : trouver dans son code les hypothèses qui ne
survivront pas au déplacement. Tu ne déploies rien, tu ne lances aucune commande d'infrastructure.

**Fais** : lire le code du service, chercher les adresses et ports en dur, comparer les variables d'environnement
à la matrice, lire les trois documents de ce dossier avant de conclure, citer `fichier:ligne`.

**Ne fais pas** : proposer une commande `gcloud`, `kubectl`, `terraform` ou `docker` visant la production —
ce n'est pas le périmètre du développeur. Ne modifie pas `docker-compose.yml`. N'invente pas un nom de service ou
une URL : si l'information n'est pas dans les documents, dis-le et laisse le développeur poser la question.

## Vocabulaire

| Terme | Sens |
|---|---|
| **VM GPU** | `vm-embedding-g2-std-24-use`, us-east4. L'existant. Porte le GPU et ~155 conteneurs |
| **shadow** | Un service déployé sur le cloud qui ne reçoit aucun trafic de production |
| **cutover / bascule** | Le moment où le service cloud prend les vraies données et où le jumeau VM s'arrête |
| **CR** | Cloud Run | 
| **GKE** | Kubernetes, pour les consommateurs de files et le cluster gateway |
| **consumer** | Service qui s'abonne à une file RabbitMQ. **Il n'a pas d'adresse**, personne ne l'appelle |
| **lot P1…P10** | Ordre de bascule. P1 = déjà traité, P10 = reste sur la VM. Voir l'inventaire |

## Pièges de nommage — vérifie systématiquement

Ces confusions ont déjà coûté du temps. Elles ne se devinent pas, elles se vérifient dans l'inventaire.

- **`embedding-service` ≠ `api-embedding-service`.** Le premier est un *consumer* (lot P1, GKE), le second un
  service *HTTP* (lot P4, Cloud Run). Deux services distincts, deux comportements opposés.
- **Les services `*-database-qdrant-service` écrivent dans Milvus, pas dans Qdrant.** Le nom « qdrant » est un
  héritage abandonné. Lis la configuration, jamais le nom.
- **Certains noms perdent leur suffixe `-service` en passant sur le cloud** : `prix-milvus-processor-service` →
  `prix-milvus-processor`, `graph-rag-dlq-manager-service` → `graph-rag-dlq-manager`. L'inventaire donne le nom exact.
- **Les variables `ZILLIZ_*` désignent Milvus**, pas le SaaS Zilliz Cloud (essai abandonné).
- **`template-llm-service` se désabonne volontairement de sa file entre 06h et 10h UTC** pour éviter le tarif
  double de DeepSeek. Une file sans consommateur à ces heures est **normale**, ce n'est pas une panne.

## Ce qu'on cherche dans le code

Par ordre de fréquence :

1. **URL d'un autre service en dur** : `http://<nom-de-conteneur>:<port>`. Sur la VM, Docker résout ces noms.
   Sur Cloud Run et GKE, ils n'existent plus. C'est le défaut numéro un.
2. **Port gRPC en dur**, en particulier le défaut `50051`. Quatre clients de `libs/common-utils` portent ce
   défaut alors que les vrais ports sont 50055 à 50058 — le bug est masqué tant que l'environnement surcharge.
3. **`localhost`** utilisé pour joindre un autre service. Fonctionne sur une VM partagée, jamais ailleurs.
4. **Chemin de fichier local** (`/mnt/data/...`, volume monté) : Cloud Run n'a pas de disque persistant.
5. **Variable d'environnement absente de la matrice** : soit elle est morte, soit la matrice est incomplète —
   dans les deux cas c'est à remonter.

## Comment conclure

Rends au développeur une liste courte, chaque ligne avec :

```
<fichier>:<ligne>   ce qui est en dur   ce que ça devient (ou « à décider avec le DevSecOps »)
```

Si tu ne trouves rien, dis-le franchement : beaucoup de services sont propres, en particulier les consumers du
lot P1. Un pré-contrôle vide est un résultat valide, pas un échec.

## Règles de sécurité, sans exception

- **Aucun secret en clair.** Ni dans le code, ni dans un exemple, ni dans un message. Si tu en croises un dans le
  code ou dans un log, **signale-le sans le recopier**.
- Les identifiants vivent dans **Secret Manager** et sont injectés au démarrage. La matrice donne le *nom* du
  secret, jamais sa valeur — c'est voulu.

## Les documents de ce dossier

| Fichier | Contenu |
|---|---|
| `README.md` | Point d'entrée du développeur : quoi faire, quand, où remonter |
| `guide-pre-check-service.md` | La procédure de vérification, étape par étape, avec les commandes de recherche |
| `inventaire-services-migration-par-lot.md` | Les 117 services : migré ou non, équivalent exact, lot, points de vigilance |
| `correspondance-endpoints-vm-cloud.md` | Ancienne adresse → nouvelle adresse → variable d'environnement |
| `env-migration-matrix.md` | Variables d'environnement par service, et leur origine |
| `strategie-bigbang-vs-par-lot.md` | Comparaison des deux stratégies de bascule (aide à la décision) |
