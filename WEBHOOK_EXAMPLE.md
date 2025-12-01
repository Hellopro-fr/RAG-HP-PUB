# 📨 EXEMPLE COMPLET - WEBHOOK PRODUIT

Ce document explique **exactement** ce qui est envoyé par le webhook-service et comment vérifier la signature.

---

## 🔄 FLUX COMPLET

```
1. Product-Database-Service → RabbitMQ
2. RabbitMQ → Webhook-Service
3. Webhook-Service → Votre URL externe (webhook.site)
```

---

## 📦 EXEMPLE 1 : DONNÉES PRODUIT ENVOYÉES

### Message original dans RabbitMQ

```json
{
  "database": "milvus",
  "collection": "produits",
  "data": {
    "ids": "450123456,450123457,450123458",
    "status": "success"
  },
  "id_produit": "PROD-HP-12345",
  "already_in_bdd": false,
  "updated": false,
  "origin": "bo"
}
```

### Ce que le webhook-service envoie à votre URL

**URL de destination** : `https://webhook.site/c93aedc0-90b3-4f54-bba5-05ed43c3c482`

#### Headers HTTP :
```http
POST /c93aedc0-90b3-4f54-bba5-05ed43c3c482 HTTP/1.1
Host: webhook.site
Content-Type: application/json
X-Webhook-Signature: 8f3d9a7b2c1e5f4a6d8b9c0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a
Content-Length: 186
User-Agent: python-requests/2.31.0
Accept-Encoding: gzip, deflate
Accept: */*
Connection: keep-alive
```

#### Body (JSON compact, sans espaces) :
```json
{"database":"milvus","collection":"produits","data":{"ids":"450123456,450123457,450123458","status":"success"},"id_produit":"PROD-HP-12345","already_in_bdd":false,"updated":false,"origin":"bo"}
```

**⚠️ IMPORTANT** : Le JSON est **sans espaces ni retours à la ligne** pour garantir que la signature reste identique.

---

## 🔐 COMMENT FONCTIONNE LA SIGNATURE (X-Webhook-Signature)

### Étape 1 : Configuration de la clé secrète

Dans votre fichier `.env` :
```bash
KEY_WEBHOOK=mon_super_secret_key_12345
```

### Étape 2 : Calcul de la signature côté webhook-service

```python
import hmac
import hashlib
import json

# 1. Les données à envoyer
payload = {
    "database": "milvus",
    "collection": "produits",
    "data": {
        "ids": "450123456,450123457,450123458",
        "status": "success"
    },
    "id_produit": "PROD-HP-12345",
    "already_in_bdd": False,
    "updated": False,
    "origin": "bo"
}

# 2. Conversion en JSON compact (sans espaces)
payload_body = json.dumps(payload, separators=(',', ':')).encode('utf-8')
# Résultat: b'{"database":"milvus","collection":"produits",...}'

# 3. Calcul de la signature HMAC-SHA256
webhook_key = "mon_super_secret_key_12345"
signature = hmac.new(
    webhook_key.encode('utf-8'),  # Clé secrète
    payload_body,                  # Message à signer
    hashlib.sha256                 # Algorithme
).hexdigest()

# Résultat: "8f3d9a7b2c1e5f4a6d8b9c0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a"
```

### Étape 3 : Envoi du webhook

```http
POST https://webhook.site/c93aedc0-90b3-4f54-bba5-05ed43c3c482
Content-Type: application/json
X-Webhook-Signature: 8f3d9a7b2c1e5f4a6d8b9c0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a

{"database":"milvus","collection":"produits",...}
```

---

## 🔍 VÉRIFICATION DE LA SIGNATURE (CÔTÉ RÉCEPTION)

### Pourquoi vérifier la signature ?

La signature garantit que :
1. ✅ Le message vient bien de votre système (authentification)
2. ✅ Le message n'a pas été modifié en transit (intégrité)
3. ✅ Ce n'est pas un attaquant qui envoie de fausses données

### Code Python pour vérifier (côté serveur qui reçoit le webhook)

