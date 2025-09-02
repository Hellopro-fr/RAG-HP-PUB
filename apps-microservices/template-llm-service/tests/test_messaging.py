import json
import pytest
from unittest.mock import MagicMock, patch
from app.messaging.consumer import Consumer

# On mock le service de classification pour ne pas dépendre du LLM ici
@patch('app.messaging.consumer.get_qualifier_service')
def test_consumer_callback_successful(mock_get_service):
    """
    Teste le traitement réussi d'un message par le consumer.
    """
    # --- Arrange ---
    # Configurer le mock du service pour qu'il retourne une classification simple
    mock_service_instance = mock_get_service.return_value
    mock_service_instance.classify.return_value = ("article", None, None)

    # Créer des mocks pour les objets RabbitMQ (connection, publisher)
    mock_connection = MagicMock()
    mock_publisher = MagicMock()
    
    # Instancier le consumer avec les mocks
    consumer = Consumer(mock_connection, mock_publisher)

    # Préparer les arguments pour l'appel du callback
    mock_channel = MagicMock()
    mock_method = MagicMock()
    mock_method.delivery_tag = 123 # Un delivery tag de test
    
    # Le corps du message entrant (ce que le consumer reçoit)
    incoming_message_body = json.dumps({
        "data": {
            "url": "http://example.com/blog/mon-article",
            "content": "<h1>Titre de l'article</h1><p>Contenu...</p>"
        }
    }).encode('utf-8')

    # --- Act ---
    # Appeler directement la méthode de callback pour la tester
    consumer._on_message_callback(mock_channel, mock_method, None, incoming_message_body)

    # --- Assert ---
    # 1. Vérifier que le service de classification a été appelé avec les bonnes données
    mock_service_instance.classify.assert_called_once_with(
        url="http://example.com/blog/mon-article",
        content="<h1>Titre de l'article</h1><p>Contenu...</p>"
    )

    # 2. Vérifier que le publisher a été appelé pour envoyer le message enrichi
    mock_publisher.publish_message.assert_called_once()
    # Récupérer le message qui a été publié
    published_message = mock_publisher.publish_message.call_args[0][0]
    
    # Vérifier que le message publié contient bien le résultat de la classification
    assert "classification_result" in published_message
    assert published_message["classification_result"]["type_page"] == "article"
    # Vérifier que les données originales sont toujours là
    assert published_message["data"]["url"] == "http://example.com/blog/mon-article"

    # 3. Vérifier que le message original a bien été acquitté (ack)
    mock_channel.basic_ack.assert_called_once_with(delivery_tag=123)