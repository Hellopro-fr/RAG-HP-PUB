import pandas as pd
import requests
from pymilvus import (
    connections,
    utility,
    FieldSchema,
    CollectionSchema,
    DataType,
    Collection,
)

# --- Configuration ---
# 1. Zilliz Cloud Credentials
ZILLIZ_URI = "https://in03-c954cd03915d400.serverless.gcp-us-west1.cloud.zilliz.com"  # Replace with your Public Endpoint
ZILLIZ_TOKEN = "7a26080a88c884073b1436b73d0f801b35605650a8d7f4b99dc1011f7257a8562f9a9510ea659df4b80d657dabd507e96927b5f7"  # Replace with your API Key

# 2. Collection & Model Config
COLLECTION_NAME = "semantic_vigil_collection"
DIMENSION = 1024
EMBEDDING_URL = "https://api.hellopro.eu/embedding-service/embedding"  # Your local or remote embedding service
SIMILARITY_THRESHOLD = 0.92
CSV_FILE_PATH = "input.csv"

# --- 1. Connect to Zilliz Cloud ---
print(f"Connecting to Zilliz Cloud...")
try:
    connections.connect("default", uri=ZILLIZ_URI, token=ZILLIZ_TOKEN)
    print("Connected successfully.")
except Exception as e:
    print(f"Failed to connect to Zilliz: {e}")
    exit(1)

# --- 2. Define Collection Schema ---
if not utility.has_collection(COLLECTION_NAME):
    print(f"Creating collection: {COLLECTION_NAME}")

    fields = [
        FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=DIMENSION),
        FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=65535),
    ]

    schema = CollectionSchema(fields, description="Semantic Vigil Storage")
    collection = Collection(name=COLLECTION_NAME, schema=schema)

    index_params = {
        "metric_type": "COSINE",
        "index_type": "HNSW",
        "params": {"M": 32, "efConstruction": 300},
    }
    collection.create_index(field_name="embedding", index_params=index_params)
    print("Index created.")
else:
    print(f"Loading existing collection: {COLLECTION_NAME}")
    collection = Collection(COLLECTION_NAME)

collection.load()


# --- 3. Helper Function: Get Embedding ---
def get_embedding(text_input):
    payload = {"text": text_input}
    try:
        response = requests.post(EMBEDDING_URL, json=payload)
        response.raise_for_status()
        data = response.json()

        if data and isinstance(data, list):
            return data[0]["embedding"]
        else:
            raise ValueError("Unexpected API response format")

    except Exception as e:
        print(f"Error getting embedding: {e}")
        return None


# --- 4. Main Logic ---
def process_csv(file_path):
    try:
        # NOTE: Assuming semicolon delimiter based on your prompt "valeur; caracteristique; categorie"
        # If your file uses commas, remove `sep=';'`
        df = pd.read_csv(file_path, sep=";")

        # Clean column names (remove whitespace)
        df.columns = df.columns.str.strip()

        required_cols = ["valeur", "caracteristique", "categorie"]
        if not all(col in df.columns for col in required_cols):
            print(f"Error: CSV must contain columns: {required_cols}")
            print(f"Found columns: {df.columns.tolist()}")
            return

        print(f"Processing {len(df)} rows...")

        for index, row in df.iterrows():
            # Construct the text based on the template
            # {caracteristique} : {valeur} (categorie)
            valeur = str(row["valeur"]).strip()
            carac = str(row["caracteristique"]).strip()
            cat = str(row["categorie"]).strip()

            formatted_text = f"{carac} : {valeur} ({cat})"

            # 1. Generate Embedding
            vector = get_embedding(formatted_text)
            if vector is None:
                continue

            # 2. Search in Zilliz
            search_params = {"metric_type": "COSINE", "params": {"ef": 64}}

            results = collection.search(
                data=[vector],
                anns_field="embedding",
                param=search_params,
                limit=1,
                output_fields=["text"],
                consistency_level="Strong",
            )

            is_duplicate = False

            if results and len(results[0]) > 0:
                match = results[0][0]
                score = match.distance

                if score >= SIMILARITY_THRESHOLD:
                    print(
                        f"[SKIP] '{formatted_text}' is similar (Score: {score:.4f}) to DB value: '{match.entity.get('text')}'"
                    )
                    is_duplicate = True

            # 3. Insert if not duplicate
            if not is_duplicate:
                collection.insert(
                    [[vector], [formatted_text]]  # We store the formatted text
                )
                print(f"[INSERT] Added: '{formatted_text}'")

    except FileNotFoundError:
        print(f"File not found: {file_path}")
    except Exception as e:
        print(f"An error occurred: {e}")


if __name__ == "__main__":
    process_csv(CSV_FILE_PATH)
