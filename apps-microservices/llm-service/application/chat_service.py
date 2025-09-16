from infrastructure.vllm_client import VLLMClient

class ChatApplicationService:
    """
    Couche application qui orchestre la logique de chat.
    Elle utilise un client (VLLMClient) pour interagir avec l'infrastructure externe (le serveur vLLM).
    """
    def __init__(self, vllm_client: VLLMClient):
        self.vllm_client = vllm_client

    async def handle_chat_stream(self, request_iterator):
        """
        Gère un flux de conversation bi-directionnel.
        
        Args:
            request_iterator: Un itérateur asynchrone de requêtes gRPC.
        
        Yields:
            str: Un chunk de la réponse générée par le modèle.
        """
        # Pour ce cas, nous construisons un historique simple.
        # Dans une application réelle, cet historique pourrait être géré par session.
        message_history = [{"role": "system", "content": "You are a helpful assistant."}]
        
        async for request in request_iterator:
            message_history.append({"role": "user", "content": request.message})
            
            # Le client vLLM gère le streaming de la réponse
            response_generator = self.vllm_client.stream_chat(message_history)
            
            full_response = ""
            async for chunk in response_generator:
                yield chunk
                full_response += chunk
            
            # Ajoute la réponse complète de l'assistant à l'historique pour le prochain tour
            message_history.append({"role": "assistant", "content": full_response})

