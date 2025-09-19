import httpx
import json
import os
import logging

# Configuration du client vLLM qui expose une API compatible OpenAI
VLLM_API_URL = os.getenv("VLLM_API_URL", "http://vllm-server:8000/v1/chat/completions")
# MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen3-14B-AWQ")
MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen3-14B-AWQ")

class VLLMClient:
    """
    Client asynchrone pour communiquer avec le serveur vLLM via son API
    compatible OpenAI. Gère le streaming des réponses.
    """
    async def stream_chat(self, message_history):
        """
        Envoie une requête de chat en streaming au serveur vLLM et yield les chunks de réponse.
        
        Args:
            message_history (list): Une liste de dictionnaires représentant l'historique de la conversation.
        
        Yields:
            str: Un chunk de la réponse du modèle.
        """
        # TODO: Ajouter une gestion plus fine des erreurs (timeouts, 5xx, etc.)
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                request_payload = {
                    "model": MODEL_NAME,
                    "messages": message_history,
                    "stream": True,
                    "max_tokens": 2048, # Paramètre ajustable
                }
                async with client.stream("POST", VLLM_API_URL, json=request_payload) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if line.startswith('data: '):
                            data_str = line[len('data: '):].strip()
                            if data_str == '[DONE]':
                                break
                            try:
                                chunk_data = json.loads(data_str)
                                if 'choices' in chunk_data and len(chunk_data['choices']) > 0:
                                    delta = chunk_data['choices'][0].get('delta', {})
                                    content = delta.get('content')
                                    if content:
                                        yield content
                            except json.JSONDecodeError:
                                logging.warning(f"Impossible de décoder le chunk JSON: {data_str}")
                                continue
        except httpx.RequestError as e:
            logging.error(f"Erreur de requête vers vLLM: {e}")
            # Propager une erreur ou retourner un message d'erreur au client gRPC
            yield "[ERREUR: Le service LLM est indisponible]"
        except Exception as e:
            logging.error(f"Erreur inattendue dans VLLMClient: {e}")
            yield "[ERREUR: Une erreur interne est survenue]"
            
    async def chat(self, message_history) -> str:
        """
        Envoie une requête de chat non-streamée au serveur vLLM et retourne la réponse complète.
        
        Args:
            message_history (list): L'historique de la conversation.
        
        Returns:
            str: La réponse complète du modèle.
        """
        try:
            # mettre le timeout à 5 minutes : 300s
            # avant c'est 60s un timeout raisonnable
            async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=10.0)) as client: # Timeout raisonnable
                request_payload = {
                    "model": MODEL_NAME,
                    "messages": message_history,
                    "stream": False, # La différence clé est ici
                    "max_tokens": 2048,
                }
                response = await client.post(VLLM_API_URL, json=request_payload)
                response.raise_for_status()
                
                response_data = response.json()
                if 'choices' in response_data and len(response_data['choices']) > 0:
                    message = response_data['choices'][0].get('message', {})
                    content = message.get('content', '')
                    return content
                else:
                    logging.warning("La réponse de vLLM n'a pas le format attendu.")
                    return "[ERREUR: Réponse inattendue du service LLM]"

        except httpx.RequestError as e:
            logging.error(f"Erreur de requête non-streamée vers vLLM: {e}")
            return "[ERREUR: Le service LLM est indisponible]"
        except Exception as e:
            logging.error(f"Erreur inattendue dans VLLMClient (non-streamé): {e}")
            return "[ERREUR: Une erreur interne est survenue]"

