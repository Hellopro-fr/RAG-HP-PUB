"""
DLQ Management Router - API endpoints for managing Dead Letter Queue messages.
"""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, status

from app.schemas.dlq import (
    DLQListResponse,
    DLQQueuesResponse,
    DLQMessageFilter,
    RequeueRequest,
    DeleteRequest,
    OperationResponse,
)
from app.services import rabbitmq_client
from app.core.config import settings


router = APIRouter()


@router.get("/queues", response_model=DLQQueuesResponse, summary="List all DLQ queues")
async def list_dlq_queues():
    """
    List all DLQ-related queues with their message counts and status.

    Returns queues that contain 'dlq', 'manual', or 'retry' in their names.
    """
    try:
        queues = await rabbitmq_client.list_dlq_queues()
        return DLQQueuesResponse(success=True, queues=queues)
    except Exception as e:
        logging.error(f"Failed to list DLQ queues: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list queues: {str(e)}",
        )


@router.get(
    "/messages", response_model=DLQListResponse, summary="List messages in a DLQ"
)
async def list_dlq_messages(
    queue_name: str = Query(
        default=None,
        description="Queue name to get messages from. Defaults to manual DLQ.",
    ),
    routing_key: Optional[str] = Query(
        default=None,
        description="Filter messages by routing key (partial match)",
    ),
    exchange: Optional[str] = Query(
        default=None,
        description="Filter messages by exchange name (partial match)",
    ),
    limit: int = Query(
        default=20,
        ge=1,
        le=100,
        description="Maximum number of messages to return",
    ),
):
    """
    Get messages from a DLQ queue with optional filters.

    Messages are retrieved using the RabbitMQ Management API without removing them
    from the queue (peek mode).
    """
    try:
        # Default to manual DLQ if not specified
        target_queue = queue_name or settings.MANUAL_DLQ_QUEUE

        messages = await rabbitmq_client.get_messages(
            queue_name=target_queue,
            count=limit,
            ack_mode="reject_requeue_true",  # Peek mode - using reject to ensure requeue
            routing_key_filter=routing_key,
            exchange_filter=exchange,
        )

        return DLQListResponse(
            success=True,
            messages=messages,
            total_count=len(messages),
        )

    except Exception as e:
        logging.error(f"Failed to get messages: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get messages: {str(e)}",
        )


@router.post(
    "/requeue",
    response_model=OperationResponse,
    summary="Requeue messages to retry queue",
)
async def requeue_messages(request: RequeueRequest):
    """
    Requeue messages from a DLQ back to the retry queue.

    This will:
    1. Get messages from the source queue (removing them)
    2. Publish them to the target exchange with the specified routing key

    By default, messages are requeued to the normalization retry exchange.
    """
    try:
        # Use defaults from config if not specified
        target_exchange = request.target_exchange or settings.RETRY_EXCHANGE
        target_routing_key = request.target_routing_key or settings.RETRY_ROUTING_KEY

        if request.queue_name == "graph_rag_llm_extraction_queue_dlq":
            target_exchange = "graph_rag_product_extracted"
            target_routing_key = "graph_rag.product.extracted"

        result = await rabbitmq_client.requeue_messages(
            queue_name=request.queue_name,
            target_exchange=target_exchange,
            target_routing_key=target_routing_key,
            count=request.count,
        )

        return OperationResponse(
            success=result["success"],
            message=result["message"],
            processed_count=result["processed_count"],
            errors=result.get("errors", []),
        )

    except Exception as e:
        logging.error(f"Requeue operation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Requeue failed: {str(e)}",
        )


@router.delete(
    "/messages", response_model=OperationResponse, summary="Delete messages from DLQ"
)
async def delete_messages(request: DeleteRequest):
    """
    Delete (acknowledge and discard) messages from a DLQ.

    This permanently removes messages from the queue. Use with caution.
    """
    try:
        result = await rabbitmq_client.delete_messages(
            queue_name=request.queue_name,
            count=request.count,
        )

        return OperationResponse(
            success=result["success"],
            message=result["message"],
            processed_count=result["processed_count"],
            errors=result.get("errors", []),
        )

    except Exception as e:
        logging.error(f"Delete operation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Delete failed: {str(e)}",
        )


@router.post(
    "/purge/{queue_name}",
    response_model=OperationResponse,
    summary="Purge all messages from a queue",
)
async def purge_queue(queue_name: str):
    """
    Purge ALL messages from a DLQ queue.

    ⚠️ WARNING: This permanently deletes all messages in the queue. Use with extreme caution.
    """
    try:
        result = await rabbitmq_client.purge_queue(queue_name)

        return OperationResponse(
            success=result["success"],
            message=result["message"],
            processed_count=result["processed_count"],
            errors=result.get("errors", []),
        )

    except Exception as e:
        logging.error(f"Purge operation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Purge failed: {str(e)}",
        )
