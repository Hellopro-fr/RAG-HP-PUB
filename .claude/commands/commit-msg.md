---
description: Génère un message de commit Conventional Commits bilingue EN+FR agrégeant les changements de la session
allowed-tools: Bash, Read
---

# /commit-msg — Generate Commit Message

Aggregate everything changed **in this session** into a single commit message.
(The `conventional-commits.py` PreToolUse hook validates the format at commit time; this command writes it.)

## Format

- **Conventional Commits**: `feat|fix|refactor|docs|chore|test|perf|style|ci|build|revert(scope): subject`
- **Bilingual EN + FR**, both bodies in the same message, separated by a `---` line.
- Subject line: imperative, lower case after the colon, aim for under 72 characters.
- Describe ONLY what changed in this session — never restate unrelated prior work.
- Say *why*, not just *what*. A reviewer reading it in six months must understand the motivation without opening the diff.
- Ask the user which language they want (EN / FR / both) before committing, unless they already said.

## Process

1. `git status --porcelain` and `git diff --stat HEAD` to establish the real scope.
2. Group the changes by intent, not by file.
3. Produce the message. If several unrelated intents are mixed, say so and propose splitting the commit.

If no file changes were made in this session, respond:
**"No file changes detected in this session. Please describe what was done and I will generate the commit message."**
