from fastapi import APIRouter, HTTPException, Depends, Body
from typing import List, Dict, Any, Optional
import asyncio

from .es_client import ElasticsearchClient, get_es_client
from .rabbitmq_client import RabbitMQClient, get_rabbitmq_client
from .models import (
    SearchRequest, RequeueBulkRequest, UpdateStatusBulkRequest,
    EditAndRequeueRequest, RequeueByFilterRequest
)

router = APIRouter()

@router.get("/dashboard-stats")
async def get_dashboard_stats(es_client: ElasticsearchClient = Depends(get_es_client)):
    """
    Provides aggregated data for the main dashboard.
    Functionality #1: Central Dashboard
    """
    try:
        return await es_client.get_dashboard_stats()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/messages/search")
async def search_messages(request: SearchRequest, es_client: ElasticsearchClient = Depends(get_es_client)):
    """
    Performs an advanced search for messages based on multiple filters.
    Functionality #2: Advanced Search and Multi-Filter Panel
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
        raise HTTPException(status_code=500, detail=str(e))

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
    Functionality #8: Automatic Error Grouping
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
    Functionality #4: Single Message Re-queue
    """
    try:
        message = await es_client.get_message(message_id)
        if not message:
            raise HTTPException(status_code=404, detail="Message not found")
        
        await rmq_client.publish_message(message)
        await es_client.update_message_status(message_id, "Re-queued")
        
        return {"status": "success", "message": f"Message {message_id} has been re-queued."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/messages/bulk-requeue")
async def bulk_requeue(request: RequeueBulkRequest, es_client: ElasticsearchClient = Depends(get_es_client), rmq_client: RabbitMQClient = Depends(get_rabbitmq_client)):
    """
    Re-queues multiple messages in a batch with optional throttling.
    Functionality #5: Bulk Actions & #11: Throttled Re-queuing
    """
    success_count = 0
    errors = []
    
    messages = await es_client.get_messages_bulk(request.message_ids)
    
    for msg in messages:
        try:
            await rmq_client.publish_message(msg)
            success_count += 1
            if request.rate_limit_per_second and request.rate_limit_per_second > 0:
                await asyncio.sleep(1.0 / request.rate_limit_per_second)
        except Exception as e:
            errors.append({"message_id": msg['_id'], "error": str(e)})

    # Update statuses in bulk
    succeeded_ids = [msg['_id'] for msg in messages if msg['_id'] not in [e['message_id'] for e in errors]]
    if succeeded_ids:
        await es_client.update_message_status_bulk(succeeded_ids, "Re-queued")
        
    return {"success_count": success_count, "errors": errors}

@router.post("/messages/bulk-archive")
async def bulk_archive(request: UpdateStatusBulkRequest, es_client: ElasticsearchClient = Depends(get_es_client)):
    """
    Updates the status of multiple messages to 'Archived'.
    Functionality #5: Bulk Actions (Archive)
    """
    try:
        updated_count = await es_client.update_message_status_bulk(request.message_ids, "Archived")
        return {"status": "success", "updated_count": updated_count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/messages/requeue-by-filter")
async def requeue_by_filter(request: RequeueByFilterRequest, es_client: ElasticsearchClient = Depends(get_es_client), rmq_client: RabbitMQClient = Depends(get_rabbitmq_client)):
    """
    Finds all messages matching a filter and re-queues them.
    Functionality #6: "Re-queue All Matching Filter" Action
    """
    try:
        total_requeued = 0
        async for batch in es_client.scroll_messages(filters=request.filters, search_term=request.search_term):
            for msg in batch:
                await rmq_client.publish_message(msg)
                total_requeued += 1
                if request.rate_limit_per_second and request.rate_limit_per_second > 0:
                    await asyncio.sleep(1.0 / request.rate_limit_per_second)

            message_ids = [msg['_id'] for msg in batch]
            await es_client.update_message_status_bulk(message_ids, "Re-queued")
            
        return {"status": "success", "total_requeued": total_requeued}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/messages/{message_id}/edit-and-requeue")
async def edit_and_requeue(message_id: str, request: EditAndRequeueRequest, es_client: ElasticsearchClient = Depends(get_es_client), rmq_client: RabbitMQClient = Depends(get_rabbitmq_client)):
    """
    Allows editing a message payload before re-queuing it.
    Functionality #7: Live Payload Editing
    """
    try:
        message = await es_client.get_message(message_id)
        if not message:
            raise HTTPException(status_code=404, detail="Message not found")

        # Override the original payload with the new one
        message['_source']['original_payload'] = request.new_payload
        
        await rmq_client.publish_message(message)
        await es_client.update_message_status(message_id, "Re-queued (Edited)")
        
        return {"status": "success", "message": f"Message {message_id} has been edited and re-queued."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/history")
async def get_requeue_history(page: int = 1, page_size: int = 50, es_client: ElasticsearchClient = Depends(get_es_client)):
    """
    Retrieves a log of all re-queue actions.
    Functionality #9: Audit Trail / Re-queue History
    """
    try:
        results, total = await es_client.get_history(page, page_size)
        return {"history": results, "total": total}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))