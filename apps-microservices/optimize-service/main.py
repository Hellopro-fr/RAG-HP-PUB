import logging
import torch
from dotenv import load_dotenv
import os
from fastapi import APIRouter, FastAPI, Request, status
from fastapi.openapi.utils import get_openapi
from fastapi.middleware.cors import CORSMiddleware

from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig

from app.core.credentials import settings
from app.utils.params import params
from app.utils.response import error_response

load_dotenv(dotenv_path=".env")

description = """
API d'embedding [RAG Hellopro] 🚀
"""

os.makedirs(f'{settings.DOCUMENT_ROOT}/logs', exist_ok=True)

# ===== CHARGEMENT DU MODÈLE QWEN =====
def load_qwen_model(model_name: str = ""):
    """
    Charge le modèle Qwen avec quantization 4-bit.
    
    Args:
        model_name (str): Nom du modèle Hugging Face
        
    Returns:
        tuple: (tokenizer, model)
    """
    try:
        print(f"Chargement du tokenizer {model_name}...")
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        
        # Ajouter un token de padding si nécessaire
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token

        # Vérifier les conditions pour la quantization
        if not torch.cuda.is_available():
            raise Exception("GPU non disponible - quantization impossible")
            
        print("Configuration de la quantization 4-bit...")
        
        # Vérifier la version de bitsandbytes
        try:
            import bitsandbytes as bnb
            print(f"✓ BitsAndBytes version détectée")
        except ImportError:
            raise Exception("BitsAndBytes non disponible")
        
        # Config quantization Q4 avec BitsAndBytes
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",  # nf4 > fp4 en qualité
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.float16
        )

        print(f"Chargement du modèle {model_name} en 4-bit...")
        # Charger le modèle en 4-bit (Q4)
        model = AutoModelForCausalLM.from_pretrained(
            model_name,
            quantization_config=bnb_config,
            device_map="auto",
            torch_dtype=torch.float16,
            trust_remote_code=True
        )

        # Vérifier le device
        device = next(model.parameters()).device
        print(f"✓ Modèle {model_name} chargé en 4-bit sur {device}")
        
        return tokenizer, model
        
    except Exception as e:
        print(f"Erreur lors du chargement du modèle: {e}")
        raise

app = FastAPI()

# ===== CHARGEMENT DU MODÈLE QWEN =====
version_llm = "Qwen/Qwen3-14B"
tokenizer, model = load_qwen_model(version_llm)  # Chargé une seule fois

app.state.qwen_tokenizer = tokenizer
app.state.qwen_model = model

# TODO 
# ajout des origines à utiliser pour l'API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    filename=f"{settings.DOCUMENT_ROOT}/logs/app.log",
    filemode="a"
)


@app.exception_handler(Exception)
async def error_handler(request, exc: Exception):
    logging.error(str(exc))
    return error_response(
        "EXCEPTION_ERROR", f"{exc}", status.HTTP_500_INTERNAL_SERVER_ERROR)


for item in params:
    app.include_router(
        item[0],
        prefix=item[1],
        tags=item[2],
        include_in_schema=item[3]
    )


def use_route_names_as_operation_ids(app: FastAPI) -> None:
    for route in app.routes:
        if isinstance(route, APIRouter):
            route.operation_id = route.name


use_route_names_as_operation_ids(app)

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title="API Hellopro",
        description=description,
        version="v1",
        terms_of_service="http://example.com/terms/",
        routes=app.routes,
    )

    openapi_schema["info"]["x-logo"] = {
        # "url": "https://fastapi.tiangolo.com/img/logo-margin/logo-teal.png"
        "url": "statics/plaks.png"
    }
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi