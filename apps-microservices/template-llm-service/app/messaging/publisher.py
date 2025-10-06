import aio_pika
import json
import logging 
# import os
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
            base_name = message_dict.get("base_name")

            log_file = f"{base_name}.txt"

            # Créer un logger spécifique pour ce document (pas le logger root)
            logger = logging.getLogger(f"doc_processor_{base_name}")
            logger.setLevel(logging.INFO)
            
            # Supprimer les handlers existants pour ce logger
            logger.handlers.clear()
            
            # Ajouter les nouveaux handlers
            file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
            file_handler.setLevel(logging.INFO)
            file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
            
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            console_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
            
            logger.addHandler(file_handler)
            logger.addHandler(console_handler)
            
            # Empêcher la propagation au logger root
            logger.propagate = False
            
            page_type = message_dict.get("data", {}).get("page_type", "Inconnu")
            logger.info(f"page_type : {page_type}")
            
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