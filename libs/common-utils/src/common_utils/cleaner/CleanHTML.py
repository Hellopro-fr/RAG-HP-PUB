import logging
import re

from bs4 import BeautifulSoup, Tag
from markdownify import MarkdownConverter

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class CleanHTML:
    """
    Class base to clean data.
    """

    def __init__(self, data: str):
        self.data = data
        self.TABLE_RELATED_TAGS = ['table', 'thead', 'tbody', 'tfoot', 'tr', 'th', 'td']
        
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
        
        soup = self._strip_tags(soup)
        if not soup:
            logging.warning("Le contenu de la page est vide après le stripping des tags.")
            return result
        
        # Convert to markdown
        def md(soup: BeautifulSoup, **options):
            return MarkdownConverter(**options).convert_soup(soup)
        
        markdown_text = md(soup, convert=self.TABLE_RELATED_TAGS)
        if not markdown_text:
            logging.warning("La conversion en markdown a échoué.")
            return result
        
        return markdown_text.strip()
    
    def _strip_tags(self, soup: BeautifulSoup) -> BeautifulSoup:
        """
        Strip HTML tags and return cleaned text.
        Remove all tags except tags related to table
        """
        if not soup or not isinstance(soup, BeautifulSoup):
            logging.warning("Invalid BeautifulSoup object.")
            return soup
        
        # Remove script and style elements
        for element in soup(['script', 'style']):
            element.decompose()
            
        # Keep only table tags
        for element in soup.find_all(True):
            if isinstance(element, Tag) and element.name not in ['table', 'tr', 'td', 'th']:
                element.unwrap()
                
        return soup
