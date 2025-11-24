import asyncio
import logging
import subprocess
import tempfile
import os
import json
from concurrent.futures import ThreadPoolExecutor
from typing import Dict

# Tier 1 Imports
from readability import Document as ReadabilityDocument
import justext
from goose3 import Goose

# Tier 3 Imports
from newspaper import Article as NewspaperArticle
import newsplease
from boilerpipe.extract import Extractor as BoilerpipeExtractor
# import extractnet
from bs4 import BeautifulSoup

from schemas.schemas import ResultItem
from common_utils.cleaner.TrafilaturaCleaning import TrafilaturaHp

logger = logging.getLogger(__name__)

# --- Helper Function to run extractors ---
def run_extraction(func, *args) -> ResultItem:
    try:
        content = func(*args)
        if content is None:
            content = ""
        # Ensure content is a string
        content = str(content).strip()
        return ResultItem(content=content, char_count=len(content), error=None)
    except Exception as e:
        logger.error(f"Error in {func.__name__}: {e}", exc_info=True)
        return ResultItem(content="", char_count=0, error=str(e))

# --- Tier 1 Library Functions ---

def extract_readability_lxml(html: str) -> str:
    doc = ReadabilityDocument(html)
    return doc.summary()

def extract_justext(html: str) -> str:
    paragraphs = justext.justext(html, justext.get_stoplist("French"))
    return "\n".join([p.text for p in paragraphs if not p.is_boilerplate])


def extract_goose3(html: str, url: str = None) -> str:
    config = {
        'enable_image_fetching': True,
    }
    g = Goose(config)
    # Pass URL to Goose3 if available for better extraction context
    if url:
        article = g.extract(url=url, raw_html=html)
    else:
        article = g.extract(raw_html=html)
    return article.raw_html

# --- Tier 3 Library Functions ---

def extract_newspaper4k(html: str) -> str:
    article = NewspaperArticle(url='', html=html)
    # Manually set the download state to avoid the "You must `download()` an article first!" error
    article.download_state = 2
    article.parse()
    return article.html

def extract_newsplease(html: str) -> str:
    article = newsplease.NewsPlease.from_html(html, url=None)
    return article.maintext if article and article.maintext else ""


def extract_boilerpipe3_default(html: str) -> str:
    extractor = BoilerpipeExtractor(extractor='DefaultExtractor', html=html)
    return extractor.getText()


def extract_boilerpipe3_article(html: str) -> str:
    extractor = BoilerpipeExtractor(extractor='ArticleExtractor', html=html)
    return extractor.getText()


def extract_boilerpipe3_article_sentences(html: str) -> str:
    extractor = BoilerpipeExtractor(
        extractor='ArticleSentencesExtractor', html=html)
    return extractor.getText()


def extract_boilerpipe3_keep_everything(html: str) -> str:
    extractor = BoilerpipeExtractor(
        extractor='KeepEverythingExtractor', html=html)
    return extractor.getText()


def extract_boilerpipe3_keep_everything_with_min_k_words(html: str) -> str:
    extractor = BoilerpipeExtractor(
        extractor='KeepEverythingWithMinKWordsExtractor', html=html)
    return extractor.getText()


def extract_boilerpipe3_largest_content(html: str) -> str:
    extractor = BoilerpipeExtractor(
        extractor='LargestContentExtractor', html=html)
    return extractor.getText()


def extract_boilerpipe3_num_words_rules(html: str) -> str:
    extractor = BoilerpipeExtractor(
        extractor='NumWordsRulesExtractor', html=html)
    return extractor.getText()


def extract_boilerpipe3_canola(html: str) -> str:
    extractor = BoilerpipeExtractor(extractor='CanolaExtractor', html=html)
    return extractor.getText()

# def extract_extractnet(html: str) -> str:
#     extracted_blocks = extractnet.extract(html)
#     # The result is a list of dicts, each with a 'text' key.
#     # We join the text from all blocks to get the full content.
#     return "\n".join([block['text'] for block in extracted_blocks if 'text' in block])

# --- Custom HP Trafilatura Extractor ---
def extract_trafilatura_hp(html: str) -> str:
    """
    Runs the custom TrafilaturaHp extractor from the common-utils library.
    """
    info = {
        "url": "",
        "content": html,
        "fetch": False
    }
    # The __init__ expects a BaseTrafilatura object, but the implementation
    # uses it like a dict, so we pass a dict for consistency with other services.
    extractor = TrafilaturaHp(info)
    result = extractor.extract()
    return result.content if result else ""

# --- Tier 2 (Non-Python) Library Functions ---

def run_subprocess(command: list, html: str, timeout: int = 15) -> str:
    try:
        result = subprocess.run(
            command,
            input=html,
            capture_output=True,
            text=True,
            check=True,
            timeout=timeout
        )
        return result.stdout
    except subprocess.TimeoutExpired:
        raise Exception(f"Process '{command[0]}' timed out after {timeout} seconds.")
    except subprocess.CalledProcessError as e:
        raise Exception(f"Process '{command[0]}' failed with error: {e.stderr}")

