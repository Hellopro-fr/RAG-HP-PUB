from fastapi import APIRouter, HTTPException, Depends, Body, BackgroundTasks, Request
from fastapi.responses import JSONResponse
from typing import List, Dict, Any, Optional
import asyncio
import traceback
import time
import uuid

from .es_client import ElasticsearchClient, get_es_client
from .rabbitmq_client import RabbitMQClient, get_rabbitmq_client, get_rabbitmq_channel
from .models import (
    SearchRequest, RequeueBulkRequest, UpdateStatusBulkRequest,
    EditAndRequeueRequest, RequeueByFilterRequest, ArchiveByFilterRequest, CheckUrlsBatchRequest,
    AutoArchiveRuleCreate, ExtractFieldRequest, UniqueErrorsRequest, ServiceNamesRequest
)

router = APIRouter()


async def unhandled_exception_handler(request: Request, exc: Exception):
    """Centralized error logging for all unhandled exceptions in API routes."""
    print(f"--- UNHANDLED ERROR IN {request.method} {request.url.path} ---")
    print(traceback.format_exc())
    print("---")
    return JSONResponse(status_code=500, content={"detail": f"An internal error occurred: {exc}"})

# In-memory tracking for background tasks with TTL eviction.
# Each entry: {"status": str, "error": str | None, "created_at": float}
TASK_STORE: Dict[str, Dict[str, Any]] = {}
TASK_TTL_SECONDS = 3600  # Evict completed tasks after 1 hour


def _evict_stale_tasks():
    """Remove completed/errored tasks older than TTL."""
    now = time.time()
    stale_keys = [
        k for k, v in TASK_STORE.items()
        if v["status"] in ("completed", "error") and (now - v["created_at"]) > TASK_TTL_SECONDS
    ]
    for k in stale_keys:
        del TASK_STORE[k]


def _create_task(task_id: str):
    _evict_stale_tasks()
    TASK_STORE[task_id] = {"status": "processing", "error": None, "created_at": time.time()}


def _complete_task(task_id: str):
    TASK_STORE[task_id]["status"] = "completed"


def _fail_task(task_id: str, error: str):
    TASK_STORE[task_id]["status"] = "error"
    TASK_STORE[task_id]["error"] = error

# --- AUTO-ARCHIVE RULES ENDPOINTS ---

@router.get("/rules")
async def get_rules(es_client: ElasticsearchClient = Depends(get_es_client)):
    return await es_client.get_rules()

@router.post("/rules")
async def create_rule(rule: AutoArchiveRuleCreate, es_client: ElasticsearchClient = Depends(get_es_client)):
    try:
        rule_id = await es_client.create_rule(rule.model_dump())
        return {"status": "success", "rule_id": rule_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/rules/{rule_id}/toggle")
async def toggle_rule(rule_id: str, is_active: bool = Body(..., embed=True), es_client: ElasticsearchClient = Depends(get_es_client)):
    try:
        await es_client.update_rule_status(rule_id, is_active)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: str, es_client: ElasticsearchClient = Depends(get_es_client)):
    try:
        await es_client.delete_rule(rule_id)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- EXISTING ENDPOINTS ---

@router.get("/check-url")
async def check_url_in_dlq(url: str, es_client: ElasticsearchClient = Depends(get_es_client)):
    """
    Vérifie si une URL existe dans les DLQ Elasticsearch.
    
    Args:
        url: L'URL à vérifier (query parameter)
        
    Returns:
        - exists: bool - true si l'URL est trouvée dans les DLQ
        - count: int - nombre d'occurrences trouvées
        - latest: dict - détails de l'occurrence la plus récente (si exists=true)
    
    Exemple d'utilisation:
        GET /api/check-url?url=https://example.com/page
    """
    if not url:
        raise HTTPException(status_code=400, detail="Le paramètre 'url' est requis")
    return await es_client.check_url_in_dlq(url)


