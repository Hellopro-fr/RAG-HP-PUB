import os
import json
import copy
import pika
from functools import lru_cache
import contextlib

RABBITMQ_URL = os.environ.get("RABBITMQ_URL", "amqp://user:password@localhost:5672/")

class RabbitMQClient:
    """
    A stateless client for publishing messages to RabbitMQ.
    Connection management is handled externally by a context manager.
    """
    
    def _set_nested_value(self, obj: dict, path: str, value) -> None:
        """
        Sets a value at a nested path in the object.
        
        Args:
            obj: The object to modify
            path: Dot-separated path (e.g., "data.chunks.0.embedding")
            value: The value to set at the path
        """
        keys = path.split('.')
        current = obj
        
        for i, key in enumerate(keys[:-1]):
            # Handle list indices
            if key.isdigit():
                key = int(key)
            
            if isinstance(current, dict):
                if key not in current:
                    # Create intermediate dict or list based on next key
                    next_key = keys[i + 1]
                    current[key] = [] if next_key.isdigit() else {}
                current = current[key]
            elif isinstance(current, list):
                while len(current) <= key:
                    next_key = keys[i + 1]
                    current.append([] if next_key.isdigit() else {})
                current = current[key]
        
        # Set the final value
        final_key = keys[-1]
        if final_key.isdigit():
            final_key = int(final_key)
        
        if isinstance(current, dict):
            current[final_key] = value
        elif isinstance(current, list):
            while len(current) <= final_key:
                current.append(None)
            current[final_key] = value
    
    def _restore_embeddings(self, payload: dict, raw_embedding_data: str) -> dict:
        """
        Restores embeddings into the payload from the serialized backup.
        
        Args:
            payload: The sanitized payload with placeholder strings
            raw_embedding_data: JSON string containing {path: embedding_array} mapping
        
        Returns:
            The payload with embeddings restored at their original paths
        """
        try:
            embeddings_dict = json.loads(raw_embedding_data)
            for path, embedding in embeddings_dict.items():
                self._set_nested_value(payload, path, embedding)
            return payload
        except (json.JSONDecodeError, Exception) as e:
            print(f"⚠️ Warning: Failed to restore embeddings: {e}")
            return payload  # Return original payload on failure
    
    def publish_message(self, channel, message: dict):
        """
        Publishes a single message using a provided channel. This is a SYNCHRONOUS method.
        If the message contains serialized embedding data, it will be restored before publishing.
        """
        source = message["_source"]
        original_payload = source.get("original_payload", {})
        original_exchange = source.get("original_exchange")
        original_routing_key = source.get("original_routing_key")

        if not original_exchange or not original_routing_key:
            raise ValueError(f"Message {message['_id']} is missing original exchange or routing key.")

        # Restore embeddings if backup data exists
        raw_embedding_data = source.get("_raw_embedding_data")
        if raw_embedding_data:
            # Deep copy to avoid mutating the original message
            original_payload = copy.deepcopy(original_payload)
            original_payload = self._restore_embeddings(original_payload, raw_embedding_data)
            print(f"✅ Embeddings restored for message {message['_id']}")

        channel.basic_publish(
            exchange=original_exchange,
            routing_key=original_routing_key,
            body=json.dumps(original_payload).encode('utf-8'),
            properties=pika.BasicProperties(delivery_mode=pika.DeliveryMode.Persistent)
        )

@contextlib.contextmanager
def get_rabbitmq_channel():
    """
    A context manager that provides a RabbitMQ channel and ensures the connection is closed.
    """
    connection = None
    try:
        connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
        channel = connection.channel()
        yield channel
    finally:
        if connection and connection.is_open:
            connection.close()

@lru_cache()
def get_rabbitmq_client() -> RabbitMQClient:
    """
    Returns a cached, stateless instance of the RabbitMQClient.
    """
    return RabbitMQClient()