import jsonlines
import fitz  # PyMuPDF
import mimetypes
from pathlib import Path
import requests
from multiprocessing import Pool, cpu_count
import os
import sys
import httpx
import logging
from typing import List, Optional, Dict, Any
from io import BytesIO
from urllib.parse import urlparse
import asyncio
import tempfile
from dataclasses import dataclass

from pymilvus import (
    connections,
    Collection,
    MilvusException
)

# Configuration du logging pour éviter le spam, on garde les erreurs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class ModelConfig:
    model_id: str = "Camembert-large"
    collection_name: str = "document"
    dimension: int = 1024

class MilvusDocumentCrud:
    def __init__(self , **kwargs: Any):
        self.config = {
            "ZILLIZ_URI": "milvus-prod.hello.dev.private.com",
            "ZILLIZ_PORT": "19530"
        }

        self.collection: Optional[Collection] = None
        # On évite de lever une erreur ici si c'est juste pour initier la classe, 
        # mais on garde la logique demandée.
        if not self.config.get("ZILLIZ_URI") or not self.config.get("ZILLIZ_PORT"):
            raise ValueError("Zilliz Cloud URI and API Key/Port must be set in the environment.")
        self.logger = kwargs.get('logger', logging)
        
    def _connect_to_milvus(self):
        # Optimisation : Ne pas se reconnecter si déjà connecté
        try:
            if not connections.has_connection("default"):
                self.logger.info("Connexion sur Zilliz cloud...")
                connections.connect("default", host=self.config.get("ZILLIZ_URI"), port=self.config.get("ZILLIZ_PORT"))
                self.logger.info("✓ Connexion sur Zilliz cloud avec succès.")
        except Exception as e:
            self.logger.error(f"Erreur de connexion Milvus: {e}")
    
    def _get_or_create_collection(self, model_config: ModelConfig) -> Collection:
        collection_name = model_config.collection_name
        # Optimisation : Collection est légère, mais on peut vérifier si chargée
        collection = Collection(collection_name)
        collection.load()
        return collection

    async def get_document(self,fichier_source: str) -> Dict[str, Any]:
        list_fichier_source = [fichier_source]
        model_config = ModelConfig()
        
        try:
            await asyncio.to_thread(self._connect_to_milvus)
            self.collection = await asyncio.to_thread(self._get_or_create_collection, model_config)

            if not self.collection:
                return {"status": "error", "message": "Collection non initialisée.", "code": 404}

            if not fichier_source:
                return {"status": "error", "message": "Fichier source requis.", "code" : 400}

            result = await asyncio.to_thread(self.collection.query,
                expr=f"fichier_source in {list_fichier_source}",
                output_fields=["id","text","date_ajout","date_maj"]
            )
            
            data = None
            if isinstance(result, list):
                data = result
            elif hasattr(result, "data"):
                data = result.data
            elif isinstance(result, dict) and "data" in result:
                data = result["data"]

            return {"status": "success", "data": data}

        except MilvusException as e:
            # self.logger.error(f"Erreur Milvus : {e}") # Commenté pour réduire le bruit si fréquent
            return {"status": "error", "message": f"Erreur Milvus : {e}", "code": 500}
        except Exception as e:
            return {"status": "error", "message": f"Erreur inattendue : {e}", "code": 500}


BASE_URL_OCR = os.environ.get("URL_OCR", "http://34.34.166.5:8501")