@router.post("/check-urls")
async def check_urls_batch_in_dlq(request: CheckUrlsBatchRequest, es_client: ElasticsearchClient = Depends(get_es_client)):
    """
    Vérifie si une liste d'URLs existe dans les DLQ Elasticsearch.
    
    Args:
        request: CheckUrlsBatchRequest avec une liste d'URLs
        
    Returns:
        - results: Dict avec le statut de chaque URL
        - summary: Statistiques globales (total, found, missing)
    
    Exemple d'utilisation:
        POST /api/check-urls
        Body: {"urls": ["https://example.com/page1", "https://example.com/page2"]}
    """
    if not request.urls:
        return {
            "results": {},
            "summary": {"total": 0, "found": 0, "missing": 0}
        }
    return await es_client.check_urls_batch_in_dlq(request.urls)

@router.post("/dashboard-stats")
async def get_dashboard_stats(filters: Optional[Dict[str, Any]] = Body(None), es_client: ElasticsearchClient = Depends(get_es_client)):
    """
    Provides aggregated data for the main dashboard, with optional filters.
    """
    return await es_client.get_dashboard_stats(filters=filters)

@router.post("/services")
async def get_service_names(request: ServiceNamesRequest, es_client: ElasticsearchClient = Depends(get_es_client)):
    """Returns the list of service names matching the given filters (status, date range)."""
    buckets = await es_client.get_service_names(filters=request.filters)
    return {"services": buckets}

@router.post("/messages/search")
async def search_messages(request: SearchRequest, es_client: ElasticsearchClient = Depends(get_es_client)):
    """
    Performs an advanced search for messages based on multiple filters.
    """
    results, total = await es_client.search_messages(
        filters=request.filters,
        search_term=request.search_term,
        page=request.page,
        page_size=request.page_size
    )
    return {"messages": results, "total": total}

