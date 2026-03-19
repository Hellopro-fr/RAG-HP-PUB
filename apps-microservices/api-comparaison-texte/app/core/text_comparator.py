import difflib

from app.core.config import settings


def compare_texts(old_text: str, new_text: str, threshold: float | None = None) -> dict:
    """
    Compare deux textes avec difflib.SequenceMatcher.
    Reproduit la CONDITION 2 de processor.py (lignes 191-204) :
      - Si ratio < seuil → UPDATE
      - Si ratio >= seuil → SKIP

    Args:
        old_text: Texte de référence (stocké en base).
        new_text: Nouveau texte extrait.
        threshold: Seuil de similarité (défaut: settings.SIMILARITY_THRESHOLD).

    Returns:
        dict avec similarity_ratio, decision, reason.
    """
    effective_threshold = threshold if threshold is not None else settings.SIMILARITY_THRESHOLD
    ratio = difflib.SequenceMatcher(None, old_text, new_text).ratio()

    if ratio < effective_threshold:
        decision = "UPDATE"
        reason = f"text_similarity {ratio:.4f} < {effective_threshold}"
    else:
        decision = "SKIP"
        reason = f"text_similarity {ratio:.4f} >= {effective_threshold}"

    return {
        "similarity_ratio": round(ratio, 4),
        "decision": decision,
        "reason": reason,
    }