```python
import hmac
import hashlib
from flask import Flask, request, jsonify

app = Flask(__name__)

# La même clé secrète que dans votre .env
WEBHOOK_SECRET_KEY = "mon_super_secret_key_12345"

@app.route('/webhook', methods=['POST'])
def receive_webhook():
    # 1. Récupérer la signature envoyée
    received_signature = request.headers.get('X-Webhook-Signature')

    if not received_signature:
        return jsonify({"error": "Missing signature"}), 401

    # 2. Récupérer le body brut (bytes)
    payload_body = request.get_data()

    # 3. Recalculer la signature avec la même clé
    expected_signature = hmac.new(
        WEBHOOK_SECRET_KEY.encode('utf-8'),
        payload_body,
        hashlib.sha256
    ).hexdigest()

    # 4. Comparer les signatures (timing-safe comparison)
    if not hmac.compare_digest(received_signature, expected_signature):
        return jsonify({"error": "Invalid signature"}), 403

    # 5. Si signature valide, traiter les données
    data = request.get_json()
    print(f"✅ Webhook valide reçu pour produit: {data.get('id_produit')}")

    # Votre logique métier ici
    # ...

    return jsonify({"status": "success"}), 200

if __name__ == '__main__':
    app.run(port=5000)
```

---

## 📊 EXEMPLE 2 : PRODUIT AVEC MISE À JOUR

### Scénario : Un produit existant est mis à jour

```json
{
  "database": "milvus",
  "collection": "produits",
  "data": {
    "ids": "450123459,450123460,450123461",
    "status": "success"
  },
  "id_produit": "PROD-HP-12345",
  "already_in_bdd": true,
  "updated": true,
  "update_reason": "field_change: prix_ht, prix_ttc",
  "origin": "bo"
}
```

**Champs spécifiques à la mise à jour :**
- `already_in_bdd`: `true` (produit existait déjà)
- `updated`: `true` (mise à jour effectuée)
- `update_reason`: Raison de la mise à jour
  - `"field_change: prix_ht, prix_ttc"` → Champs critiques modifiés
  - `"text_similarity: 0.72"` → Similarité text < 0.85

---

## 📋 EXEMPLE 3 : DONNÉES D'UN ÉCHANGE

### Message pour un échange

```json
{
  "database": "milvus",
  "collection": "echanges",
  "data": {
    "ids": "789456123,789456124",
    "status": "success"
  },
  "conversation_id": "REQ-2024-001_FOURN-HP-123",
  "already_in_bdd": false,
  "updated": false
}
```

**URL de destination** : `https://webhook.site/44bd6be7-e2b2-42eb-bd04-7b5d27761645`

---

## 🧪 TESTER AVEC WEBHOOK.SITE

### Étape 1 : Voir vos webhooks en temps réel

