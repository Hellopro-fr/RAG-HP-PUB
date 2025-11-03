import requests
from typing import List, Optional, Dict, Any
from pathlib import Path
import mimetypes
from io import BytesIO
from urllib.parse import urlparse


class DeepseekOCRDocExtractor:
    """Client pour l'API OCR externe utilisant Deepseek"""
    
    def __init__(self, base_url: str = "http://localhost:8501", timeout: int = 300, download_timeout: int = 60):
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
    
    def _download_file(self, url: str) -> tuple[BytesIO, str]:
        """
        Télécharge un fichier depuis une URL directement en mémoire
        Aucun fichier n'est écrit sur le disque
        
        Args:
            url: URL du fichier à télécharger
            
        Returns:
            Tuple (contenu du fichier en BytesIO, nom du fichier)
            
        Raises:
            requests.exceptions.RequestException: En cas d'erreur de téléchargement
        """
        try:
            response = requests.get(url, timeout=self.download_timeout)
            response.raise_for_status()
            
            # Extraction du nom de fichier depuis l'URL
            parsed_url = urlparse(url)
            filename = Path(parsed_url.path).name
            
            # Si pas de nom de fichier dans l'URL, en générer un
            if not filename:
                filename = "document.pdf"
            
            # Création d'un objet BytesIO avec le contenu (reste en mémoire)
            file_content = BytesIO(response.content)
            
            return file_content, filename
            
        except requests.exceptions.RequestException as e:
            raise requests.exceptions.RequestException(
                f"Erreur lors du téléchargement de {url}: {str(e)}"
            )
    
    def extract_from_urls(
        self, 
        urls: List[str], 
        prompt: Optional[str] = "<image>\nFree OCR."
    ) -> Dict[str, Any]:
        """
        Traite des fichiers à partir d'URLs
        Les fichiers sont téléchargés en mémoire et automatiquement libérés après traitement
        
        Args:
            urls: Liste d'URLs des fichiers à traiter
            prompt: Prompt optionnel pour personnaliser l'extraction
            
        Returns:
            Dictionnaire contenant les résultats de l'extraction
            
        Raises:
            requests.exceptions.RequestException: En cas d'erreur réseau
        """
        files = []
        downloaded_files = []
        
        try:
            # Téléchargement de tous les fichiers en mémoire
            for url in urls:
                file_content, filename = self._download_file(url)
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
            
            # Envoi de la requête à l'API OCR
            response = requests.post(
                self.endpoint,
                files=files,
                data=data if data else None,
                timeout=self.timeout
            )
            
            # Vérification de la réponse
            response.raise_for_status()
            
            return response.json()
            
        except requests.exceptions.Timeout:
            raise requests.exceptions.RequestException(
                f"Timeout après {self.timeout}s lors de l'appel à l'API OCR"
            )
        except requests.exceptions.RequestException as e:
            raise requests.exceptions.RequestException(
                f"Erreur lors du traitement: {str(e)}"
            )
        finally:
            # Fermeture et libération automatique de la mémoire
            # Les objets BytesIO sont fermés et garbage collected
            for file_io in downloaded_files:
                file_io.close()
    
    def extract_from_url(
        self, 
        url: str, 
        prompt: Optional[str] = "<image>\nFree OCR."
    ) -> Dict[str, Any]:
        """
        Traite un seul fichier à partir d'une URL
        
        Args:
            url: URL du fichier à traiter
            prompt: Prompt optionnel pour personnaliser l'extraction
            
        Returns:
            Dictionnaire contenant le résultat de l'extraction pour ce fichier
        """
        result = self.extract_from_urls([url], prompt)
        
        if result.get('success') and result.get('results'):
            return result['results'][0]
        
        return result