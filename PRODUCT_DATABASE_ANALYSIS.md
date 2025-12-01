# Analyse Complète: Product-Database-Qdrant-Service

## 1. STRUCTURE DU SERVICE

### Arborescence Complète
```
product-database-qdrant-service/
├── app/
│   ├── __init__.py
│   ├── main.py                    # Point d'entrée principal
│   ├── core/processor.py          # Logique métier insertion_data()
│   └── messaging/
│       ├── consumer.py             # Consumer RabbitMQ
│       └── publisher.py            # Publisher RabbitMQ
├── tests/
├── Dockerfile
└── requirements.txt
```

### Dépendances
- qdrant-client, pymilvus, pika, pydantic, python-dotenv

---

## 2. FLUX ARCHITECTURAL

```
RabbitMQ Exchange: produits_embedded_data_exchange
       ↓ (Routing: data.produits.ready_for_insertion)
Consumer.start_consuming()
       ↓
Processor.insertion_data()
       ↓ (CAS 1/2A/2B)
MilvusProduitsCrud ou QdrantProduitsCrud
       ↓
Publisher.publish_message()
       ↓
Webhook Service
```

---

## 3. ENDPOINTS CRÉATION/MODIFICATION

**Pas d'API REST!** Service asynchrone basé sur RabbitMQ.

Point d'entrée: Message RabbitMQ avec payload:
```json
{
  "data": [{id_produit, nom_produit, prix_ht, prix_ttc, source, text, embedding, ...}],
  "collection": "produits_3",
  "database": "milvus|qdrant",
  "origin": "bo|siteweb|api|..."
}
```

---

## 4. MODÈLES DE DONNÉES

### Milvus Collection: produits_3

Champs critiques:
- `id` (INT64, PK, AUTO_ID)
- `id_produit` (VARCHAR) ← CLE DE DEDUPLICATION
- `embedding` (FLOAT_VECTOR, 1024)
- `source` (VARCHAR) ← SOURCE (BO, SITEWEB, API)
- `nom_produit`, `id_categorie`, `prix_ht`, `prix_ttc`, `type_produit`, `text`
- `date_ajout`, `date_maj`

Index: HNSW sur embedding, Scalar sur id_produit

### Table de Correspondance: correspondance_produits_bo_milvus_3

Mappe: id_produit → id_produit_milvus (avec origin)

---

## 5. INTERACTIONS BASE DE DONNÉES

### Opérations Milvus
1. `insert_produits()` - Insert batch + sanitize
2. `update_produits()` - DELETE + INSERT (pas vrai UPDATE)
3. `get_produit(id_produit)` - Query par id_produit
4. `delete_produits_by_id_produit_and_source()` - Delete par id_produit+source

### Opérations Qdrant
1. `insert_produits()` - Upsert avec UUID
2. `get_produit(id_produit)` - Scroll avec filter
3. `update_produits()` - Non implémenté comme Milvus

---

## 6. MÉCANISMES DE PRÉVENTION DOUBLONS

### CAS 1: Produit N'EXISTE PAS (404)
```
get_produit(id_produit) → NOT FOUND
ACTION: INSERTION
- Ajoute source = origin.upper()
- Insert chunks
- Crée correspondance (Milvus)
RÉSULTAT: already_in_bdd=False, updated=False
```

### CAS 2A: Produit EXISTS, SOURCE DIFFÉRENTE
```
Condition: source_à_insérer ∉ existing_sources
ACTION: INSERT NOUVELLE SOURCE
RÉSULTAT: already_in_bdd=True, updated=False
EXEMPLE: id_produit="123" source="BO" + nouveau source="SITEWEB" = 2 sources
```

### CAS 2B: Produit EXISTS, SOURCE IDENTIQUE (MILVUS ONLY)
```
Condition: source_à_insérer ∈ existing_sources

ÉTAPE 1: Champs critiques modifiés?
  Fields: [nom_produit, id_categorie, prix_ht, prix_ttc, type_produit]
  Si ≥1 changé: UPDATE, reason="field_change: ..."
  Sinon: ÉTAPE 2

ÉTAPE 2: Similarité textuelle?
  ratio = difflib.SequenceMatcher(old_text, new_text).ratio()
  Si ratio < 0.85: UPDATE, reason="text_similarity: 0.82"
  Si ratio >= 0.85: SKIP

RÉSULTAT: already_in_bdd=True, updated=True/False
```