1. Aller sur [webhook.site](https://webhook.site)
2. Récupérer votre URL unique (ex: `https://webhook.site/c93aedc0-90b3-4f54-bba5-05ed43c3c482`)
3. Configurer cette URL dans [CollectionWebhook.py](libs/common-utils/src/common_utils/autres/CollectionWebhook.py)

### Étape 2 : Ce que vous verrez sur webhook.site

```
📨 Request received at 2025-01-15 14:23:45

Method: POST
URL: /c93aedc0-90b3-4f54-bba5-05ed43c3c482

Headers:
  Content-Type: application/json
  X-Webhook-Signature: 8f3d9a7b2c1e5f4a6d8b9c0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a
  Content-Length: 186

Body:
{
  "database": "milvus",
  "collection": "produits",
  "data": {
    "ids": "450123456,450123457,450123458",
    "status": "success"
  },
  "id_produit": "PROD-HP-12345",
  "already_in_bdd": false,
  "updated": false,
  "origin": "bo"
}
```

### Étape 3 : Vérifier la signature manuellement

#### En Python (dans la console Python de webhook.site) :

```python
import hmac
import hashlib

# Le body exactement comme reçu (sans modification)
body = b'{"database":"milvus","collection":"produits","data":{"ids":"450123456,450123457,450123458","status":"success"},"id_produit":"PROD-HP-12345","already_in_bdd":false,"updated":false,"origin":"bo"}'

# Votre clé secrète
key = "mon_super_secret_key_12345"

# Calcul de la signature
signature = hmac.new(key.encode(), body, hashlib.sha256).hexdigest()
print(signature)
# Doit correspondre au header X-Webhook-Signature
```

#### Avec curl :

```bash
# Simuler l'envoi d'un webhook
curl -X POST https://webhook.site/c93aedc0-90b3-4f54-bba5-05ed43c3c482 \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Signature: 8f3d9a7b2c1e5f4a6d8b9c0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a" \
  -d '{"database":"milvus","collection":"produits","data":{"ids":"450123456,450123457,450123458","status":"success"},"id_produit":"PROD-HP-12345","already_in_bdd":false,"updated":false,"origin":"bo"}'
```

---

## 🔑 DIFFÉRENTS SCÉNARIOS DE KEY_WEBHOOK

### Scénario 1 : KEY_WEBHOOK manquante

```bash
# .env (vide ou KEY_WEBHOOK non définie)
```

**Résultat :**
```
2025-01-15 14:23:45 - webhook_service.main - CRITICAL - ❌ Variables d'environnement manquantes:
2025-01-15 14:23:45 - webhook_service.main - CRITICAL -   - KEY_WEBHOOK: Clé secrète pour signer les webhooks
2025-01-15 14:23:45 - webhook_service.main - CRITICAL -
💡 Veuillez définir ces variables dans votre fichier .env ou variables d'environnement.
   Exemple .env:
   RABBITMQ_URL=amqp://user:password@localhost:5672/
   KEY_WEBHOOK=your_secret_webhook_key_here

❌ Arrêt du service: configuration invalide
```

### Scénario 2 : KEY_WEBHOOK correcte

```bash
# .env
KEY_WEBHOOK=mon_super_secret_key_12345
RABBITMQ_URL=amqp://user:password@rabbitmq:5672/
```

**Résultat :**
```
2025-01-15 14:23:45 - webhook_service.main - INFO - 🚀 Démarrage du webhook-service...
2025-01-15 14:23:45 - webhook_service.main - INFO - 🔌 Tentative de connexion à RabbitMQ...
2025-01-15 14:23:46 - webhook_service.main - INFO - ✅ webhook-service: Connexion à RabbitMQ établie avec succès
2025-01-15 14:23:46 - webhook_service.messaging.consumer - INFO - ✅ Consumer webhook-service initialisé avec succès
2025-01-15 14:23:46 - webhook_service.main - INFO - 🎧 webhook-service: Prêt à traiter les webhooks
```

---

## 📈 EXEMPLE COMPLET DE LOGS

### Logs côté webhook-service lors de l'envoi

```
2025-01-15 14:25:30 - webhook_service.messaging.consumer - INFO - 📥 Message reçu pour collection: produits
2025-01-15 14:25:30 - webhook_service.core.processor - INFO - Traitement du webhook pour la collection: produits
2025-01-15 14:25:30 - webhook_service.core.processor - INFO - Tentative 1/3 d'envoi du webhook vers https://webhook.site/c93aedc0-90b3-4f54-bba5-05ed43c3c482
2025-01-15 14:25:31 - webhook_service.core.processor - INFO - ✅ Webhook envoyé avec succès à https://webhook.site/c93aedc0-90b3-4f54-bba5-05ed43c3c482 (statut: 200, tentative: 1)
2025-01-15 14:25:31 - webhook_service.messaging.consumer - INFO - ✅ Message traité et acquitté (delivery_tag: 1)
```

### Logs en cas d'erreur avec retry

```
2025-01-15 14:27:10 - webhook_service.messaging.consumer - INFO - 📥 Message reçu pour collection: produits
2025-01-15 14:27:10 - webhook_service.core.processor - INFO - Traitement du webhook pour la collection: produits
2025-01-15 14:27:10 - webhook_service.core.processor - INFO - Tentative 1/3 d'envoi du webhook vers https://webhook.site/c93aedc0-90b3-4f54-bba5-05ed43c3c482
2025-01-15 14:27:20 - webhook_service.core.processor - WARNING - ⏱️ Timeout lors de l'envoi du webhook (tentative 1/3): HTTPSConnectionPool(host='webhook.site', port=443): Read timed out. (read timeout=10)
2025-01-15 14:27:20 - webhook_service.core.processor - INFO - ⏳ Attente de 1s avant la prochaine tentative...
2025-01-15 14:27:21 - webhook_service.core.processor - INFO - Tentative 2/3 d'envoi du webhook vers https://webhook.site/c93aedc0-90b3-4f54-bba5-05ed43c3c482
2025-01-15 14:27:22 - webhook_service.core.processor - INFO - ✅ Webhook envoyé avec succès à https://webhook.site/c93aedc0-90b3-4f54-bba5-05ed43c3c482 (statut: 200, tentative: 2)
2025-01-15 14:27:22 - webhook_service.messaging.consumer - INFO - ✅ Message traité et acquitté (delivery_tag: 1)
```

---

## 🎯 RÉSUMÉ

### Ce qui est envoyé :
- ✅ JSON compact (sans espaces)
- ✅ Header `Content-Type: application/json`
- ✅ Header `X-Webhook-Signature` avec HMAC-SHA256

### Ce qui garantit la sécurité :
- 🔐 KEY_WEBHOOK (clé secrète partagée)
- 🔐 HMAC-SHA256 (algorithme cryptographique)
- 🔐 Signature hexadécimale (64 caractères)

### Comment vérifier :
1. Recalculer la signature avec la même clé
2. Comparer avec `X-Webhook-Signature`
3. Si identique → webhook valide ✅
4. Si différent → webhook invalide ❌

---

## 🔗 URLS DE WEBHOOK PAR COLLECTION

| Collection | URL webhook.site |
|------------|------------------|
| `produits` | `https://webhook.site/c93aedc0-90b3-4f54-bba5-05ed43c3c482` |
| `devis` | `https://webhook.site/44bd6be7-e2b2-42eb-bd04-7b5d27761645` |
| `categories` | `https://webhook.site/c9e32e3d-348e-4df4-9584-f0848d23900b` |
| `echanges` | `https://webhook.site/44bd6be7-e2b2-42eb-bd04-7b5d27761645` |
| `fournisseurs` | `https://webhook.site/c9e32e3d-348e-4df4-9584-f0848d23900b` |
| `siteweb` | `https://webhook.site/44bd6be7-e2b2-42eb-bd04-7b5d27761645` |

Configuration : [CollectionWebhook.py](../libs/common-utils/src/common_utils/autres/CollectionWebhook.py)

---

## 📝 EXEMPLE DE .env COMPLET

```bash
# Configuration RabbitMQ
RABBITMQ_URL=amqp://user:password@rabbitmq:5672/

# Clé secrète pour signer les webhooks (OBLIGATOIRE)
KEY_WEBHOOK=mon_super_secret_key_12345_changez_moi_en_production

# Optionnel : Level de logging
LOG_LEVEL=INFO
```

**⚠️ IMPORTANT EN PRODUCTION :**
- Utiliser une clé forte (minimum 32 caractères aléatoires)
- Ne JAMAIS commiter la clé dans Git
- Utiliser un gestionnaire de secrets (AWS Secrets Manager, etc.)

---

## 🧪 SCRIPT DE TEST COMPLET

```python
#!/usr/bin/env python3
"""
Script de test pour vérifier l'envoi et la validation des webhooks
"""
import hmac
import hashlib
import json
import requests

# Configuration
WEBHOOK_URL = "https://webhook.site/c93aedc0-90b3-4f54-bba5-05ed43c3c482"
WEBHOOK_KEY = "mon_super_secret_key_12345"

# Données de test
payload = {
    "database": "milvus",
    "collection": "produits",
    "data": {
        "ids": "450123456,450123457",
        "status": "success"
    },
    "id_produit": "PROD-TEST-001",
    "already_in_bdd": False,
    "updated": False,
    "origin": "test"
}

# Conversion en JSON compact
payload_body = json.dumps(payload, separators=(',', ':')).encode('utf-8')

# Calcul de la signature
signature = hmac.new(
    WEBHOOK_KEY.encode('utf-8'),
    payload_body,
    hashlib.sha256
).hexdigest()

# Headers
headers = {
    'Content-Type': 'application/json',
    'X-Webhook-Signature': signature
}

# Envoi
print("📤 Envoi du webhook de test...")
print(f"URL: {WEBHOOK_URL}")
print(f"Signature: {signature}")
print(f"Payload: {payload_body.decode('utf-8')}")
print()

response = requests.post(WEBHOOK_URL, data=payload_body, headers=headers, timeout=10)

print(f"✅ Réponse reçue: {response.status_code}")
print(f"Body: {response.text[:200]}")
```

**Exécution :**
```bash
python test_webhook.py
```

---

**Date de création** : 2025-01-15
**Auteur** : Claude (Assistant IA)
**Version** : 1.0
