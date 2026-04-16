# /new-feature-claude-md — Update CLAUDE.md After a New Feature

A significant new feature or module has been added to an existing service. Update its CLAUDE.md.

## When to Use

- New module/domain added (e.g., WebSocket support, Stripe billing)
- New external dependency integrated
- Folder structure changed significantly
- New commands became available

Do NOT use for minor changes (bug fixes, small refactors, single endpoint).

## Process

1. Ask: **Which service?** and **What was added?**
2. Read the current service CLAUDE.md.
3. Scan the service directory for structural changes (new folders, dependencies, scripts, tests).
4. Propose surgical edits — add to Tech Stack, Commands, Structure, Conventions, or Dependencies as needed.
5. Show diff preview and ask for confirmation.

## Rules

Same as `/update-claude-md`: surgical edits only, keep under 80 lines, extract to `.claude/rules/` if needed.
