import os
from elasticsearch import AsyncElasticsearch
from functools import lru_cache
from typing import List, Dict, Any, Tuple

# Read connection details from environment variables
ELASTICSEARCH_URL = os.environ.get("ELASTICSEARCH_URL", "http://localhost:9200")
ES_USERNAME = os.environ.get("ES_USERNAME")
ES_PASSWORD = os.environ.get("ES_PASSWORD")

ELASTIC_INDEX_NAME = "failed_messages_archive"

class ElasticsearchClient:
    def __init__(self, client: AsyncElasticsearch):
        self.client = client

    async def get_dashboard_stats(self, filters: Dict = None) -> Dict[str, Any]:
        """Runs aggregations for the dashboard, focusing only on 'New' messages."""
        # This is the base filter for the entire dashboard: only show actionable "New" messages.
        query = {
            "bool": {
                "must": [],
                "must_not": [
                    {"exists": {"field": "status"}},
                    {"exists": {"field": "requeued_at"}}
                ]
            }
        }

        if filters:
            if filters.get("date_start") or filters.get("date_end"):
                time_range = {}
                if filters.get("date_start"):
                    time_range["gte"] = filters["date_start"]
                if filters.get("date_end"):
                    time_range["lte"] = filters["date_end"]
                query["bool"]["must"].append({"range": {"@timestamp": time_range}})

        body = {
            "size": 0,
            "query": query,
            "aggs": {
                "by_service": {"terms": {"field": "service_name", "size": 100}},
                "by_error": {"terms": {"field": "error_reason.keyword", "size": 10}},
                "over_time": {
                    "date_histogram": {
                        "field": "@timestamp",
                        "fixed_interval": "1h",
                        "min_doc_count": 0
                    }
                }
            }
        }
        response = await self.client.search(index=ELASTIC_INDEX_NAME, body=body, track_total_hits=True)
        aggs = response['aggregations']
        pending_count = response['hits']['total']['value']
        
        return {
            "pending_count": pending_count,
            "by_service": aggs['by_service']['buckets'],
            "by_error": aggs['by_error']['buckets'],
            "over_time": aggs['over_time']['buckets']
        }

    def _build_query(self, filters: Dict[str, Any], search_term: str) -> Dict[str, Any]:
        """Helper to construct the ES query DSL."""
        query = {"bool": {"must": [], "must_not": []}}
        
        if search_term:
            query["bool"]["must"].append({
                "query_string": {
                    "query": f"*{search_term}*",
                    "fields": ["error_reason", "original_payload.*", "service_name"],
                    "lenient": True
                }
            })

        if filters:
            if filters.get("date_start") or filters.get("date_end"):
                time_range = {}
                if filters.get("date_start"):
                    time_range["gte"] = filters["date_start"]
                if filters.get("date_end"):
                    time_range["lte"] = filters["date_end"]
                query["bool"]["must"].append({"range": {"@timestamp": time_range}})
            
            service_names = filters.get("service_names")
            if service_names and isinstance(service_names, list) and len(service_names) > 0:
                query["bool"]["must"].append({"terms": {"service_name": service_names}})

            status_filter = filters.get("status")
            if status_filter and isinstance(status_filter, list) and len(status_filter) > 0:
                status_should_clauses = []
                regular_statuses = []

                for status in status_filter:
                    if status == "New":
                        status_should_clauses.append({
                            "bool": {
                                "must_not": [
                                    {"exists": {"field": "status"}},
                                    {"exists": {"field": "requeued_at"}}
                                ]
                            }
                        })
                    elif status == "Re-queued (Legacy)":
                        status_should_clauses.append({
                            "bool": {
                                "must": [{"exists": {"field": "requeued_at"}}],
                                "must_not": [{"exists": {"field": "status"}}]
                            }
                        })
                    else:
                        regular_statuses.append(status)
                
                if regular_statuses:
                    status_should_clauses.append({"terms": {"status.keyword": regular_statuses}})

                if status_should_clauses:
                    query["bool"]["must"].append({
                        "bool": {
                            "should": status_should_clauses,
                            "minimum_should_match": 1
                        }
                    })

        return query

    async def search_messages(self, filters: Dict, search_term: str, page: int, page_size: int) -> Tuple[List[Dict], int]:
        """Performs a paginated search for messages, excluding the large payload."""
        query = self._build_query(filters, search_term)
        response = await self.client.search(
            index=ELASTIC_INDEX_NAME,
            body={
                "query": query,
                "from": (page - 1) * page_size,
                "size": page_size,
                "sort": [{"@timestamp": "desc"}],
                "_source": {"excludes": ["original_payload"]}
            },
            track_total_hits=True
        )
        hits = [hit for hit in response['hits']['hits']]
        total = response['hits']['total']['value']
        
        # Transform data for consistent presentation in the UI
        for hit in hits:
            source = hit['_source']
            if 'status' not in source and 'requeued_at' in source:
                source['status'] = 'Re-queued (Legacy)'
                
        return hits, total

    async def get_grouped_errors(self, filters: Dict, search_term: str) -> List[Dict]:
        """Gets error groups by service and reason."""
        query = self._build_query(filters, search_term)
        body = {
            "size": 0,
            "query": query,
            "aggs": {
                "grouped_errors": {
                    "terms": {"field": "service_name.keyword", "size": 100},
                    "aggs": {
                        "reasons": {
                            "terms": {"field": "error_reason.keyword", "size": 20},
                            "aggs": {
                                "latest_occurrence": {"max": {"field": "@timestamp"}}
                            }
                        }
                    }
                }
            }
        }
        response = await self.client.search(index=ELASTIC_INDEX_NAME, body=body)
        return response['aggregations']['grouped_errors']['buckets']
    
    async def get_message(self, message_id: str) -> Dict:
        """Gets the full document for a single message, including the payload."""
        try:
            response = await self.client.get(index=ELASTIC_INDEX_NAME, id=message_id)
            return response
        except:
            return None
            
    async def get_messages_bulk(self, message_ids: List[str]) -> List[Dict]:
        if not message_ids:
            return []
        response = await self.client.mget(index=ELASTIC_INDEX_NAME, body={"ids": message_ids})
        return [doc for doc in response['docs'] if doc['found']]

    async def update_message_status(self, message_id: str, status: str):
        await self.client.update(
            index=ELASTIC_INDEX_NAME,
            id=message_id,
            body={
                "doc": {
                    "status": status,
                    "status_updated_at": "now/s"
                }
            }
        )

    async def update_message_status_bulk(self, message_ids: List[str], status: str) -> int:
        if not message_ids:
            return 0
        
        actions = []
        for msg_id in message_ids:
            actions.append({"update": {"_index": ELASTIC_INDEX_NAME, "_id": msg_id}})
            actions.append({"doc": {"status": status, "status_updated_at": "now/s"}})
            
        response = await self.client.bulk(body=actions)
        return len([item for item in response['items'] if not item['update'].get('error')])
        
    async def scroll_messages(self, filters: Dict, search_term: str):
        """Scrolls through all messages matching a query, yielding them in batches."""
        query = self._build_query(filters, search_term)
        pit = await self.client.open_point_in_time(index=ELASTIC_INDEX_NAME, keep_alive="1m")
        
        body = {
            "size": 100,
            "query": query,
            "sort": [{"@timestamp": "asc"}],
            "pit": {"id": pit['id'], "keep_alive": "1m"}
        }
        
        try:
            while True:
                response = await self.client.search(body=body)
                hits = response['hits']['hits']
                if not hits:
                    break
                
                yield hits
                
                body['pit']['id'] = response['pit_id']
                if 'sort' in hits[-1]:
                    body['search_after'] = hits[-1]['sort']
                
        finally:
            await self.client.close_point_in_time(body={"id": pit['id']})

    async def get_history(self, page: int, page_size: int) -> Tuple[List[Dict], int]:
        """Gets messages that have been actioned upon."""
        query = {"bool": {"must": [{"exists": {"field": "status"}}]}}
        response = await self.client.search(
            index=ELASTIC_INDEX_NAME,
            body={
                "query": query,
                "from": (page - 1) * page_size,
                "size": page_size,
                "sort": [{"status_updated_at": "desc"}],
            }
        )
        hits = [hit for hit in response['hits']['hits']]
        total = response['hits']['total']['value']
        return hits, total

@lru_cache()
def get_es_client() -> ElasticsearchClient:
    # Use credentials if they are provided
    if ES_USERNAME and ES_PASSWORD:
        es_instance = AsyncElasticsearch(
            ELASTICSEARCH_URL,
            basic_auth=(ES_USERNAME, ES_PASSWORD)
        )
    else:
        es_instance = AsyncElasticsearch(ELASTICSEARCH_URL)
        
    return ElasticsearchClient(es_instance)