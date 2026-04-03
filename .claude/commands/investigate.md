# /investigate — Evidence-Based Statement Verification

The user provides a statement or claim about the codebase. Your job is to verify it with evidence.

## Input

The user provides a statement to verify, e.g.:
- "All processor services use DLQ"
- "Every service has a health check endpoint"
- "The api-gateway has no rate limiting"
- "Redis is only used by crawler services"

## Process

1. **Parse the claim** into a testable assertion.
2. **Gather evidence** — use Grep, Glob, Read, and Bash (git log/git blame) to search the codebase exhaustively.
3. **Check every relevant service/file** — do not sample. If the claim is "all services do X", check ALL services.
4. **Produce a verdict** with one of these labels:

   | Verdict | Meaning |
   |---------|---------|
   | **CONFIRMED** | Evidence supports the claim across all relevant files/services |
   | **PARTIALLY TRUE** | True for some but not all — list exceptions |
   | **FALSE** | Evidence contradicts the claim |
   | **INCONCLUSIVE** | Not enough information in the codebase to determine |

5. **Present findings:**

   ```
   ## Investigation: "<original statement>"

   **Verdict: [LABEL]**

   ### Evidence
   - [file:line] — supports/contradicts because...
   - [file:line] — supports/contradicts because...

   ### Exceptions (if PARTIALLY TRUE)
   - [service/file] — does not match because...

   ### Summary
   One paragraph explaining the conclusion.
   ```

## Rules

- Do NOT modify any files. This is a read-only investigation.
- Be exhaustive — check every service, not just a sample.
- Use `grep` across the entire codebase for patterns, not just a few known files.
- If the claim involves history ("was X ever changed?"), use `git log` and `git blame`.
- If the investigation reveals a real problem, flag it: "**Finding:** This investigation revealed [issue]. Consider fixing."
