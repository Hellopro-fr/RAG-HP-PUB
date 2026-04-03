import pika

class DLQProperties:
    @staticmethod
    def create_dlq_headers(error: Exception, service_name: str, retry_count: int, message_or_method) -> dict:
        """
        Creates a dictionary of headers for a DLQ message, compatible with both pika and aio-pika.
        It inspects the object to find the required attributes.
        """
        original_exchange = 'N/A'
        original_routing_key = 'N/A'

        # Duck-typing to check for attributes from either library's object
        if hasattr(message_or_method, 'exchange'):
            original_exchange = message_or_method.exchange or 'N/A' # aio-pika can have None here
        
        if hasattr(message_or_method, 'routing_key'):
            original_routing_key = message_or_method.routing_key or 'N/A' # aio-pika can have None here
        
        headers = {
            'x-error-reason': repr(error),
            'x-service-name': service_name,
            'x-retry-count': retry_count,
            'x-original-exchange': original_exchange,
            'x-original-routing-key': original_routing_key
        }
        return headers

    @staticmethod
    def create_dlq_properties(error: Exception, service_name: str, retry_count: int, method: pika.spec.Basic.Deliver) -> pika.BasicProperties:
        """
        Creates pika.BasicProperties for a DLQ message. For backward compatibility with blocking consumers.
        """
        headers = DLQProperties.create_dlq_headers(error, service_name, retry_count, method)
        return pika.BasicProperties(headers=headers, delivery_mode=pika.DeliveryMode.Persistent)