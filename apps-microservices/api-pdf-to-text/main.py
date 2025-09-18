from fastapi import FastAPI, UploadFile, File

from typing import List

from common_utils.extractor.PDFProcessor import PDFProcessor

import logging
import asyncio
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

description = """
API pour extraire les textes dans un PDF !
"""
PROJECT_NAME__    = "API-HP-RAG"
PROJECT_VERSION__ = "1.0.0"

app = FastAPI(
    title       = PROJECT_NAME__,
    version     = PROJECT_VERSION__,
    description = description
)

logger = logging.getLogger(__name__)


@app.post("/process_pdfs/")
async def process_pdf_files(files: List[UploadFile] = File(...)):
    """
    Reçoit une liste de fichiers PDF, en extrait le texte via PDFProcessor et renvoie les résultats en JSON.
    """
    results = []
    
    for file in files:
        if file.content_type != 'application/pdf':
            results.append({
                "filename": file.filename,
                "error": "Le fichier doit être au format PDF."
            })
            continue
        
        # Lire le contenu binaire de chaque fichier en mémoire
        file_content = await file.read()
        
        # Créer une instance de votre classe avec le contenu binaire
        processor = PDFProcessor(file_content)
        
        # Lancer le traitement et stocker le résultat
        processed_data = processor.process()
        
        if processed_data:
            results.append({
                "filename": file.filename,
                "data": processed_data
            })
        else:
            results.append({
                "filename": file.filename,
                "error": "Échec de l'extraction du texte."
            })
            
    return {"results": results}


@app.get("/", tags=["Monitoring"])
def read_root():    
    return {"message": f"Bienvenue sur l'API {PROJECT_NAME__} v{PROJECT_VERSION__}"}

