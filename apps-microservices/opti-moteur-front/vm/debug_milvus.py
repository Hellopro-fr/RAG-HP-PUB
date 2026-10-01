#!/usr/bin/env python3
"""Debug : inspecte les valeurs reelles de etat, affichage, chunk_number."""
import os
from pymilvus import connections, Collection

connections.connect(
    alias="default",
    host=os.getenv("MILVUS_HOST"),
    port=os.getenv("MILVUS_PORT"),
    user=os.getenv("MILVUS_USER"),
    password=os.getenv("MILVUS_PASSWORD"),
)
col = Collection("produits_3")
col.load()

print("\n=== Sample 10 rows (chunk_number == 0) ===")
rows = col.query(
    expr="chunk_number == 0",
    output_fields=["id_produit", "etat", "affichage", "chunk_number", "categorie"],
    limit=10,
)
for r in rows:
    print(r)

print("\n=== Sample sans filtre ===")
rows = col.query(
    expr="",
    output_fields=["id_produit", "etat", "affichage", "chunk_number", "categorie"],
    limit=10,
)
for r in rows:
    print(r)

print("\n=== Distinct etat (sample 50 rows) ===")
rows = col.query(expr="", output_fields=["etat"], limit=500)
print(sorted(set(r.get("etat", "") for r in rows)))

print("\n=== Distinct affichage ===")
rows = col.query(expr="", output_fields=["affichage"], limit=500)
print(sorted(set(r.get("affichage", "") for r in rows)))

connections.disconnect("default")
