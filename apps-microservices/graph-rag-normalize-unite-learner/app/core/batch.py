"""
BatchRunner — exécution MANUELLE par lot.

Déclenché à la demande (HTTP /run). Draine jusqu'à `limit` messages du manual DLQ,
les DÉDUPLIQUE par unité, traite `MAX_PARALLEL` unités en parallèle (1 seul réplica),
puis ACK les unités traitées et REQUEUE celles en erreur de service. Retourne un rapport.

Aucune consommation continue : pas de boucle nack infinie, pas de claim concurrent.
"""
import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

import aio_pika

from app.config import settings
from app.core.dynamic_client import DynamicValidationError
from app.core.learner import (
    STATUS_PENDING,
    STATUS_PROCESSING_ERROR,
    STATUS_SKIPPED,
    STATUS_VERIF_ERROR,
    Learner,
    ProcessingError,
    UnitOutcome,
)

logger = logging.getLogger(__name__)


def _parse_message(body: bytes) -> Optional[Dict[str, Any]]:
    """Extrait (unite, label, values, type_donnee, failed_node_entry) ou None si inexploitable."""
    try:
        payload = json.loads(body.decode())
    except (json.JSONDecodeError, ValueError):
        return None
    fne = payload.get("failed_node_entry") or payload
    props = (fne.get("node") or {}).get("properties") or {}
    unite = props.get("unite")
    if not unite or str(unite).strip().lower() in ("", "null"):
        return None
    type_donnee = props.get("type_donnee")
    if type_donnee == "numeric_range":
        values = [props.get("valeur_min"), props.get("valeur_max")]
    else:
        values = [props.get("valeur")]
    values = [v for v in values if v is not None]
    return {
        "unite_key": str(unite).strip().lower(),
        "label": str(props.get("label") or "").strip()[:255],
        "values": values,
        "failed_node_entry": fne,
    }


