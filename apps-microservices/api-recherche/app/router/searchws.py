# app/router/search_ws.py

import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.core.searchws import search_in_milvus_reranker, search_in_milvus_stream  # We will create this new streaming function
from app.schemas.search import SearchRequestWs as SearchRequest
from app.core.ConnexionManager import manager

router = APIRouter()
logger = logging.getLogger(__name__)

@router.websocket("/ws/search")
async def websocket_search(websocket: WebSocket):
    """
    Handles the WebSocket connection for real-time search.
    - Accepts a connection.
    - Waits for a JSON message containing the search request.
    - Calls the streaming search function and sends updates to the client.
    """
    await manager.connect(websocket)
    # await websocket.accept()
    logger.info("WebSocket connection accepted.")
    try:
        # Wait for the client to send the search request
        data = await websocket.receive_text()
        request_data = json.loads(data)
        
        # Validate the request data using our Pydantic model
        search_request = SearchRequest(**request_data)
        
        # Call the streaming search function and send updates
        if search_request.option.rrf:
            async for update in search_in_milvus_reranker(search_request):
                await websocket.send_json(update)
        else:
            async for update in search_in_milvus_stream(search_request):
                await websocket.send_json(update)

    except WebSocketDisconnect:
        logger.warning(f"Client {websocket.client} disconnected.")
    except Exception as e:
        logger.error(f"An error occurred in the WebSocket pour {websocket.client}: {e}", exc_info=True)
        # Send an error message to the client before closing
        error_payload  = {"type": "error", "payload": str(e)}
        await manager.send_personal_message(error_payload, websocket)
    finally:
        logger.info(f"Closing WebSocket connection pour {websocket.client}.")
        manager.disconnect(websocket)
        # await websocket.close()