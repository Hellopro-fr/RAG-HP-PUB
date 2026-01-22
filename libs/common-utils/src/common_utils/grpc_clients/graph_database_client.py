import grpc
import os
import logging
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass

from google.protobuf import struct_pb2
from google.protobuf.json_format import MessageToDict

from grpc_stubs import graph_database_pb2
from grpc_stubs import graph_database_pb2_grpc

GRAPH_DATABASE_SERVICE_URL = os.getenv("GRAPH_DATABASE_SERVICE_URL", "graph-rag-database-connector-service:50051")


@dataclass
class PropertyInfo:
    """Property information for nodes or relationships."""
    name: str
    data_type: str
    indexed: bool
    unique: bool


@dataclass
class NodeLabel:
    """Node label with its properties."""
    name: str
    properties: List[PropertyInfo]


@dataclass
class RelationshipType:
    """Relationship type with its properties."""
    name: str
    source_label: str
    target_label: str
    properties: List[PropertyInfo]


@dataclass
class GraphSchema:
    """Complete graph schema information."""
    node_labels: List[NodeLabel]
    relationship_types: List[RelationshipType]
    schema_text: str


@dataclass
class BatchResult:
    """Result for a single statement in a batch execution."""
    index: int
    success: bool
    error_message: str
    records_affected: int


def _dict_to_struct(d: Dict[str, Any]) -> struct_pb2.Struct:
    """Convert a Python dictionary to a protobuf Struct."""
    struct = struct_pb2.Struct()
    if d:
        struct.update(d)
    return struct


async def execute_cypher(
    query: str,
    parameters: Optional[Dict[str, Any]] = None,
    read_only: bool = False
) -> Tuple[bool, List[Dict[str, Any]], int]:
    """
    Execute a single Cypher query.
    
    Args:
        query: The Cypher query to execute.
        parameters: Query parameters as key-value pairs.
        read_only: If true, execute in read-only mode.
        
    Returns:
        Tuple of (success, results as list of dicts, records_affected).
    """
    try:
        async with grpc.aio.insecure_channel(GRAPH_DATABASE_SERVICE_URL) as channel:
            stub = graph_database_pb2_grpc.GraphDatabaseServiceStub(channel)
            
            request = graph_database_pb2.ExecuteCypherRequest(
                cypher_query=query,
                parameters=_dict_to_struct(parameters or {}),
                read_only=read_only
            )
            response = await stub.ExecuteRawCypher(request)
            
            # Convert results from Struct to dict
            results = [
                MessageToDict(result_struct, preserving_proto_field_name=True)
                for result_struct in response.results
            ]
            
            return response.success, results, response.records_affected
    except grpc.aio.AioRpcError as e:
        logging.error(f"gRPC error executing Cypher: {e.details()}")
        raise e


async def execute_batch_cypher(
    statements: List[Dict[str, Any]],
    transactional: bool = True
) -> Tuple[bool, str, List[BatchResult]]:
    """
    Execute multiple Cypher queries in a batch.
    
    Args:
        statements: List of dicts with 'query' and optional 'parameters' keys.
        transactional: If true, rollback all on any failure.
        
    Returns:
        Tuple of (success, error_message, list of BatchResult).
    """
    try:
        async with grpc.aio.insecure_channel(GRAPH_DATABASE_SERVICE_URL) as channel:
            stub = graph_database_pb2_grpc.GraphDatabaseServiceStub(channel)
            
            pb_statements = []
            for stmt in statements:
                pb_statements.append(
                    graph_database_pb2.CypherStatement(
                        cypher_query=stmt["query"],
                        parameters=_dict_to_struct(stmt.get("parameters", {}))
                    )
                )
            
            request = graph_database_pb2.ExecuteBatchCypherRequest(
                statements=pb_statements,
                transactional=transactional
            )
            response = await stub.ExecuteBatchCypher(request)
            
            batch_results = [
                BatchResult(
                    index=res.index,
                    success=res.success,
                    error_message=res.error_message,
                    records_affected=res.records_affected
                )
                for res in response.results
            ]
            
            return response.success, response.error_message, batch_results
    except grpc.aio.AioRpcError as e:
        logging.error(f"gRPC error executing batch Cypher: {e.details()}")
        raise e


async def get_graph_schema(
    include_properties: bool = True,
    include_indexes: bool = False
) -> GraphSchema:
    """
    Get the current graph schema.
    
    Args:
        include_properties: If true, include property type information.
        include_indexes: If true, include index information.
        
    Returns:
        GraphSchema object with node labels, relationship types, and schema text.
    """
    try:
        async with grpc.aio.insecure_channel(GRAPH_DATABASE_SERVICE_URL) as channel:
            stub = graph_database_pb2_grpc.GraphDatabaseServiceStub(channel)
            
            request = graph_database_pb2.GetGraphSchemaRequest(
                include_properties=include_properties,
                include_indexes=include_indexes
            )
            response = await stub.GetGraphSchema(request)
            
            node_labels = [
                NodeLabel(
                    name=nl.name,
                    properties=[
                        PropertyInfo(
                            name=p.name,
                            data_type=p.data_type,
                            indexed=p.indexed,
                            unique=p.unique
                        )
                        for p in nl.properties
                    ]
                )
                for nl in response.node_labels
            ]
            
            relationship_types = [
                RelationshipType(
                    name=rt.name,
                    source_label=rt.source_label,
                    target_label=rt.target_label,
                    properties=[
                        PropertyInfo(
                            name=p.name,
                            data_type=p.data_type,
                            indexed=p.indexed,
                            unique=p.unique
                        )
                        for p in rt.properties
                    ]
                )
                for rt in response.relationship_types
            ]
            
            return GraphSchema(
                node_labels=node_labels,
                relationship_types=relationship_types,
                schema_text=response.schema_text
            )
    except grpc.aio.AioRpcError as e:
        logging.error(f"gRPC error getting graph schema: {e.details()}")
        raise e


async def setup_schema(
    apply_constraints: bool = True,
    apply_indexes: bool = True
) -> Tuple[bool, str, List[str], List[str]]:
    """
    Setup constraints and indexes for the graph.
    
    Args:
        apply_constraints: If true, apply constraint setup.
        apply_indexes: If true, apply index setup.
        
    Returns:
        Tuple of (success, message, applied_constraints, applied_indexes).
    """
    try:
        async with grpc.aio.insecure_channel(GRAPH_DATABASE_SERVICE_URL) as channel:
            stub = graph_database_pb2_grpc.GraphDatabaseServiceStub(channel)
            
            request = graph_database_pb2.SetupSchemaRequest(
                apply_constraints=apply_constraints,
                apply_indexes=apply_indexes
            )
            response = await stub.SetupSchema(request)
            
            return (
                response.success,
                response.message,
                list(response.applied_constraints),
                list(response.applied_indexes)
            )
    except grpc.aio.AioRpcError as e:
        logging.error(f"gRPC error setting up schema: {e.details()}")
        raise e