def extract_readability_js(html: str) -> str:
    # readability-cli requires a file, so we create a temporary one.
    with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix=".html", encoding='utf-8') as tmp_file:
        tmp_file.write(html)
        filepath = tmp_file.name
    
    try:
        # The command is the 'readable' executable with the '-j' flag for JSON output.
        command = ["readable", "-j", filepath]
        # The tool outputs a JSON string to stdout.
        json_output = run_subprocess(command, html="") # Input is via file, not stdin
        # Parse the JSON and extract the 'textContent' field.
        result_obj = json.loads(json_output)
        return result_obj.get("textContent", "")
    finally:
        os.remove(filepath)


def extract_go_trafilatura(html: str, url: str = None) -> str:
    # Prepare input for Go script
    input_data = {
        "url": url or "",
        "html": html
    }

    command = ["go-trafilatura-hp"]
    result = run_subprocess(command, json.dumps(input_data))

    # Parse JSON output
    try:
        output = json.loads(result)
        if output.get("error"):
            raise Exception(output["error"])
        return output.get("html", "")
    except json.JSONDecodeError as e:
        raise Exception(f"Failed to parse Go script output: {e}")

def extract_go_readability(html: str) -> str:
    # Pipe the content directly to the command via stdin.
    command = ["go-readability"]
    return run_subprocess(command, html=html)

# --- Main Orchestrator ---


async def run_all_extractors(html: str, url: str = None) -> Dict[str, ResultItem]:
    """
    Runs all defined extraction functions, then applies post-processing
    (article extraction and deduplication) to each successful result.
    
    Args:
        html: The HTML content to extract from
        url: Optional URL for extractors that can utilize it (e.g., Goose3)
    """
    loop = asyncio.get_running_loop()
    
    extractors = {
        # Tier 1
        # "readability-lxml": (extract_readability_lxml, html),
        # "jusText": (extract_justext, html),
        "Goose3": (extract_goose3, html, url),
        # Tier 2
        "Readability.js (Mozilla)": (extract_readability_js, html),
        "go-trafilatura": (extract_go_trafilatura, html, url),
        "go-readability": (extract_go_readability, html),
        # Custom
        "Trafilatura (Custom HP)": (extract_trafilatura_hp, html),
        # Tier 3
        # "newspaper4k": (extract_newspaper4k, html),
        # "news-please": (extract_newsplease, html),
        "boilerpipe3-default": (extract_boilerpipe3_default, html),
        "boilerpipe3-article": (extract_boilerpipe3_article, html),
        "boilerpipe3-article-sentences": (extract_boilerpipe3_article_sentences, html),
        "boilerpipe3-keep-everything": (extract_boilerpipe3_keep_everything, html),
        "boilerpipe3-keep-everything-with-min-k-words": (extract_boilerpipe3_keep_everything_with_min_k_words, html),
        "boilerpipe3-largest-content": (extract_boilerpipe3_largest_content, html),
        "boilerpipe3-num-words-rules": (extract_boilerpipe3_num_words_rules, html),
        "boilerpipe3-canola": (extract_boilerpipe3_canola, html),
        # "extractnet": (extract_extractnet, html),
    }

    base_results = {}
    with ThreadPoolExecutor() as executor:
        futures = {
            name: loop.run_in_executor(executor, run_extraction, func, *args)
            for name, (func, *args) in extractors.items()
        }
        
        for name, future in futures.items():
            logger.info(f"Running extractor: {name}")
            try:
                base_results[name] = await asyncio.wait_for(future, timeout=20.0)
            except asyncio.TimeoutError:
                logger.error(f"Extractor '{name}' timed out overall.")
                base_results[name] = ResultItem(content="", char_count=0, error="Processing timed out after 20 seconds.")
            except Exception as e:
                logger.error(f"Future for '{name}' failed with an unexpected error: {e}")
                base_results[name] = ResultItem(content="", char_count=0, error=f"An unexpected error occurred: {e}")

    # --- Post-Processing Stage ---
    logger.info("--- Starting Post-Processing Stage ---")
    post_processed_results = {}
    
    # Instantiate the processor once to access its methods
    post_processor = TrafilaturaHp({"url": "", "content": html, "fetch": False})
    soup = BeautifulSoup(html, 'html5lib')
    
    # Extract special article content once
    article_content = post_processor.extract_article(soup)
    if article_content:
        logger.info(f"Found {len(article_content)} chars of special article content for post-processing.")

    for name, result_item in base_results.items():
        if not result_item.error and result_item.content:
            try:
                logger.info(f"Post-processing result for: {name}")
                # Combine article content with the extractor's main content
                combined_content = result_item.content
                if article_content:
                    combined_content = article_content + "\n" + combined_content
                
                # Apply deduplication
                deduplicated_content = post_processor.dedoublonnage(combined_content)

                new_name = f"{name} + Post-Processing"
                post_processed_results[new_name] = ResultItem(
                    content=deduplicated_content,
                    char_count=len(deduplicated_content),
                    error=None
                )
            except Exception as e:
                logger.error(f"Error during post-processing for {name}: {e}", exc_info=True)
                # Avoid adding a failed post-processing result
                pass

    # Merge original and post-processed results
    final_results = {**base_results, **post_processed_results}
    
    return dict(sorted(final_results.items()))