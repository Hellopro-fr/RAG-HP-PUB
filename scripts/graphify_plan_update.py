#!/usr/bin/env python3
"""Plan the graphify re-extraction: say WHICH scoped commands are still owed.

`scripts/graphify-status.sh` answers "is the graph stale?" with one bit. That is
not enough when you touched two graphed services in a session: you run one
`/graphify <path> --update`, the flag clears, and the second service is silently
left behind. This script answers the useful question instead — *which* paths are
owed an update, and whether each one actually needs the LLM.

Why git and not mtimes: graphify's own `detect_incremental` compares mtimes
against `graphify-out/manifest.json`. A `git checkout`, a merge, or a branch
switch bumps mtime without touching content, so that path over-reports wildly
(measured 2026-08-04: 201 files flagged for two services where a handful had
actually been edited). Git diffs content, so the plan below is precise.

Scope comes from `graphify-out/graph.json` — the same source the post-commit
hook uses, and tracked, so a teammate gets the right answer right after a pull.

Usage:
    python scripts/graphify_plan_update.py            # human-readable plan
    python scripts/graphify_plan_update.py --quiet    # exit 0 nothing owed, 1 owed
    python scripts/graphify_plan_update.py --commands # just the commands, one per line
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GRAPH = REPO / "graphify-out/graph.json"
SEP = chr(92)

CODE_EXT = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".cpp", ".c",
    ".rb", ".swift", ".kt", ".cs", ".scala", ".php", ".cc", ".cxx", ".hpp",
    ".h", ".kts", ".lua", ".toc",
}


def _rel(path: str) -> str:
    """Normalize a graph source_file to a repo-relative POSIX path."""
    p = path.replace(SEP, "/")
    marker = "RAG-HP-PUB/"
    if marker in p:
        p = p.split(marker, 1)[1]
    return p.lstrip("./")


class ScopeIndex:
    """Which files the graph already covers, and which area each one belongs to.

    An *area* is the unit a `/graphify <path> --update` can target: one service
    under apps-microservices, or one backbone root (libs, tools, docs, protos,
    model-optimizer). Anything outside a known area is out of scope entirely.
    """

    def __init__(self, files: set[str]):
        self.files = files
        self.areas = {a for a in (self._area(f) for f in files) if a}

    @classmethod
    def from_graph(cls, graph_path: Path = GRAPH) -> "ScopeIndex":
        data = json.loads(graph_path.read_text(encoding="utf-8"))
        return cls({_rel(n["source_file"]) for n in data["nodes"] if n.get("source_file")})

    @staticmethod
    def _area(rel: str) -> str | None:
        parts = [p for p in rel.split("/") if p]
        if not parts:
            return None
        if parts[0] == "apps-microservices":
            return "/".join(parts[:2]) if len(parts) > 1 else None
        return parts[0]

    def knows(self, rel: str) -> bool:
        return _rel(rel) in self.files

    def area_of(self, rel: str) -> str | None:
        """Area of a path, but only if that area is actually in the graph."""
        area = self._area(_rel(rel))
        return area if area in self.areas else None


@dataclass
class AreaChanges:
    area: str
    code: list[str] = field(default_factory=list)
    docs: list[str] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)  # not yet in the graph


@dataclass
class Action:
    area: str
    command: str
    needs_llm: bool
    hook_covers: bool
    code: int
    docs: int
    new_files: int


def classify_paths(paths, scope: ScopeIndex) -> dict[str, AreaChanges]:
    """Group changed paths by graph area, splitting code / doc / not-yet-graphed."""
    by_area: dict[str, AreaChanges] = {}
    for raw in paths:
        rel = _rel(raw)
        area = scope.area_of(rel)
        if area is None:
            continue
        entry = by_area.setdefault(area, AreaChanges(area))
        if Path(rel).suffix.lower() in CODE_EXT:
            entry.code.append(rel)
        else:
            entry.docs.append(rel)
        if not scope.knows(rel):
            entry.unknown.append(rel)
    return by_area


def build_plan(by_area: dict[str, AreaChanges]) -> list[Action]:
    """Turn grouped changes into the ordered list of commands still owed.

    The post-commit hook already re-extracts AST for files the graph knows, at
    zero LLM cost. It cannot admit a file the graph has never seen, and it
    cannot refresh doc semantics. So an area needs an explicit command when a
    doc changed or a new file appeared; otherwise the hook has it covered.
    """
    plan: list[Action] = []
    for area, ch in sorted(by_area.items()):
        needs_llm = bool(ch.docs)
        hook_covers = not ch.docs and not ch.unknown
        plan.append(Action(
            area=area,
            command=f"/graphify {area} --update",
            needs_llm=needs_llm,
            hook_covers=hook_covers,
            code=len(ch.code),
            docs=len(ch.docs),
            new_files=len(ch.unknown),
        ))
    return plan


def _git(*args) -> str:
    out = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True)
    return out.stdout if out.returncode == 0 else ""


DOC_EXT = {".md", ".json", ".txt", ".yml", ".yaml", ".rst"}


def never_extracted(scope: ScopeIndex) -> dict[str, list[str]]:
    """In-scope files the graph has never seen, regardless of the watermark.

    The watermark advances on *any* commit touching graph.json, not just one that
    extracted the file in front of it. So a scoped update that only re-extracts
    area A moves the watermark past a doc added to area B in the same window, and
    `changed_since_graph()` can never surface that doc again — it is invisible
    for good. Measured 2026-08-05: 187 in-scope files in that state, including a
    whole spec+plan chantier whose successor then had no lineage edge to point at.

    Reported as advisory only: it deliberately does NOT feed the exit code, so
    `--quiet` still converges to 0 once the changed-set is drained. Draining a
    138-file backlog is a decision for a human, not a precondition for the hook.
    """
    owed: dict[str, list[str]] = {}
    for raw in _git("ls-files").splitlines():
        f = raw.strip()
        if not f or f.startswith("graphify-out/"):
            continue
        rel_f = _rel(f)
        suffix = Path(rel_f).suffix.lower()
        if suffix not in CODE_EXT and suffix not in DOC_EXT:
            continue
        area = scope.area_of(rel_f)
        if area is None or scope.knows(rel_f):
            continue
        owed.setdefault(area, []).append(rel_f)
    return owed


def changed_since_graph() -> tuple[list[str], str]:
    """Files whose content moved since the graph was last committed, plus the watermark.

    Watermark = the last commit that touched graphify-out/graph.json. Everything
    after it is, by definition, not reflected in the graph. Uncommitted work is
    added on top so the plan covers what is still in the working tree.
    """
    watermark = _git("log", "-1", "--format=%H", "--", "graphify-out/graph.json").strip()
    paths: set[str] = set()
    if watermark:
        paths.update(l for l in _git("diff", "--name-only", f"{watermark}..HEAD").splitlines() if l)
    for line in _git("status", "--porcelain").splitlines():
        if len(line) > 3:
            paths.add(line[3:].strip().strip('"'))
    return sorted(paths), (watermark[:8] if watermark else "(inconnu)")


def main() -> int:
    quiet = "--quiet" in sys.argv
    commands_only = "--commands" in sys.argv

    if not GRAPH.exists():
        if not quiet:
            print("[graphify] aucun graphe dans ce depot (graphify-out/graph.json absent)")
        return 2

    scope = ScopeIndex.from_graph()
    changed, watermark = changed_since_graph()
    plan = [a for a in build_plan(classify_paths(changed, scope)) if not a.hook_covers]

    if commands_only:
        for action in plan:
            print(action.command)
        return 1 if plan else 0

    if quiet:
        return 1 if plan else 0

    def advisory() -> None:
        owed = never_extracted(scope)
        total = sum(len(v) for v in owed.values())
        if not total:
            return
        print()
        print(f"  --- pour information : {total} fichier(s) du scope jamais extraits ---")
        print("  Invisibles au diff ci-dessus (commites avant le repere). N'affecte pas")
        print("  le code de sortie ; a resorber deliberement, pas en prerequis du hook.")
        for area, files in sorted(owed.items(), key=lambda kv: -len(kv[1])):
            print(f"    {area:<52} {len(files):>4}")
        print("  Detail : python scripts/graphify_plan_update.py --never-extracted")

    if "--never-extracted" in sys.argv:
        for area, files in sorted(never_extracted(scope).items()):
            for f in sorted(files):
                print(f"{area}\t{f}")
        return 0

    if not plan:
        print(f"[graphify] rien a re-extraire (repere: {watermark}, "
              f"{len(changed)} fichier(s) modifie(s), aucun dans le scope du graphe)")
        advisory()
        return 0

    print(f"[graphify] {len(plan)} aire(s) a re-extraire - repere: {watermark}\n")
    for action in plan:
        why = []
        if action.docs:
            why.append(f"{action.docs} doc(s) modifiee(s) -> passe semantique (LLM)")
        if action.new_files:
            why.append(f"{action.new_files} fichier(s) absent(s) du graphe -> le hook ne les admet pas")
        print(f"  {action.command}")
        print(f"      {action.code} fichier(s) de code, {action.docs} doc(s)")
        for reason in why:
            print(f"      raison: {reason}")
        print()
    print("  Lancer les commandes ci-dessus depuis une session Claude Code, dans cet ordre,")
    print("  puis re-labelliser une seule fois a la fin (chaque merge re-clusterise).")
    advisory()
    return 1


if __name__ == "__main__":
    sys.exit(main())
