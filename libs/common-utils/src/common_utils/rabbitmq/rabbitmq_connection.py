import pika
import time
import os

from dotenv import load_dotenv
load_dotenv()

class RabbitMQConnection:
    def __init__(self, host="localhost"):
        self.host = os.environ.get("RABBITMQ_URL", host)
        self.connection = None

    def create_connection(self,max_retries=10, retry_delay=5):
        """
        Crée une connexion RabbitMQ avec un nombre limité de tentatives.

        :param max_retries: Nombre maximum de tentatives avant abandon
        :param retry_delay: Temps d’attente (s) entre deux tentatives
        :return: pika.BlockingConnection
        :raises Exception: si la connexion échoue après max_retries tentatives
        """
        attempts = 0
        while attempts < max_retries:
            try:
                print(f"🔄 Tentative {attempts+1}/{max_retries} de connexion à RabbitMQ...")
           
                self.connection = pika.BlockingConnection(pika.URLParameters(self.host))
        
                print("✅ Connexion RabbitMQ établie.")
                return self.connection
            except Exception as e:
                attempts += 1
                print(f"❌ Échec de connexion ({e}), nouvelle tentative dans {retry_delay}s...")
                time.sleep(retry_delay)

        raise Exception(f"❌ Impossible de se connecter à RabbitMQ après {max_retries} tentatives.")
