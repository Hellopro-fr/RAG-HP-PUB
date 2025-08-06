import json
import os
import logging
import re

# Useful for typing
from logging import Logger
from bs4 import BeautifulSoup
from markdownify import markdownify as md
from datetime import datetime

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
            
    def strip_html(self) -> str:
        """
        Process data to remove HTML tags and extract text.
        Remove all tags except tags related to table and convert the result to markdown.
        """
        result = ""
        
        if not self.data:
            logging.warning("Aucune donnée à traiter.")
            return result
        
        if isinstance(self.data, str):
            soup = self.convert_to_soup(self.data)
            if soup:
                
        
        for item in self.data:
            if not isinstance(item, dict):
                logging.warning("Item is not a dictionary: %s", item)
                continue
            
            identifier = getattr(item, keys.get('id') or 'id', None)
            content_to_strip = getattr(item, keys.get('content') or 'content', None)
            
            if not identifier or not content_to_strip:
                logging.warning("Identifier or content to strip is missing in item: %s", item)
                continue
            
            soup = self.convert_to_soup(identifier, content_to_strip)
            stripped_content = self._strip_tags(soup, identifier)
            
            if stripped_content:
                item[keys.get('content') or 'content'] = stripped_content
                result.append(item)
            
        return {
            "result": result,
            "output": self.output
        }
    
    def _strip_tags(self, soup: BeautifulSoup):
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
            if element.name not in ['table', 'tr', 'td', 'th']:
                element.unwrap()
        
        # Get text and normalize whitespace
        stripped_content = self._normalize_whitespace(soup.get_text(separator=' ', strip=True))
        
        # Check if stripped content is empty
        if not stripped_content:
            logging.warning("Stripped content is empty.")
            return ""
        
        return stripped_content
        
        if not soup or not isinstance(soup, BeautifulSoup):
            logging.warning("Invalid BeautifulSoup object for the identifier: %s", identifier)
            return ""
        
        # Remove script and style elements
        for element in soup(['script', 'style']):
            element.decompose()
        
        # Get text and normalize whitespace
        stripped_content = self._normalize_whitespace(soup.get_text(separator=' ', strip=True))
        
        # Check if stripped content is empty
        if not stripped_content:
            logging.warning("Stripped content is empty for the identifier: %s", identifier)
            return ""
        
        return stripped_content
    
    def convert_markdown(self, keys: dict = {}) -> dict:
        """
        Process data to convert HTML content to Markdown.
        """
        result = []
        
        for item in self.data:
            if not isinstance(item, dict):
                logging.warning("Item is not a dictionary: %s", item)
                continue
            
            identifier = getattr(item, keys.get('id') or 'id', None)
            content_to_convert = getattr(item, keys.get('content') or 'content', None)
            
            if not identifier or not content_to_convert:
                logging.warning("Identifier or content to convert is missing in item: %s", item)
                continue
            
            markdown_content = self._convert_to_markdown(content_to_convert)
            
            if markdown_content:
                item[keys.get('content') or 'content'] = markdown_content
                result.append(item)
        
        return {
            "result": result,
            "output": self.output
        }
    
    def _convert_to_markdown(self, html_content):
        """
        Convert HTML content to Markdown format.
        """
        if not html_content:
            logging.warning("HTML content is empty or None.")
            return ""
        
        markdown_content = md(html_content, heading_style="ATX", escape_html=False)
        if not markdown_content:
            logging.warning("Markdown conversion resulted in empty content.")
            return ""
        
        # Normalize whitespace in the markdown content
        markdown_content = self._normalize_whitespace(markdown_content)
        
        # Check if markdown content is empty after normalization
        if not markdown_content:
            logging.warning("Markdown content is empty after normalization.")
            return ""
        
        return markdown_content
