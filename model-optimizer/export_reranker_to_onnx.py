import torch
from sentence_transformers.cross_encoder import CrossEncoder
import os

def export_reranker_model():
    """
    Charge le modèle de reranking, l'exporte au format ONNX,
    et génère le fichier de configuration Triton correspondant.
    """
    # --- Configuration ---
    model_name_hf = "BAAI/bge-reranker-v2-m3"
    model_name_triton = "bge-reranker"
    output_dir = f"/output/{model_name_triton}/1"
    output_path_onnx = os.path.join(output_dir, "model.onnx")
    output_path_config = os.path.join(output_dir, "../config.pbtxt")

    # --- Étape 1: Exportation du modèle ONNX ---
    print(f"Chargement du modèle Hugging Face: {model_name_hf}")
    model = CrossEncoder(model_name_hf)
    
    dummy_input = model.tokenizer(
        ["query", "document"], padding=True, truncation=True, return_tensors="pt"
    )
    dynamic_axes = {
        "input_ids": {0: "batch_size", 1: "sequence_length"},
        "attention_mask": {0: "batch_size", 1: "sequence_length"},
        "output": {0: "batch_size"},
    }
    
    os.makedirs(output_dir, exist_ok=True)
    
    print(f"Exportation du modèle ONNX vers {output_path_onnx}")
    torch.onnx.export(
        model.model,
        (dummy_input['input_ids'], dummy_input['attention_mask']),
        output_path_onnx,
        input_names=["input_ids", "attention_mask"],
        output_names=["output"],
        dynamic_axes=dynamic_axes,
        opset_version=14,
    )
    print("Exportation ONNX terminée.")

    # --- Étape 2: Génération du config.pbtxt ---
    config_pbtxt_content = f"""
name: "{model_name_triton}"
platform: "onnxruntime_onnx"
max_batch_size: 256

# --- MODIFICATION ---
# Ajout de l'instance_group pour le déploiement multi-GPU automatique.
instance_group [
  {{
    kind: KIND_GPU
  }}
]

dynamic_batching {{
  preferred_batch_size: [ 8, 16, 32, 64 ]
  max_queue_delay_microseconds: 10000
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
    name: "output"
    data_type: TYPE_FP32
    dims: [ 1 ]
  }}
]
"""
    print(f"Génération du fichier de configuration Triton vers {output_path_config}")
    with open(output_path_config, "w") as f:
        f.write(config_pbtxt_content)

    print(f"Modèle '{model_name_triton}' prêt pour Triton.")

if __name__ == "__main__":
    export_reranker_model()