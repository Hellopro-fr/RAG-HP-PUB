---
description: Absorbe et résume plusieurs fichiers ou un sujet large avant d'en discuter — sans rien modifier
argument-hint: <fichiers ou sujet>
allowed-tools: Read, Grep, Glob
---
# /understand — Content Comprehension

Absorb and summarize **multiple files, uploads, or broad topics** before discussing them. Use `/explain` instead for a single file or code block deep-dive.

The user wants you to absorb and understand content before discussing it.

1. Identify the content: uploaded files first, then any text following the command.
   Before reading, size it: lines × ~15 tokens per file, docs included.
2. Read and analyze the content thoroughly — but "thoroughly" is not "exhaustively": read in full only the
   decision core (the function that produces the verdict and its orchestrator); read the periphery by its plan
   (`def`/`class` lines, then the pivot functions only); delegate what lives outside the repo (callers,
   deployment).
3. Provide a detailed summary of:
   - The content's purpose.
   - Key components, sections, or concepts.
   - Notable patterns, dependencies, or constraints.

Do NOT generate code or make changes.

End with: **"What would you like to discuss or work on next?"**