@router.get("/messages/{message_id}")
async def get_message_details(message_id: str, es_client: ElasticsearchClient = Depends(get_es_client)):
    """
    Gets the full details for a single message, including its payload.
    """
    message = await es_client.get_message(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    return message


@router.post("/messages/grouped-search")
async def search_grouped_messages(request: SearchRequest, es_client: ElasticsearchClient = Depends(get_es_client)):
    """
    Searches for messages and groups them by service and error reason.
    """
    try:
        results = await es_client.get_grouped_errors(
            filters=request.filters,
            search_term=request.search_term
        )
        return {"groups": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/messages/{message_id}/requeue")
async def requeue_message(message_id: str, es_client: ElasticsearchClient = Depends(get_es_client), rmq_client: RabbitMQClient = Depends(get_rabbitmq_client)):
    """
    Re-queues a single message.
    """
    try:
        message = await es_client.get_message(message_id)
        if not message:
            raise HTTPException(status_code=404, detail="Message not found")
        
        def do_publish():
            with get_rabbitmq_channel() as channel:
                rmq_client.publish_message(channel, message)
        
        await asyncio.to_thread(do_publish)
        await es_client.update_message_status(message_id, "Re-queued")
        
        return {"status": "success", "message": f"Message {message_id} has been re-queued."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/messages/bulk-requeue")
async def bulk_requeue(request: RequeueBulkRequest, es_client: ElasticsearchClient = Depends(get_es_client), rmq_client: RabbitMQClient = Depends(get_rabbitmq_client)):
    """
    Re-queues multiple messages in a batch with optional throttling.
    """
    messages = await es_client.get_messages_bulk(request.message_ids)

    def do_bulk_publish():
        publish_errors = []
        publish_success_count = 0
        with get_rabbitmq_channel() as channel:
            for msg in messages:
                try:
                    rmq_client.publish_message(channel, msg)
                    publish_success_count += 1
                    if request.rate_limit_per_second and request.rate_limit_per_second > 0:
                        time.sleep(1.0 / request.rate_limit_per_second)
                except Exception as e:
                    publish_errors.append({"message_id": msg['_id'], "error": str(e)})
        return publish_success_count, publish_errors

    success_count, errors = await asyncio.to_thread(do_bulk_publish)

    # Update statuses in bulk
    succeeded_ids = [msg['_id'] for msg in messages if msg['_id'] not in [e['message_id'] for e in errors]]
    if succeeded_ids:
        await es_client.update_message_status_bulk(succeeded_ids, "Re-queued")
        
    return {"success_count": success_count, "errors": errors}

@router.post("/messages/bulk-archive")
async def bulk_archive(request: UpdateStatusBulkRequest, es_client: ElasticsearchClient = Depends(get_es_client)):
    """
    Updates the status of multiple messages to 'Archived'.
    """
    try:
        updated_count = await es_client.update_message_status_bulk(request.message_ids, "Archived")
        return {"status": "success", "updated_count": updated_count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/messages/requeue-by-filter")
async def requeue_by_filter(
    request: RequeueByFilterRequest, 
    background_tasks: BackgroundTasks, 
    es_client: ElasticsearchClient = Depends(get_es_client), 
    rmq_client: RabbitMQClient = Depends(get_rabbitmq_client)
):
    """
    Finds all messages matching a filter and re-queues them as a background task
    to prevent HTTP timeout limits on massive queues.
    """
    task_id = f"requeue_{uuid.uuid4().hex}"
    _create_task(task_id)

    async def process_requeue():
        try:
            print(f"Background Task {task_id}: Starting bulk requeue by filter...")
            total_requeued = 0
            # Reduced batch size to 50 to prevent memory pressure when loading heavy payloads
            async for batch in es_client.scroll_messages(filters=request.filters, search_term=request.search_term, batch_size=50):
                def do_batch_publish(current_batch):
                    batch_requeued = 0
                    with get_rabbitmq_channel() as channel:
                        for msg in current_batch:
                            rmq_client.publish_message(channel, msg)
                            batch_requeued += 1
                            if request.rate_limit_per_second and request.rate_limit_per_second > 0:
                                time.sleep(1.0 / request.rate_limit_per_second)
                    return batch_requeued

                requeued_in_batch = await asyncio.to_thread(do_batch_publish, batch)
                total_requeued += requeued_in_batch

                message_ids = [msg['_id'] for msg in batch]
                await es_client.update_message_status_bulk(message_ids, "Re-queued")

                # Pressure relief valve: give ES Garbage Collector time to clean up
                await asyncio.sleep(0.5)

            print(f"Background Task {task_id}: Finished bulk requeue. Total: {total_requeued} messages.")
            _complete_task(task_id)
        except Exception as e:
            print(f"Background Task {task_id}: Error in bulk requeue: {e}")
            _fail_task(task_id, str(e))

    background_tasks.add_task(process_requeue)
    return {"status": "success", "message": "Re-queue process successfully started in the background.", "task_id": task_id}

@router.post("/messages/archive-by-filter")
async def archive_by_filter(
    request: ArchiveByFilterRequest, 
    background_tasks: BackgroundTasks, 
    es_client: ElasticsearchClient = Depends(get_es_client)
):
    """
    Finds all messages matching a filter and archives them utilizing the background 
    task engine and reliable scroll methodology to prevent mapping issues.
    """
    task_id = f"archive_{uuid.uuid4().hex}"
    _create_task(task_id)

    async def process_archive():
        try:
            print(f"Background Task {task_id}: Starting bulk archive by filter...")
            total_archived = 0
            async for batch in es_client.scroll_messages(filters=request.filters, search_term=request.search_term, batch_size=50, include_source=False):
                message_ids = [msg['_id'] for msg in batch]
                archived_in_batch = await es_client.update_message_status_bulk(message_ids, "Archived")
                total_archived += archived_in_batch

                # Pressure relief valve: give ES Garbage Collector time to clean up
                await asyncio.sleep(0.5)

            print(f"Background Task {task_id}: Finished bulk archive. Total: {total_archived} messages.")
            _complete_task(task_id)
        except Exception as e:
            print(f"Background Task {task_id}: Error in bulk archive: {e}")
            _fail_task(task_id, str(e))

    background_tasks.add_task(process_archive)
    return {"status": "success", "message": "Archive process successfully started in the background.", "task_id": task_id}

@router.get("/tasks/{task_id}")
async def get_task_status(task_id: str, es_client: ElasticsearchClient = Depends(get_es_client)):
    """
    Checks the status of an asynchronous task (either ES internal or Python background task).
    """
    # 1. Check if it's a python background task
    if task_id.startswith("requeue_") or task_id.startswith("archive_"):
        if task_id in TASK_STORE:
            task = TASK_STORE[task_id]
            status = task["status"]
            result = {"task_id": task_id, "completed": status in ("completed", "error"), "status": status}
            if task.get("error"):
                result["error"] = task["error"]
            return result
        else:
            raise HTTPException(status_code=404, detail="Background task not found")
            
    # 2. Assume it's an Elasticsearch background task (legacy fallback)
    es_task = await es_client.get_task_status(task_id)
    if es_task:
        completed = es_task.get("completed", False)
        return {"task_id": task_id, "completed": completed, "status": "completed" if completed else "processing"}
    
    raise HTTPException(status_code=404, detail="Task not found")

@router.put("/messages/{message_id}/edit-and-requeue")
async def edit_and_requeue(message_id: str, request: EditAndRequeueRequest, es_client: ElasticsearchClient = Depends(get_es_client), rmq_client: RabbitMQClient = Depends(get_rabbitmq_client)):
    """
    Allows editing a message payload before re-queuing it.
    """
    message = await es_client.get_message(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    # Override the original payload with the new one
    message['_source']['original_payload'] = request.new_payload

    def do_publish():
        with get_rabbitmq_channel() as channel:
            rmq_client.publish_message(channel, message)

    await asyncio.to_thread(do_publish)
    await es_client.update_message_status(message_id, "Re-queued (Edited)")

    return {"status": "success", "message": f"Message {message_id} has been edited and re-queued."}

@router.get("/history")
async def get_requeue_history(page: int = 1, page_size: int = 50, es_client: ElasticsearchClient = Depends(get_es_client)):
    """
    Retrieves a log of all re-queue actions.
    """
    try:
        results, total = await es_client.get_history(page, page_size)
        return {"history": results, "total": total}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/messages/unique-errors")
async def get_unique_errors(
    request: UniqueErrorsRequest,
    es_client: ElasticsearchClient = Depends(get_es_client)
):
    """
    Returns all unique (service_name, error_reason) combinations matching the current filters.
    Uses composite aggregation for unlimited bucket count.
    """
    return await es_client.get_unique_errors(
        filters=request.filters or {},
        search_term=request.search_term or ""
    )

@router.post("/messages/extract-field")
async def extract_field_from_messages(
    request: ExtractFieldRequest,
    es_client: ElasticsearchClient = Depends(get_es_client)
):
    """
    Extracts a specific field from original_payload of all matching messages.
    Uses scroll API to handle large result sets efficiently.

    Example: extract all fichier_source from document processor failures:
    {
        "filters": {
            "date_start": "2026-04-01T02:00:00Z",
            "service_names": ["document-echange-processor-service"],
            "status": ["New", "Archived", "Auto-Archived"]
        },
        "field_path": "data.fichier_source"
    }
    """
    try:
        values, total_scanned = await es_client.extract_field_from_messages(
            filters=request.filters or {},
            search_term=request.search_term or "",
            field_path=request.field_path
        )
        return {
            "values": values,
            "total": len(values),
            "total_scanned": total_scanned
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))