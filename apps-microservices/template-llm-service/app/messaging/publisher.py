import aio_pika
import json
import logging 
import os
class Publisher:
    def __init__(self, connection: aio_pika.RobustConnection):
        """
        Initialise le publisher asynchrone.
        """
        self.connection = connection
        self.exchange_name = 'processed_data_exchange'
        self.routing_key = 'data.ready_for_embedding'
        self.metric_routing_key = 'metrics.deepseek.result'
        print(f"✅ Publisher initialisé (vers exchange '{self.exchange_name}').")

    async def publish_message(self, message_dict: dict, channel: aio_pika.abc.AbstractChannel):
        """
        Publie un message de manière asynchrone sur le canal fourni.
        """

        log_file = message_dict.get("log_file")
        collection = message_dict.get("collection")
        
        self.routing_key = "data.document.ready_for_insertion" if collection == "document" else "data.ready_for_embedding"
        self.exchange_name = "inserted_data_exchange" if collection == "document" else "processed_data_exchange"

        if log_file and collection == "document":
            # os.makedirs(os.path.dirname(log_file), exist_ok=True)
            page_type = message_dict.get("data", {}).get("page_type", "Inconnu")

            log_path = os.path.join("/app", log_file)  # chemin absolu vers /app
            os.makedirs(os.path.dirname(log_path), exist_ok=True)

            with open(log_path, "a+", encoding="utf-8") as f:
                f.write(f"\npage_type : {page_type}\n")  # écriture simple
            
            if not log_file:
                print(f"⚠️ Collection {collection}: Aucun 'log_file' défini dans message_dict. Le logging fichier sera ignoré.")


        # La déclaration de l'exchange est idempotente et rapide, on s'assure qu'elle existe.
        exchange = await channel.get_exchange(self.exchange_name, ensure=True)
        
        await exchange.publish(
            aio_pika.Message(
                body=json.dumps(message_dict).encode('utf-8'),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            ),
            routing_key=self.routing_key
        )
        print(f"   📤 Message classifié publié avec la clé '{self.routing_key}'.")

    async def publish_metric_message(self, metric_dict: dict, channel: aio_pika.abc.AbstractChannel):
        """
        Publie un message de métrique de manière asynchrone sur le canal fourni.
        """
        exchange = await channel.get_exchange(self.exchange_name, ensure=True)
        
        await exchange.publish(
            aio_pika.Message(
                body=json.dumps(metric_dict).encode('utf-8'),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            ),
            routing_key=self.metric_routing_key
        )