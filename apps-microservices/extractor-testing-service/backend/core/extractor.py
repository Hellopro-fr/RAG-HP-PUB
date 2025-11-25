import asyncio
import logging
import subprocess
import tempfile
import os
import json
from concurrent.futures import ThreadPoolExecutor
from typing import Dict
from markdownify import markdownify as md

# Tier 1 Imports
from goose3 import Goose

# Tier 3 Imports
from boilerpipe.extract import Extractor as BoilerpipeExtractor
# import extractnet
from bs4 import BeautifulSoup

from schemas.schemas import ResultItem
from common_utils.cleaner.TrafilaturaCleaning import TrafilaturaHp

logger = logging.getLogger(__name__)

# --- Helper Function to run extractors ---


def run_extraction(func, *args) -> ResultItem:
    try:
        result = func(*args)

        # Handle functions that return (content, metadata) tuples
        if isinstance(result, tuple) and len(result) == 2:
            content, metadata = result
        else:
            content = result
            metadata = None

        if content is None:
            content = ""
        # Ensure content is a string
        content = str(content).strip()

        result_item = ResultItem(
            content=content, char_count=len(content), error=None)
        # Always include metadata if present (Trafilatura variants return it)
        if metadata:
            result_item.metadata = metadata

        return result_item
    except Exception as e:
        logger.error(f"Error in {func.__name__}: {e}", exc_info=True)
        return ResultItem(content="", char_count=0, error=str(e))

# --- Tier 1 Library Functions ---


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


def extract_boilerpipe3_keep_everything(html: str) -> str:
    extractor = BoilerpipeExtractor(
        extractor='KeepEverythingExtractor', html=html)
    return extractor.getHTML()

# def extract_extractnet(html: str) -> str:
#     extracted_blocks = extractnet.extract(html)
#     # The result is a list of dicts, each with a 'text' key.
#     # We join the text from all blocks to get the full content.
#     return "\n".join([block['text'] for block in extracted_blocks if 'text' in block])

# --- Custom HP Trafilatura Extractor ---


