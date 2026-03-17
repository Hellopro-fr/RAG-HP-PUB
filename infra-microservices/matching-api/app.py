from fastapi import FastAPI
from pymilvus import connections, exceptions

app = FastAPI()
MILVUS_HOST = "milvus.hello.dev.private.com"
MILVUS_PORT = 19530

@app.get("/test-milvus")
async def test_milvus():
    try:
        # Connect to Milvus, this returns a connection object
        conn = connections.connect(alias="default", host=MILVUS_HOST, port=MILVUS_PORT)
        # If no exception, connection is successful
        return {"status": "success", "message": "Connection to Milvus successful"}
    except exceptions.MilvusException as e:
        return {"status": "error", "message": f"Milvus error: {str(e)}"}
    except Exception as e:
        return {"status": "error", "message": f"Error: {str(e)}"}
