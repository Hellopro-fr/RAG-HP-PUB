import os
from elasticsearch import AsyncElasticsearch
from functools import lru_cache
from typing import List, Dict, Any, Tuple, Optional

# Read connection details from environment variables
ELASTICSEARCH_URL = os.environ.get("ELASTICSEARCH_URL", "http://localhost:9200")
ES_USERNAME = os.environ.get("ES_USERNAME")
ES_PASSWORD = os.environ.get("ES_PASSWORD")

ELASTIC_INDEX_NAME = "failed_messages_archive"

class ElasticsearchClient:
    def __init__(self, client: AsyncElasticsearch):
        self.client = client

    async def check_url_in_dlq(self, url: str) -> Dict[str, Any]:
        """
        Vérifie si une URL existe dans les DLQ Elasticsearch.
        Recherche dans original_payload.data.url et original_payload.url
        
        Args:
            url: L'URL à vérifier
            
        Returns:
            Dict avec exists (bool), count (int), et latest (dict) si trouvé
        """
        # Normaliser l'URL (retirer trailing slash)
        normalized_url = url.rstrip('/')
        
        query = {
            "bool": {
                "should": [
                    # Recherche exacte sur les champs keyword
                    {"term": {"original_payload.data.url.keyword": url}},
                    {"term": {"original_payload.url.keyword": url}},
                    {"term": {"original_payload.data.url.keyword": normalized_url}},
                    {"term": {"original_payload.url.keyword": normalized_url}},
                    # Recherche par phrase pour plus de flexibilité
                    {"match_phrase": {"original_payload.data.url": url}},
                    {"match_phrase": {"original_payload.url": url}}
                ],
                "minimum_should_match": 1
            }
        }
        
        try:
            response = await self.client.search(
                index=ELASTIC_INDEX_NAME,
                body={
                    "query": query,
                    "size": 1,
                    "sort": [{"@timestamp": "desc"}],
                    "_source": ["service_name", "error_reason", "@timestamp", "status", "original_payload.data.url", "original_payload.url"]
                }
            )
            
            hits = response['hits']['hits']
            total_count = response['hits']['total']['value']
            
            if hits:
                return {
                    "exists": True,
                    "count": total_count,
                    "latest": {
                        "service_name": hits[0]['_source'].get('service_name', 'N/A'),
                        "error_reason": hits[0]['_source'].get('error_reason', 'N/A'),
                        "timestamp": hits[0]['_source'].get('@timestamp', 'N/A'),
                        "status": hits[0]['_source'].get('status', 'New')
                    }
                }
            return {"exists": False, "count": 0}
            
        except Exception as e:
            # Log l'erreur mais retourne un résultat safe
            print(f"Erreur lors de la vérification DLQ pour URL {url}: {e}")
            return {"exists": False, "count": 0, "error": str(e)}

    async def check_urls_batch_in_dlq(self, urls: List[str]) -> Dict[str, Any]:
        """
        Vérifie si une liste d'URLs existe dans les DLQ Elasticsearch.
        Utilise msearch pour optimiser les performances.
        
        Args:
            urls: Liste d'URLs à vérifier
            
        Returns:
            Dict avec:
            - results: Dict[url, {exists, count, latest}]
            - summary: {total, found, missing}
        """
        if not urls:
            return {
                "results": {},
                "summary": {"total": 0, "found": 0, "missing": 0}
            }
        
        # Dédupliquer les URLs
        unique_urls = list(set(urls))
        
        # Construire les requêtes msearch
        search_lines = []
        for url in unique_urls:
            normalized_url = url.rstrip('/')
            
            # Header de la requête (index)
            search_lines.append({"index": ELASTIC_INDEX_NAME})
            
            # Body de la requête
            query = {
                "bool": {
                    "should": [
                        {"term": {"original_payload.data.url.keyword": url}},
                        {"term": {"original_payload.url.keyword": url}},
                        {"term": {"original_payload.data.url.keyword": normalized_url}},
                        {"term": {"original_payload.url.keyword": normalized_url}},
                        {"match_phrase": {"original_payload.data.url": url}},
                        {"match_phrase": {"original_payload.url": url}}
                    ],
                    "minimum_should_match": 1
                }
            }
            search_lines.append({
                "query": query,
                "size": 1,
                "sort": [{"@timestamp": "desc"}],
                "_source": ["service_name", "error_reason", "@timestamp", "status", "original_payload.data.url", "original_payload.url"]
            })
        
        try:
            # Exécuter msearch
            response = await self.client.msearch(body=search_lines)
            
            # Traiter les résultats
            results = {}
            found_count = 0
            
            for i, url in enumerate(unique_urls):
                resp = response['responses'][i]
                
                if 'error' in resp:
                    results[url] = {"exists": False, "count": 0, "error": str(resp['error'])}
                    continue
                
                hits = resp['hits']['hits']
                total_count = resp['hits']['total']['value']
                
                if hits:
                    found_count += 1
                    results[url] = {
                        "exists": True,
                        "count": total_count,
                        "latest": {
                            "service_name": hits[0]['_source'].get('service_name', 'N/A'),
                            "error_reason": hits[0]['_source'].get('error_reason', 'N/A'),
                            "timestamp": hits[0]['_source'].get('@timestamp', 'N/A'),
                            "status": hits[0]['_source'].get('status', 'New')
                        }
                    }
                else:
                    results[url] = {"exists": False, "count": 0}
            
            return {
                "results": results,
                "summary": {
                    "total": len(unique_urls),
                    "found": found_count,
                    "missing": len(unique_urls) - found_count
                }
            }
            
        except Exception as e:
            print(f"Erreur lors de la vérification batch DLQ: {e}")
            return {
                "results": {url: {"exists": False, "count": 0, "error": str(e)} for url in unique_urls},
                "summary": {"total": len(unique_urls), "found": 0, "missing": len(unique_urls), "error": str(e)}
            }

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
            # Check for advanced syntax characters
            if any(char in search_term for char in [':', '*', '?']):
                query_str = search_term
            else:
                query_str = f"*{search_term}*"

            query["bool"]["must"].append({
                "query_string": {
                    "query": query_str,
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

    async def archive_by_filter(self, filters: Dict, search_term: str) -> Dict:
        """Archives all messages matching a filter efficiently using _update_by_query in the background."""
        query = self._build_query(filters, search_term)
        body = {
            "query": query,
            "script": {
                "source": "ctx._source.status = 'Archived'; ctx._source.status_updated_at = 'now/s';",
                "lang": "painless"
            }
        }
        
        # wait_for_completion=False instantly returns a task ID. The cluster handles the bulk update.
        response = await self.client.update_by_query(
            index=ELASTIC_INDEX_NAME,
            body=body,
            wait_for_completion=False,
            conflicts="proceed"
        )
        return response

    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Gets the status of an Elasticsearch background task."""
        try:
            response = await self.client.tasks.get(task_id=task_id)
            return response
        except Exception as e:
            print(f"Error fetching task status for {task_id}: {e}")
            return None

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