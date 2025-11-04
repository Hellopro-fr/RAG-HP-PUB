import os
from elasticsearch import AsyncElasticsearch
from functools import lru_cache
from typing import List, Dict, Any, Tuple

ELASTICSEARCH_URL = os.environ.get("ELASTICSEARCH_URL", "http://localhost:9200")
ELASTIC_INDEX_NAME = "failed_messages_archive"

class ElasticsearchClient:
    def __init__(self, client: AsyncElasticsearch):
        self.client = client

    async def get_dashboard_stats(self) -> Dict[str, Any]:
        """Runs aggregations for the dashboard."""
        body = {
            "size": 0,
            "aggs": {
                "total_failed": {"value_count": {"field": "_id"}},
                "by_service": {"terms": {"field": "service_name.keyword", "size": 20}},
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
        response = await self.client.search(index=ELASTIC_INDEX_NAME, body=body)
        aggs = response['aggregations']
        return {
            "total_failed": aggs['total_failed']['value'],
            "by_service": aggs['by_service']['buckets'],
            "by_error": aggs['by_error']['buckets'],
            "over_time": aggs['over_time']['buckets']
        }

    def _build_query(self, filters: Dict[str, Any], search_term: str) -> Dict[str, Any]:
        """Helper to construct the ES query DSL."""
        query = {"bool": {"must": [], "must_not": []}}
        
        if search_term:
            query["bool"]["must"].append({
                "multi_match": {
                    "query": search_term,
                    "fields": ["error_reason", "original_payload.*", "service_name"],
                    "fuzziness": "AUTO"
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
            
            if filters.get("service_names"):
                query["bool"]["must"].append({"terms": {"service_name.keyword": filters["service_names"]}})

            if filters.get("status") == "New":
                 query["bool"]["must_not"].append({"exists": {"field": "status"}})
            elif filters.get("status"):
                query["bool"]["must"].append({"term": {"status.keyword": filters["status"]}})

        return query

    async def search_messages(self, filters: Dict, search_term: str, page: int, page_size: int) -> Tuple[List[Dict], int]:
        """Performs a paginated search for messages."""
        query = self._build_query(filters, search_term)
        response = await self.client.search(
            index=ELASTIC_INDEX_NAME,
            body={
                "query": query,
                "from": (page - 1) * page_size,
                "size": page_size,
                "sort": [{"@timestamp": "desc"}],
            }
        )
        hits = [hit for hit in response['hits']['hits']]
        total = response['hits']['total']['value']
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
    es_instance = AsyncElasticsearch(ELASTICSEARCH_URL)
    return ElasticsearchClient(es_instance)