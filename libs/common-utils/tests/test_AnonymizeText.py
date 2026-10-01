"""Tests for AnonymizeText Presidio-engine singleton reuse.

presidio_* are heavy (load a ~1GB spaCy model) and not installed locally, so
they are faked here. The point of the fix under test: the AnalyzerEngine /
AnonymizerEngine must be built ONCE and reused across documents, not
re-instantiated per call (per-doc model reload was the OOM driver).
"""

import importlib.machinery
import importlib.util
import sys
import types


def _install_fake_presidio():
    class _FakeAnalyzer:
        instances = 0

        def __init__(self):
            type(self).instances += 1

        def analyze(self, text, entities, language):
            return []

    class _FakeAnonymizer:
        instances = 0

        def __init__(self):
            type(self).instances += 1

        def anonymize(self, text, analyzer_results, operators):
            return types.SimpleNamespace(text=text)

    def _mod(name):
        m = types.ModuleType(name)
        m.__spec__ = importlib.machinery.ModuleSpec(name, loader=None)
        return m

    analyzer_mod = _mod("presidio_analyzer")
    analyzer_mod.AnalyzerEngine = _FakeAnalyzer
    anonymizer_mod = _mod("presidio_anonymizer")
    anonymizer_mod.AnonymizerEngine = _FakeAnonymizer
    entities_mod = _mod("presidio_anonymizer.entities")
    entities_mod.OperatorConfig = lambda *a, **k: None

    sys.modules["presidio_analyzer"] = analyzer_mod
    sys.modules["presidio_anonymizer"] = anonymizer_mod
    sys.modules["presidio_anonymizer.entities"] = entities_mod
    return _FakeAnalyzer, _FakeAnonymizer


if importlib.util.find_spec("presidio_analyzer") is None:
    _FakeAnalyzer, _FakeAnonymizer = _install_fake_presidio()
else:  # pragma: no cover - real presidio present
    from presidio_analyzer import AnalyzerEngine as _FakeAnalyzer
    from presidio_anonymizer import AnonymizerEngine as _FakeAnonymizer

from common_utils.cleaner.AnonymizeText import AnonymizeText  # noqa: E402


def test_engines_built_once_across_documents():
    AnonymizeText._analyzer = None
    AnonymizeText._anonymizer = None
    _FakeAnalyzer.instances = 0
    _FakeAnonymizer.instances = 0

    # two separate instances, two documents each — engines must load only once
    AnonymizeText().anonymize_text("call contact@example.com now")
    AnonymizeText().anonymize_text("email a@b.com again")

    assert _FakeAnalyzer.instances == 1
    assert _FakeAnonymizer.instances == 1


def test_anonymize_returns_text():
    AnonymizeText._analyzer = None
    AnonymizeText._anonymizer = None
    out = AnonymizeText().anonymize_text("hello Page 1 of 3 world")
    assert "hello" in out
    assert "Page 1 of 3" not in out  # page-number pattern stripped
