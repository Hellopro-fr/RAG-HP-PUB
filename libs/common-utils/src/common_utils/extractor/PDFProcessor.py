import fitz
import logging
import io

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class PDFProcessor:
    """
    A class to extract text from a PDF file's binary content.
    """
    def __init__(self, file_content: bytes):
        """
        Initializes the PDFProcessor with the binary content of the file.
        :param file_content: The binary content of the PDF file.
        """
        self.file_content = file_content
        self.document = None
        self.text_content = ""
        self.word_count = 0

    def process(self):
        """
        Executes the full workflow: opens the file from memory and extracts text.
        """
        try:
            # fitz.open peut lire directement à partir d'un objet binaire en mémoire
            self.document = fitz.open(stream=self.file_content, filetype="pdf")
            logging.info(f"Le document a {self.document.page_count} pages.")

            for page in self.document:
                self.text_content += page.get_text()

            self.word_count = len(self.text_content.split())
            logging.info(f"Nombre total de mots dans le document : {self.word_count}")

            return {
                "text_content": self.text_content,
                "word_count": self.word_count
            }

        except Exception as e:
            logging.error(f"Une erreur s'est produite pendant le traitement du PDF : {e}")
            return None

        finally:
            if self.document:
                self.document.close()