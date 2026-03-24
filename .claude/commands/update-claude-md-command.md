# /update-claude-md — Propose CLAUDE.md Updates

The user has encountered an issue or made a project change that requires updating CLAUDE.md files.

## Process

1. Ask the user: **"What happened? Pick one:"**
   - (a) Claude made a mistake I want to prevent in the future.
   - (b) Something changed in the project (new dependency, restructure, new convention).
   - (c) I just want you to rescan this service and refresh its CLAUDE.md.

2. Based on the answer:

   **(a) Mistake prevention:**
   - Ask what went wrong specifically.
   - Identify which CLAUDE.md or rule file should be updated (root, service, or a rule in `.claude/rules/`).
   - Propose the exact line(s) to add.
   - Show a diff preview: "I will add this line to [file]. Confirm?"
   - On confirmation, apply the edit surgically — do NOT rewrite the whole file.

   **(b) Project change:**
   - Ask what changed.
   - Identify all CLAUDE.md files affected.
   - Propose edits for each file.
   - Show a summary: which files, what changes.
   - On confirmation, apply all edits.

   **(c) Rescan:**
   - Read the service directory thoroughly (configs, source, tests).
   - Compare against the current CLAUDE.md for that service.
   - Propose additions, removals, and corrections.
   - Show a diff summary.
   - On confirmation, apply the changes.

## Rules

- NEVER rewrite an entire CLAUDE.md from scratch unless explicitly asked. Always make surgical edits.
- Keep every CLAUDE.md under 80 lines after the update.
- If a file would exceed 80 lines, suggest moving specific rules to `.claude/rules/` instead.
- After updating, verify the file is still valid markdown.
