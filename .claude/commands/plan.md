# /plan — Interactive Planning

Summarize your understanding of the user's request:
1. Restate the goal in one sentence.
2. List the steps you would take.
3. If the user included "with file details", also provide a table:
   | File Path | Action | Explanation |
   |-----------|--------|-------------|
   with actions: `CREATE`, `UPDATE`, or `DELETE`.

## Complexity Escalation

Assess the task complexity:

- **Simple** (1-2 files, single service): Present the plan as above — steps + optional file table.
- **Complex** (3+ files, cross-service, or shared component changes): Escalate the plan with:
  - **File structure map**: List all files to create/modify BEFORE defining steps.
  - **No placeholders**: Every step must contain the actual content needed (exact file paths, exact changes). Never write "TBD", "implement later", or "similar to step N".
  - **Self-review**: After writing the plan, re-check against the original request — any gaps? Any placeholder language? Any type/name inconsistencies between steps?

Do NOT generate any code or solution.

End with: **"Does this align with what you are looking for? Please confirm to proceed."**

Wait for explicit confirmation before doing any work.
