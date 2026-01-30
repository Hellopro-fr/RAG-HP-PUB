from typing import Annotated, Any, Dict, List, Optional
from pydantic import BaseModel, Field
from datetime import datetime


class DLQMessage(BaseModel):
    """Represents a single message in a DLQ queue."""

    message_id: Annotated[
        str,
        Field(title="Message ID", description="Unique identifier for the message"),
    ]
    queue_name: Annotated[
        str,
        Field(
            title="Queue Name", description="Name of the queue containing this message"
        ),
    ]
    exchange: Annotated[
        Optional[str],
        Field(title="Exchange", description="Exchange the message was published to"),
    ] = None
    routing_key: Annotated[
        Optional[str],
        Field(title="Routing Key", description="Routing key used for this message"),
    ] = None
    payload: Annotated[
        Dict[str, Any],
        Field(title="Payload", description="The message body/payload"),
    ]
    headers: Annotated[
        Optional[Dict[str, Any]],
        Field(title="Headers", description="Message headers"),
    ] = None
    timestamp: Annotated[
        Optional[str],
        Field(title="Timestamp", description="When the message was published"),
    ] = None
    redelivered: Annotated[
        bool,
        Field(
            title="Redelivered", description="Whether the message has been redelivered"
        ),
    ] = False


class DLQQueue(BaseModel):
    """Represents a DLQ queue with metadata."""

    name: Annotated[
        str,
        Field(title="Queue Name"),
    ]
    message_count: Annotated[
        int,
        Field(title="Message Count", description="Number of messages in the queue"),
    ] = 0
    consumer_count: Annotated[
        int,
        Field(title="Consumer Count", description="Number of active consumers"),
    ] = 0
    state: Annotated[
        str,
        Field(title="State", description="Queue state (running, idle, etc.)"),
    ] = "unknown"


class DLQMessageFilter(BaseModel):
    """Filter parameters for listing DLQ messages."""

    queue_name: Annotated[
        Optional[str],
        Field(title="Queue Name", description="Filter by queue name"),
    ] = None
    routing_key: Annotated[
        Optional[str],
        Field(title="Routing Key", description="Filter by routing key"),
    ] = None
    exchange: Annotated[
        Optional[str],
        Field(title="Exchange", description="Filter by exchange name"),
    ] = None
    limit: Annotated[
        int,
        Field(
            title="Limit",
            description="Maximum number of messages to return",
            ge=1,
            le=100,
        ),
    ] = 20
    ack_mode: Annotated[
        str,
        Field(
            title="Ack Mode",
            description="How to handle messages: 'ack_requeue_true' keeps them, 'ack_requeue_false' removes them",
        ),
    ] = "ack_requeue_true"


class RequeueRequest(BaseModel):
    """Request to requeue messages from DLQ to retry queue."""

    queue_name: Annotated[
        str,
        Field(title="Source Queue", description="Queue to requeue messages from"),
    ]
    message_ids: Annotated[
        Optional[List[str]],
        Field(
            title="Message IDs",
            description="Specific message IDs to requeue. If empty, requeues all.",
        ),
    ] = None
    target_exchange: Annotated[
        Optional[str],
        Field(
            title="Target Exchange",
            description="Exchange to requeue to. Defaults to retry exchange.",
        ),
    ] = None
    target_routing_key: Annotated[
        Optional[str],
        Field(
            title="Target Routing Key", description="Routing key for requeued messages."
        ),
    ] = None
    count: Annotated[
        int,
        Field(
            title="Count",
            description="Number of messages to requeue if message_ids not specified",
            ge=1,
            le=100,
        ),
    ] = 10


class DeleteRequest(BaseModel):
    """Request to delete/acknowledge messages from DLQ."""

    queue_name: Annotated[
        str,
        Field(title="Queue Name", description="Queue to delete messages from"),
    ]
    count: Annotated[
        int,
        Field(title="Count", description="Number of messages to delete", ge=1, le=100),
    ] = 1


class DLQListResponse(BaseModel):
    """Response containing list of DLQ messages."""

    success: bool = True
    messages: List[DLQMessage] = []
    total_count: int = 0


class DLQQueuesResponse(BaseModel):
    """Response containing list of DLQ queues."""

    success: bool = True
    queues: List[DLQQueue] = []


class OperationResponse(BaseModel):
    """Response for requeue/delete operations."""

    success: bool
    message: str
    processed_count: int = 0
    errors: List[str] = []
