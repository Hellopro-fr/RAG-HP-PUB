# /new-feature-claude-md — Update CLAUDE.md After a New Feature

A significant new feature or module has been added to an existing service. Update its CLAUDE.md to reflect the change.

## When to Use

Use this when:
- A new module/domain was added (e.g., "added WebSocket support to gateway")
- A new external dependency was integrated (e.g., "added Stripe billing to auth-service")
- The folder structure changed significantly (e.g., "added a jobs/ directory for background workers")
- New commands became available (e.g., "added npm run seed for database seeding")

Do NOT use for minor changes (bug fixes, small refactors, adding a single endpoint).

## Process

1. Ask the user:
   - **Which service?** (path)
   - **What was added?** (brief description)

2. **Read the current service CLAUDE.md.**

3. **Scan the service directory** for changes:
   - New folders or files that indicate structural change.
   - New dependencies in config files.
   - New scripts or commands.
   - New test directories or patterns.

4. **Propose surgical edits** to the existing CLAUDE.md:
   - Add new items to Tech Stack if a major dependency was added.
   - Add new commands to Commands section if new scripts exist.
   - Update Structure if new folders appeared.
   - Add new conventions if the feature introduces patterns.
   - Update Dependencies on Other Services if new inter-service calls exist.

5. **Show a diff preview** of the proposed changes and ask for confirmation.

## Rules

- NEVER rewrite the full file. Only add or modify the lines that changed.
- If the CLAUDE.md would exceed 80 lines after the update, suggest extracting detailed feature docs into a `.claude/rules/<feature-name>.md` file and adding an @import.
- Do not remove existing content unless it is now factually incorrect.
