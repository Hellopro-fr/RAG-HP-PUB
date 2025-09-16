FROM python:3.10-slim

# ÉTAPE 1: Installation du compilateur Protobuf au niveau du système
# Ceci est la solution définitive. Il fournit les fichiers .proto standards (comme struct.proto)
# dans un chemin que le compilateur peut trouver nativement.
RUN apt-get update && apt-get install -y protobuf-compiler && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY protos /app/protos
COPY apps-microservices/database-recherche-service/requirements.txt .

# L'installation de grpcio-tools est toujours nécessaire pour le plugin Python
RUN pip install --no-cache-dir -r requirements.txt

# ÉTAPE 2: Lancement de la compilation
# Maintenant que le compilateur système et ses dépendances sont installés,
# cette commande simple fonctionnera. Le compilateur trouvera "google/protobuf/struct.proto"
# tout seul, sans aide.
RUN python -m grpc_tools.protoc \
    -I./protos \
    --python_out=. \
    --grpc_python_out=. \
    ./protos/database.proto

# Copie du code source de l'application
COPY apps-microservices/database-recherche-service /app

EXPOSE 50054

CMD ["python", "-m", "app.main"]