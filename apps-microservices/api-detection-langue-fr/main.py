import logging
from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from app.api.routes import router
# Import to ensure metric objects are registered with the default registry.
from app.core import metrics  # noqa: F401

# Configuration du logging — INFO pour voir les logs de stratégie proxy, retry, etc.
# Sans cette configuration, Python utilise WARNING par défaut et masque les logs INFO.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

app = FastAPI(
    title="API Détection Langue Française",
    description=(
        "Détecte si un site web est en français ou dispose d'une version française.\n\n"
        "## Pipeline de détection\n\n"
        "1. **Cache Redis** — Lookup par domaine (TTL 30j ok, 7j nok, 6h transitoire). Bypass via `force_refresh`.\n"
        "2. **Fetch HTML** — Playwright headless via proxy Apify (3 tentatives auto-rotation + fallback variantes URL).\n"
        "3. **Détection challenge** — Identifie Cloudflare, DataDome, Squid, Imperva, pages HTTP 4XX/5XX.\n"
        "4. **Analyse URL** — TLD `.fr` (signal fort), `/fr/` path, `lang=fr` query, sous-domaine `fr.`\n"
        "5. **Balises HTML** — `<html lang>`, `<meta og:locale>`, `<meta http-equiv=content-language>`\n"
        "6. **NLP** — fastText (primaire) + langdetect/langid (cross-check). Cookie consent strippé avant analyse.\n"
        "7. **Liens alternatifs** — hreflang, data-lang, data-gt-lang, liens `/fr/`, options (triés par fiabilité).\n"
        "8. **Matrice de décision** — 9 cas combinant signaux URL/HTML/NLP avec scores de confiance.\n\n"
        "## Modes\n\n"
        "- `simple` — URL + balises HTML uniquement (rapide)\n"
        "- `complete` — + NLP + liens alternatifs (complet)\n"
        "- `first_match` — Batch groupé : arrêt au premier FR par groupe\n"
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

@app.get("/metrics", include_in_schema=False)
async def metrics_endpoint() -> Response:
    """Prometheus metrics exposition endpoint."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


app.include_router(router, prefix="/api/v1")


@app.get("/")
async def root():
    return {
        "message": "API Détection Langue Française",
        "documentation": "/docs",
        "version": "1.0.0"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8999)
