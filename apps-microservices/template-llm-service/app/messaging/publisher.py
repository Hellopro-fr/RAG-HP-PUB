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
        print(f"✅ Publisher initialisé (vers exchange '{self.exchange_name}').")

    async def publish_message(self, message_dict: dict, channel: aio_pika.abc.AbstractChannel):
        """
        Publie un message de manière asynchrone sur le canal fourni.
        """

        log_file = message_dict.get("log_file")
        collection = message_dict.get("collection")
        
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
        print(f"   📤 Message classifié publié '{message_dict}'.")