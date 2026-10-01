"""POST /agents/{code}/run (exécution synchrone) et GET /agents/{code} (fiche publiée)."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from app.core.api_v2 import ErreurApiV2
from app.core.dependances import get_dependances
from app.core.execution import AgentIntrouvable, Dependances, executer_agent
from app.schemas.agents import DemandeExecution, ReponseExecution

router = APIRouter(prefix="/agents", tags=["Agents"])
CODES_HTTP = {"ok": 200, "format_invalide": 422, "erreur": 502, "timeout": 504}


@router.post("/{code}/run", response_model=ReponseExecution)
def run(code: str, demande: DemandeExecution, deps: Dependances = Depends(get_dependances)):
    try:
        resultat = executer_agent(code, demande.input, demande.version, demande.origine,
                                  demande.id_user_bo, deps)
    except AgentIntrouvable as exc:
        raise HTTPException(status_code=404, detail=exc.raison)
    except ErreurApiV2:
        raise HTTPException(status_code=503, detail="api_v2_indisponible")
    return JSONResponse(status_code=CODES_HTTP[resultat["statut"]],
                        content=ReponseExecution(**resultat).model_dump())


@router.get("/{code}")
def lire(code: str, deps: Dependances = Depends(get_dependances)):
    try:
        fiche = deps.api_v2.lire_fiche(code, "publiee") or {}
    except ErreurApiV2:
        raise HTTPException(status_code=503, detail="api_v2_indisponible")
    if not fiche.get("trouve"):
        raise HTTPException(status_code=404, detail=fiche.get("raison", "agent_inconnu"))
    return fiche