class DeepseekOCRDocExtractor:
    """Client asynchrone pour l'API OCR externe utilisant Deepseek"""
    
    def __init__(self, base_url: str = BASE_URL_OCR, timeout: int = 300, download_timeout: int = 120):
        # J'ai réduit les timeouts par défaut, 3000s c'est énorme et bloque les workers
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.download_timeout = download_timeout
        self.endpoint = f"{self.base_url}/ocr/batch"
    
    def _is_supported_format(self, filename: str) -> bool:
        supported_extensions = {'.pdf', '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp'}
        ext = Path(filename).suffix.lower()
        return ext in supported_extensions
    
    async def _download_file(self, url: str) -> tuple[BytesIO, str]:
        try:
            # Correction: follow_redirects=True pour gérer les 302 Found
            async with httpx.AsyncClient(follow_redirects=True, verify=False) as client:
                response = await client.get(url, timeout=self.download_timeout)
                response.raise_for_status()
                
                parsed_url = urlparse(url)
                filename = Path(parsed_url.path).name
                if not filename:
                    filename = "document.pdf"
                
                file_content = BytesIO(response.content)
                
                if not self._is_supported_format(filename):
                    # print(f"⚠️  {filename} n'est pas un PDF/image - conversion en PDF...")
                    file_content, filename = await self._convert_to_pdf(file_content, filename)
                
                file_content.seek(0)
                return file_content, filename
                
        except httpx.HTTPError as e:
            # On relance l'erreur pour qu'elle soit catchée plus haut
            raise httpx.HTTPError(f"Erreur DL {url}: {str(e)}")
        except Exception as e:
             raise ValueError(f"Erreur générale DL {url}: {str(e)}")
    
    async def extract_from_urls(
        self, 
        urls: List[str], 
        prompt: Optional[str] = "<image>\nConvert the document to markdown."
    ) -> Dict[str, Any]:
        
        files = []
        downloaded_files = []
        
        try:
            download_tasks = [self._download_file(url) for url in urls]
            # Return_exceptions=True évite que tout plante si 1 fichier foire
            downloads = await asyncio.gather(*download_tasks, return_exceptions=True)
            
            valid_downloads = []
            for res in downloads:
                if isinstance(res, Exception):
                    print(f"⚠️ Erreur de téléchargement OCR : {res}")
                else:
                    valid_downloads.append(res)

            if not valid_downloads:
                return {} # Retour vide si aucun fichier n'a pu être téléchargé

            for file_content, filename in valid_downloads:
                downloaded_files.append(file_content)
                mime_type, _ = mimetypes.guess_type(filename)
                if mime_type is None:
                    mime_type = 'application/pdf'
                files.append(('files', (filename, file_content, mime_type)))
            
            data = {}
            if prompt is not None:
                data['prompt'] = prompt
            
            # Timeout augmenté pour le traitement OCR
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.endpoint,
                    files=files,
                    data=data if data else None
                )
                response.raise_for_status()
                return response.json()
            
        except httpx.TimeoutException:
            print(f"Timeout OCR après {self.timeout}s")
            return {}
        except Exception as e:
            print(f"Erreur OCR globale: {str(e)}")
            return {}
        finally:
            for file_io in downloaded_files:
                try:
                    file_io.close()
                except:
                    pass
    
    async def extract_from_url(self, url: str, prompt: Optional[str] = "<image>\nConvert the document to markdown.") -> Dict[str, Any]:
        return await self.extract_from_urls([url], prompt)
    
    def get_clean_result(self, response: Dict) -> Dict:
        res_dict = {}
        # Correction: Vérification défensive si response est None
        if not response:
            return res_dict

        if response.get('success') and response.get('results'):
            for results in response['results']:
                texts = []
                filename = results.get('filename', 'unknown')

                if 'results' in results.get('result', {}).keys():
                    for res in results['result']['results']:
                        texts.append(res.get("result", ""))
                elif 'result' in results.get('result', {}):
                    texts.append(results['result']['result'])

                total_pages = results.get('result', {}).get("total_pages", 1)

                res_dict[filename] = {
                  "text" : " ".join([t for t in texts if t]), # filter None
                  "total_pages": total_pages  
                }
        return res_dict

    async def _convert_to_pdf(self, content: BytesIO, filename: str) -> tuple[BytesIO, str]:
        temp_input = None
        temp_output_dir = None
        try:
            content.seek(0)
            ext = Path(filename).suffix.lower()
            libreoffice_formats = ['.doc', '.docx', '.odt', '.xls', '.xlsx', '.ppt', '.pptx']
            
            if ext in libreoffice_formats:
                temp_output_dir = tempfile.mkdtemp()
                temp_input = tempfile.NamedTemporaryFile(delete=False, suffix=ext, dir=temp_output_dir)
                temp_input.write(content.read())
                temp_input.close()
                
                cmd = ['libreoffice', '--headless', '--convert-to', 'pdf', '--outdir', temp_output_dir, temp_input.name]
                
                process = await asyncio.create_subprocess_exec(
                    *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )
                
                try:
                    stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=60)
                except asyncio.TimeoutError:
                    try:
                        process.kill()
                    except: pass
                    raise ValueError(f"Timeout conversion {filename}")
                
                pdf_path = Path(temp_output_dir) / f"{Path(temp_input.name).stem}.pdf"
                
                if process.returncode == 0 and pdf_path.exists():
                    with open(pdf_path, 'rb') as pdf_file:
                        pdf_content = BytesIO(pdf_file.read())
                    new_filename = Path(filename).stem + '.pdf'
                    return pdf_content, new_filename
                else:
                    raise Exception("Echec conversion LibreOffice")
            else:
                # Si format non supporté, on renvoie tel quel pour éviter crash total
                content.seek(0)
                return content, filename
                
        except Exception as e:
            # En cas d'erreur conversion, on log et on renvoie l'original pour éviter de casser la chaine
            print(f"Erreur conversion {filename}: {e}")
            content.seek(0)
            return content, filename
        finally:
            # Nettoyage robuste
            try:
                if temp_input and os.path.exists(temp_input.name):
                    os.unlink(temp_input.name)
                if temp_output_dir and os.path.exists(temp_output_dir):
                    import shutil
                    shutil.rmtree(temp_output_dir, ignore_errors=True)
            except:
                pass

