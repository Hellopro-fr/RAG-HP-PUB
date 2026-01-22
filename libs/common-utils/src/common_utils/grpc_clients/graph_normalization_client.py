import grpc
import os
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass

from grpc_stubs import graph_normalization_pb2
from grpc_stubs import graph_normalization_pb2_grpc

NORMALIZATION_SERVICE_URL = os.getenv("NORMALIZATION_SERVICE_URL", "graph-rag-normalize-unite-service:50051")


@dataclass
class NormalizedQuantity:
    """Result of quantity normalization."""
    success: bool
    canonical_value: float
    canonical_unit: str
    error_message: str = ""


@dataclass
class NormalizedRange:
    """Result of range normalization."""
    success: bool
    canonical_min: float
    canonical_max: float
    canonical_unit: str
    error_message: str = ""


async def normalize_quantity(
    label: str,
    unit: str,
    value: str,
    data_type: str = "numeric"
) -> NormalizedQuantity:
    """
    Normalize a single quantity (value + unit).
    
    Args:
        label: The characteristic label (provides context for normalization).
        unit: The original unit string.
        value: The raw value as string.
        data_type: Type of data ('numeric', 'text', 'list').
        
    Returns:
        NormalizedQuantity with canonical value and unit.
    """
    try:
        async with grpc.aio.insecure_channel(NORMALIZATION_SERVICE_URL) as channel:
            stub = graph_normalization_pb2_grpc.GraphNormalizationServiceStub(channel)
            request = graph_normalization_pb2.NormalizeQuantityRequest(
                label=label or "",
                unit=unit or "null",
                value=str(value),
                data_type=data_type or "numeric"
            )
            response = await stub.NormalizeQuantity(request)
            
            return NormalizedQuantity(
                success=response.success,
                canonical_value=response.canonical_value,
                canonical_unit=response.canonical_unit,
                error_message=response.error_message
            )
    except grpc.aio.AioRpcError as e:
        logging.error(f"gRPC error normalizing quantity: {e.details()}")
        raise e


async def normalize_range(
    label: str,
    unit: str,
    min_value: float,
    max_value: float,
    data_type: str = "numeric"
) -> NormalizedRange:
    """
    Normalize a numeric range (min/max + unit).
    
    Args:
        label: The characteristic label (provides context for normalization).
        unit: The original unit string.
        min_value: Minimum value of the range.
        max_value: Maximum value of the range.
        data_type: Type of data ('numeric', 'text', 'list').
        
    Returns:
        NormalizedRange with canonical min, max, and unit.
    """
    try:
        async with grpc.aio.insecure_channel(NORMALIZATION_SERVICE_URL) as channel:
            stub = graph_normalization_pb2_grpc.GraphNormalizationServiceStub(channel)
            request = graph_normalization_pb2.NormalizeRangeRequest(
                label=label or "",
                unit=unit or "null",
                min_value=float(min_value) if min_value is not None else 0.0,
                max_value=float(max_value) if max_value is not None else 0.0,
                data_type=data_type or "numeric"
            )
            response = await stub.NormalizeRange(request)
            
            return NormalizedRange(
                success=response.success,
                canonical_min=response.canonical_min,
                canonical_max=response.canonical_max,
                canonical_unit=response.canonical_unit,
                error_message=response.error_message
            )
    except grpc.aio.AioRpcError as e:
        logging.error(f"gRPC error normalizing range: {e.details()}")
        raise e
