"""graphify service classifier for RAG-HP-PUB.

Reads `graphify-out/services-policy.yml` — the single source of truth for
which services under `apps-microservices/` are in the unified knowledge
graph and which are intentionally excluded.

Two modes:

1. `python scripts/graphify_check_service.py <service-path>`
   Verdict for one service. Exit code 0 on any classified answer, 1 if the
   path is missing from both lists.

2. `python scripts/graphify_check_service.py --scan`
   Cross-checks the filesystem against the policy. Exits 0 when every
   `apps-microservices/<name>` directory is classified, 1 if any are
   missing. Used by `.github/workflows/graphify-coverage-check.yml` to
   block PRs that add a service without updating the policy.

Designed to be callable both locally (by a dev who wants to know "is this
service in the graph?") and from CI.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
POLICY_PATH = REPO_ROOT / "graphify-out" / "services-policy.yml"


def _apps_dir() -> Path:
    """Resolve apps-microservices/ relative to the current REPO_ROOT.

    Reading the module attribute each call lets tests monkeypatch REPO_ROOT
    and get a matching apps dir in the same tmp_path.
    """
    return REPO_ROOT / "apps-microservices"


@dataclass
class Verdict:
    status: str  # "graphed" | "not_graphed" | "unclassified"
    reason: str | None
    details: str | None
    message: str


def _normalize(path_str: str) -> str:
    """Return the canonical relative form used by the policy."""
    p = Path(path_str.rstrip("/\\").lstrip("./"))
    return str(p).replace("\\", "/")


def _load_policy(policy_path: Path | None = None) -> dict:
    target = policy_path or POLICY_PATH
    if not target.exists():
        raise SystemExit(f"error: policy file not found at {target}")
    with open(target, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def classify(service_path: str, *, policy_path: Path | None = None) -> Verdict:
    normalized = _normalize(service_path)
    policy = _load_policy(policy_path)

    for entry in policy.get("graphed", []) or []:
        if _normalize(entry.get("path", "")) == normalized:
            notes = entry.get("notes") or ""
            suffix = f" — {notes}" if notes else ""
            return Verdict(
                status="graphed",
                reason=None,
                details=notes or None,
                message=f"'{normalized}' is ALREADY IN the unified graph (added_at={entry.get('added_at')}){suffix}",
            )

    for entry in policy.get("not_graphed", []) or []:
        if _normalize(entry.get("path", "")) == normalized:
            reason = entry.get("reason", "")
            details = entry.get("details") or ""
            msg = (
                f"'{normalized}' is INTENTIONALLY NOT in the graph\n"
                f"  reason: {reason}"
            )
            if details:
                msg += f"\n  details: {details}"
            msg += (
                "\n  if you want to change this, update graphify-out/services-policy.yml "
                "and follow the 'Adding a service' checklist in docs/graphify-guide-en.md"
            )
            return Verdict(status="not_graphed", reason=reason, details=details or None, message=msg)

    return Verdict(
        status="unclassified",
        reason=None,
        details=None,
        message=(
            f"'{normalized}' is missing from graphify-out/services-policy.yml\n"
            f"  decide whether it belongs in the unified graph and add it to either "
            f"`graphed:` or `not_graphed:`. See docs/graphify-guide-en.md § 'Adding a service'."
        ),
    )


def scan_missing() -> list[str]:
    """Return the list of apps-microservices/<name> directories absent from policy."""
    apps = _apps_dir()
    if not apps.exists():
        return []
    policy = _load_policy()
    known: set[str] = set()
    for entry in policy.get("graphed", []) or []:
        known.add(_normalize(entry.get("path", "")))
    for entry in policy.get("not_graphed", []) or []:
        known.add(_normalize(entry.get("path", "")))

    missing: list[str] = []
    for service_dir in sorted(apps.iterdir()):
        if not service_dir.is_dir():
            continue
        rel = _normalize(f"apps-microservices/{service_dir.name}")
        if rel not in known:
            missing.append(str(service_dir))
    return missing


def _cli() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("service", nargs="?", help="apps-microservices/<name> path to classify")
    group.add_argument("--scan", action="store_true", help="scan for unclassified services (CI mode)")
    args = parser.parse_args()

    if args.scan:
        missing = scan_missing()
        if not missing:
            print("[graphify-coverage] all services classified in graphify-out/services-policy.yml")
            return 0
        print(
            "[graphify-coverage] FAIL — the following service directories are not classified:",
            file=sys.stderr,
        )
        for m in missing:
            print(f"  - {m}", file=sys.stderr)
        print(
            "\nAdd each path to either `graphed:` or `not_graphed:` in "
            "graphify-out/services-policy.yml. See docs/graphify-guide-en.md "
            "§ 'Adding a service' for the full checklist.",
            file=sys.stderr,
        )
        return 1

    verdict = classify(args.service)
    print(verdict.message)
    return 1 if verdict.status == "unclassified" else 0


if __name__ == "__main__":
    sys.exit(_cli())
