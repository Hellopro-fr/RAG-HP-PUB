import pika
import json
from app.messaging.publisher import Publisher
from app.core.qualifier.service import QualifierService

# Le système de lazy loading du service LLM reste identique
qualifier_service_instance: QualifierService | None = None

def get_qualifier_service() -> QualifierService:
    global qualifier_service_instance
    if qualifier_service_instance is None:
        print("--- LAZY LOADING: Initialisation du QualifierService (chargement du modèle)... ---")
        qualifier_service_instance = QualifierService()
        print("--- LAZY LOADING: Service initialisé et prêt. ---")
    return qualifier_service_instance

class Consumer:
    def __init__(self, connection: pika.BlockingConnection, publisher: Publisher):
        self.channel = connection.channel()
        self.publisher = publisher
        
        # --- MODIFICATIONS ICI POUR CORRESPONDRE AU FLUX ---
        # On écoute sur un exchange où les données prêtes pour la classification arrivent.
        # On peut supposer que c'est 'processed_data_exchange' ou un autre nom logique.
        # Utilisons un nom clair pour l'instant.
        self.exchange_name = 'cleaned_data_exchange' # Hypothèse : un service de nettoyage publie ici.
        self.routing_key = 'data.ready_for_templating' # La clé exacte que vous avez fournie.
        self.queue_name = 'llm_templating_queue'
        # --- FIN DES MODIFICATIONS ---

        self.channel.exchange_declare(exchange=self.exchange_name, exchange_type='topic', durable=True)
        self.channel.queue_declare(queue=self.queue_name, durable=True)
        self.channel.queue_bind(exchange=self.exchange_name, queue=self.queue_name, routing_key=self.routing_key)
        print(f"✅ Consumer initialisé, en écoute de '{self.routing_key}' sur l'exchange '{self.exchange_name}'.")

    def _on_message_callback(self, ch, method, properties, body):
        try:
            message = json.loads(body)
            print(f"\n📥 template-llm-service: Message reçu pour templating (classification).")

            service = get_qualifier_service()

            data_payload = message.get("data", {})
            url = data_payload.get("url", "URL non fournie")
            content = data_payload.get("content", "")

            if not content:
                print("   -> Contenu vide, message ignoré.")
                ch.basic_ack(delivery_tag=method.delivery_tag)
                return

            type_page, _, _ = service.classify(url=url, content=content)
            
            print(f"   -> Classification terminée : {type_page}")

            # On enrichit le message original avec le type de page
            message["classification_result"] = {
                "type_page": type_page
            }
            
            self.publisher.publish_message(message)

        except Exception as e:
            print(f"❌ Erreur lors du traitement du message : {e}")
        
        finally:
            ch.basic_ack(delivery_tag=method.delivery_tag)

    def start_consuming(self):
        self.channel.basic_consume(queue=self.queue_name, on_message_callback=self._on_message_callback)
        print("👂 template-llm-service: En attente de messages...")
        self.channel.start_consuming()