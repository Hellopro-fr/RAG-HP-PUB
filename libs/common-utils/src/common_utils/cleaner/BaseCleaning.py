import logging
import re

# Useful for typing
from logging import Logger
from bs4 import BeautifulSoup, Tag
from markdownify import markdownify as md
from datetime import datetime
from lxml.etree import tostring

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class CleanerBase:
    """
    Class base to clean data.
    """

    def __init__(self, data: str):
        self.date = datetime.now()
        self.data = data
        
    @staticmethod
    def _normalize_whitespace(text: str) -> str:
        """
        Cleans up whitespace and removes control characters.
        """
        if not text:
            return ""
        text = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', text) # Remove control characters
        text = re.sub(r'\s+', ' ', text) # Collapse whitespace
        return text.strip()
            
    def convert_to_soup(self, html_content: str):
        """
        Convert HTML content to BeautifulSoup object.
        """
        if not html_content:
            logging.warning("Contenu de page vide")
            return None
        
        soup = BeautifulSoup(html_content, 'html5lib')
        if not soup:
            soup = BeautifulSoup(html_content, 'lxml')
        
        return soup
    
    def clean(self) -> str:
        """
        Steps:
        1. Convert HTML to BeautifulSoup object.
        2. Keep only tags related to table.
        3. Convert the result to markdown.
        4. Return the cleaned text.
        """
        result = ""
        
        if not self.data:
            logging.warning("Aucune donnée à traiter.")
            return result
        
        if not isinstance(self.data, str):
            logging.warning("Les données doivent être une chaîne de caractères.")
            return result
        
        soup = self.convert_to_soup(self.data)
        if not soup:
            logging.warning("Impossible de convertir les données en BeautifulSoup.")
            return result
        
        stripped_text = self._strip_tags(soup)
        if not stripped_text:
            logging.warning("Le texte nettoyé est vide.")
            return result
        
        # Convert to markdown
        markdown_text = self._convert_to_markdown(stripped_text)
        if not markdown_text:
            logging.warning("La conversion en markdown a échoué.")
            return result
        
        return markdown_text
    
    def _strip_tags(self, soup: BeautifulSoup) -> str:
        """
        Strip HTML tags and return cleaned text.
        Remove all tags except tags related to table
        """
        if not soup or not isinstance(soup, BeautifulSoup):
            logging.warning("Invalid BeautifulSoup object.")
            return ""
        
        # Remove script and style elements
        for element in soup(['script', 'style']):
            element.decompose()
            
        # Keep only table tags
        for element in soup.find_all(True):
            if isinstance(element, Tag) and element.name not in ['table', 'tr', 'td', 'th']:
                element.unwrap()
                
        # Convert to string
        stripped_content = self._normalize_whitespace(tostring(soup, encoding='unicode', method='text')).strip()
        
        return stripped_content
    
    def _convert_to_markdown(self, data: str) -> str:
        """
        Convert HTML content to Markdown format.
        """
        if not data:
            logging.warning("Aucune donnée à convertir en markdown.")
            return ""
        
        if not isinstance(data, str):
            logging.warning("Les données doivent être une chaîne de caractères.")
            return ""
        
        # Convert into markdown
        markdown_content = md(data, heading_style="ATX", escape_html=False)
        if not markdown_content:
            logging.warning("La conversion en markdown a échoué, le contenu est vide.")
            return ""
        
        # Normalize whitespace in the markdown content
        markdown_content = self._normalize_whitespace(markdown_content).strip()
        
        # Check if markdown content is empty after normalization
        if not markdown_content:
            logging.warning("Le contenu markdown est vide après normalisation.")
            return ""
        
        return markdown_content
