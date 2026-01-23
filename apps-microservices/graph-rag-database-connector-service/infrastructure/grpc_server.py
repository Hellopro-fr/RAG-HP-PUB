import grpc
import logging
from concurrent import futures
from typing import Dict, Any

from google.protobuf import struct_pb2

from grpc_stubs import graph_database_pb2
from grpc_stubs import graph_database_pb2_grpc

from application.graph_database_use_case import GraphDatabaseUseCase
from app.config import settings


def dict_to_struct(d: Dict[str, Any]) -> struct_pb2.Struct:
    """Convert a Python dictionary to a protobuf Struct."""
    struct = struct_pb2.Struct()
    if d:
        struct.update(d)
    return struct


def struct_to_dict(struct: struct_pb2.Struct) -> Dict[str, Any]:
    """Convert a protobuf Struct to a Python dictionary."""
    from google.protobuf.json_format import MessageToDict

    return MessageToDict(struct, preserving_proto_field_name=True)


class GraphDatabaseServiceImpl(graph_database_pb2_grpc.GraphDatabaseServiceServicer):
    """gRPC service implementation for Neo4j graph database operations."""

    def __init__(self, use_case: GraphDatabaseUseCase):
        self.use_case = use_case

    async def ExecuteRawCypher(self, request, context):
        """Execute a single Cypher query."""
        logging.info(
            f"ExecuteRawCypher request received: {request.cypher_query[:100]}..."
        )

        try:
            parameters = (
                struct_to_dict(request.parameters) if request.parameters else None
            )

            # Debug: Log parameters with their types
            if parameters:
                logging.debug(f"📝 Parameters received:")
                for key, value in parameters.items():
                    logging.debug(f"   {key}: {value} (type: {type(value).__name__})")

            results, records_affected = self.use_case.execute_cypher(
                query=request.cypher_query,
                parameters=parameters,
                read_only=request.read_only,
            )

            # Convert results to protobuf structs
            result_structs = [dict_to_struct(r) for r in results] if results else []

            return graph_database_pb2.ExecuteCypherResponse(
                success=True,
                error_message="",
                results=result_structs,
                records_affected=records_affected,
            )
        except Exception as e:
            logging.error(f"ExecuteRawCypher error: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return graph_database_pb2.ExecuteCypherResponse(
                success=False, error_message=str(e), results=[], records_affected=0
            )

    async def ExecuteBatchCypher(self, request, context):
        """Execute multiple Cypher queries in batch."""
        logging.info(
            f"ExecuteBatchCypher request received: {len(request.statements)} statements"
        )

        try:
            # Convert protobuf statements to tuples
            statements = []
            for stmt in request.statements:
                params = struct_to_dict(stmt.parameters) if stmt.parameters else {}
                statements.append((stmt.cypher_query, params))

            results = self.use_case.execute_batch_cypher(
                statements=statements, transactional=request.transactional
            )

            # Convert results to protobuf BatchResult messages
            batch_results = []
            all_success = True
            error_msg = ""

            for idx, (success, err_msg, affected) in enumerate(results):
                batch_results.append(
                    graph_database_pb2.BatchResult(
                        index=idx,
                        success=success,
                        error_message=err_msg,
                        records_affected=affected,
                    )
                )
                if not success:
                    all_success = False
                    if not error_msg:
                        error_msg = err_msg

            return graph_database_pb2.ExecuteBatchCypherResponse(
                success=all_success, error_message=error_msg, results=batch_results
            )
        except Exception as e:
            logging.error(f"ExecuteBatchCypher error: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return graph_database_pb2.ExecuteBatchCypherResponse(
                success=False, error_message=str(e), results=[]
            )

    async def GetGraphSchema(self, request, context):
        """Get the graph schema."""
        logging.info("GetGraphSchema request received")

        try:
            schema_info = self.use_case.get_schema(
                include_properties=request.include_properties,
                include_indexes=request.include_indexes,
            )

            # Convert node labels
            node_labels = []
            for label_info in schema_info.get("node_labels", []):
                props = [
                    graph_database_pb2.PropertyInfo(
                        name=p["name"],
                        data_type=p.get("data_type", "Unknown"),
                        indexed=p.get("indexed", False),
                        unique=p.get("unique", False),
                    )
                    for p in label_info.get("properties", [])
                ]
                node_labels.append(
                    graph_database_pb2.NodeLabel(
                        name=label_info["name"], properties=props
                    )
                )

            # Convert relationship types
            rel_types = []
            for rel_info in schema_info.get("relationship_types", []):
                props = [
                    graph_database_pb2.PropertyInfo(
                        name=p["name"],
                        data_type=p.get("data_type", "Unknown"),
                        indexed=p.get("indexed", False),
                        unique=p.get("unique", False),
                    )
                    for p in rel_info.get("properties", [])
                ]
                rel_types.append(
                    graph_database_pb2.RelationshipType(
                        name=rel_info["name"],
                        source_label=rel_info.get("source_label", ""),
                        target_label=rel_info.get("target_label", ""),
                        properties=props,
                    )
                )

            return graph_database_pb2.GetGraphSchemaResponse(
                node_labels=node_labels,
                relationship_types=rel_types,
                schema_text=schema_info.get("schema_text", ""),
            )
        except Exception as e:
            logging.error(f"GetGraphSchema error: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return graph_database_pb2.GetGraphSchemaResponse()

    async def SetupSchema(self, request, context):
        """Setup constraints and indexes."""
        logging.info("SetupSchema request received")

        try:
            constraints, indexes = self.use_case.setup_schema(
                apply_constraints=request.apply_constraints,
                apply_indexes=request.apply_indexes,
            )

            return graph_database_pb2.SetupSchemaResponse(
                success=True,
                message=f"Applied {len(constraints)} constraints and {len(indexes)} indexes",
                applied_constraints=constraints,
                applied_indexes=indexes,
            )
        except Exception as e:
            logging.error(f"SetupSchema error: {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return graph_database_pb2.SetupSchemaResponse(
                success=False,
                message=str(e),
                applied_constraints=[],
                applied_indexes=[],
            )


async def serve(use_case: GraphDatabaseUseCase):
    """Start the gRPC server."""
    server = grpc.aio.server(
        futures.ThreadPoolExecutor(max_workers=settings.GRPC_MAX_WORKERS)
    )
    graph_database_pb2_grpc.add_GraphDatabaseServiceServicer_to_server(
        GraphDatabaseServiceImpl(use_case), server
    )
    server.add_insecure_port(f"[::]:{settings.GRPC_PORT}")
    logging.info(f"gRPC Graph Database Service started on port {settings.GRPC_PORT}...")
    await server.start()
    await server.wait_for_termination()
