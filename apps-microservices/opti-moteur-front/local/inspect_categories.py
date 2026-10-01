#!/usr/bin/env python3
"""Inspect categorie distribution in Typesense produits_20k collection."""
import typesense

client = typesense.Client({
    "api_key": "hp_poc_2026",
    "nodes": [{"host": "localhost", "port": "8108", "protocol": "http"}],
    "connection_timeout_seconds": 10,
})

# All categories, top 300 by frequency
res = client.multi_search.perform({
    "searches": [{
        "collection": "produits_20k",
        "q": "*",
        "facet_by": "categorie",
        "max_facet_values": 300,
        "per_page": 0,
    }]
}, {})

counts = res["results"][0]["facet_counts"][0]["counts"]

# Categories contenant armoire/pharmacie/medical/pompe/batterie
print("=== Categories pertinentes pour nos tests ===")
for item in counts:
    v = item["value"].lower()
    if any(k in v for k in ["armoire", "pharmacie", "medic", "pompe", "batterie", "lithium"]):
        print(f"  {item['count']:>4}  {item['value']}")

print(f"\n=== Total distinct categories: {len(counts)} ===")
print(f"=== Top 10 plus frequentes: ===")
for item in counts[:10]:
    print(f"  {item['count']:>5}  {item['value']}")
