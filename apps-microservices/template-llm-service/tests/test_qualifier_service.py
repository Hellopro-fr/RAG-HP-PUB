import pytest
from unittest.mock import patch, MagicMock
from app.core.qualifier.service import QualifierService

# Le décorateur @patch remplace l'objet 'vllm.LLM' par un mock pendant toute la durée du test.
# C'est CRUCIAL pour ne pas essayer de charger le modèle sur le GPU.
@patch('app.core.qualifier.service.LLM')
def test_classify_successful_fiche_produit(mock_llm_class):
    """
    Teste une classification réussie pour une "fiche_produit".
    """
    # --- Arrange (Préparation) ---
    # Configurer le mock pour qu'il se comporte comme le vrai LLM
    mock_llm_instance = mock_llm_class.return_value
    
    # Simuler la sortie de la méthode .generate()
    # La structure est un peu complexe, mais elle imite la vraie sortie de VLLM.
    mock_output = MagicMock()
    mock_output.outputs[0].text = '{"type_page": "fiche_produit"}'
    mock_llm_instance.generate.return_value = [mock_output]

    # Instancier le service. L'appel à LLM() dans __init__ utilisera notre mock.
    service = QualifierService()
    
    # Données d'entrée pour le test
    test_url = "http://example.com/produit/123"
    test_content = "<h1>Titre du Produit</h1><p>Description du produit.</p>"

    # --- Act (Action) ---
    type_page, _, _ = service.classify(test_url, test_content)

    # --- Assert (Vérification) ---
    assert type_page == "fiche_produit"
    # Vérifier que la méthode generate a bien été appelée
    mock_llm_instance.generate.assert_called_once()


@patch('app.core.qualifier.service.LLM')
def test_classify_parsing_error(mock_llm_class):
    """
    Teste le cas où le LLM renvoie une chaîne qui n'est pas un JSON valide.
    """
    # --- Arrange ---
    mock_llm_instance = mock_llm_class.return_value
    # Le LLM renvoie du texte non-JSON
    mock_output = MagicMock()
    mock_output.outputs[0].text = "Désolé, je ne peux pas classifier ça."
    mock_llm_instance.generate.return_value = [mock_output]

    service = QualifierService()
    test_url = "http://example.com/page-inconnue"
    test_content = "Contenu non structuré."

    # --- Act ---
    type_page, _, _ = service.classify(test_url, test_content)

    # --- Assert ---
    assert type_page == "erreur_parsing"


@patch('app.core.qualifier.service.LLM')
def test_html_cleaning(mock_llm_class):
    """
    Teste que le contenu HTML est bien nettoyé avant d'être envoyé au LLM.
    """
    # --- Arrange ---
    mock_llm_instance = mock_llm_class.return_value
    mock_output = MagicMock()
    mock_output.outputs[0].text = '{"type_page": "article"}'
    mock_llm_instance.generate.return_value = [mock_output]

    service = QualifierService()
    test_url = "http://example.com/article"
    # Contenu HTML "bruyant"
    messy_content = """
    <html>
        <head><style>.title {color: red;}</style></head>
        <body>
            <header>Menu de navigation</header>
            <main><h1>Titre Principal de l'Article</h1><p>Ceci est le vrai contenu.</p></main>
            <footer>Copyright 2025</footer>
            <script>alert('ne pas lire ca');</script>
        </body>
    </html>
    """

    # --- Act ---
    service.classify(test_url, messy_content)

    # --- Assert ---
    # On vérifie avec quoi la méthode .generate() a été appelée.
    mock_llm_instance.generate.assert_called_once()
    # On récupère le prompt qui a été réellement envoyé au LLM
    call_args, _ = mock_llm_instance.generate.call_args
    prompt_sent_to_llm = call_args[0][0]

    # On vérifie que le bruit a été retiré...
    assert "Menu de navigation" not in prompt_sent_to_llm
    assert "Copyright 2025" not in prompt_sent_to_llm
    assert "alert('ne pas lire ca')" not in prompt_sent_to_llm
    # ...et que le contenu principal est bien présent.
    assert "Titre Principal de l'Article" in prompt_sent_to_llm
    assert "Ceci est le vrai contenu" in prompt_sent_to_llm