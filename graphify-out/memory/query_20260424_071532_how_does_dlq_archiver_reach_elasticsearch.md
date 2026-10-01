---
type: "query"
date: "2026-04-24T07:15:32.827559+00:00"
question: "How does DLQ archiver reach Elasticsearch"
contributor: "graphify"
source_nodes: ["dlq_archiver", "DLQArchiver", "get_elasticsearch_client", "es_mapping"]
---

# Q: How does DLQ archiver reach Elasticsearch

## Answer

Path: tools/requirements.txt references pika+elasticsearch [EXTRACTED]. main() in dlq_archiver.py:L287 calls DLQArchiver.start_consuming() which calls .connect() L28 -> .setup_queues() L37 -> .archive_and_ack_batch(). ES client from tools/connections.py:L36 get_elasticsearch_client(). Data contract es_mapping.py failed_messages_archive index shared with dlq_requeuer.py [INFERRED]. GAP: no explicit edge DLQArchiver.archive_and_ack_batch calls get_elasticsearch_client() - subagents missed the call wiring. Confidence high for internals AST; medium for ES client binding.

## Source Nodes

- dlq_archiver
- DLQArchiver
- get_elasticsearch_client
- es_mapping