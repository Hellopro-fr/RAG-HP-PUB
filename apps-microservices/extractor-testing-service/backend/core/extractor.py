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
    paragraphs = justext.justext(html, justext.get_stoplist("English"))
    return "\n".join([p.text for p in paragraphs if not p.is_boilerplate])

def extract_goose3(html: str) -> str:
    g = Goose()
    article = g.extract(raw_html=html)
    return article.cleaned_text

# --- Tier 3 Library Functions ---

def extract_newspaper4k(html: str) -> str:
    article = NewspaperArticle(url='', html=html)
    # Manually set the download state to avoid the "You must `download()` an article first!" error
    article.download_state = 2
    article.parse()
    return article.text

def extract_newsplease(html: str) -> str:
    article = newsplease.NewsPlease.from_html(html, url=None)
    return article.maintext if article and article.maintext else ""

def extract_boilerpipe3(html: str) -> str:
    extractor = BoilerpipeExtractor(extractor='ArticleExtractor', html=html)
    return extractor.getText()

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

def extract_go_trafilatura(html: str) -> str:
    command = ["go-trafilatura"]
    return run_subprocess(command, html)

def extract_go_readability(html: str) -> str:
    # Pipe the content directly to the command via stdin.
    command = ["go-readability"]
    return run_subprocess(command, html=html)

# --- Main Orchestrator ---

async def run_all_extractors(html: str) -> Dict[str, ResultItem]:
    """
    Runs all defined extraction functions in parallel using a thread pool.
    """
    loop = asyncio.get_running_loop()
    
    extractors = {
        # Tier 1
        "readability-lxml": (extract_readability_lxml, html),
        "jusText": (extract_justext, html),
        "Goose3": (extract_goose3, html),
        # Tier 2
        "Readability.js (Mozilla)": (extract_readability_js, html),
        "go-trafilatura": (extract_go_trafilatura, html),
        "go-readability": (extract_go_readability, html),
        # Custom
        "Trafilatura (Custom HP)": (extract_trafilatura_hp, html),
        # Tier 3
        "newspaper4k": (extract_newspaper4k, html),
        "news-please": (extract_newsplease, html),
        "boilerpipe3": (extract_boilerpipe3, html),
    }

    results = {}
    with ThreadPoolExecutor() as executor:
        futures = {
            name: loop.run_in_executor(executor, run_extraction, func, *args)
            for name, (func, *args) in extractors.items()
        }
        
        for name, future in futures.items():
            logger.info(f"Running extractor: {name}")
            try:
                results[name] = await asyncio.wait_for(future, timeout=20.0)
            except asyncio.TimeoutError:
                logger.error(f"Extractor '{name}' timed out overall.")
                results[name] = ResultItem(content="", char_count=0, error="Processing timed out after 20 seconds.")
            except Exception as e:
                logger.error(f"Future for '{name}' failed with an unexpected error: {e}")
                results[name] = ResultItem(content="", char_count=0, error=f"An unexpected error occurred: {e}")

    return dict(sorted(results.items()))