# API de Détection de Langue Française

API FastAPI pour détecter si un site web est en français ou dispose d'une version française.

## Installation

```bash
cd api-detection-langue-fr
pip install -r requirements.txt
```

## Lancement

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8999 --reload
```

## Endpoints

| Endpoint | Méthode | Description |
|----------|---------|-------------|
| `/detect` | POST | Détection pour une URL unique |
| `/detect-batch` | POST | Détection pour plusieurs URLs |
| `/check-url` | GET | Vérification rapide d'URL |
| `/health` | GET | État de l'API |

## Documentation interactive

- Swagger UI : http://localhost:8999/docs
- ReDoc : http://localhost:8999/redoc

## Modes de détection

- **simple** : Vérifie URL + balise `<html lang>` uniquement
- **complete** : + recherche de liens alternatifs (hreflang, options, etc.)

## Exemple d'utilisation

```python
import httpx

# Détection simple
response = httpx.post("http://localhost:8999/detect", json={
    "url": "https://www.example.com",
    "mode": "complete",
    "use_nlp_detection": True
})
print(response.json())

# Détection batch
response = httpx.post("http://localhost:8999/detect-batch", json={
    "urls": ["https://www.lemonde.fr", "https://www.bbc.co.uk"],
    "mode": "simple",
    "max_concurrency": 5
})
print(response.json())
```
