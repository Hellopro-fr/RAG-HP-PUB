"""Test bootstrap — stubs heavy native/3rd-party deps so unit tests can
import the service without installing chardet, langdetect, langid, fasttext,
playwright, camoufox, etc."""
import sys
from unittest.mock import MagicMock

for _name in (
    "chardet",
    "langdetect",
    "langid",
    "fasttext",
    "playwright",
    "playwright.async_api",
    "camoufox",
    "camoufox.async_api",
    "lxml",
):
    sys.modules.setdefault(_name, MagicMock())
