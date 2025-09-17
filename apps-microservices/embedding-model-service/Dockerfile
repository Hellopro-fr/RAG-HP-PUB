FROM python:3.10-slim

WORKDIR /app

# MODIFIÉ: Le chemin est maintenant relatif à la racine du projet
COPY protos /app/protos

# MODIFIÉ: Le chemin est maintenant relatif à la racine du projet
COPY apps-microservices/embedding-model-service/requirements.txt .

# Note: L'installation de torch peut être lourde. Pour la production,
# utilisez une image de base avec CUDA pré-installé (ex: nvidia/cuda).
RUN pip install --no-cache-dir -r requirements.txt
RUN python -m grpc_tools.protoc -I./protos --python_out=. --grpc_python_out=. ./protos/embedding.proto

# MODIFIÉ: On copie uniquement le code source de ce service spécifique
COPY apps-microservices/embedding-model-service /app

EXPOSE 50052

CMD ["python", "-m", "app.main"]