BASE_DIR = Path(__file__).parent
JSONL_DIR = BASE_DIR / "stat_colab"
DOWNLOAD_DIR = BASE_DIR / "downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)

async def download_file(url, save_dir=DOWNLOAD_DIR):
    try:
        local_path = save_dir / Path(urlparse(url).path).name
        if not local_path.name:
            local_path = save_dir / "temp_unnamed_file"

        # On évite de re-télécharger si ça existe déjà pour gagner du temps/IO
        if local_path.exists() and local_path.stat().st_size > 0:
            return str(local_path)

        loop = asyncio.get_event_loop()
        # Utilisation de requests avec timeout pour éviter blocage
        # Correction: verify=False parfois nécessaire pour vieux serveurs, stream=True pour mémoire
        resp = await loop.run_in_executor(None, lambda: requests.get(url, timeout=30, verify=False))
        resp.raise_for_status()
        
        # Écriture
        local_path.write_bytes(resp.content)
        return str(local_path)
    except Exception as e:
        print(f"Echec download {url}: {e}")
        return None

def extract_text_from_pdf_sync(pdf_path: str) -> str:
    text = ""
    try:
        with fitz.open(pdf_path) as doc:
            for page in doc:
                text += page.get_text()
    except Exception as e:
        print(f"Erreur lecture PDF {pdf_path}: {e}")
    return text.strip()

async def extract_text_from_pdf(pdf_path: str) -> str:
    return await asyncio.to_thread(extract_text_from_pdf_sync, pdf_path)

def convert_to_pdf_sync(input_path: str, output_path: str):
    try:
        doc = fitz.open(input_path)
        pdf_bytes = doc.convert_to_pdf()
        pdf_doc = fitz.open("pdf", pdf_bytes)
        pdf_doc.save(output_path)
        pdf_doc.close()
        doc.close()
    except Exception as e:
        print(f"Erreur conversion PDF MuPDF {input_path}: {e}")

async def convert_to_pdf(input_path: str, output_path: str):
    await asyncio.to_thread(convert_to_pdf_sync, input_path, output_path)

# --- SÉMAPHORE GLOBAL ---
# Limite le nombre de fichiers ouverts/tâches simultanées pour éviter "Too many open files"
# Ajuste ce nombre selon la puissance de ta machine (CPU/RAM). 20 est très safe.
MAX_CONCURRENT_TASKS = 20
semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)

