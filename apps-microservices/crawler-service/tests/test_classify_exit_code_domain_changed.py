"""Exit code 7 (domain changed) must classify as a domain_changed failure."""

from app.core.crawler_manager import CrawlerManager


def test_exit_7_classifies_as_domain_changed():
    message, failure_cause = CrawlerManager._classify_exit_code(7)
    assert failure_cause == "domain_changed"
    assert message is not None and len(message) > 0


def test_exit_7_is_not_unknown():
    message, _ = CrawlerManager._classify_exit_code(7)
    assert "inattendue" not in message  # not the catch-all "Erreur inattendue" branch


def test_exit_7_is_a_failure_not_success():
    # Mirrors the is_success check in _monitor_process (exit_code in (0, 2)).
    assert 7 not in (0, 2)


def test_success_codes_still_return_none():
    assert CrawlerManager._classify_exit_code(0) == (None, None)
    assert CrawlerManager._classify_exit_code(2) == (None, None)
