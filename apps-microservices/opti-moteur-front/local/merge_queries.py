#!/usr/bin/env python3
"""Merge existing query_embeddings.json with new_queries.json."""
import json

with open("data/query_embeddings.json", "r", encoding="utf-8") as f:
    existing = json.load(f)
with open("data/new_queries.json", "r", encoding="utf-8") as f:
    new = json.load(f)

existing_texts = {item["text"] for item in existing}
merged = list(existing)
added = 0
for item in new:
    if item["text"] not in existing_texts:
        merged.append(item)
        added += 1

with open("data/query_embeddings.json", "w", encoding="utf-8") as f:
    json.dump(merged, f, ensure_ascii=False)

print(f"Avant: {len(existing)} requetes")
print(f"Ajoutees: {added}")
print(f"Total: {len(merged)} requetes")
