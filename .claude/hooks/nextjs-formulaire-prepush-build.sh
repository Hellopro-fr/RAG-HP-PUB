#!/usr/bin/env bash
# PreToolUse hook : avant un `git push`, si la range pushée touche
# apps-microservices/nextjs-formulaire-hp/, lance `npm run build` dans ce dossier.
# - Build OK → push autorisé.
# - Build KO → push bloqué, output remonté à Claude via permissionDecision "deny".
# - Prérequis manquants (npm, node_modules) → warning + push autorisé (fail open).

set -u
INPUT=$(cat)

PROJECT_ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
SERVICE_DIR="$PROJECT_ROOT/apps-microservices/nextjs-formulaire-hp"
SERVICE_PREFIX="apps-microservices/nextjs-formulaire-hp/"

cd "$PROJECT_ROOT" || exit 0

# 1. Déterminer la range pushée (upstream → origin/main → HEAD~)
if RANGE_FROM=$(git rev-parse '@{u}' 2>/dev/null); then
  RANGE="$RANGE_FROM..HEAD"
elif RANGE_FROM=$(git rev-parse origin/main 2>/dev/null); then
  RANGE="$RANGE_FROM..HEAD"
else
  RANGE="HEAD~..HEAD"
fi

# 2. La range touche-t-elle le formulaire ?
CHANGED=$(git diff --name-only "$RANGE" 2>/dev/null || echo "")
if ! echo "$CHANGED" | grep -q "^${SERVICE_PREFIX}"; then
  exit 0
fi

# 3. Pré-check setup local (fail open si manquant)
if ! command -v npm >/dev/null 2>&1; then
  >&2 echo "[hook nextjs-build] npm introuvable dans PATH — push autorisé sans build check"
  exit 0
fi
if [ ! -d "$SERVICE_DIR/node_modules" ]; then
  >&2 echo "[hook nextjs-build] $SERVICE_DIR/node_modules manquant"
  >&2 echo "[hook nextjs-build] Si tu travailles sur ce service, lance 'npm install' d'abord pour activer le check."
  >&2 echo "[hook nextjs-build] Push autorisé."
  exit 0
fi

# 4. Lancer le build
cd "$SERVICE_DIR" || exit 0
if BUILD_OUT=$(npm run build 2>&1); then
  exit 0
fi

# 5. Build KO → bloquer le push avec l'output (tail pour rester court)
TAIL=$(echo "$BUILD_OUT" | tail -60)
REASON="npm run build a échoué dans nextjs-formulaire-hp. Le push est bloqué — corriger avant de re-tenter.

--- Build output (last 60 lines) ---
$TAIL"

# Produire le JSON via node : garanti dispo puisque npm a tourné juste avant
# (npm est un script exécuté par node, donc si npm marche, node aussi).
# Fallback exit 2 + stderr si pour raison pathologique node manque.
if command -v node >/dev/null 2>&1; then
  node -e '
    const reason = process.argv[1];
    console.log(JSON.stringify({
      hookSpecificOutput: {
        hookEventName: "PreToolUse",
        permissionDecision: "deny",
        permissionDecisionReason: reason
      }
    }));
  ' "$REASON"
  exit 0
fi

# Fallback ultime : exit 2 + stderr (Claude Code bloque et affiche stderr)
>&2 echo "$REASON"
exit 2
