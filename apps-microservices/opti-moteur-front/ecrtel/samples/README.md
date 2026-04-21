# Samples — Sortie de `build_categories_from_roots.php`

Échantillon généré à partir des sections HelloPro **Fabrication et processus**
(id=1000006) et **Santé** (id=2000405) via le script PHP :

```bash
php apps-microservices/opti-moteur-front/ecrtel/build_categories_from_roots.php 1000006 2000405
```

## Fichiers

| Fichier | Usage |
|---|---|
| `categories_from_roots.csv` | Vue complète (id_rubrique, nom, type, depth, parent, nb_produits) — pour review Excel |
| `categories_from_roots.txt` | Liste brute des noms — input direct pour `CATEGORIES_FILE=` de `ingest_by_categories.py` |

## Contenu

- **671 catégories** au total (depth 0 à 3)
- **380 avec produits** (nb_produits > 0), ~28 k produits cumulés (`nombre_produits_rubrique` MySQL)
- Couvre : armoires, pompes, batteries, matériels médicaux, chariots, compresseurs,
  fraiseuses, rayonnages, outillage, équipements sanitaires, etc.

## Usage sur VM

```bash
# Ingestion directe via le fichier .txt
MILVUS_HOST="$ZILLIZ_URI" MILVUS_PORT="$ZILLIZ_PORT" \
MILVUS_USER="$ZILLIZ_USER" MILVUS_PASSWORD="$ZILLIZ_PASSWORD" \
CATEGORIES_FILE=apps-microservices/opti-moteur-front/ecrtel/samples/categories_from_roots.txt \
TS_COLLECTION=produits_scale \
EXTRA_FILTER='etat in ["Client","Prospect"] or (etat == "Pause" and affichage == "Complet")' \
python3 apps-microservices/opti-moteur-front/vm/ingest_by_categories.py
```
