import os
import re
import json
import asyncio
from elasticsearch import AsyncElasticsearch
from functools import lru_cache
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime, timezone

# Read connection details from environment variables
ELASTICSEARCH_URL = os.environ.get("ELASTICSEARCH_URL", "http://localhost:9200")
ES_USERNAME = os.environ.get("ES_USERNAME")
ES_PASSWORD = os.environ.get("ES_PASSWORD")

ELASTIC_INDEX_NAME = "failed_messages_archive"
RULES_INDEX_NAME = "dlq_auto_archive_rules"

class ElasticsearchClient:
    def __init__(self, client: AsyncElasticsearch):
        self.client = client

    def _rehydrate_document(self, hit: Dict) -> Dict:
        """
        Restores the original_payload from the payload_conflict_fallback string 
        if a mapping conflict occurred during archiving. This makes the fallback 
        completely transparent to the frontend and the requeuing processes.
        """
        if not hit or '_source' not in hit:
            return hit
            
        source = hit['_source']
        if 'payload_conflict_fallback' in source and source['payload_conflict_fallback']:
            try:
                # Reconstruct the original object from the serialized fallback string
                source['original_payload'] = json.loads(source['payload_conflict_fallback'])
                # Remove it so we don't send duplicate heavy data to the frontend
                del source['payload_conflict_fallback']
            except Exception as e:
                print(f"Warning: Failed to rehydrate fallback document {hit.get('_id')}: {e}")
        return hit

    async def ensure_rules_index(self):
        """Ensures the auto-archive rules index exists with proper mappings."""
        try:
            if not await self.client.indices.exists(index=RULES_INDEX_NAME):
                await self.client.indices.create(
                    index=RULES_INDEX_NAME,
                    body={
                        "mappings": {
                            "properties": {
                                "name": {"type": "keyword"},
                                "description": {"type": "text"},
                                "search_term": {"type": "text"},
                                "filters": {"type": "object", "enabled": False}, # Do not index inner structure
                                "is_active": {"type": "boolean"},
                                "created_at": {"type": "date"},
                                "execution_count": {"type": "integer"},
                                "last_evaluated_at": {"type": "date"},
                                "last_archived_at": {"type": "date"}
                            }
                        }
                    }
                )
        except Exception as e:
            print(f"Failed to ensure rules index: {e}")

    async def get_rules(self, only_active: bool = False) -> List[Dict[str, Any]]:
        """Retrieves all rules or only active rules."""
        await self.ensure_rules_index()
        query = {"match_all": {}} if not only_active else {"term": {"is_active": True}}
        try:
            res = await self.client.search(
                index=RULES_INDEX_NAME,
                body={"query": query, "size": 1000, "sort": [{"created_at": "desc"}]}
            )
            rules = []
            for hit in res['hits']['hits']:
                r = hit['_source']
                r['_id'] = hit['_id']
                # Safely fallback to 0 if the field is missing or null
                r['execution_count'] = r.get('execution_count') or 0
                rules.append(r)
            return rules
        except Exception as e:
            print(f"Error getting rules: {e}")
            return[]

    async def create_rule(self, rule_data: Dict) -> str:
        """Creates a new auto-archive rule."""
        await self.ensure_rules_index()
        rule_data['created_at'] = datetime.now(timezone.utc).isoformat()
        rule_data['execution_count'] = 0
        rule_data['last_evaluated_at'] = None
        rule_data['last_archived_at'] = None
        res = await self.client.index(index=RULES_INDEX_NAME, body=rule_data)
        return res['_id']

    async def update_rule_status(self, rule_id: str, is_active: bool):
        """Toggles a rule on or off."""
        await self.client.update(
            index=RULES_INDEX_NAME,
            id=rule_id,
            body={"doc": {"is_active": is_active}}
        )

    async def delete_rule(self, rule_id: str):
        """Deletes a rule."""
        await self.client.delete(index=RULES_INDEX_NAME, id=rule_id)

    async def increment_rule_execution(self, rule_id: str, count: int):
        """Safely increments the execution count of a rule."""
        try:
            await self.client.update(
                index=RULES_INDEX_NAME,
                id=rule_id,
                body={
                    "script": {
                        "source": "if (ctx._source.execution_count == null) { ctx._source.execution_count = params.count } else { ctx._source.execution_count += params.count }",
                        "params": {"count": count}
                    }
                },
                retry_on_conflict=3
            )
        except Exception as e:
            print(f"Error incrementing execution count for rule {rule_id}: {e}")

    async def apply_auto_archive_rule(self, rule: Dict) -> int:
        """Executes an auto-archive rule strictly against 'New' messages using memory-safe scrolling."""
        raw_filters = rule.get('filters', {})
        search_term = rule.get('search_term', "")
        rule_id = rule.get('_id')
        
        # Override the status filter to ONLY target "New" messages to be safe.
        active_filters = dict(raw_filters) if raw_filters else {}
        active_filters["status"] = ["New"] 
        
        total_archived = 0
        try:
            # source=False disables payload fetching. batch_size=50 prevents OOM during bulk updates.
            async for batch in self.scroll_messages(filters=active_filters, search_term=search_term, batch_size=50, include_source=False):
                message_ids = [msg['_id'] for msg in batch]
                if message_ids:
                    archived_in_batch = await self.update_message_status_bulk(message_ids, "Auto-Archived")
                    total_archived += archived_in_batch
                    
                    # Live update the execution counter progressively
                    if archived_in_batch > 0 and rule_id:
                        await self.increment_rule_execution(rule_id, archived_in_batch)
                    
                    # Pressure relief valve: give ES Garbage Collector time to clean up
                    await asyncio.sleep(0.5)

            # Update rule timestamps after execution
            if rule_id:
                now_iso = datetime.now(timezone.utc).isoformat()
                update_body = {"last_evaluated_at": now_iso}
                if total_archived > 0:
                    update_body["last_archived_at"] = now_iso
                try:
                    await self.client.update(
                        index=RULES_INDEX_NAME,
                        id=rule_id,
                        body={"doc": update_body}
                    )
                except Exception as e:
                    print(f"Error updating rule timestamps for {rule_id}: {e}")

            return total_archived
        except Exception as e:
            print(f"Error applying auto-archive rule {rule.get('name')}: {e}")
            return total_archived

    async def get_service_names(self, filters: Dict = None) -> List[Dict[str, Any]]:
        """Returns service name buckets respecting the full filter context (status + date range)."""
        query = self._build_query(filters or {}, "")
        body = {
            "size": 0,
            "query": query,
            "aggs": {
                "by_service": {"terms": {"field": "service_name", "size": 100}}
            }
        }
        response = await self.client.search(index=ELASTIC_INDEX_NAME, body=body)
        return response['aggregations']['by_service']['buckets']

    @staticmethod
    def _build_url_query(url: str) -> Dict:
        """Builds the ES query for matching a URL in DLQ payloads."""
        normalized_url = url.rstrip('/')
        return {
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

    async def check_url_in_dlq(self, url: str) -> Dict[str, Any]:
        """
        Vérifie si une URL existe dans les DLQ Elasticsearch.
        Recherche dans original_payload.data.url et original_payload.url

        Args:
            url: L'URL à vérifier

        Returns:
            Dict avec exists (bool), count (int), et latest (dict) si trouvé
        """
        query = self._build_url_query(url)
        
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
            # Header de la requête (index)
            search_lines.append({"index": ELASTIC_INDEX_NAME})

            # Body de la requête
            query = self._build_url_query(url)
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
            # Detect quoted field:value pattern like error_reason:'...' or error_reason:"..."
            field_value_match = re.match(r'^(\w+):[\'"](.+)[\'"]$', search_term, re.DOTALL)
            if field_value_match:
                field_name = field_value_match.group(1)
                field_value = field_value_match.group(2)
                query["bool"]["must"].append({
                    "match_phrase": {
                        field_name: field_value
                    }
                })
            elif any(char in search_term for char in [':', '*', '?']):
                # Advanced query_string syntax (unquoted field:value, wildcards, etc.)
                query["bool"]["must"].append({
                    "query_string": {
                        "query": search_term,
                        "fields": ["error_reason", "original_payload.*", "service_name"],
                        "lenient": True
                    }
                })
            else:
                # Simple search term — wrap with wildcards
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

            error_reason = filters.get("error_reason")
            if error_reason and isinstance(error_reason, str):
                query["bool"]["must"].append({
                    "match_phrase": {"error_reason": error_reason}
                })

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
                "_source": {"excludes":["original_payload", "payload_conflict_fallback"]}
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
    
    async def get_message(self, message_id: str) -> Optional[Dict]:
        """Gets the full document for a single message, including the payload."""
        try:
            response = await self.client.get(index=ELASTIC_INDEX_NAME, id=message_id)
            raw_hit = dict(response.body) if hasattr(response, "body") else dict(response)
            return self._rehydrate_document(raw_hit)
        except Exception as e:
            print(f"Error fetching message {message_id}: {e}")
            return None
            
    async def get_messages_bulk(self, message_ids: List[str]) -> List[Dict]:
        if not message_ids:
            return []
        response = await self.client.mget(index=ELASTIC_INDEX_NAME, body={"ids": message_ids})
        hits = [doc for doc in response['docs'] if doc['found']]
        return[self._rehydrate_document(hit) for hit in hits]

    async def update_message_status(self, message_id: str, status: str):
        now_iso = datetime.now(timezone.utc).isoformat()
        await self.client.update(
            index=ELASTIC_INDEX_NAME,
            id=message_id,
            body={
                "doc": {
                    "status": status,
                    "status_updated_at": now_iso
                }
            }
        )

    async def update_message_status_bulk(self, message_ids: List[str], status: str) -> int:
        if not message_ids:
            return 0
        
        actions = []
        now_iso = datetime.now(timezone.utc).isoformat()
        for msg_id in message_ids:
            actions.append({"update": {"_index": ELASTIC_INDEX_NAME, "_id": msg_id}})
            actions.append({"doc": {"status": status, "status_updated_at": now_iso}})
            
        response = await self.client.bulk(body=actions)
        return len([item for item in response['items'] if not item['update'].get('error')])
        
    async def scroll_messages(self, filters: Dict, search_term: str, batch_size: int = 100, include_source: bool = True):
        """
        Scrolls through all messages matching a query, yielding them in batches.
        :param batch_size: Number of documents to fetch per batch.
        :param include_source: Set to False to exclude _source fields entirely (saves massive memory).
        """
        query = self._build_query(filters, search_term)
        pit = await self.client.open_point_in_time(index=ELASTIC_INDEX_NAME, keep_alive="1m")

        body = {
            "size": batch_size,
            "query": query,
            "sort": [{"@timestamp": "asc"}],
            "pit": {"id": pit['id'], "keep_alive": "1m"}
        }

        if not include_source:
            body["_source"] = False

        try:
            while True:
                response = await self.client.search(body=body)
                hits = response['hits']['hits']
                if not hits:
                    break

                if include_source:
                    hits = [self._rehydrate_document(hit) for hit in hits]
                    
                yield hits
                
                body['pit']['id'] = response['pit_id']
                if 'sort' in hits[-1]:
                    body['search_after'] = hits[-1]['sort']
                
        finally:
            try:
                await self.client.close_point_in_time(body={"id": pit['id']})
            except Exception as e:
                print(f"Silently ignored error closing PIT (likely connection drop): {e}")

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

    async def extract_field_from_messages(
        self, filters: Dict, search_term: str, field_path: str
    ) -> Tuple[List[Any], int]:
        """
        Scrolls through all matching messages, loads original_payload,
        and extracts a specific nested field value.

        field_path: dot-separated path within original_payload (e.g. "data.fichier_source")
        Returns: (unique_values, total_scanned)
        """
        query = self._build_query(filters, search_term)
        unique_values = set()
        total_scanned = 0
        batch_size = 500

        # Use search_after for efficient deep pagination
        sort_field = "@timestamp"
        search_after = None

        while True:
            body = {
                "query": query,
                "size": batch_size,
                "sort": [{sort_field: "asc"}, {"_shard_doc": "asc"}],
                "_source": ["original_payload", "payload_conflict_fallback"]
            }
            if search_after:
                body["search_after"] = search_after

            response = await self.client.search(
                index=ELASTIC_INDEX_NAME,
                body=body,
                track_total_hits=True
            )

            hits = response['hits']['hits']
            if not hits:
                break

            for hit in hits:
                rehydrated = self._rehydrate_document(hit)
                source = rehydrated.get('_source', {})
                payload = source.get('original_payload', {})

                # Navigate the field_path (e.g. "data.fichier_source")
                value = payload
                for key in field_path.split('.'):
                    if isinstance(value, dict):
                        value = value.get(key)
                    else:
                        value = None
                        break

                if value is not None and value != "":
                    unique_values.add(value)

            total_scanned += len(hits)
            search_after = hits[-1]['sort']

            if len(hits) < batch_size:
                break

        return sorted(unique_values, key=str), total_scanned

    async def get_unique_errors(self, filters: Dict, search_term: str) -> Dict[str, Any]:
        """Returns all unique (service_name, error_reason) combinations matching the query
        using a composite aggregation for unlimited bucket count."""
        query = self._build_query(filters, search_term)
        buckets = []
        after_key = None

        while True:
            composite_source = {
                "sources": [
                    {"service_name": {"terms": {"field": "service_name"}}},
                    {"error_reason": {"terms": {"field": "error_reason.keyword"}}}
                ],
                "size": 500
            }
            if after_key:
                composite_source["after"] = after_key

            body = {
                "size": 0,
                "query": query,
                "aggs": {
                    "unique_errors": {
                        "composite": composite_source
                    }
                }
            }

            response = await self.client.search(index=ELASTIC_INDEX_NAME, body=body)
            agg_buckets = response['aggregations']['unique_errors']['buckets']

            for bucket in agg_buckets:
                buckets.append({
                    "service_name": bucket['key']['service_name'],
                    "error_reason": bucket['key']['error_reason'],
                    "count": bucket['doc_count']
                })

            if len(agg_buckets) < 500:
                break
            after_key = agg_buckets[-1]['key']

        return {"buckets": buckets, "total_unique": len(buckets)}

    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Gets the status of an Elasticsearch background task."""
        try:
            response = await self.client.tasks.get(task_id=task_id)
            # Safely convert ObjectApiResponse to standard Python dict
            return dict(response.body) if hasattr(response, "body") else dict(response)
        except Exception as e:
            print(f"Error fetching task status for {task_id}: {e}")
            return None

@lru_cache()
def get_es_client() -> ElasticsearchClient:
    # Adding generous timeouts to allow massive bulk operations in background tasks
    # to complete without severing the HTTP connection between Python and the cluster.
    if ES_USERNAME and ES_PASSWORD:
        es_instance = AsyncElasticsearch(
            ELASTICSEARCH_URL,
            basic_auth=(ES_USERNAME, ES_PASSWORD),
            request_timeout=120,
            max_retries=3,
            retry_on_timeout=True
        )
    else:
        es_instance = AsyncElasticsearch(
            ELASTICSEARCH_URL,
            request_timeout=120,
            max_retries=3,
            retry_on_timeout=True
        )
        
    return ElasticsearchClient(es_instance)