class BatchRunner:
    def __init__(self, learner: Learner):
        self.learner = learner
        self.semaphore = asyncio.Semaphore(settings.MAX_PARALLEL)

    async def _fetch_referentiel(self) -> Dict[str, Any]:
        ref = await self.learner.api.get_referentiel()
        if ref is None:
            raise ProcessingError("référentiel BO injoignable (impossible de préparer le batch)")
        canonical_units = {
            str(r.get("dimension", "")).strip(): str(r.get("unite_canonique", "")).strip()
            for r in ref.get("dimension_canonique", [])
            if r.get("dimension") and r.get("unite_canonique")
        }
        # Garde santé (#8) : un référentiel sans canoniques ferait inventer une dimension par
        # unité au LLM → pollution massive. On annule le run plutôt que d'apprendre n'importe quoi.
        if not canonical_units:
            raise ProcessingError(
                "référentiel BO vide/incohérent (aucune dimension canonique) — run annulé"
            )
        return {"canonical_units": canonical_units}

    async def _drain(self, queue, limit: int) -> List[aio_pika.abc.AbstractIncomingMessage]:
        messages = []
        while len(messages) < limit:
            msg = await queue.get(fail=False, timeout=5)
            if msg is None:
                break
            messages.append(msg)
        return messages

    async def run(self, limit: Optional[int] = None) -> Dict[str, Any]:
        limit = limit or settings.DEFAULT_LIMIT
        limit = max(1, min(int(limit), settings.MAX_LIMIT))  # borne dure (anti-drain massif)
        referentiel = await self._fetch_referentiel()

        connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
        try:
            channel = await connection.channel()
            exchange = await channel.declare_exchange(
                settings.INPUT_EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True
            )
            queue = await channel.declare_queue(settings.INPUT_QUEUE, durable=True)
            await queue.bind(exchange, routing_key=settings.INPUT_ROUTING_KEY)

            messages = await self._drain(queue, limit)
            logger.info("Batch : %d messages drainés (limit=%d)", len(messages), limit)

            # Dédup par unité (filtrage par unité) — 1 traitement LLM par unité unique
            groups: Dict[tuple, Dict[str, Any]] = {}
            ignored = 0
            for msg in messages:
                parsed = _parse_message(msg.body)
                if parsed is None:
                    ignored += 1
                    await self._peek(msg)  # PEEK : inexploitable mais laissé dans le DLQ
                    continue
                key = (parsed["unite_key"], parsed["label"])
                group = groups.setdefault(
                    key,
                    {"unite_key": parsed["unite_key"], "label": parsed["label"],
                     "values": [], "messages": []},
                )
                # Union des valeurs de TOUS les messages du groupe (dédup, ordre préservé) : Gate 1
                # valide ainsi toutes les valeurs observées, pas seulement celles du 1er message.
                for v in parsed["values"]:
                    if v not in group["values"]:
                        group["values"].append(v)
                group["messages"].append(msg)

            report = {
                "limit": limit, "fetched": len(messages), "ignored": ignored,
                "unique_units": len(groups),
                "pending_activation": [], "verification_errors": [],
                "processing_errors": [], "skipped": [],
            }
            # #6 : chaque unité est traitée PUIS ack/nack immédiatement (route au fil de l'eau)
            # → fenêtre non-ackée bornée à MAX_PARALLEL, pas à tout le lot (anti consumer_timeout).
            await asyncio.gather(
                *[self._handle_group(g, referentiel, report) for g in groups.values()]
            )

            # TODO(mail-recap) : déclencher le mail récap géré par le BACKEND (endpoint à créer,
            # cf. docs/BACKEND_PLAN.md → action `normalisation/learner/mail_recap`). Les 2 issues
            # (unités apprises inactives / erreurs de vérification) doivent y figurer.
            # Ex. à câbler quand le backend existera :
            #   await self.learner.api.post("normalisation", "learner", "mail_recap", {"report": report})
            return report
        finally:
            await connection.close()

    async def _handle_group(self, group: Dict[str, Any], referentiel: Dict[str, Any], report: Dict[str, Any]) -> None:
        outcome = await self._process_group(group, referentiel)
        await self._route(group, outcome, report)

    async def _process_group(self, group: Dict[str, Any], referentiel: Dict[str, Any]) -> UnitOutcome:
        async with self.semaphore:
            try:
                return await self.learner.process_unit(
                    group["unite_key"], group["label"], group["values"], referentiel
                )
            except DynamicValidationError as exc:
                # #3 : 4xx = contrat (permanent), 5xx/réseau = transitoire
                etype = "contract" if getattr(exc, "permanent", False) else "transient"
                return UnitOutcome(group["unite_key"], STATUS_PROCESSING_ERROR, str(exc), error_type=etype)
            except ProcessingError as exc:
                return UnitOutcome(group["unite_key"], STATUS_PROCESSING_ERROR, str(exc), error_type="processing")
            except Exception as exc:  # garde-fou : toute erreur inattendue = erreur service
                logger.error("Erreur inattendue sur %s: %s", group["unite_key"], exc, exc_info=True)
                return UnitOutcome(group["unite_key"], STATUS_PROCESSING_ERROR, str(exc), error_type="processing")

    async def _peek(self, msg) -> None:
        """Mode PEEK : on REMET toujours le message dans le DLQ (nack requeue=True), comme
        /dlq/messages du dlq-manager. Le learner ne consomme JAMAIS la file — le retrait se
        fait plus tard via le requeue manuel (après vérification + activation des unités).
        Échec isolé toléré (un canal fermé n'avorte pas le run)."""
        try:
            await msg.nack(requeue=True)
        except Exception as exc:
            logger.error("nack/peek échoué (message reste dans le DLQ): %s", exc)

    async def _route(self, group: Dict[str, Any], outcome: UnitOutcome, report: Dict[str, Any]) -> None:
        # PEEK : aucun message n'est retiré du DLQ, quelle que soit l'issue.
        for msg in group["messages"]:
            await self._peek(msg)

        if outcome.status == STATUS_PENDING:
            # Enrichi avec la proposition LLM → le mail récap affiche dimension/define à valider.
            prop = outcome.proposal or {}
            report["pending_activation"].append({
                "unite": outcome.unite,
                "dimension": prop.get("dimension"),
                "pint_define": prop.get("pint_define"),
                "reecriture": prop.get("reecriture"),
                "confiance": prop.get("confiance"),
            })
        elif outcome.status == STATUS_VERIF_ERROR:
            report["verification_errors"].append({"unite": outcome.unite, "reason": outcome.reason})
        elif outcome.status == STATUS_PROCESSING_ERROR:
            report["processing_errors"].append(
                {"unite": outcome.unite, "error": outcome.reason, "type": outcome.error_type}
            )
        elif outcome.status == STATUS_SKIPPED:
            report["skipped"].append(outcome.unite)
