import logging
import os
from optimum.onnxruntime import ORTModelForSequenceClassification
from transformers import AutoTokenizer

# Configuration du logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Paramètres ---
MODEL_ID = "BAAI/bge-reranker-v2-m3"

# Le chemin de sortie est maintenant relatif au script
# Il créera le dossier 'bge-reranker-v2-m3-onnx' dans le même répertoire
# que ce script, soit /app/ dans le contexte du conteneur Docker.
ONNX_PATH = "bge-reranker-v2-m3-onnx" 

def convert_model_to_onnx():
    """
    Télécharge, convertit et sauvegarde le modèle au format ONNX.
    """
    if os.path.exists(ONNX_PATH) and os.listdir(ONNX_PATH):
        logger.info(f"Le modèle ONNX existe déjà dans '{ONNX_PATH}'. Aucune action n'est requise.")
        return

    logger.info(f"Démarrage de la conversion du modèle '{MODEL_ID}' au format ONNX.")
    
    try:
        logger.info("Téléchargement du modèle et du tokenizer depuis Hugging Face...")
        model = ORTModelForSequenceClassification.from_pretrained(MODEL_ID, from_transformers=True, trust_remote_code=True)
        tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)

        logger.info(f"Sauvegarde du modèle converti dans '{ONNX_PATH}'...")
        model.save_pretrained(ONNX_PATH)
        tokenizer.save_pretrained(ONNX_PATH)

        logger.info("Conversion du modèle ONNX terminée avec succès !")
    except Exception as e:
        logger.error(f"Une erreur est survenue lors de la conversion ONNX : {e}")
        raise

if __name__ == "__main__":
    convert_model_to_onnx()