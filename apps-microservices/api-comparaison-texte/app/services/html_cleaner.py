from bs4 import BeautifulSoup


def extract_text_from_html(html_content: str) -> str:
    """
    Extrait le texte visible d'un contenu HTML.
    Supprime les balises non visibles (script, style, meta, nav, etc.).

    Args:
        html_content: Chaîne HTML brute.

    Returns:
        Texte brut extrait.
    """
    soup = BeautifulSoup(html_content, "lxml")

    for tag in soup(["script", "style", "meta", "link", "noscript", "header", "footer", "nav"]):
        tag.decompose()

    text = soup.get_text(separator=" ", strip=True)
    return text
