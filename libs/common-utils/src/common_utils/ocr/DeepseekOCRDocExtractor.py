import httpx
import logging
from typing import List, Optional, Dict, Any
from pathlib import Path
import mimetypes
from io import BytesIO
from urllib.parse import urlparse
import asyncio
import tempfile
import os


BASE_URL_OCR = os.environ.get("URL_OCR", "http://34.34.166.5:8501")


class DeepseekOCRDocExtractor:
    """Client asynchrone pour l'API OCR externe utilisant Deepseek"""
    
    def __init__(self, base_url: str = BASE_URL_OCR, timeout: int = 300, download_timeout: int = 120):
        """
        Initialise le client OCR
        
        Args:
            base_url: URL de base de l'API (ex: "http://localhost:8000")
            timeout: Timeout en secondes pour les requêtes OCR
            download_timeout: Timeout en secondes pour le téléchargement des fichiers
        """
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.download_timeout = download_timeout
        self.endpoint = f"{self.base_url}/ocr/batch"
        logging.info(f"URL ocr : {self.base_url}")
    
    def _is_supported_format(self, filename: str) -> bool:
        """
        Vérifie si le fichier est un format supporté (PDF ou image)
        
        Args:
            filename: Nom du fichier
            
        Returns:
            True si le format est supporté directement, False sinon
        """
        supported_extensions = {'.pdf', '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp'}
        ext = Path(filename).suffix.lower()
        return ext in supported_extensions
    
    async def _download_file(self, url: str) -> tuple[BytesIO, str]:
        """
        Télécharge un fichier depuis une URL directement en mémoire (asynchrone)
        Aucun fichier n'est écrit sur le disque
        
        Args:
            url: URL du fichier à télécharger
            
        Returns:
            Tuple (contenu du fichier en BytesIO, nom du fichier)
            
        Raises:
            httpx.HTTPError: En cas d'erreur de téléchargement
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=self.download_timeout)
                response.raise_for_status()
                
                # Extraction du nom de fichier depuis l'URL
                parsed_url = urlparse(url)
                filename = Path(parsed_url.path).name
                
                # Si pas de nom de fichier dans l'URL, en générer un
                if not filename:
                    filename = "document.pdf"
                
                # Création d'un objet BytesIO avec le contenu (reste en mémoire)
                file_content = BytesIO(response.content)
                
                # Vérifier si le format est supporté
                if not self._is_supported_format(filename):
                    print(f"⚠️  {filename} n'est pas un PDF/image - conversion en PDF...")
                    file_content, filename = await self._convert_to_pdf(file_content, filename)
                    print(f"✓ Converti en {filename}")
                
                # Réinitialiser la position pour la lecture
                file_content.seek(0)

                return file_content, filename
                
        except httpx.HTTPError as e:
            raise httpx.HTTPError(
                f"Erreur lors du téléchargement de {url}: {str(e)}"
            )
    
    async def extract_from_urls(
        self, 
        urls: List[str], 
        prompt: Optional[str] = "<image>\nConvert the document to markdown."
    ) -> Dict[str, Any]:
        """
        Traite des fichiers à partir d'URLs (asynchrone)
        Les fichiers sont téléchargés en mémoire et automatiquement libérés après traitement
        
        Args:
            urls: Liste d'URLs des fichiers à traiter
            prompt: Prompt optionnel pour personnaliser l'extraction
            
        Returns:
            Dictionnaire contenant les résultats de l'extraction
            
        Raises:
            httpx.HTTPError: En cas d'erreur réseau
        """
        files = []
        downloaded_files = []
        
        try:
            # Téléchargement de tous les fichiers en mémoire (en parallèle)
            download_tasks = [self._download_file(url) for url in urls]
            downloads = await asyncio.gather(*download_tasks)
            
            for file_content, filename in downloads:
                downloaded_files.append(file_content)
                
                # Détection du type MIME
                mime_type, _ = mimetypes.guess_type(filename)
                if mime_type is None:
                    mime_type = 'application/pdf'
                
                files.append(
                    ('files', (filename, file_content, mime_type))
                )
            
            # Préparation des données du formulaire
            data = {}
            if prompt is not None:
                data['prompt'] = prompt
            
            # Envoi de la requête à l'API OCR (asynchrone)
            async with httpx.AsyncClient(timeout=None) as client:
                response = await client.post(
                    self.endpoint,
                    files=files,
                    data=data if data else None
                )
                
                # Vérification de la réponse
                response.raise_for_status()
                
                # todo: traitement de response en cas de batching
                return response.json()
            
        except httpx.TimeoutException:
            raise httpx.HTTPError(
                f"Timeout après {self.timeout}s lors de l'appel à l'API OCR"
            )
        except httpx.HTTPError as e:
            raise httpx.HTTPError(
                f"Erreur lors du traitement: {str(e)}"
            )
        finally:
            # Fermeture et libération automatique de la mémoire
            for file_io in downloaded_files:
                file_io.close()
    
    async def extract_from_url(
        self, 
        url: str, 
        prompt: Optional[str] = "<image>\nConvert the document to markdown."
    ) -> Dict[str, Any]:
        """
        Traite un seul fichier à partir d'une URL (asynchrone)
        
        Args:
            url: URL du fichier à traiter
            prompt: Prompt optionnel pour personnaliser l'extraction
            
        Returns:
            Dictionnaire contenant le résultat de l'extraction pour ce fichier
        """
        response = await self.extract_from_urls([url], prompt) 
        return response
    
    def get_clean_result(self,response: Dict) -> Dict:
        res_dict = {}

        if response.get('success') and response.get('results'):
  
            for results in response['results']:

                texts = []
                
                filename = results['filename']

                if 'results' in results.get('result', {}).keys():
                    for res in results['result']['results']:
                        texts.append(res["result"])
                else:
                    texts.append(results['result']['result'])


                if "total_pages" in results.get('result', {}):
                    total_pages = results['result']['total_pages']
                else:
                    total_pages = 1


                res_dict[filename] = {
                  "text" : " ".join(texts),
                  "total_pages": total_pages  
                }

        return res_dict

    async def _convert_to_pdf(self, content: BytesIO, filename: str) -> tuple[BytesIO, str]:
        """
        Convertit un fichier non-supporté en PDF en utilisant LibreOffice (asynchrone)
        
        Args:
            content: Contenu du fichier en BytesIO
            filename: Nom du fichier original
            
        Returns:
            Tuple (contenu PDF en BytesIO, nouveau nom de fichier)
            
        Raises:
            ValueError: Si la conversion échoue
        """
        temp_input = None
        temp_output_dir = None
        
        try:
            content.seek(0)
            ext = Path(filename).suffix.lower()
            
            # Formats supportés par LibreOffice
            libreoffice_formats = [
                '.doc', '.docx', '.odt',  # Word
                '.xls', '.xlsx',  # Excel
                '.ppt', '.pptx',  # PowerPoint
            ]
            
            # === Si format Office, utiliser LibreOffice ===
            if ext in libreoffice_formats:
                # Créer un répertoire temporaire
                temp_output_dir = tempfile.mkdtemp()
                
                # Créer un fichier temporaire avec le bon nom/extension
                temp_input = tempfile.NamedTemporaryFile(
                    delete=False, 
                    suffix=ext,
                    dir=temp_output_dir
                )
                temp_input.write(content.read())
                temp_input.close()
                
                # Commande LibreOffice pour conversion
                cmd = [
                    'libreoffice',
                    '--headless',
                    '--convert-to', 'pdf',
                    '--outdir', temp_output_dir,
                    temp_input.name
                ]
                
                # Exécution asynchrone du subprocess
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                try:
                    stdout, stderr = await asyncio.wait_for(
                        process.communicate(), 
                        timeout=60
                    )
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
                    raise ValueError(f"Timeout lors de la conversion de {filename} (> 60s)")
                
                # Chemin du PDF généré
                pdf_path = Path(temp_output_dir) / f"{Path(temp_input.name).stem}.pdf"
                
                if process.returncode == 0 and pdf_path.exists():
                    # Lire le PDF généré
                    with open(pdf_path, 'rb') as pdf_file:
                        pdf_content = BytesIO(pdf_file.read())
                    
                    new_filename = Path(filename).stem + '.pdf'
                    print(f"✓ Converti avec LibreOffice: {filename} -> {new_filename}")
                    
                    return pdf_content, new_filename
                else:
                    error_msg = stderr.decode() if stderr else "Raison inconnue"
                    raise Exception(f"Échec de la conversion LibreOffice: {error_msg}")
            
            # === Sinon, format non supporté ===
            else:
                raise Exception("Format de document non supporté")
                
        except Exception as e:
            raise ValueError(f"Impossible de convertir {filename} en PDF: {str(e)}")
        finally:
            # Nettoyage des fichiers temporaires
            try:
                if temp_input and os.path.exists(temp_input.name):
                    os.unlink(temp_input.name)
            except Exception as e:
                print(f"⚠️ Impossible de supprimer {temp_input.name}: {e}")
            
            try:
                if temp_output_dir and os.path.exists(temp_output_dir):
                    # Supprimer tous les fichiers du répertoire
                    for file in Path(temp_output_dir).glob('*'):
                        try:
                            file.unlink()
                        except:
                            pass
                    # Supprimer le répertoire
                    os.rmdir(temp_output_dir)
            except Exception as e:
                print(f"⚠️ Impossible de supprimer le répertoire temporaire: {e}")