def extract_trafilatura_hp(html: str, strategy: str = "balanced", extract_metadata: bool = False) -> tuple[str, dict]:
    """
    Runs the custom TrafilaturaHp extractor from the common-utils library.
    
    Args:
        html: HTML content to extract from
        strategy: "precision", "recall", or "balanced"
        extract_metadata: Whether to extract article metadata
    
    Returns:
        Tuple of (content, metadata_dict)
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

    content = result.content if result else ""
    metadata = {}

    # If metadata extraction is requested, use trafilatura.extract directly
    if extract_metadata and html:
        try:
            import trafilatura
            from copy import deepcopy

            config = deepcopy(trafilatura.settings.DEFAULT_CONFIG)

            # Set strategy-specific parameters
            favor_precision = (strategy == "precision")
            favor_recall = (strategy == "recall")

            extracted_data = trafilatura.extract(
                html,
                output_format="json",
                include_tables=True,
                include_links=True,
                include_images=False,
                include_formatting=True,
                include_comments=False,
                with_metadata=True,
                favor_recall=favor_recall,
                favor_precision=favor_precision,
                config=config,
                deduplicate=True,
                url="",
            )

            if extracted_data:
                import json
                metadata_obj = json.loads(extracted_data)
                # Extract metadata fields
                metadata = {
                    "title": metadata_obj.get("title"),
                    "author": metadata_obj.get("author"),
                    "date": metadata_obj.get("date"),
                    "description": metadata_obj.get("description"),
                    "sitename": metadata_obj.get("sitename"),
                    "categories": metadata_obj.get("categories"),
                    "tags": metadata_obj.get("tags"),
                    "source": metadata_obj.get("source"),
                    "hostname": metadata_obj.get("hostname"),
                }
                # Remove None values
                metadata = {k: v for k, v in metadata.items() if v is not None}
        except Exception as e:
            logger.error(f"Error extracting metadata: {e}")

    return content, metadata


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
        raise Exception(
            f"Process '{command[0]}' timed out after {timeout} seconds.")
    except subprocess.CalledProcessError as e:
        raise Exception(
            f"Process '{command[0]}' failed with error: {e.stderr}")


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

# --- Main Orchestrator ---


async def run_all_extractors(html: str, url: str = None, strategy: str = "balanced", extract_metadata: bool = False) -> Dict[str, ResultItem]:
    """
    Runs all defined extraction functions, then applies post-processing
    (article extraction and deduplication) to each successful result.

    Args:
        html: The HTML content to extract from
        url: Optional URL for extractors that can utilize it (e.g., Goose3)
        strategy: Extraction strategy for Trafilatura variants ("precision", "recall", "balanced")
        extract_metadata: Whether to extract metadata for Trafilatura variants
    """
    loop = asyncio.get_running_loop()

    extractors = {
        # Tier 1
        # "readability-lxml": (extract_readability_lxml, html),
        # "jusText": (extract_justext, html),
        "Goose3": (extract_goose3, html, url),
        # Tier 2
        "go-trafilatura": (extract_go_trafilatura, html, url),
        # Custom - Three strategy variants
        "Trafilatura HP (Precision)": (extract_trafilatura_hp, html, "precision", extract_metadata),
        "Trafilatura HP (Recall)": (extract_trafilatura_hp, html, "recall", extract_metadata),
        "Trafilatura HP (Balanced)": (extract_trafilatura_hp, html, "balanced", extract_metadata),
        # Tier 3
        "boilerpipe3-keep-everything": (extract_boilerpipe3_keep_everything, html),
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
                base_results[name] = ResultItem(
                    content="", char_count=0, error="Processing timed out after 20 seconds.")
            except Exception as e:
                logger.error(
                    f"Future for '{name}' failed with an unexpected error: {e}")
                base_results[name] = ResultItem(
                    content="", char_count=0, error=f"An unexpected error occurred: {e}")

    # --- Create HTML and Markdown versions for specific extractors ---
    logger.info("--- Creating HTML and Markdown versions ---")

    # Extractors that should have both HTML and Markdown versions
    html_markdown_extractors = [
        "Goose3", "go-trafilatura", "boilerpipe3-keep-everything"]

    for extractor_name in html_markdown_extractors:
        if extractor_name in base_results and not base_results[extractor_name].error:
            # Create a copy for HTML version (preserve original HTML output)
            base_results[f"{extractor_name} (HTML)"] = ResultItem(
                content=base_results[extractor_name].content,
                char_count=base_results[extractor_name].char_count,
                error=None,
                metadata=base_results[extractor_name].metadata
            )

            # Rename original to Markdown (will be converted below)
            base_results[f"{extractor_name} (Markdown)"] = base_results.pop(
                extractor_name)
            logger.info(
                f"Created HTML and Markdown versions for: {extractor_name}")

    # --- Post-Processing Stage ---
    logger.info("--- Starting Post-Processing Stage ---")
    post_processed_results = {}

    # Instantiate the processor once to access its methods
    post_processor = TrafilaturaHp(
        {"url": "", "content": html, "fetch": False})
    soup = BeautifulSoup(html, 'html5lib')

    # Extract special article content once
    article_content = post_processor.extract_article(soup)
    if article_content:
        logger.info(
            f"Found {len(article_content)} chars of special article content for post-processing.")

    for name, result_item in base_results.items():
        # Skip HTML-only versions from post-processing
        # They should remain as pure HTML output
        if "(HTML)" in name:
            logger.info(f"Skipping post-processing for HTML version: {name}")
            continue

        if not result_item.error and result_item.content:
            try:
                logger.info(f"Post-processing result for: {name}")

                # Convert HTML to Markdown using markdownify and put it back in the result
                result_item.content = md(
                    result_item.content, heading_style="ATX", escape_html=False)

                # Combine article content with the extractor's main content
                combined_content = result_item.content
                if article_content:
                    combined_content = article_content + "\n" + combined_content

                # Apply deduplication
                deduplicated_content = post_processor.dedoublonnage(
                    combined_content)

                new_name = f"{name} + Post-Processing"
                post_processed_results[new_name] = ResultItem(
                    content=deduplicated_content,
                    char_count=len(deduplicated_content),
                    error=None
                )
            except Exception as e:
                logger.error(
                    f"Error during post-processing for {name}: {e}", exc_info=True)
                # Avoid adding a failed post-processing result
                pass

    # Merge original and post-processed results
    final_results = {**base_results, **post_processed_results}

    return dict(sorted(final_results.items()))
