"""
Shared threading lock for pymilvus connection management.

All Milvus CRUD and Inserer classes share the pymilvus "default" connection alias,
which is a process-wide singleton. This module provides a single lock to serialize
all connect/disconnect operations across classes, preventing race conditions.
"""

import threading

milvus_connection_lock = threading.Lock()
