# This dictionary defines the explicit and robust mapping for the DLQ archive index.
# By defining the mapping beforehand, we prevent Elasticsearch from guessing incorrect
# data types, which is the root cause of the mapping conflict errors.

INDEX_MAPPING = {
    "mappings": {
        "properties": {
            "@timestamp": {"type": "date"},
            "service_name": {
                "type": "keyword"  # Use keyword for exact, case-sensitive matching and aggregation.
            },
            "error_reason": {
                "type": "text",  # Use text for full-text search on the error message.
                "fields": {
                    "keyword": {
                        "type": "keyword", # Use keyword sub-field for wildcard searches.
                        "ignore_above": 1024 # Ignore very long error messages for this specific field.
                    }
                }
            },
            "retry_count": {"type": "integer"},
            "original_exchange": {"type": "keyword"},
            "original_routing_key": {"type": "keyword"},
            "original_payload": {
                "type": "flattened" # The key to the solution: treats the entire payload object as a set of keywords, preventing any mapping conflicts with nested fields of varying types.
            }
        }
    }
}