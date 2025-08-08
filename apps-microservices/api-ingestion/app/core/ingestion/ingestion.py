from enum import Enum
from libs.common_utils.autres.CollectionName import CollectionName, RoutingKeys as collections


def routing_key_collection(collection: CollectionName):
    # Use .get() to provide a default value if the key is not found
    return collections.get(collection, "")


