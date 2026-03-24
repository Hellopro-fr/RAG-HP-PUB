# Commit Message Protocol

## When to Generate

- Automatically after any response that creates or modifies files.
- Manually when asked via `/commit-msg` command.

## Format

Default: **Conventional Commits** (`feat:`, `fix:`, `refactor:`, `docs:`, `chore:`, `test:`).
If the user specifies a different format, use that instead.

## Output Structure

```
#### 📝 Commit Message

**🇬🇧 English**
\`\`\`
type(scope): concise description

- Detail 1
- Detail 2
\`\`\`

**🇫🇷 French**
\`\`\`
type(scope): description concise

- Détail 1
- Détail 2
\`\`\`
```

## Scope Rules

- Describe ONLY changes made in the current response.
- Never reference unrelated prior work.
- Keep the subject line under 72 characters.
