# agent-service

Exécute les agents IA HelloPro (remplacement de Dust) avec LangGraph. Les outils (recherche web,
MCP HelloPro) sont ceux des fournisseurs : le service les déclare, il n'en exécute aucun.
Fiches et journal via l'API v2 PHP (`etape = agents`) ; aucun accès MySQL.
Doc : `analyse_prix_v2/dust_maison_langgraph_decision_et_plan.md`.

## Lancer / tester
- Tests : `python -m venv .venv && .venv/Scripts/python -m pip install -r requirements-dev.txt && .venv/Scripts/python -m pytest -v`
- Image : `docker build -f apps-microservices/agent-service/Dockerfile .` (contexte = racine du repo), port 8596, profil `agent-service`.

## Routes
- `POST /agents/{code}/run` `{input, origine?, version?: publiee|brouillon, id_user_bo?}` → 200 ok, 422 format invalide ou entrée vide, 502 erreur fournisseur, 504 délai, 404 agent introuvable, 503 API v2 injoignable.
- `GET /agents/{code}` : fiche publiée. `GET /health`.

## Variables (.env)
`HELLOPRO_API_URL`, `HP_TOKEN`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`,
`MCP_GATEWAY_URL`, `MCP_CLIENT_ID`, `MCP_CLIENT_SECRET`, `TIMEOUT_MODELE_S` (300), `TTL_CACHE_FICHE_S` (60).

## Pièges
- La version publiée est en cache 60 s : une publication s'applique en moins d'une minute.
- Outils refusés quand `capacites` (renvoyé par `agents.php` : XML de prix du BO + règle MCP) les met à 0 : MCP Gemini, tous les outils DeepSeek, modèle absent des XML.
