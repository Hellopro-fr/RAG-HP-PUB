"""Helpers texte : normalisation accents, tokenisation, prefix-match tolerant."""
import re
import unicodedata
from typing import List, Set


def normalize(s: str) -> str:
    """Strip accents + lowercase."""
    if not s:
        return ""
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


def tokenize(s: str) -> Set[str]:
    """Tokens alphanumeriques normalises (min 2 chars), ordre non preserve."""
    return set(re.findall(r"[a-z0-9]{2,}", normalize(s)))


def tokenize_ordered(s: str) -> List[str]:
    """Idem mais avec ordre preserve (pour detection prefix)."""
    return re.findall(r"[a-z0-9]{2,}", normalize(s))


def is_prefix_match(
    query_tokens: Set[str],
    category_name: str,
    max_lookahead: int = 2,
    min_prefix_chars: int = 4,
) -> bool:
    """
    Teste si tous les query_tokens apparaissent dans les PREMIERS mots du
    nom de categorie, avec tolerance singulier/pluriel (startswith bilateral).

    Ex :
      query="batterie lithium"
      - "Armoire de stockage batterie lithium"   -> False (batterie pos 4)
      - "Batterie lithium 24V"                    -> True
      - "Batterie industrielle"                   -> False (lithium absent)

      query="signalisation securite"
      - "Signalisations securite travail"         -> True (signalisation ~ signalisations)

      query="armoire"
      - "Armoires a pharmacie"                    -> True (armoire ~ armoires)
    """
    cat_toks = tokenize_ordered(category_name)
    prefix_toks = cat_toks[: len(query_tokens) + max_lookahead]

    def matches(q_tok: str) -> bool:
        for ct in prefix_toks:
            if ct == q_tok:
                return True
            if len(q_tok) >= min_prefix_chars and len(ct) >= min_prefix_chars:
                if ct.startswith(q_tok) or q_tok.startswith(ct):
                    return True
        return False

    return all(matches(q) for q in query_tokens)
