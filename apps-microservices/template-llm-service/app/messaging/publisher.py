import pika
import json
import os
import threading
from common_utils.rabbitmq.rabbitmq_connection import RabbitMQConnection

# On crée un objet de stockage local pour chaque thread.
# Chaque thread aura sa propre copie de 'connection' et 'channel'.
thread_local = threading.local()

class Publisher:
    def __init__(self):
        """
        L'initialiseur ne fait plus rien. La connexion sera gérée par thread.
        """
        self.rabbitmq_connection = RabbitMQConnection()
        self.exchange_name = 'processed_data_exchange'
        self.routing_key = 'data.ready_for_embedding'
        print(f"✅ Publisher initialisé (mode thread-safe).")

    def _get_channel(self):
        """
        Cette méthode garantit que chaque thread a sa propre connexion/canal.
        """
        # On vérifie si ce thread a déjà une connexion stockée
        if not hasattr(thread_local, 'connection') or not thread_local.connection.is_open:
            # Si non, on en crée une et on la stocke
            print(f"   -> [Thread {threading.get_ident()}] Création d'une nouvelle connexion publisher...")
            thread_local.connection = self.rabbitmq_connection.create_connection()
            thread_local.channel = thread_local.connection.channel()
            thread_local.channel.exchange_declare(
                exchange=self.exchange_name, 
                exchange_type='topic', 
                durable=True
            )
        return thread_local.channel

    def publish_message(self, message_dict: dict):
        """
        Publie un message en utilisant la connexion spécifique à ce thread.
        """
        try:
            # On récupère le canal sécurisé pour ce thread
            channel = self._get_channel()
            
            channel.basic_publish(
                exchange=self.exchange_name,
                routing_key=self.routing_key,
                body=json.dumps(message_dict).encode('utf-8'),
                properties=pika.BasicProperties(delivery_mode=2)
            )
            print(f"   📤 Message classifié publié avec la clé '{self.routing_key}'.")
        except Exception as e:
            print(f"PUBLISHER ERROR [Thread {threading.get_ident()}]: {e}")
            # On invalide la connexion pour forcer une reconnexion au prochain appel
            if hasattr(thread_local, 'connection'):
                thread_local.connection.close()
                del thread_local.connection

    def close_thread_connection(self):
        """
        Méthode à appeler à la fin pour nettoyer la connexion du thread.
        """
        if hasattr(thread_local, 'connection') and thread_local.connection.is_open:
            thread_local.connection.close()