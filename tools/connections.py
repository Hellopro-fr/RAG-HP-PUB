"""Shared connection factories for RabbitMQ and Elasticsearch."""

import os
import time
import pika
from elasticsearch import Elasticsearch

RABBITMQ_URL = os.environ.get("RABBITMQ_URL")
ELASTICSEARCH_URL = os.environ.get("ELASTICSEARCH_URL")
ES_USERNAME = os.environ.get("ES_USERNAME")
ES_PASSWORD = os.environ.get("ES_PASSWORD")


def _validate_env():
    """Fail fast if required environment variables are missing."""
    if not RABBITMQ_URL:
        raise ValueError("RABBITMQ_URL environment variable is required.")
    if not ELASTICSEARCH_URL:
        raise ValueError("ELASTICSEARCH_URL environment variable is required.")


def get_rabbitmq_connection(retries: int = 10) -> pika.BlockingConnection:
    """Connects to RabbitMQ with exponential backoff retries."""
    _validate_env()
    for i in range(retries):
        try:
            conn = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
            print("✅ Connecté à RabbitMQ.")
            return conn
        except pika.exceptions.AMQPConnectionError:
            print(f"⏳ En attente de RabbitMQ... {i + 1}s")
            time.sleep(i + 1)
    raise ConnectionError("❌ Impossible de se connecter à RabbitMQ après plusieurs tentatives.")


def get_elasticsearch_client(retries: int = 10, request_timeout: int = 30) -> Elasticsearch:
    """Connects to Elasticsearch with exponential backoff retries."""
    _validate_env()
    for i in range(retries):
        try:
            if ES_USERNAME and ES_PASSWORD:
                es_client = Elasticsearch(
                    ELASTICSEARCH_URL,
                    basic_auth=(ES_USERNAME, ES_PASSWORD),
                    request_timeout=request_timeout
                )
            else:
                es_client = Elasticsearch(ELASTICSEARCH_URL, request_timeout=request_timeout)

            if es_client.ping():
                print("✅ Connecté à Elasticsearch.")
                return es_client
            else:
                raise ConnectionError("Ping Elasticsearch a échoué.")
        except Exception as e:
            print(f"⏳ En attente d'Elasticsearch... {i + 1}s ({e})")
            time.sleep(i + 1)
    raise ConnectionError("❌ Impossible de se connecter à Elasticsearch après plusieurs tentatives.")
