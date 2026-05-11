"""Pure page validator for api-detection-langue-fr.

Classifies a ScrapeResult against the requested URL into one of:
  - VALID — looks like real content
  - HTTP_ERROR — Playwright reported a 4XX/5XX status
  - SOFT_404 — body or final URL signals "page not found" despite 200 OK
  - REDIRECTED_TO_HOME — requested non-root path, final URL is root

No I/O. Heuristics + regex only. Easy unit-test surface.
"""
from __future__ import annotations

import logging
import re
from enum import Enum
from typing import Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from app.core.config import settings
from app.services.scraper import ScrapeResult

logger = logging.getLogger(__name__)


class ValidationVerdict(str, Enum):
    VALID = "valid"
    HTTP_ERROR = "http_error"
    SOFT_404 = "soft_404"
    REDIRECTED_TO_HOME = "redirected_to_home"


# Multilingual "page not found" patterns (FR + EN).
_NOT_FOUND_RE = re.compile(
    r"\b(404|not\s+found|page\s+not\s+found|page\s+introuvable|"
    r"page\s+non\s+trouv[eé]e|page\s+n['']existe\s+pas|erreur\s+404|"
    r"page\s+inexistante|file\s+not\s+found)\b",
    re.IGNORECASE,
)

# URL path containing a 404/error/not-found segment.
_URL_404_PATH_RE = re.compile(
    r"/(?:404|error|not[-_]found|page[-_]non[-_]trouv[eé]e|page[-_]introuvable)(?:/|$)",
    re.IGNORECASE,
)


def validate(scrape: ScrapeResult, requested_url: str) -> ValidationVerdict:
    """Classify a ScrapeResult against the requested URL.

    Order of checks:
      1. Hard HTTP error (status 400-599).
      2. Redirected to home (requested path non-root, final path root).
      3. Soft-404 (URL path marker, or title/H1 regex + thin body).
      4. Otherwise VALID.
    """
    if 400 <= scrape.status_code < 600:
        return ValidationVerdict.HTTP_ERROR

    if _is_redirect_to_home(scrape, requested_url):
        return ValidationVerdict.REDIRECTED_TO_HOME

    soft = _detect_soft_404(scrape)
    if soft is not None:
        return soft

    return ValidationVerdict.VALID


def _is_redirect_to_home(scrape: ScrapeResult, requested_url: str) -> bool:
    req_path = (urlparse(requested_url).path or "/").rstrip("/")
    final_path = (urlparse(scrape.final_url).path or "/").rstrip("/")
    return req_path != "" and final_path == ""


def _detect_soft_404(scrape: ScrapeResult) -> Optional[ValidationVerdict]:
    if _URL_404_PATH_RE.search(scrape.final_url):
        return ValidationVerdict.SOFT_404

    try:
        soup = BeautifulSoup(scrape.html, "lxml")
        title = (soup.title.string if soup.title else "") or ""
        h1_tag = soup.h1
        h1 = h1_tag.get_text(strip=True) if h1_tag else ""
        visible_len = _visible_text_length(soup)
    except Exception as e:
        logger.warning(
            f"[VALIDATE] parse error for {scrape.final_url}: {e} — fail-open as VALID"
        )
        return None

    if _NOT_FOUND_RE.search(title) and visible_len < settings.SOFT_404_TITLE_THIN_THRESHOLD:
        return ValidationVerdict.SOFT_404
    if _NOT_FOUND_RE.search(h1) and visible_len < settings.SOFT_404_H1_THIN_THRESHOLD:
        return ValidationVerdict.SOFT_404

    return None


def _visible_text_length(soup) -> int:
    """Lightweight visible-text length for the thin-content threshold."""
    for tag in soup(["script", "style", "noscript", "head"]):
        tag.decompose()
    return len(soup.get_text(separator=" ", strip=True))
