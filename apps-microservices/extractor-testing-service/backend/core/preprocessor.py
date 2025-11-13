import logging
from bs4 import BeautifulSoup
from lxml import etree
from lxml.html import fromstring, tostring

logger = logging.getLogger(__name__)

def preprocess_html(html_content: str) -> str:
    """
    Replicates the preprocessing logic from TrafilaturaCleaning.py.
    1. Removes script, style, and noscript tags.
    2. Converts product-related <a> tags to <h3> tags.
    """
    if not html_content:
        return ""

    try:
        # Remove script and style elements with BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')
        for tag in soup.find_all(['script', 'noscript', 'style']):
            tag.decompose()
        
        cleaned_html = str(soup)
        logger.info("Successfully removed script and style tags.")

        # Convert <a> to <h3> with lxml for robustness
        tree = fromstring(cleaned_html)
        anchors = tree.xpath("//*[contains(@class, 'product') or contains(@id, 'product') or contains(@class, 'produit') or contains(@id, 'produit')]//a")
        
        if anchors:
            logger.info(f"Found {len(anchors)} product-related <a> tags to convert to <h3>.")
            for a_tag in anchors:
                parent = a_tag.getparent()
                if parent is None:
                    continue

                h3_tag = etree.Element('h3')
                h3_tag.text = a_tag.text
                h3_tag.tail = a_tag.tail
                for child in a_tag:
                    h3_tag.append(child)
                
                # Copy attributes from <a> to <h3>, except for 'href'
                for name, value in a_tag.attrib.items():
                    if name.lower() != 'href':
                        h3_tag.set(name, value)
                
                parent.replace(a_tag, h3_tag)

        processed_html = tostring(tree, method='html', encoding='unicode')
        return processed_html

    except Exception as e:
        logger.warning(f"Failed during HTML preprocessing. Falling back to original content. Error: {e}")
        # If any part of preprocessing fails, it's safer to return the original content
        return html_content