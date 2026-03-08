from fastapi import APIRouter, HTTPException, Depends, Body, BackgroundTasks
from typing import List, Dict, Any, Optional
import asyncio
import traceback
import time
import uuid

from .es_client import ElasticsearchClient, get_es_client
from .rabbitmq_client import RabbitMQClient, get_rabbitmq_client, get_rabbitmq_channel
from .models import (
    SearchRequest, RequeueBulkRequest, UpdateStatusBulkRequest,
    EditAndRequeueRequest, RequeueByFilterRequest, ArchiveByFilterRequest, CheckUrlsBatchRequest
)

router = APIRouter()

# In-memory tracking for background tasks initiated by FastAPI
TASK_STORE: Dict[str, str] = {}

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
    try:
        if not url:
            raise HTTPException(status_code=400, detail="Le paramètre 'url' est requis")
        result = await es_client.check_url_in_dlq(url)
        return result
    except Exception as e:
        print(f"--- UNHANDLED ERROR IN /api/check-url ---")
        print(traceback.format_exc())
        print("------------------------------------------")
        raise HTTPException(status_code=500, detail=f"An internal error occurred: {e}")


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
    try:
        if not request.urls:
            return {
                "results": {},
                "summary": {"total": 0, "found": 0, "missing": 0}
            }
        result = await es_client.check_urls_batch_in_dlq(request.urls)
        return result
    except Exception as e:
        print(f"--- UNHANDLED ERROR IN /api/check-urls ---")
        print(traceback.format_exc())
        print("-------------------------------------------")
        raise HTTPException(status_code=500, detail=f"An internal error occurred: {e}")

@router.post("/dashboard-stats")
async def get_dashboard_stats(filters: Optional[Dict[str, Any]] = Body(None), es_client: ElasticsearchClient = Depends(get_es_client)):
    """
    Provides aggregated data for the main dashboard, with optional filters.
    """
    try:
        return await es_client.get_dashboard_stats(filters=filters)
    except Exception as e:
        print("--- UNHANDLED ERROR IN /api/dashboard-stats ---")
        print(traceback.format_exc())
        print("---------------------------------------------")
        raise HTTPException(status_code=500, detail=f"An internal error occurred: {e}")

@router.post("/messages/search")
async def search_messages(request: SearchRequest, es_client: ElasticsearchClient = Depends(get_es_client)):
    """
    Performs an advanced search for messages based on multiple filters.
    """
    try:
        results, total = await es_client.search_messages(
            filters=request.filters,
            search_term=request.search_term,
            page=request.page,
            page_size=request.page_size
        )
        return {"messages": results, "total": total}
    except Exception as e:
        print("--- UNHANDLED ERROR IN /api/messages/search ---")
        print(traceback.format_exc())
        print("---------------------------------------------")
        raise HTTPException(status_code=500, detail=f"An internal error occurred: {e}")

@router.get("/messages/{message_id}")
async def get_message_details(message_id: str, es_client: ElasticsearchClient = Depends(get_es_client)):
    """
    Gets the full details for a single message, including its payload.
    """
    try:
        message = await es_client.get_message(message_id)
        if not message:
            raise HTTPException(status_code=404, detail="Message not found")
        return message
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
    TASK_STORE[task_id] = "processing"

    async def process_requeue():
        try:
            print(f"Background Task {task_id}: Starting bulk requeue by filter...")
            total_requeued = 0
            async for batch in es_client.scroll_messages(filters=request.filters, search_term=request.search_term):
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
                
            print(f"Background Task {task_id}: Finished bulk requeue. Total: {total_requeued} messages.")
            TASK_STORE[task_id] = "completed"
        except Exception as e:
            print(f"Background Task {task_id}: Error in bulk requeue: {e}")
            TASK_STORE[task_id] = "error"

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
    TASK_STORE[task_id] = "processing"

    async def process_archive():
        try:
            print(f"Background Task {task_id}: Starting bulk archive by filter...")
            total_archived = 0
            async for batch in es_client.scroll_messages(filters=request.filters, search_term=request.search_term):
                message_ids = [msg['_id'] for msg in batch]
                archived_in_batch = await es_client.update_message_status_bulk(message_ids, "Archived")
                total_archived += archived_in_batch
                
            print(f"Background Task {task_id}: Finished bulk archive. Total: {total_archived} messages.")
            TASK_STORE[task_id] = "completed"
        except Exception as e:
            print(f"Background Task {task_id}: Error in bulk archive: {e}")
            TASK_STORE[task_id] = "error"

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
            status = TASK_STORE[task_id]
            return {"task_id": task_id, "completed": status in ["completed", "error"], "status": status}
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
    try:
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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