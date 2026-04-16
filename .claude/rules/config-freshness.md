# Configuration Freshness

> Always work with the latest `.claude/` configuration, even mid-conversation.

## Rule

Before invoking any agent, applying any rule, or when the user references a config by name:
re-read the file from disk if it was created or modified in this conversation.

- Files created mid-conversation are immediately active.
- If disk content conflicts with your cached version, **disk wins**.
- When in doubt, re-read. The cost is negligible; the cost of stale rules is bad output.
