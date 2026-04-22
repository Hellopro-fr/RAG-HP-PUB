# Code Modification Rules

## Output Format

- Every code block preceded by its full file path as a Markdown header.
- New files/full rewrites: output the complete file.
- Surgical edits: ONLY the changed function/block with 3 lines of context, marked with `// ... existing code ...`.

## Surgical Edit Protocol

1. **Read first** — always read the file from disk. Never rely on memory.
2. **Minimal diff** — change only what the task requires. Preserve every unrelated line character-for-character.
3. **Preserve formatting** — keep original indentation, line structure, style.
4. **Preserve comments** — never remove unless factually incorrect after the change.
5. **Verify after** — run typecheck/lint. Fix before moving on.