---

## 7. RISQUES DE DOUBLONS

| # | Risque | Probabilité | Impact | Cause |
|----|--------|-------------|--------|-------|
| 1 | Race condition GET+INSERT | MOYEN | DOUBLON | Non-atomique, pas verrou |
| 2 | Source non-normalisée | FAIBLE | AUCUN | Normalization uppercase OK |
| 3 | Source manquante | MOYEN | DOUBLON | Données migrées sans source |
| 4 | Similarité seuil trop élevé | MOYEN | CONTENU PÉRIMÉ | Seuil 0.85 trop haut |
| 5 | Non-idempotence | MOYEN | INCOHÉRENCE | Rejeu messages non dédetecté |
| 6 | Update race condition | FAIBLE | TEMP DOUBLON | DELETE during GET |
| 7 | Correspondance non sync | FAIBLE | INCONSISTANCE | INSERT correspondance échoue |

### Détails Risque 1: Race Condition
```
T0: Thread A: get_produit("123") → NOT FOUND
T1: Thread B: get_produit("123") → NOT FOUND
T2: Thread A: insert() → Succès
T3: Thread B: insert() → DOUBLON!
```

### Détails Risque 3: Source Manquante
```
Produit EXISTANT: id_produit="123", source=""
Nouveau: id_produit="123", origin="BO"
Check: "BO" not in [""] → TRUE
→ Traite comme SOURCE DIFFÉRENTE (INSERT)
→ Crée doublon avec sources différentes!
```

### Détails Risque 4: Similarité Faible
```
Old: "Laptop HP 15" + "Best laptop for business..."
New: "Laptop HP 15" + "Best laptop for professionals..."
Champs critiques: IDENTIQUES
Similarité: 0.88 >= 0.85
→ SKIP (contenu pas à jour!)
```

---

## 8. FICHIERS CLÉS (CHEMINS ABSOLUS)

### Service Principal
```
c:/Users/USER/Documents/VSCode/RAG-HP-PUB/apps-microservices/product-database-qdrant-service/
  ├── app/main.py
  ├── app/core/processor.py (CRITIQUE - insertion_data())
  ├── app/messaging/consumer.py
  └── app/messaging/publisher.py
```

### Librairies CRUD
```
c:/Users/USER/Documents/VSCode/RAG-HP-PUB/libs/common-utils/src/common_utils/database/
  ├── MilvusProduitCrud.py (insert, update, get, delete_by_id_and_source)
  ├── QdrantProduitCrud.py (insert, get)
  └── MilvusProduitInserer.py (correspondance table)
```

---

## 9. RÉSUMÉ ENDPOINTS INSERTION/MODIFICATION

### ÉTAPE 1: Consumer reçoit message RabbitMQ
- Exchange: `produits_embedded_data_exchange`
- Queue: `insertion_produits_queue`
- Routing key: `data.produits.ready_for_insertion`

### ÉTAPE 2: Processor.insertion_data()
- get_produit(id_produit) pour vérification
- Branche CAS 1/2A/2B
- Appel CRUD insert/update

### ÉTAPE 3: CRUD Operations
- Milvus: insert_produits() ou update_produits() (DELETE+INSERT)
- Qdrant: insert_produits() (upsert)

### ÉTAPE 4: Publisher
- Envoie résultat sur exchange: `inserted_data_exchange`
- Routing key: `data.ready_for_webhook`

---

## 10. RECOMMANDATIONS

### P0 - CRITIQUE
1. Ajouter verrou distribué (Redis) sur id_produit avant GET+INSERT
2. Deduplication RabbitMQ: message_id + TTL 24h
3. Valider source ∈ [BO, SITEWEB, API, ...], rejeter vide

### P1 - IMPORTANT
4. Réduire seuil similarité: 0.85 → 0.75-0.80
5. Implémenter vrai UPDATE pour Qdrant
6. Idempotence: UUID message + processed table

### P2 - BON À FAIRE
7. Monitoring: doublon rate, update ratio
8. Audit trail: log CAS 1/2A/2B avec raisons
9. Correspondance: exponential backoff retry
10. Tests intégration: race conditions

---
