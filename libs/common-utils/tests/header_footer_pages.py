"""Synthetic pages shared by the HeaderFooterExtractor tests.

Page shape (common on B2B sites): a site-wide promo/contact top bar that is NOT
inside <header>, then a semantic <header> holding a <nav>. The original method
keeps the <nav> only; the intersection strategies keep top bar + full header.
Wrapping a region in the reference pages only (see WRAPPED_* below) breaks the
structural signature of that region while its class signature still matches.
"""

TOPBAR = (
    '<div class="topbar"><p>Livraison gratuite des 50 euros HT</p>'
    "<p>Service client 01 23 45 67 89 du lundi au vendredi</p></div>"
)
HEADER = (
    '<header class="site-header"><div class="logo"><p>Acme Industrie</p></div>'
    '<nav><ul><li><a href="/pompes">Pompes</a></li>'
    '<li><a href="/vannes">Vannes</a></li>'
    '<li><a href="/compresseurs">Compresseurs</a></li></ul></nav></header>'
)
FOOTER = (
    '<footer><div class="footer-content"><p>Copyright 2026 Acme Industrie</p>'
    '<ul><li><a href="/mentions">Mentions legales</a></li>'
    '<li><a href="/contact">Contact</a></li></ul></div></footer>'
)
WRAPPED_TOP = f'<div class="page">{TOPBAR}{HEADER}</div>'
WRAPPED_BOTTOM = f'<div class="bottom">{FOOTER}</div>'
OTHER_BOTTOM = "<aside><p>fin</p></aside>"


def page(title: str, body: str, top: str = TOPBAR + HEADER, bottom: str = FOOTER) -> str:
    paras = "".join(
        f"<p>{body} paragraphe {i} avec du texte unique.</p>" for i in range(12)
    )
    return (
        f"<html><head><title>{title}</title></head><body>{top}"
        f"<main><article><h1>{title}</h1><h2>Caracteristiques</h2>{paras}"
        f"</article></main>{bottom}</body></html>"
    )


MAIN = ("Pompe centrifuge PX-200", "La pompe PX-200 offre un debit eleve")
REFERENCES = [
    ("Vanne papillon VB-50", "La vanne VB-50 assure une etancheite parfaite"),
    ("Compresseur a vis CV-7", "Le compresseur CV-7 reduit la consommation"),
]
MAIN_HTML = page(*MAIN)


def references(**region) -> list[str]:
    """Reference pages, with `top` and/or `bottom` overridden."""
    return [page(*ref, **region) for ref in REFERENCES]
