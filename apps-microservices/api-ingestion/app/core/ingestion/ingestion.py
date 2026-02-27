from enum import Enum
from common_utils.autres.CollectionName import (
    CollectionName,
    CollectionNameGraph,
    RoutingKeys as collections,
    RoutingKeysGraph as graph_collections,
)


def routing_key_collection(collection: CollectionName):
    # Use .get() to provide a default value if the key is not found
    return collections.get(collection, "")


def routing_key_collection_graph(collection: CollectionNameGraph):
    # Use .get() to provide a default value if the key is not found
    return graph_collections.get(collection, "")
