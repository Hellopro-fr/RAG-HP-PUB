# Configuration Freshness Rules

> Ensures the agent always works with the latest `.claude/` configuration, even mid-conversation.

## When to Re-Read Configuration

1. **Before invoking any agent** (`@code-reviewer`, `@debugger`, `@test-writer`, `@doc-writer`):
   - Re-read the agent's `.md` file to pick up any changes made earlier in the conversation.

2. **Before applying any rule** (`security.md`, `impact-awareness.md`, etc.):
   - If the rule file was created or modified in this conversation, re-read it.

3. **After creating or updating any `.claude/` file**:
   - Treat the new content as immediately active. Do not rely on the version loaded at session start.

4. **When the user references a command, agent, or rule by name**:
   - Re-read the file to ensure you have the current version, not a stale cached version.

## How to Apply

- When in doubt, re-read the file. The cost of reading is negligible; the cost of applying stale rules is a bad output.
- If a rule or agent was created during the current conversation, it is valid and must be followed — even if it was not present at session start.
- If you detect a conflict between a stale instruction in your context and a freshly-read file, the file on disk wins.
