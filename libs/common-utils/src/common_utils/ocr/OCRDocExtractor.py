import time
import os
from typing import List
from gradio_client import Client, handle_file

CLIENT_URL = os.getenv("CLIENT_URL_OCR", "http://127.0.0.1:8559")
USERNAME = os.getenv("USERNAME_OCR", "admin")
PASSWORD = os.getenv("PASSWORD_OCR", "admin")

class OCRDocExtractor:
    def __init__(self,client_url: str = CLIENT_URL, username: str = USERNAME, password: str = PASSWORD):
        self.client_url = client_url
        self.username = username
        self.password = password

    def convert_doc_to_markdown(self,file_paths: List):
        """
        Convert PDF/images to markdown using the API

        Args:
            client_url: URL of the docext server
            username: Authentication username
            password: Authentication password

        Returns:
            str: Converted markdown content
        """
        client = Client(self.client_url, auth=(self.username, self.password))

        # Prepare file inputs
        file_inputs = [{"image": handle_file(file_path)} for file_path in file_paths]

        # Convert to markdown (non-streaming)
        start_time = time.time()
        result = client.predict(images=file_inputs, api_name="/process_markdown_streaming")
        elapsed = time.time() - start_time

        # Log dans un fichier
        with open("ocr_log.txt", "a") as log:
            for f in file_paths:
                log.write(f"{f} - {elapsed:.3f} seconds\n")


        return result
