# /new-service-claude-md — Generate CLAUDE.md for a New Service

A new microservice has been added to the project. Generate its CLAUDE.md and update the root.

## Process

1. Ask the user:
   - **Service name:** (e.g., "notification-service")
   - **Service path:** (e.g., "services/notifications/")
   - **Runs locally?** Yes / No (remote-only with GPU/bandwidth requirements)

2. **Scan the service directory** thoroughly:
   - Read all config files (package.json, pyproject.toml, Dockerfile, Makefile, etc.)
   - Detect language, framework, database, dependencies.
   - Detect available commands (test, lint, build, dev).
   - Map the folder structure.
   - Identify connections to other services (imports from libs/, gRPC protos, API calls, event subscriptions).

3. **Generate `services/<name>/CLAUDE.md`** following this template:

   ```markdown
   # Service: <name>

   > <one-line purpose detected from README or code>

   ## [⚠️ Remote-Only Service — if applicable]
   [Only if remote-only: include the warning block with what CAN vs CANNOT be done locally]

   ## Tech Stack
   - Language: ...
   - Framework: ...
   - Database: ...
   - Testing: ...

   ## Commands
   [Only commands that actually work in the target environment]

   ## Structure
   [Folder tree of the service]

   ## Conventions
   [Detected from the code — naming, patterns, error handling]

   ## Dependencies on Other Services
   [What this service calls or subscribes to]
   ```

4. **Update root CLAUDE.md:**
   - Add a new row to the Service Map table.
   - Add a new @import line under "Per-Service Details."

5. **Show the user both files** (new service CLAUDE.md + root CLAUDE.md diff) and ask for confirmation before writing.

## Rules

- Keep the new service CLAUDE.md under 60 lines.
- Use ONLY information detectable from actual files. Mark unknowns as [TODO].
- If the service has no tests yet, note: "⚠️ No test suite detected. Add tests before relying on test feedback loops."
- If the service has no linter config, note: "⚠️ No linter detected. Consider adding [appropriate linter for the language]."
