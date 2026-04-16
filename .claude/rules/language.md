# Language Rules

## Response Language

Determined ONLY by the user's CURRENT message. Nothing else.

- English message → respond entirely in English
- French message → respond entirely in French
- Mixed → use the dominant language

## Always English

Code identifiers, file names, directory names, log messages, error codes.

## Follows User's Language

Explanations, descriptions, code comments you ADD (existing stay as-is), summaries.

## Exception

Commit messages: always bilingual (EN + FR). See `commit-messages.md`.
