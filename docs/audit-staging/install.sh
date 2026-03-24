#!/bin/bash
# Claude Code Audit — Install Critical Files
# Run from project root: bash docs/audit-staging/install.sh

set -e

echo "=== Claude Code Audit — Installing Critical Files ==="
echo ""

# 1. Security rule
echo "📏 Installing .claude/rules/security.md"
read -p "   Copy security rule? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    cp docs/audit-staging/rules/security.md .claude/rules/security.md
    echo "   ✅ Installed"
else
    echo "   ⏭️ Skipped"
fi

# 2. Test-writer agent
echo ""
echo "🤖 Installing .claude/agents/test-writer.md"
read -p "   Copy test-writer agent? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    mkdir -p .claude/agents
    cp docs/audit-staging/agents/test-writer.md .claude/agents/test-writer.md
    echo "   ✅ Installed"
else
    echo "   ⏭️ Skipped"
fi

# 3. Pre-push command
echo ""
echo "⚡ Installing .claude/commands/pre-push.md"
read -p "   Copy pre-push command? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    mkdir -p .claude/commands
    cp docs/audit-staging/commands/pre-push.md .claude/commands/pre-push.md
    echo "   ✅ Installed"
else
    echo "   ⏭️ Skipped"
fi

echo ""
echo "=== Installation Complete ==="
echo "Review the fixes in docs/audit-staging/fixes/ manually."
echo "Don't forget to commit the new files: git add .claude/ && git commit"
