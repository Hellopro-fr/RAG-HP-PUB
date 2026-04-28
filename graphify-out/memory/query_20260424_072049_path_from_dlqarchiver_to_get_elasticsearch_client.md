---
type: "path_query"
date: "2026-04-24T07:20:49.160349+00:00"
question: "Path from DLQArchiver to get_elasticsearch_client"
contributor: "graphify"
source_nodes: ["DLQArchiver", "connect", "get_elasticsearch_client"]
---

# Q: Path from DLQArchiver to get_elasticsearch_client

## Answer

Shortest 2 hops: DLQArchiver --method [EXTRACTED]--> .connect() --calls [INFERRED]--> get_elasticsearch_client(). All 8 simple paths within cutoff 4 route through .connect(). Architectural meaning: .connect() is single hydration point for both RabbitMQ + ES clients at startup in tools/connections.py. SELF-CORRECTION: earlier DLQ->ES query incorrectly flagged edge as missing - it exists via .connect(), not via .archive_and_ack_batch().

## Source Nodes

- DLQArchiver
- connect
- get_elasticsearch_client