async def process_line(line):
    # On encapsule tout le traitement d'une ligne dans le sémaphore
    async with semaphore:
        url = line.get("url")
        if not url:
            return None

        document_data = line.get("original_data",{})

        try:
            # Milvus
            res = await MilvusDocumentCrud().get_document(fichier_source=document_data.get("fichier_source"))
            tab_data = res.get('data',[])

            if tab_data:
                text_bdd = tab_data[0].get('text','').strip()
                date_maj = tab_data[0].get('date_maj','').strip()
                if date_maj or text_bdd:
                    line['content'] = text_bdd
                    # On retourne tôt, pas besoin de télécharger
                    return line    
            
            path = Path(urlparse(url).path)
            mime, _ = mimetypes.guess_type(path.name)
            if not mime: mime = ""

            # --- Image -> OCR ---
            if mime.startswith("image"):
                extractor = DeepseekOCRDocExtractor()
                response = await extractor.extract_from_urls([url])
                
                # Correction : Gestion du cas où response est None ou vide
                if response:
                    results = extractor.get_clean_result(response)
                    nom_doc = os.path.basename(document_data.get("document","inconnu"))
                    
                    # Recherche un peu plus flexible du résultat
                    texts = ""
                    if results:
                        # On prend le premier résultat si le nom exact match pas (souvent le cas avec URL temporaire)
                        key = next(iter(results))
                        texts = results[key].get("text", "")
                    
                    line["comment"] = "OCR"
                    line["content"] = texts
                    print(f"[IMAGE] {url} → OCR Ok")
                    return line
                else:
                    print(f"[IMAGE] {url} → OCR Échec (pas de réponse)")
                    line["content"] = ""
                    return line

            # --- Téléchargement local pour PDF/Autre ---
            downloaded_path = None
            if url.startswith("http://") or url.startswith("https://"):
                downloaded_path = await download_file(url)
                if not downloaded_path:
                    line["content"] = ""
                    line["comment"] = "Download Fail"
                    return line
                url_to_process = downloaded_path
            else:
                url_to_process = url

            content = ""
            tmp_pdf = None

            try:
                # --- PDF ---
                if mime == "application/pdf" or url_to_process.lower().endswith(".pdf"):
                    content = await extract_text_from_pdf(url_to_process)
                else:
                    # --- Conversion en PDF ---
                    try:
                        tmp_pdf = Path(url_to_process).with_suffix(".converted.pdf")
                        await convert_to_pdf(url_to_process, str(tmp_pdf))
                        if tmp_pdf.exists():
                            content = await extract_text_from_pdf(str(tmp_pdf))
                    except Exception as e:
                        print(f"Erreur conversion locale {url}: {e}")
            except Exception as e:
                print(f"Erreur extraction texte {url}: {e}")
            
            line["content"] = content
            if len(content) < 200:
                line["comment"] = "⚠️ Document court (<200 caractères)"
                # print(f"[COURT] {url}") # Commenté pour réduire logs
            else:
                line["comment"] = ""

            return line

        except Exception as e:
            # Catch global pour qu'une ligne ne plante pas tout le batch
            print(f"🔥 Erreur critique sur ligne {url}: {e}")
            return None
            
        finally:
            # Nettoyage impératif
            try:
                if downloaded_path and os.path.exists(downloaded_path):
                    os.remove(downloaded_path)
                if tmp_pdf and tmp_pdf.exists():
                    os.remove(tmp_pdf)
            except Exception as e:
                pass

async def process_jsonl_for_year_async(jsonl_dir, annee):
    jsonl_files = list(jsonl_dir.glob(f"*{annee}*.jsonl"))
    if not jsonl_files:
        print(f"Aucun fichier JSONL trouvé pour l'année {annee}")
        return 0

    lines = []
    for jsonl_file in jsonl_files:
        with jsonlines.open(jsonl_file, "r") as reader:
            lines.extend(list(reader))

    print(f"Traitement de {len(lines)} documents avec {MAX_CONCURRENT_TASKS} tâches parallèles...")

    # Création des tâches async
    tasks = [process_line(line) for line in lines]
    
    # return_exceptions=True est crucial pour voir les résultats même si une tâche crash
    processed_lines = await asyncio.gather(*tasks, return_exceptions=True)

    short_content_count = 0
    
    for res in processed_lines:
        if isinstance(res, Exception):
            # On log l'erreur mais on ne compte pas la ligne
            # print(f"Tâche échouée : {res}") 
            continue
        if res is None:
            continue
        
        content = res.get("content", "")
        if content and len(content) < 200:
            short_content_count += 1

    output_file = BASE_DIR / f"resultats_{annee}.jsonl"
    with jsonlines.open(output_file, mode="w") as writer:
        # On n'écrit pas la phrase de stat DANS le jsonl de données, ça casse le format
        writer.write({"stat": f"Nombre total de documents < 200 caractères : {short_content_count}"})

    print("\n🔎 Résultat final")
    print(f"Nombre total de documents < 200 caractères : {short_content_count}")
    print(f"✅ Résultats enregistrés dans : {output_file}")

    return short_content_count

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python script.py <année>")
        sys.exit(1)

    annee = sys.argv[1]
        
    try:
        asyncio.run(process_jsonl_for_year_async(JSONL_DIR, annee))
    except KeyboardInterrupt:
        print("Arrêt manuel.")