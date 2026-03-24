# Fix: prix-traitement Port Discrepancy

## Problem
In `apps-microservices/prix-traitement/Dockerfile`:
- `EXPOSE 8595` (line in Dockerfile)
- But CMD uses `--port 8591`

The CLAUDE.md correctly documents port 8591.

## Action Required
[À VÉRIFIER PAR L'ÉQUIPE] — Determine the correct port:
- If 8591 is correct: update Dockerfile EXPOSE to 8591
- If 8595 is correct: update CMD and CLAUDE.md to 8595
- Check docker-compose.yml for the actual port mapping used in production
