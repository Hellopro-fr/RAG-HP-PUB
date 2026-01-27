import grpc
import logging
from concurrent import futures

from grpc_stubs import graph_normalization_pb2
from grpc_stubs import graph_normalization_pb2_grpc

from application.normalization_use_case import NormalizationUseCase
from app.config import settings


class GraphNormalizationServiceImpl(
    graph_normalization_pb2_grpc.GraphNormalizationServiceServicer
):
    """gRPC Service Implementation for Unit Normalization."""

    def __init__(self, use_case: NormalizationUseCase):
        self.use_case = use_case

    def NormalizeQuantity(self, request, context):
        """Handle NormalizeQuantity RPC."""
        logging.info(
            f"NormalizeQuantity request: label='{request.label}', value='{request.value}', unit='{request.unit}'"
        )
        try:
            result = self.use_case.normalize_quantity(
                label=request.label,
                unit=request.unit,
                value=request.value,
                data_type=request.data_type,
            )

            if result:
                return graph_normalization_pb2.NormalizeQuantityResponse(
                    success=True,
                    canonical_value=result.get("valeur_canonique", 0.0),
                    canonical_unit=result.get("unite_canonique", ""),
                    error_message="",
                )
            else:
                return graph_normalization_pb2.NormalizeQuantityResponse(
                    success=False,
                    error_message=f"Could not normalize value for label '{request.label}'",
                )

        except Exception as e:
            logging.error(f"NormalizeQuantity error: {e}", exc_info=True)
            return graph_normalization_pb2.NormalizeQuantityResponse(
                success=False, error_message=str(e)
            )

    def NormalizeRange(self, request, context):
        """Handle NormalizeRange RPC."""
        logging.info(
            f"NormalizeRange request: label='{request.label}', range=[{request.min_value}, {request.max_value}], unit='{request.unit}'"
        )
        try:
            result = self.use_case.normalize_range(
                label=request.label,
                unit=request.unit,
                min_value=request.min_value,
                max_value=request.max_value,
            )

            if result:
                return graph_normalization_pb2.NormalizeRangeResponse(
                    success=True,
                    canonical_min=result.get("valeur_min_canonique", 0.0),
                    canonical_max=result.get("valeur_max_canonique", 0.0),
                    canonical_unit=result.get("unite_canonique", ""),
                    error_message="",
                )
            else:
                return graph_normalization_pb2.NormalizeRangeResponse(
                    success=False,
                    error_message=f"Could not normalize range for label '{request.label}'",
                )

        except Exception as e:
            logging.error(f"NormalizeRange error: {e}", exc_info=True)
            return graph_normalization_pb2.NormalizeRangeResponse(
                success=False, error_message=str(e)
            )


def serve(use_case: NormalizationUseCase):
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=settings.GRPC_MAX_WORKERS)
    )
    graph_normalization_pb2_grpc.add_GraphNormalizationServiceServicer_to_server(
        GraphNormalizationServiceImpl(use_case), server
    )
    server.add_insecure_port(f"[::]:{settings.GRPC_PORT}")
    logging.info(
        f"gRPC Graph Normalization Service started on port {settings.GRPC_PORT}..."
    )
    server.start()
    server.wait_for_termination()
