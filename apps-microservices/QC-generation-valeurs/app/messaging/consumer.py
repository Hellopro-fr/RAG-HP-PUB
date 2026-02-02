import pika
import json
import asyncio
import traceback
from app.messaging.publisher import Publisher
from app.core.info_caracteristiques_generator import InfoCaracteristiquesGenerator
from app.core.api_client import HelloProAPIClient
from app.schemas.question_caracteristique import RequestProcessus
from common_utils.rabbitmq.rabbitmq_connection import RabbitMQConnection
from common_utils.autres.DLQProperties import DLQProperties

MAX_RETRIES = 3
RETRY_TTL_MS = 30000

class Consumer:
    """Consumer pour le service QC-generation-valeurs (step 4)."""
    def __init__(self, connection: pika.BlockingConnection, publisher: Publisher):
        self.connection = connection
        self.channel = connection.channel()
        self.publisher = publisher
        
        self.exchange_name = 'qc_pipeline_exchange'
        self.routing_key = 'qc.step4.start'
        self.queue_name = 'qc_valeurs_queue'
        self.retry_exchange = 'qc_retry_exchange'
        self.retry_queue_name = f'{self.queue_name}_retry'
        self.dead_letter_exchange = 'qc_dead_letter_exchange'
        self.dead_letter_queue_name = f'{self.queue_name}_dlq'
        
        self.rabbitmq_connection = RabbitMQConnection()
        self.connect()
        print("✅ QC-Valeurs Consumer initialisé.")
    
    def connect(self):
        """Établit la connexion et configure le consumer."""
        self.connection = self.rabbitmq_connection.create_connection(max_retries=10, retry_delay=5)
        self.channel = self.connection.channel()

        # Infrastructure DLQ
        self.channel.exchange_declare(exchange=self.dead_letter_exchange, exchange_type='topic', durable=True)
        self.channel.queue_declare(queue=self.dead_letter_queue_name, durable=True)
        self.channel.queue_bind(exchange=self.dead_letter_exchange, queue=self.dead_letter_queue_name, routing_key=self.routing_key)

        # Infrastructure Retry
        self.channel.exchange_declare(exchange=self.retry_exchange, exchange_type='topic', durable=True)
        retry_queue_args = {
            'x-message-ttl': RETRY_TTL_MS,
            'x-dead-letter-exchange': self.exchange_name,
            'x-dead-letter-routing-key': self.routing_key
        }
        self.channel.queue_declare(queue=self.retry_queue_name, durable=True, arguments=retry_queue_args)
        self.channel.queue_bind(exchange=self.retry_exchange, queue=self.retry_queue_name, routing_key=self.routing_key)

        # Queue Principale
        self.channel.exchange_declare(exchange=self.exchange_name, exchange_type='topic', durable=True)
        main_queue_args = {
            'x-dead-letter-exchange': self.retry_exchange,
            'x-dead-letter-routing-key': self.routing_key
        }
        self.channel.queue_declare(queue=self.queue_name, durable=True, arguments=main_queue_args)
        self.channel.queue_bind(exchange=self.exchange_name, queue=self.queue_name, routing_key=self.routing_key)
        
        # Mettre à jour la connexion du publisher
        self.publisher.connection = self.connection
        self.publisher.channel = self.channel
    
    def _ensure_channel_open(self, ch):
        """Vérifie que le channel est ouvert, sinon reconnecte."""
        try:
            if ch.is_closed or not ch.connection or ch.connection.is_closed:
                print("⚠️ Channel/Connection fermé, reconnexion...")
                self.connect()
                return self.channel
            return ch
        except:
            print("⚠️ Erreur lors de la vérification du channel, reconnexion...")
            self.connect()
            return self.channel
    
    def _is_transient_error(self, exception: Exception) -> bool:
        """Détermine si une erreur est transitoire."""
        if isinstance(exception, (
            pika.exceptions.AMQPConnectionError,
            pika.exceptions.AMQPChannelError,
            pika.exceptions.ConnectionClosedByBroker,
            pika.exceptions.ChannelClosedByBroker,
            pika.exceptions.StreamLostError,
            pika.exceptions.ChannelWrongStateError
        )):
            return True
        
        error_msg = str(exception).lower()
        transient_keywords = [
            'timeout', 'connection reset', 'connection refused',
            'temporarily unavailable', 'service unavailable', 'timed out',
            'network unreachable', 'connection aborted', 'broken pipe',
            'eof', 'end of file'
        ]
        return any(keyword in error_msg for keyword in transient_keywords)
    
    def _get_retry_count(self, properties):
        """Récupère le nombre de tentatives depuis les headers x-death."""
        if properties.headers and 'x-death' in properties.headers:
            for death in properties.headers['x-death']:
                if death.get('queue') == self.retry_queue_name:
                    return death.get('count', 0)
        return 0
    
    def _send_to_dlq(self, ch, method, body, error: Exception, retry_count: int):
        """Envoie directement le message vers la DLQ."""
        print(f"❌ Erreur métier/permanente. Envoi direct à la DLQ. Erreur: {error}")
        try:
            dlq_props = DLQProperties.create_dlq_properties(error, 'qc-generation-valeurs', retry_count, method)
            active_ch = self._ensure_channel_open(ch)
            active_ch.basic_publish(
                exchange=self.dead_letter_exchange,
                routing_key=self.routing_key,
                body=body,
                properties=dlq_props
            )
            active_ch.basic_ack(delivery_tag=method.delivery_tag)
        except Exception as dlq_error:
            print(f"❌ Erreur lors de l'envoi DLQ: {dlq_error}")
            try:
                self.connect()
                self.channel.basic_publish(
                    exchange=self.dead_letter_exchange,
                    routing_key=self.routing_key,
                    body=body,
                    properties=dlq_props
                )
                self.channel.basic_ack(delivery_tag=method.delivery_tag)
                print("✅ Message envoyé à la DLQ après reconnexion")
            except:
                print("❌ Impossible d'envoyer à la DLQ même après reconnexion")
    
    def _on_message_callback(self, ch, method, properties, body):
        """Callback qui traite chaque message reçu."""
        try:
            print("📥 QC-Valeurs: Message reçu.")
            data = json.loads(body)
            id_categorie = data.get('id_categorie')
            is_reset = data.get('is_reset', False)
            if not id_categorie:
                raise ValueError("id_categorie manquant.")
            
            print(f"\n📥 QC-Valeurs: Traitement catégorie '{id_categorie}'.")
            
            request = RequestProcessus(id_categorie=id_categorie, is_reset=is_reset)
            api_client = HelloProAPIClient()
            generator = InfoCaracteristiquesGenerator(api_client)
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(generator.generate_all_caracteristiques(request))
                loop.run_until_complete(generator.close())
            finally:
                pending = asyncio.all_tasks(loop)
                if pending:
                    loop.run_until_complete(
                        asyncio.wait_for(
                            asyncio.gather(*pending, return_exceptions=True),
                            timeout=5.0
                        )
                    )
                loop.close()
            
            output_message = {
                'id_categorie': id_categorie,
                'is_reset': is_reset,
                'step': 5,
                'previous_step': 'valeurs',
                'status': result.status
            }
            
            self.publisher.publish_message(output_message)
            
            active_ch = self._ensure_channel_open(ch)
            active_ch.basic_ack(delivery_tag=method.delivery_tag)
            print(f"✅ QC-Valeurs: Catégorie '{id_categorie}' traitée.")
            
        except (json.JSONDecodeError, ValueError) as e:
            self._send_to_dlq(ch, method, body, e, 0)
        
        except Exception as e:
            print(f"❌ ERREUR FATALE: {e}")
            print(f"📋 Traceback complet:\n{traceback.format_exc()}")
            
            if self._is_transient_error(e):
                retry_count = self._get_retry_count(properties)
                if retry_count < MAX_RETRIES:
                    print(f"⚠️ Erreur transitoire (essai {retry_count + 1}/{MAX_RETRIES + 1}). Erreur: {e}")
                    try:
                        active_ch = self._ensure_channel_open(ch)
                        active_ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
                    except Exception as nack_error:
                        print(f"⚠️ Erreur lors du NACK: {nack_error}")
                else:
                    print(f"❌ Échec après {MAX_RETRIES + 1} tentatives. Erreur: {e}")
                    self._send_to_dlq(ch, method, body, e, MAX_RETRIES)
            else:
                self._send_to_dlq(ch, method, body, e, 0)
    
    def start_consuming(self):
        """Démarre la boucle d'écoute des messages."""
        for i in range(3):
            try:
                self.channel.basic_consume(queue=self.queue_name, on_message_callback=self._on_message_callback)
                print("👂 QC-Valeurs: En attente de messages...")
                self.channel.start_consuming()
                break
            except (pika.exceptions.AMQPConnectionError, pika.exceptions.ChannelClosedByBroker) as e:
                print(f"⚠️ Connexion perdue: {e}")
                self.connect()
