FROM python:3.10-slim

WORKDIR /app

# MODIFIÉ: Le chemin est maintenant relatif à la racine du projet
COPY protos /app/protos

# MODIFIÉ: Le chemin est maintenant relatif à la racine du projet
COPY apps-microservices/reranking-model-service/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt
RUN python -m grpc_tools.protoc -I./protos --python_out=. --grpc_python_out=. ./protos/reranking.proto

# MODIFIÉ: On copie uniquement le code source de ce service spécifique
COPY apps-microservices/reranking-model-service /app

EXPOSE 50053

CMD ["python", "-m", "app.main"]