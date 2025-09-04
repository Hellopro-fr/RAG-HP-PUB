import requests
from app.core.credentials import settings
from requests.exceptions import HTTPError, RequestException

def chat_with_openrouter(model: str, message: str) -> str:
    url = "https://openrouter.ai/api/v1/chat/completions"

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": message
            }
        ]
    }
    headers = {
        "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=60)
        response.raise_for_status()
        response_data = response.json()
        content = response_data["choices"][0]["message"]["content"]
        
        if content is None:
             return {
                "error": True,
                "message": "Réponse API manquante ou mal formée.",
                "details": response_data
            }

        return {
            "message": content,
            "res": response_data,
            "error": False
        }

    except HTTPError as http_err:
        try:
            error_details = http_err.response.json()
        except json.JSONDecodeError:
            error_details = {"message": http_err.response.text}
        
        return {
            "error": True,
            "status_code": http_err.response.status_code,
            "message": "Erreur HTTP lors de l'appel à l'API OpenRouter.",
            "details": error_details
        }

    except RequestException as req_err:
        return {
            "error": True,
            "message": "Erreur de connexion lors de l'appel à l'API OpenRouter.",
            "details": str(req_err)
        }
    
    except (KeyError, IndexError) as e:
        return {
            "error": True,
            "message": "Retour mal formé de l'API OpenRouter.",
            "details": str(e)
        }