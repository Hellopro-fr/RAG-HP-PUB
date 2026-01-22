import aio_pika
import json
import logging
from app.messaging.publisher import Publisher
from app.core.downloader import Downloader

logger = logging.getLogger(__name__)

class Consumer:
    def __init__(self, connection: aio_pika.RobustConnection, publisher: Publisher):
        self.connection = connection
        self.publisher = publisher
        self.downloader = Downloader()
        self.queue_name = "image_download_tasks_queue"
        self.routing_key = "new_data.product" # Trigger on new product ingestion
        self.exchange_name = "data_exchange_produits" # Matches API Ingestion exchange for products

    async def start_consuming(self):
        try:
            channel = await self.connection.channel()
            # Declare exchange if not exists (assuming topic)
            exchange = await channel.declare_exchange(self.exchange_name, aio_pika.ExchangeType.TOPIC, durable=True)
            
            queue = await channel.declare_queue(self.queue_name, durable=True)
            await queue.bind(exchange, self.routing_key)
            
            logger.info(f"[*] Waiting for messages in {self.queue_name}")
            
            await queue.consume(self.process_message)
        except Exception as e:
            logger.error(f"Failed to start consumer: {e}")

    async def process_message(self, message: aio_pika.abc.AbstractIncomingMessage):
        async with message.process():
            try:
                body = message.body.decode()
                data = json.loads(body)
                
                logger.info(f"Received task for product {data.get('id_produit')}")
                
                # Process download
                result_data = await self.downloader.process_product(data)
                
                # Publish result (images downloaded)
                # We could add a check if any images were actually downloaded
                if result_data.get("local_image_paths"):
                    await self.publisher.publish_update(result_data)
                
            except Exception as e:
                logger.error(f"Error processing message: {e}")
