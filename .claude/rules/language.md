# Language Rules

## How to Determine Response Language (STRICT)

The response language is determined ONLY by the language of the user's CURRENT message.
Nothing else. Not the existing code comments, not the documentation, not the CLAUDE.md files,
not the primer.md, not previous messages in the conversation.

- User's current message is in English → respond ENTIRELY in English.
- User's current message is in French → respond ENTIRELY in French.
- User's current message mixes both → respond in the language that dominates the message.

This rule overrides any bias from surrounding context. Even if the entire codebase,
all documentation, and all CLAUDE.md files are in French, if the user writes in English,
you MUST respond in English.

## What Stays in English Always

- Code identifiers: variable names, function names, class names, enum values.
- File names and directory names.
- Log messages and error codes in source code.

## What Follows the User's Language

- All explanations, descriptions, and conversational responses.
- Code comments you ADD or MODIFY (existing comments stay as-is).
- Summaries, analyses, and recommendations.

## Git Commit Messages (Exception)

Commit messages are ALWAYS generated in both English and French regardless of conversation
language, because they are shared with the full team via git history.
See @.claude/rules/commit-messages.md for format.