FROM python:3.10-slim

WORKDIR /app

# MODIFIÉ: Le chemin est maintenant relatif à la racine du projet (le contexte de build)
COPY protos /app/protos

# MODIFIÉ: Le chemin est maintenant relatif à la racine du projet
COPY apps-microservices/llm-service/requirements.txt .

# Installation des dépendances et génération des stubs gRPC
RUN pip install --no-cache-dir -r requirements.txt
RUN python -m grpc_tools.protoc -I./protos --python_out=. --grpc_python_out=. ./protos/llm.proto

# MODIFIÉ: On copie uniquement le code source de ce service spécifique
COPY apps-microservices/llm-service /app

# Le port 50051 est le port standard pour gRPC
EXPOSE 50051

CMD ["python", "-m", "app.main"]