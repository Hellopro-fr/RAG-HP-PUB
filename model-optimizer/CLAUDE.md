# model-optimizer

Converts HuggingFace PyTorch models to ONNX format for NVIDIA Triton Inference Server deployment.

## Tech Stack

- Python 3.10
- PyTorch, transformers, sentence-transformers
- ONNX, onnxruntime, sentencepiece
- Docker (build-only container)

## Run

```bash
# Export embedding model
python model-optimizer/export_embedding_to_onnx.py

# Export reranker model
python model-optimizer/export_reranker_to_onnx.py
```

Output is written to `/output/{model_name}/1/model.onnx` with a sibling `config.pbtxt`.

## File Inventory

```
export_embedding_to_onnx.py   # Exports dangvantuan/sentence-camembert-large -> camembert-embedding
export_reranker_to_onnx.py    # Exports BAAI/bge-reranker-v2-m3 -> bge-reranker
requirements.txt              # torch, transformers, sentence-transformers, onnx, onnxruntime, sentencepiece
Dockerfile                    # Python 3.10-slim builder container (no entrypoint)
```

## Models

| Script | HuggingFace Model | Triton Name | Output Dims |
|---|---|---|---|
| export_embedding_to_onnx.py | dangvantuan/sentence-camembert-large | camembert-embedding | [-1, 1024] |
| export_reranker_to_onnx.py | BAAI/bge-reranker-v2-m3 | bge-reranker | [1] |

## Conventions

- ONNX opset version 14.
- Dynamic axes on batch_size and sequence_length.
- Triton configs enable multi-GPU (`KIND_GPU`) and dynamic batching.
- Dockerfile has no entrypoint; command is specified via docker-compose.

## What This Provides to Other Services

- Production-ready ONNX models + Triton config.pbtxt for the embedding and reranking inference servers.
