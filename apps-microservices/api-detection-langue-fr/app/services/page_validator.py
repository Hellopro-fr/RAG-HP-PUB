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
from urllib.parse import urljoin, urlparse, urlunparse

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


# =============================================================================
# Transient HTTP statuses
# =============================================================================

# Statuts qui reflètent les conditions du fetch (WAF/auth/rate-limit/incident
# serveur), pas une propriété de la page. Un retry (rotation proxy) peut
# passer. 404/410 et les autres 4xx restent définitifs (http_error, TTL 7j).
TRANSIENT_HTTP_STATUSES = frozenset({401, 403, 407, 408, 425, 429})


def is_transient_http_status(status_code: int) -> bool:
    """True quand l'erreur HTTP vaut un retry (WAF/auth/rate-limit/5xx)."""
    return status_code in TRANSIENT_HTTP_STATUSES or 500 <= status_code < 600


# =============================================================================
# Stub-page redirect target
# =============================================================================

# Les stubs sont de tout petits documents ; borne le coût du parse.
_STUB_MAX_HTML_LEN = 20_000

_META_REFRESH_URL_RE = re.compile(r"url\s*=\s*['\"]?([^'\">;]+)", re.IGNORECASE)

_NON_NAV_HREF_RE = re.compile(r"^(#|mailto:|tel:|javascript:)", re.IGNORECASE)


def find_stub_redirect_target(html: str, base_url: str) -> Optional[str]:
    """Target URL when the page is a tiny stub whose only purpose is to point
    elsewhere: a meta-refresh, or a lone same-host link ("Page has moved —
    click here"). Returns None for every other page.

    Guards:
    - raw HTML larger than _STUB_MAX_HTML_LEN → None (real pages);
    - visible text >= NLP_MIN_TEXT_LENGTH → None (page has actual content);
    - anchor signal requires a SINGLE distinct same-host target — parked/for-
      sale pages are excluded because their lone link is off-host.
    """
    if not html or len(html) > _STUB_MAX_HTML_LEN:
        return None

    try:
        soup = BeautifulSoup(html, "lxml")

        # Meta refresh — read BEFORE _visible_text_length decomposes <head>.
        meta_target: Optional[str] = None
        meta = soup.find(
            "meta", attrs={"http-equiv": re.compile(r"^refresh$", re.IGNORECASE)}
        )
        if meta:
            m = _META_REFRESH_URL_RE.search(meta.get("content") or "")
            if m:
                meta_target = m.group(1).strip()

        anchor_hrefs = [a.get("href", "").strip() for a in soup.find_all("a", href=True)]

        if _visible_text_length(soup) >= settings.NLP_MIN_TEXT_LENGTH:
            return None
    except Exception as e:
        logger.warning(f"[STUB] parse error for {base_url}: {e} — no hop")
        return None

    def _resolve(href: str) -> Optional[str]:
        if not href or _NON_NAV_HREF_RE.match(href):
            return None
        resolved = urljoin(base_url, href)
        p = urlparse(resolved)
        if p.scheme not in ("http", "https") or not p.netloc:
            return None
        # Fragment supprimé : même document = pas une cible de hop.
        return urlunparse((p.scheme, p.netloc, p.path or "/", p.params, p.query, ""))

    base_resolved = _resolve(base_url)

    if meta_target:
        resolved = _resolve(meta_target)
        if resolved and resolved != base_resolved:
            return resolved

    def _same_host(netloc_a: str, netloc_b: str) -> bool:
        a = netloc_a.lower().removeprefix("www.")
        b = netloc_b.lower().removeprefix("www.")
        return a != "" and a == b

    base_netloc = urlparse(base_url).netloc
    targets = set()
    for href in anchor_hrefs:
        resolved = _resolve(href)
        if not resolved or resolved == base_resolved:
            continue
        if not _same_host(urlparse(resolved).netloc, base_netloc):
            continue
        targets.add(resolved)

    if len(targets) == 1:
        return targets.pop()
    return None
