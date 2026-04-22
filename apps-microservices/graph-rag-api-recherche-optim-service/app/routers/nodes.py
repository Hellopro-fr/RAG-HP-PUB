from fastapi import APIRouter, HTTPException, status
from typing import Dict, Any, Optional
import logging

from app.services.node_service import node_service

router = APIRouter()


@router.put("/{label}/{id}", response_model=Dict[str, Any])
async def update_node(label: str, id: str, properties: Dict[str, Any]):
    """
    Update a specific node by its label and ID.

    - **label**: The node label (e.g., 'Produit', 'Fournisseur')
    - **id**: The unique identifier of the node.
    - **properties**: A dictionary of properties to update.
    """
    try:
        updated_node = await node_service.update_node(label, id, properties)

        if updated_node:
            return {
                "message": f"Node {label} {id} updated successfully.",
                "node": updated_node,
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Node {label} with ID {id} not found.",
            )

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logging.error(f"Error in PUT /nodes/{label}/{id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred while updating the node.",
        )


@router.get("/{label}", response_model=Dict[str, Any])
async def get_node_schema(label: str):
    """
    Get the schema (properties and datatypes) for a specific node label.

    - **label**: The node label (e.g., 'Produit', 'Fournisseur')
    """
    try:
        schema = await node_service.get_node_schema(label)

        if schema:
            return {
                "label": label,
                "schema": schema,
            }
        else:
            # If empty, it might mean label doesn't exist or has no properties.
            # We return empty schema but 200 OK is usually better than 404 if the label is just not found in schema cache yet,
            # but usually getting schema for non-existent label returns empty.
            # Let's return what we found.
            return {
                "label": label,
                "schema": [],
                "message": f"No schema found for label {label}. It might not exist in the database yet.",
            }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logging.error(f"Error in GET /nodes/{label}: {e}", exc_info=True)
        raise HTTPException(
            detail="An internal error occurred while fetching the node schema.",
        )


@router.get("/{label}/{id}", response_model=Dict[str, Any])
async def get_node(label: str, id: str):
    """
    Get a specific node by its label and ID.

    - **label**: The node label (e.g., 'Produit', 'Fournisseur')
    - **id**: The unique identifier of the node.
    """
    try:
        node = await node_service.get_node(label, id)

        if node:
            return {
                "code": 200,
                "data": {
                    "label": label,
                    "id": id,
                    "node": node,
                },
            }
        else:
            return {
                "code": 404,
                "data": {
                    "label": label,
                    "id": id,
                    "node": None,
                },
            }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logging.error(f"Error in GET /nodes/{label}/{id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred while fetching the node.",
        )
