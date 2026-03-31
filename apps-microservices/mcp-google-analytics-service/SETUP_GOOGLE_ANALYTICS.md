# Configuration du compte de service Google Analytics

Guide complet pour configurer l'accès en lecture seule à Google Analytics 4 via un compte de service GCP.

## Prérequis

- Un compte Google Cloud Platform (GCP)
- Un projet GCP existant ou les droits pour en créer un
- Une propriété Google Analytics 4 (GA4)
- Le CLI `gcloud` installé ([guide d'installation](https://cloud.google.com/sdk/docs/install))

## Étape 1 — Créer un projet GCP (si nécessaire)

```bash
gcloud projects create MON_PROJET_ID --name="Mon Projet Analytics"
gcloud config set project MON_PROJET_ID
```

## Étape 2 — Activer les APIs Google Analytics

Deux APIs sont nécessaires :

```bash
gcloud services enable analyticsadmin.googleapis.com --project=MON_PROJET_ID
gcloud services enable analyticsdata.googleapis.com --project=MON_PROJET_ID
```

Ou via la console GCP :
1. Aller sur [APIs & Services > Bibliothèque](https://console.cloud.google.com/apis/library)
2. Rechercher et activer **Google Analytics Admin API**
3. Rechercher et activer **Google Analytics Data API**

## Étape 3 — Créer le compte de service

```bash
gcloud iam service-accounts create ga-mcp-reader \
  --display-name="GA MCP Reader" \
  --project=MON_PROJET_ID
```

Vérifier la création :

```bash
gcloud iam service-accounts list --project=MON_PROJET_ID
```

L'email du compte de service sera : `ga-mcp-reader@MON_PROJET_ID.iam.gserviceaccount.com`

## Étape 4 — Générer la clé d'authentification

### Option A — Clé JSON (recommandé)

```bash
mkdir -p secrets
gcloud iam service-accounts keys create ./secrets/gcp-analytics-credentials.json \
  --iam-account=ga-mcp-reader@MON_PROJET_ID.iam.gserviceaccount.com
```

### Option B — Clé P12

```bash
mkdir -p secrets
gcloud iam service-accounts keys create ./secrets/gcp-analytics-credentials.p12 \
  --key-file-type=p12 \
  --iam-account=ga-mcp-reader@MON_PROJET_ID.iam.gserviceaccount.com
```

> Le mot de passe par défaut des clés P12 est `notasecret`.

## Étape 5 — Accorder l'accès en lecture dans Google Analytics

Le compte de service doit être ajouté comme **lecteur** dans l'interface Google Analytics :

1. Ouvrir [analytics.google.com](https://analytics.google.com)
2. Cliquer sur **Administration** (icône engrenage en bas à gauche)
3. Choisir le niveau d'accès souhaité :

### Accès à une seule propriété

4. Sous la propriété GA4 cible, cliquer sur **Gestion des accès à la propriété**
5. Cliquer sur **+** puis **Ajouter des utilisateurs**
6. Saisir l'email du compte de service :
   ```
   ga-mcp-reader@MON_PROJET_ID.iam.gserviceaccount.com
   ```
7. Sélectionner le rôle **Lecteur**
8. Cliquer sur **Ajouter**

### Accès à toutes les propriétés d'un compte

4. Au niveau du compte GA, cliquer sur **Gestion des accès au compte**
5. Suivre les mêmes étapes 5 à 8 ci-dessus

> Le rôle **Lecteur** permet uniquement de consulter les rapports et les données. Il ne permet pas de modifier la configuration, les audiences, les conversions ou les événements.

## Étape 6 — Configurer les variables d'environnement

Ajouter dans le fichier `.env` à la racine du projet :

### Avec une clé JSON

```env
GOOGLE_ANALYTICS_PROJECT_ID=MON_PROJET_ID
GOOGLE_ANALYTICS_CREDENTIALS_PATH=./secrets/gcp-analytics-credentials.json
GOOGLE_CREDENTIALS_TYPE=json
```

### Avec une clé P12

```env
GOOGLE_ANALYTICS_PROJECT_ID=MON_PROJET_ID
GOOGLE_ANALYTICS_P12_PATH=./secrets/gcp-analytics-credentials.p12
GOOGLE_CREDENTIALS_TYPE=p12
GOOGLE_SERVICE_ACCOUNT_EMAIL=ga-mcp-reader@MON_PROJET_ID.iam.gserviceaccount.com
GOOGLE_P12_PASSWORD=notasecret
```

## Étape 7 — Lancer le service

```bash
docker compose --profile mcp build mcp-google-analytics-service
docker compose --profile mcp up mcp-google-analytics-service
```

## Étape 8 — Vérifier le fonctionnement

### Vérifier que le service répond

```bash
curl -s -X POST http://localhost:8583/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

Résultat attendu : une liste de 7 outils (`get_account_summaries`, `run_report`, etc.)

### Vérifier l'accès aux données GA

```bash
curl -s -X POST http://localhost:8583/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"get_account_summaries","arguments":{}}}' \
  | python3 -m json.tool
```

Résultat attendu : la liste des comptes et propriétés GA4 accessibles par le compte de service.

## Dépannage

| Problème | Cause probable | Solution |
|---|---|---|
| `tools/list` retourne une liste vide | Le service n'a pas démarré correctement | Vérifier les logs : `docker compose logs mcp-google-analytics-service` |
| `PERMISSION_DENIED` | Le compte de service n'a pas accès à la propriété GA4 | Refaire l'étape 5 |
| `API not enabled` | Les APIs ne sont pas activées sur le projet GCP | Refaire l'étape 2 |
| `Could not load credentials` | Le fichier de clé est introuvable ou mal monté | Vérifier le chemin dans `.env` et que le fichier existe |
| `Invalid P12 key` | Mot de passe P12 incorrect | Vérifier `GOOGLE_P12_PASSWORD` (défaut : `notasecret`) |

## Sécurité

- Ne **jamais** commiter les fichiers de clé (`secrets/`) dans git
- Vérifier que `secrets/` est bien dans le `.gitignore`
- Limiter l'accès au rôle **Lecteur** uniquement
- Effectuer une rotation des clés régulièrement via :
  ```bash
  # Lister les clés existantes
  gcloud iam service-accounts keys list \
    --iam-account=ga-mcp-reader@MON_PROJET_ID.iam.gserviceaccount.com

  # Supprimer une ancienne clé
  gcloud iam service-accounts keys delete KEY_ID \
    --iam-account=ga-mcp-reader@MON_PROJET_ID.iam.gserviceaccount.com

  # Générer une nouvelle clé
  gcloud iam service-accounts keys create ./secrets/gcp-analytics-credentials.json \
    --iam-account=ga-mcp-reader@MON_PROJET_ID.iam.gserviceaccount.com
  ```