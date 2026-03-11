# This dictionary defines the explicit and robust mapping for the DLQ archive index.
# By defining the mapping beforehand, we prevent Elasticsearch from guessing incorrect
# data types, which is the root cause of the mapping conflict errors.

INDEX_MAPPING = {
    "mappings": {
        "dynamic_templates": [
            {
                "long_text_fields": {
                    "path_match": "original_payload.*.text",
                    "match_mapping_type": "string",
                    "mapping": {
                        "type": "text",
                        "index": False
                    }
                }
            }
        ],
        "properties": {
            "@timestamp": {"type": "date"},
            "_raw_embedding_data": {
                "type": "keyword",
                "index": False,
                "doc_values": False
            },
            "payload_conflict_fallback": {
                "type": "keyword",
                "index": False,
                "doc_values": False
            },
            "service_name": {
                "type": "keyword"
            },
            "error_reason": {
                "type": "text",
                "fields": {
                    "keyword": {
                        "type": "keyword",
                        "ignore_above": 1024
                    }
                }
            },
            "retry_count": {"type": "integer"},
            "original_exchange": {"type": "keyword"},
            "original_routing_key": {"type": "keyword"},
            "original_payload": {
                "type": "object",
                "dynamic": True
            }
        }
    }
}