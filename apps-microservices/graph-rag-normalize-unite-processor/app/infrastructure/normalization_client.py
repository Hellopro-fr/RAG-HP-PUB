"""
Normalization Client for graph-rag-normalize-unite-processor.
Uses centralized gRPC client from common_utils.
"""

import asyncio
import logging
import concurrent.futures
from typing import Dict, Any

from common_utils.grpc_clients import graph_normalization_client

from app.config import settings


def _run_async(coro):
    """Run an async coroutine in a new event loop in a separate thread."""
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(asyncio.run, coro)
        return future.result()


class NormalizationClient:
    """gRPC client for graph-rag-normalize-unite-service using centralized client."""

    def __init__(self):
        logging.info(
            f"NormalizationClient initialized for {settings.NORMALIZATION_SERVICE_URL}"
        )

    async def normalize_quantity_async(
        self, label: str, unit: str, value: Any, data_type: str
    ) -> Dict[str, Any]:
        """Call NormalizeQuantity RPC (async)."""
        try:
            result = await graph_normalization_client.normalize_quantity(
                label=label or "",
                unit=unit or "null",
                value=str(value),
                data_type=data_type or "numeric",
            )

            if result.success:
                return {
                    "valeur_canonique": result.canonical_value,
                    "unite_canonique": result.canonical_unit,
                }
            return {}
        except Exception as e:
            logging.error(f"RPC error (normalize_quantity): {e}")
            return {}

    async def normalize_range_async(
        self, label: str, unit: str, min_val: float, max_val: float
    ) -> Dict[str, Any]:
        """Call NormalizeRange RPC (async)."""
        try:
            result = await graph_normalization_client.normalize_range(
                label=label or "",
                unit=unit or "null",
                min_value=float(min_val) if min_val is not None else 0.0,
                max_value=float(max_val) if max_val is not None else 0.0,
            )

            if result.success:
                return {
                    "valeur_min_canonique": result.canonical_min,
                    "valeur_max_canonique": result.canonical_max,
                    "unite_canonique": result.canonical_unit,
                }
            return {}
        except Exception as e:
            logging.error(f"RPC error (normalize_range): {e}")
            return {}

    def normalize_quantity(
        self, label: str, unit: str, value: Any, data_type: str
    ) -> Dict[str, Any]:
        """Call NormalizeQuantity RPC (sync wrapper)."""
        try:
            return _run_async(
                self.normalize_quantity_async(label, unit, value, data_type)
            )
        except Exception as e:
            logging.error(f"Error in normalize_quantity: {e}")
            return {}

    def normalize_range(
        self, label: str, unit: str, min_val: float, max_val: float
    ) -> Dict[str, Any]:
        """Call NormalizeRange RPC (sync wrapper)."""
        try:
            return _run_async(
                self.normalize_range_async(label, unit, min_val, max_val)
            )
        except Exception as e:
            logging.error(f"Error in normalize_range: {e}")
            return {}

    def close(self):
        pass


# Singleton instance
normalization_client = NormalizationClient()
