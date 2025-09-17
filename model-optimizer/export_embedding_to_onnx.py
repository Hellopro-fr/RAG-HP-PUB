import torch
from sentence_transformers import SentenceTransformer
import os

def export_embedding_model():
    """
    Charge le modèle d'embedding, exporte le module Transformer sous-jacent en ONNX,
    et génère le fichier de configuration Triton correspondant.
    """
    # --- Configuration ---
    model_name_hf = "dangvantuan/sentence-camembert-large"
    model_name_triton = "camembert-embedding"
    output_dir = f"/output/{model_name_triton}/1"
    output_path_onnx = os.path.join(output_dir, "model.onnx")
    output_path_config = os.path.join(output_dir, "../config.pbtxt")

    # --- Étape 1: Exportation du modèle ONNX ---
    print(f"Chargement du modèle Hugging Face: {model_name_hf}")
    model = SentenceTransformer(model_name_hf)
    
    dummy_text = ["Ceci est une phrase de test."]
    encoded_input = model.tokenizer(
        dummy_text, padding=True, truncation=True, return_tensors="pt", max_length=512
    )
    
    # CORRECTION: On exporte le module Transformer de base, pas l'objet SentenceTransformer entier.
    transformer_model = model[0].auto_model

    dynamic_axes = {
        "input_ids": {0: "batch_size", 1: "sequence_length"},
        "attention_mask": {0: "batch_size", 1: "sequence_length"},
        "last_hidden_state": {0: "batch_size", 1: "sequence_length"},
    }
    
    os.makedirs(output_dir, exist_ok=True)
    
    print(f"Exportation du modèle ONNX vers {output_path_onnx}")
    # CORRECTION: On passe les tenseurs comme des arguments séparés, pas l'objet BatchEncoding.
    torch.onnx.export(
        transformer_model,
        (encoded_input['input_ids'], encoded_input['attention_mask']),
        output_path_onnx,
        input_names=["input_ids", "attention_mask"],
        output_names=["last_hidden_state"], # La sortie est la couche cachée avant le pooling
        dynamic_axes=dynamic_axes,
        opset_version=14,
    )
    print("Exportation ONNX terminée.")

    # --- Étape 2: Génération du config.pbtxt ---
    # La configuration doit correspondre à la sortie du modèle de base.
    config_pbtxt_content = f"""
name: "{model_name_triton}"
platform: "onnxruntime_onnx"
max_batch_size: 256

# --- MODIFICATION ---
# Ajout de l'instance_group pour le déploiement multi-GPU automatique.
# Triton créera une instance sur chaque GPU visible par le conteneur.
instance_group [
  {{
    kind: KIND_GPU
    # count: 1 # (Optionnel) Nombre de copies du modèle PAR GPU. 1 est une bonne valeur par défaut.
  }}
]

dynamic_batching {{
  preferred_batch_size: [ 8, 16, 32, 64, 128 ]
  max_queue_delay_microseconds: 5000
}}

input [
  {{
    name: "input_ids"
    data_type: TYPE_INT64
    dims: [ -1 ]
  }},
  {{
    name: "attention_mask"
    data_type: TYPE_INT64
    dims: [ -1 ]
  }}
]

output [
  {{
    name: "last_hidden_state"
    data_type: TYPE_FP32
    dims: [ -1, 1024 ]
  }}
]
"""
    print(f"Génération du fichier de configuration Triton vers {output_path_config}")
    with open(output_path_config, "w") as f:
        f.write(config_pbtxt_content)
    
    print(f"Modèle '{model_name_triton}' prêt pour Triton.")

if __name__ == "__main__":
    export_embedding_model()