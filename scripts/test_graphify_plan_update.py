"""Tests for graphify_plan_update.py — the "what did I forget to re-extract?" planner.

Run: python scripts/test_graphify_plan_update.py
No framework, matching the convention of the sibling graphify test scripts.
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from graphify_plan_update import (  # noqa: E402
    ScopeIndex,
    build_plan,
    classify_paths,    never_extracted,
)

PASSED = 0
FAILED = 0


def check(name, actual, expected):
    global PASSED, FAILED
    if actual == expected:
        PASSED += 1
        print(f"  ok   {name}")
    else:
        FAILED += 1
        print(f"  FAIL {name}\n         attendu: {expected!r}\n         obtenu : {actual!r}")


def make_scope(source_files):
    """A ScopeIndex over a fake graph containing exactly these source files."""
    nodes = [{"id": f"n{i}", "source_file": sf} for i, sf in enumerate(source_files)]
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "graph.json"
        p.write_text(json.dumps({"nodes": nodes, "links": []}), encoding="utf-8")
        return ScopeIndex.from_graph(p)


# --- ScopeIndex ------------------------------------------------------------

scope = make_scope([
    "apps-microservices/crawler-service/main.py",
    "apps-microservices/crawler-service/app/core/x.py",
    "apps-microservices/api-gateway-go/cmd/server/main.go",
    "libs/common-utils/setup.py",
    "docs/guide.md",
])

check("aires connues", sorted(scope.areas),
      ["apps-microservices/api-gateway-go", "apps-microservices/crawler-service",
       "docs", "libs"])
check("fichier connu du graphe", scope.knows("libs/common-utils/setup.py"), True)
check("fichier inconnu du graphe", scope.knows("libs/common-utils/new.py"), False)
check("aire d'un service", scope.area_of("apps-microservices/crawler-service/app/core/x.py"),
      "apps-microservices/crawler-service")
check("aire backbone", scope.area_of("libs/common-utils/setup.py"), "libs")
check("hors scope -> aucune aire", scope.area_of("apps-microservices/api-ingestion/main.py"), None)

# Le separateur Windows ne doit pas casser l'appartenance au scope.
check("chemin windows normalise",
      make_scope(["apps-microservices" + chr(92) + "crawler-service" + chr(92) + "main.py"])
      .area_of("apps-microservices/crawler-service/main.py"),
      "apps-microservices/crawler-service")

# --- classify_paths --------------------------------------------------------

changed = [
    "apps-microservices/crawler-service/main.py",          # code, deja dans le graphe
    "apps-microservices/crawler-service/CLAUDE.md",        # doc, PAS dans le graphe -> nouveau
    "apps-microservices/crawler-service/tests/new_test.py",  # code, nouveau fichier
    "apps-microservices/api-ingestion/main.py",            # hors scope -> ignore
    "README.md",                                           # hors scope -> ignore
]
by_area = classify_paths(changed, scope)

check("aires impactees", sorted(by_area), ["apps-microservices/crawler-service"])
area = by_area["apps-microservices/crawler-service"]
check("code modifie", sorted(area.code),
      ["apps-microservices/crawler-service/main.py",
       "apps-microservices/crawler-service/tests/new_test.py"])
check("doc modifiee", area.docs, ["apps-microservices/crawler-service/CLAUDE.md"])
check("fichiers absents du graphe", sorted(area.unknown),
      ["apps-microservices/crawler-service/CLAUDE.md",
       "apps-microservices/crawler-service/tests/new_test.py"])
check("hors scope ignore", "apps-microservices/api-ingestion" in by_area, False)

# --- build_plan ------------------------------------------------------------

plan = build_plan(by_area)
check("une action planifiee", len(plan), 1)
check("commande scopee", plan[0].command,
      "/graphify apps-microservices/crawler-service --update")
check("passe semantique requise (doc modifiee)", plan[0].needs_llm, True)

# Code seul, tout deja connu du graphe -> le hook post-commit suffit.
code_only = classify_paths(["apps-microservices/crawler-service/main.py"], scope)
plan2 = build_plan(code_only)
check("code deja connu -> pas de LLM", plan2[0].needs_llm, False)
check("code deja connu -> hook suffit", plan2[0].hook_covers, True)

# Code nouveau -> le hook ne l'admettra jamais, il faut la commande.
new_code = classify_paths(["apps-microservices/crawler-service/tests/new_test.py"], scope)
plan3 = build_plan(new_code)
check("code nouveau -> hook insuffisant", plan3[0].hook_covers, False)

check("rien a faire -> plan vide", build_plan({}), [])


# --- never_extracted -------------------------------------------------------
# Garde-fou : un fichier commite AVANT le repere n'apparait dans aucun diff, il
# reste donc invisible pour toujours. Mesure du 2026-08-05 : 187 fichiers du
# scope dans cet etat, dont un chantier spec+plan entier dont le successeur
# n'avait plus aucune cible de lignage.

ne_scope = make_scope([
    "apps-microservices/crawler-service/main.py",
    "libs/common-utils/setup.py",
])


def fake_ls_files(tracked):
    """Neutralise _git pour ne pas dependre de l'etat reel du depot."""
    import graphify_plan_update as mod
    mod._git = lambda *a: (chr(10).join(tracked) if a and a[0] == "ls-files" else "")


fake_ls_files([
    "apps-microservices/crawler-service/main.py",     # deja dans le graphe
    "apps-microservices/crawler-service/nouveau.py",  # jamais extrait
    "apps-microservices/api-ingestion/main.py",       # aire hors graphe
    "graphify-out/graph.json",                        # toujours exclu
    "apps-microservices/crawler-service/logo.png",    # extension ignoree
])
check("jamais extrait: seul le fichier absent du graphe est signale",
      never_extracted(ne_scope),
      {"apps-microservices/crawler-service": ["apps-microservices/crawler-service/nouveau.py"]})

fake_ls_files(["apps-microservices/crawler-service/main.py", "libs/common-utils/setup.py"])
check("jamais extrait: rien a signaler quand tout est connu",
      never_extracted(ne_scope), {})

print(f"\n  {PASSED} passes, {FAILED} echecs")
sys.exit(1 if FAILED else 0)
