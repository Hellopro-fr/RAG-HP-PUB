"""Tests for scripts/graphify_check_service.py."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import graphify_check_service as check  # noqa: E402


SAMPLE_POLICY = """
graphed:
  - path: apps-microservices/crawler-service
    added_at: 2026-04-24
  - path: apps-microservices/graph-rag-api-recherche-rust-service
    added_at: 2026-04-24

not_graphed:
  - path: apps-microservices/llm-service
    reason: too_small
  - path: apps-microservices/api-chat-llm
    reason: candidate_deferred
    details: Orchestration entry.
  - path: apps-microservices/nextjs-formulaire-hp
    reason: frontend
"""


@pytest.fixture()
def policy_path(tmp_path):
    p = tmp_path / "services-policy.yml"
    p.write_text(SAMPLE_POLICY, encoding="utf-8")
    return p


def test_classify_graphed(policy_path):
    verdict = check.classify("apps-microservices/crawler-service", policy_path=policy_path)
    assert verdict.status == "graphed"
    assert "crawler-service" in verdict.message


def test_classify_not_graphed_with_reason(policy_path):
    verdict = check.classify("apps-microservices/llm-service", policy_path=policy_path)
    assert verdict.status == "not_graphed"
    assert verdict.reason == "too_small"
    assert "too_small" in verdict.message


def test_classify_not_graphed_candidate(policy_path):
    verdict = check.classify("apps-microservices/api-chat-llm", policy_path=policy_path)
    assert verdict.status == "not_graphed"
    assert verdict.reason == "candidate_deferred"


def test_classify_unknown(policy_path):
    verdict = check.classify("apps-microservices/brand-new-service", policy_path=policy_path)
    assert verdict.status == "unclassified"
    assert "missing from" in verdict.message


def test_classify_normalises_trailing_slash(policy_path):
    verdict = check.classify("apps-microservices/crawler-service/", policy_path=policy_path)
    assert verdict.status == "graphed"


def test_classify_normalises_leading_dot_slash(policy_path):
    verdict = check.classify("./apps-microservices/crawler-service", policy_path=policy_path)
    assert verdict.status == "graphed"


def test_scan_apps_microservices_flags_missing(tmp_path, monkeypatch):
    policy = tmp_path / "services-policy.yml"
    policy.write_text(SAMPLE_POLICY, encoding="utf-8")

    apps = tmp_path / "apps-microservices"
    apps.mkdir()
    (apps / "crawler-service").mkdir()
    (apps / "llm-service").mkdir()
    (apps / "mystery-service").mkdir()

    monkeypatch.setattr(check, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(check, "POLICY_PATH", policy)

    unclassified = check.scan_missing()
    assert len(unclassified) == 1
    assert unclassified[0].endswith("mystery-service")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
