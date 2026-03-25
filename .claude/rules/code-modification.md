# Code Modification Rules

## Output Format

- Every code block MUST be preceded by its full file path as a Markdown header: `### src/api/UserService.js`
- For new files or full rewrites: output the complete file.
- For surgical edits: output ONLY the changed function/block with 3 lines of surrounding context, clearly marked with `// ... existing code ...` above and below. This saves tokens while preserving clarity.

## Surgical Edit Protocol

When modifying an existing file:

1. **Read first.** Always read the current file from disk before editing. Never rely on memory of a previous version.
2. **Minimal diff.** Change only what the task requires. Every unrelated line, comment, and blank line must be preserved character-for-character.
3. **Preserve formatting.** Keep original indentation, line structure, and style. Do not reformat, combine, or split lines.
4. **Preserve comments.** Never remove or alter comments unless a change makes one factually incorrect — then update it.
5. **Verify after.** Run typecheck/lint after the edit. If it fails, fix it before moving on.

## Mental Model

You are a **patch tool**: read current state → compute minimal diff → apply only that diff → verify.
