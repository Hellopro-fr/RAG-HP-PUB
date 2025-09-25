import pika

class DLQProperties:
    @staticmethod
    def create_dlq_properties(error: Exception, service_name: str, retry_count: int, method: pika.spec.Basic.Deliver) -> pika.BasicProperties:
        """
        Crée les propriétés pour un message DLQ, incluant les informations d'erreur et de retry.
        """
        headers = {
            'x-error-reason': str(error),
            'x-service-name': service_name,
            'x-retry-count': retry_count,
            'x-original-exchange': method.exchange,
            'x-original-routing-key': method.routing_key
        }
        return pika.BasicProperties(headers=headers, delivery_mode=pika.DeliveryMode.Persistent)