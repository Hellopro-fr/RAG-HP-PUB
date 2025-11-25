import json
import trafilatura
import logging
import re
import unicodedata

from typing import Annotated
from bs4 import BeautifulSoup
from copy import deepcopy
from markdownify import markdownify as md
from langdetect import detect
from sentence_splitter import SentenceSplitter
from collections import Counter

from common_utils.cleaner.schemas.cleaner import BaseTrafilaturaReponse, TrafilaturaReponseHtml, BaseTrafilatura

from lxml.etree import tostring, SubElement
import subprocess


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


class TrafilaturaHp:
    def __init__(self, info: BaseTrafilatura, **kwargs):
        object.__setattr__(self, '_initializing', True)
        object.__setattr__(self, '_trafilatura', trafilatura)
        object.__setattr__(self, '_bs', BeautifulSoup)
        object.__setattr__(self, '_config', deepcopy(
            self._trafilatura.settings.DEFAULT_CONFIG))

        object.__setattr__(self, 'info', info)

        object.__setattr__(self, 'output_types', kwargs.get(
            "output_types") if kwargs.get("output_types") else {'markdown': 'md'})

        object.__setattr__(
            self, 'sizes', [10, 25, 50, 100, 150, 200, 300, 500, 750, 1000])

        object.__setattr__(self, '_initializing', False)

    def __setattr__(self, name, value):
        if name.startswith("_") and not self.__dict__.get("_initializing", False):
            raise TypeError("Info de configuration non modifiable")

        if name == 'info' and not isinstance(value, list):
            raise TypeError("Valeur info doit être une liste de dict")
        elif name == 'w_csv' and not isinstance(value, bool):
            raise TypeError("Valeur doit être booléen")

        object.__setattr__(self, name, value)

    def __getattr__(self, name):
        if name.startswith("_"):
            raise TypeError("Info de configuration non récupérable")
        return object.__getattribute__(self, name)

    @staticmethod
    def _normalize_sentence(text: str) -> str:
        """Normalizes a sentence for accurate comparison."""
        return unicodedata.normalize("NFKC", text).strip().lower()

    @staticmethod
    def _normalize_whitespace(text: str) -> str:
        """Cleans up whitespace and removes control characters."""
        text = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ',
                      text)  # Remove control characters
        text = re.sub(r'\s+', ' ', text)  # Collapse whitespace
        return text.strip()

    """
    @function extract
    @params keys -> dict = {
        "url": "url",
        "content": "content",
    }
    """

    def extract(self, keys: dict = {}) -> BaseTrafilaturaReponse | TrafilaturaReponseHtml:
        # response_objects = Annotated[BaseTrafilaturaReponse | TrafilaturaReponseHtml]
        # html = []
        # url = getattr(self.info, keys.get('url') or 'url', "")
        # content = getattr(self.info, keys.get('content') or 'content', "")

        # fetch_content = getattr(self.info, keys.get('fetch') or 'fetch', False)

        url = self.info.get("url", "")
        content = self.info.get("content", "")
        fetch_content = self.info.get("fetch", False)

        if fetch_content:
            content_fetch = self._trafilatura.fetch_url(url, no_ssl=True)

            if content_fetch:
                content = content_fetch

        res = self.extract_content(url, content)

        if fetch_content:
            response_objects = TrafilaturaReponseHtml(
                url=url, content=self._normalize_whitespace(res), html=content or "")
        else:
            response_objects = BaseTrafilaturaReponse(
                url=url, content=self._normalize_whitespace(res))
        if not res:
            response_objects = BaseTrafilaturaReponse(url=url, content="")

        return response_objects

    def _preprocess_html(self, content: str) -> tuple[str, BeautifulSoup]:
        """
        Pre-processes the HTML content:
        1. Removes script/style/noscript tags.
        2. Converts product links to h3 tags.
        Returns the modified HTML string and the BeautifulSoup object.
        """
        if not content:
            return "", None

        soup = BeautifulSoup(content, 'html5lib')

        # Supprimer tout ce qui est potentiellement JS
        for tag in soup.find_all(['script', 'noscript', 'style']):
            tag.decompose()

        content = str(soup)
        # logging.info(f"[{self.info.get('url', '')}] - Taille contenu avant modification d'arbre: {len(content)} chars.")

        try:
            tree = self._trafilatura.load_html(content)
            if tree is not None:
                anchors = tree.xpath(
                    "//*[contains(@class, 'product') or contains(@id, 'product') or contains(@class, 'produit') or contains(@id, 'produit')]//a")
                if anchors:
                    # logging.info(f"[{self.info.get('url', '')}] - Détection de {len(anchors)} éléments de produits en balise <a> ==> modification <a> en <h3>")
                    for a_tag in anchors:
                        parent = a_tag.getparent()
                        if parent is None:
                            continue

                        h3_tag = SubElement(parent, 'h3')

                        h3_tag.text = a_tag.text
                        for child in a_tag:
                            h3_tag.append(child)

                        parent.insert(parent.index(a_tag), h3_tag)

                        parent.remove(a_tag)
                    content = tostring(tree, method='html', encoding='unicode')
                    # logging.info(f"[{self.info.get('url', '')}] - Taille contenu après modification d'arbre: {len(content)} chars.")
        except Exception as e:
            logging.warning(
                f"[{self.info.get('url', '')}] - Échec de la modification de l'arbre HTML. Utilisation du contenu original. Erreur: {e}")
            pass

        return content, soup

    def _postprocess_content(self, content: str, soup: BeautifulSoup) -> str:
        """
        Post-processes the extracted content:
        1. Extracts article content (product info) if found.
        2. Deduplicates content.
        """
        final_content = content
        url = self.info.get("url", "")

        article_content = self.extract_article(soup)
        if article_content:
            logging.info(f"[{url}] - Extraction article détectée.")
            final_content = article_content + "\n" + final_content
            final_content = self.dedoublonnage(final_content)

        return final_content

    def extract_content(self, url, content) -> str:
        if not content:
            logging.info(f"[{url}] - Contenu de page vide.")
            return ""

        # Pre-processing
        content, soup = self._preprocess_html(content)
        if not content:
            return ""

        # Try BS4 extraction first (for simple pages)
        # Note: We use the original soup for BS4 extraction check if we want to keep that logic,
        # but the original code re-parsed 'content' for BS4.
        # Let's keep the original flow but use the pre-processed content for Trafilatura.

        soup_original = self._bs(self.info.get("content", ""), "html5lib")
        main_element = self.extract_bs(soup_original)

        logging.info(f"[{url}] ---------------------------------")
        final_content = ""
        if main_element:
            logging.info(f"[{url}] - Extraction avec BS4 - Main - html5lib.")
            final_content = md(str(main_element),
                               heading_style="ATX", escape_html=False)
            if final_content.strip() == "":
                logging.info(f"[{url}] - Extraction avec BS4 - Main - lxml.")
                soup_lxml = self._bs(self.info.get("content", ""), "lxml")
                main_element = self.extract_bs(soup_lxml)
                final_content = md(str(main_element),
                                   heading_style="ATX", escape_html=False)
        else:
            logging.info(
                f"[{url}] - Pas de <main> détecté. Utilisation de la méthode Trafilatura multi-pass.")

            # Use pre-processed content here
            logging.info(
                f"[{url}] - Taille contenu avant modification d'arbre: {len(content)} chars.")

            results = {}
            for i, (output_type, ext) in enumerate(self.output_types.items()):
                for size in self.sizes:
                    self._config.set(
                        "DEFAULT", "MIN_EXTRACTED_SIZE", str(size))

                    try:
                        extracted = trafilatura.extract(
                            content,
                            output_format=output_type,
                            include_tables=True,
                            include_links=True,
                            include_images=True,
                            include_formatting=True,
                            include_comments=True,
                            # with_metadata=True,  # Important pour que trafilatura extraie l'image principale
                            favor_recall=True,
                            # favor_precision=True,
                            config=self._config,
                            deduplicate=True,
                            url=url,
                            prune_xpath=[
                                # Exclude d-none class
                                "//*[contains(@class, 'd-none')]",
                                # "//*[contains(@class, 'hidden')]",  # Exclude hidden class
                                # "//*[@style[contains(., 'display:none')]]"  # Exclude inline display:none
                                "//footer",
                                "//nav",
                                "//script",
                                "//noscript",
                                "//style"
                            ]
                        )
                    except Exception as e:
                        logging.warning(
                            f"[{url}] - Erreur lors de l'extraction Trafilatura avec MIN_EXTRACTED_SIZE={size}: {e}")
                        extracted = None

                    if not extracted:
                        continue

                    results[size] = extracted
                    length = len(extracted)

                if results:
                    best_size = max(
                        results.keys(), key=lambda k: len(results[k]))
                    final_content = results[best_size]

                    # Post-processing
                    final_content = self._postprocess_content(
                        final_content, soup)
                else:
                    logging.warning(
                        f"[{url}] - Aucune extraction valide après tous les essais.")

        logging.info(
            f"[{url}] - Taille contenu final Trafilatura: {len(final_content)} chars.")
        return final_content

    def dedoublonnage(self, text: str, min_occurrences: int = 2) -> str:
        try:
            lang = detect(text)
        except:
            lang = "fr"

        splitter = SentenceSplitter(language=lang)
        sentences = splitter.split(text)

        normalized_sentences = [self._normalize_sentence(s) for s in sentences]
        counts = Counter(normalized_sentences)

        seen = set()
        deduplicated = []
        for i, s in enumerate(sentences):
            norm = normalized_sentences[i]
            if counts[norm] >= min_occurrences:
                if norm not in seen:
                    deduplicated.append(s)
                    seen.add(norm)
            else:
                deduplicated.append(s)

        return " ".join(deduplicated)

    def extract_bs(self, soup) -> str:
        """Extrait le texte avec BeautifulSoup en ciblant les balises pertinentes."""
        for img in soup.find_all('img'):
            img.decompose()

        main_element = soup.find('main') or soup.select_one(
            "body > :is(#main, .main)")

        if main_element:
            # main_element.prettify()
            for selector in (':scope > header', ':scope > footer'):
                if element_to_remove := main_element.select_one(selector):
                    element_to_remove.decompose()

        if not main_element:
            return ""

        return main_element

    def extract_article(self, soup) -> str | None:
        found_articles = soup.select(
            'article[id*="product"], article[class*="product"], article[id*="produit"], article[class*="produit"]')
        return None if not found_articles else "\n".join([md(str(article), heading_style="ATX") for article in found_articles])

    def extract_go_trafilatura(self, content: str, url: str) -> str:
        """
        Extracts content using the go-trafilatura-hp binary.
        Applies pre-processing and post-processing.
        """
        # Pre-processing
        content, soup = self._preprocess_html(content)
        if not content:
            return ""

        input_data = {
            "url": url or "",
            "html": content
        }

        command = ["go-trafilatura-hp"]
        try:
            result = subprocess.run(
                command,
                input=json.dumps(input_data),
                capture_output=True,
                text=True,
                check=True,
                timeout=15
            )

            output = json.loads(result.stdout)
            if output.get("error"):
                logging.warning(
                    f"[{url}] - go-trafilatura error: {output['error']}")
                return ""

            extracted_html = output.get("html", "")
            if not extracted_html:
                return ""

            # Convert to Markdown
            final_content = md(
                extracted_html, heading_style="ATX", escape_html=False)

            # Post-processing
            final_content = self._postprocess_content(final_content, soup)

            return final_content

        except subprocess.TimeoutExpired:
            logging.warning(f"[{url}] - go-trafilatura timed out.")
            return ""
        except subprocess.CalledProcessError as e:
            logging.warning(f"[{url}] - go-trafilatura failed: {e.stderr}")
            return ""
        except Exception as e:
            logging.warning(f"[{url}] - go-trafilatura unexpected error: {e}")
            return ""

    def extract_boilerpy3(self, content: str) -> str:
        """
        Extracts content using boilerpy3.
        Applies pre-processing and post-processing.
        """
        # Pre-processing
        content, soup = self._preprocess_html(content)
        if not content:
            return ""

        try:
            from boilerpy3 import extractors as BoilerpyExtractor
            extractor = BoilerpyExtractor.KeepEverythingExtractor()
            extracted_html = extractor.get_marked_html(content)

            if not extracted_html:
                return ""

            # Convert to Markdown
            final_content = md(
                extracted_html, heading_style="ATX", escape_html=False)

            # Post-processing
            final_content = self._postprocess_content(final_content, soup)

            return final_content

        except ImportError:
            logging.error("boilerpy3 not installed.")
            return ""
        except Exception as e:
            logging.error(f"Error in boilerpy3 extraction: {e}")
            return ""
