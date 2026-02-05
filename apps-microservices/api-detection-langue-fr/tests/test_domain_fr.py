import pytest
from app.core.domain_fr import DomainFR
from app.services.language_detector import LanguageDetector
from app.models.schemas import DetectionMode


class TestDomainFR:
    """Tests unitaires pour la classe DomainFR"""
    
    @pytest.mark.asyncio
    async def test_check_url_tld_fr(self):
        """URL avec TLD .fr doit retourner ok=True"""
        result = await DomainFR.check_url("https://www.example.fr", track_redirect=False)
        assert result['ok'] is True
        assert result['method'] == 'direct_match'
    
    @pytest.mark.asyncio
    async def test_check_url_path_fr(self):
        """URL avec /fr/ dans le path doit retourner ok=True"""
        result = await DomainFR.check_url("https://www.example.com/fr/page", track_redirect=False)
        assert result['ok'] is True
        assert result['method'] == 'pattern_match_path'
    
    @pytest.mark.asyncio
    async def test_check_url_query_lang_fr(self):
        """URL avec lang=fr dans query doit retourner ok=True"""
        result = await DomainFR.check_url("https://www.example.com?lang=fr", track_redirect=False)
        assert result['ok'] is True
        assert result['method'] == 'pattern_match_query'
    
    @pytest.mark.asyncio
    async def test_check_url_no_match(self):
        """URL sans indicateur FR doit retourner ok=False"""
        result = await DomainFR.check_url("https://www.example.com", track_redirect=False)
        assert result['ok'] is False
        assert result['method'] == 'no_match'
    
    @pytest.mark.asyncio
    async def test_check_url_subdomain_fr(self):
        """URL avec sous-domaine fr. doit retourner ok=True"""
        result = await DomainFR.check_url("https://fr.example.com", track_redirect=False)
        assert result['ok'] is True
        assert result['method'] == 'direct_match'
    
    def test_get_domain_from_url(self):
        """Extraction du domaine doit fonctionner correctement"""
        assert DomainFR.get_domain_from_url("https://www.example.com") == "example"
        assert DomainFR.get_domain_from_url("https://books.google.com") == "google"
        assert DomainFR.get_domain_from_url("https://example.fr") == "example"
    
    def test_resolve_url_relative(self):
        """Résolution d'URL relative doit fonctionner"""
        base = "https://www.example.com/page/"
        assert DomainFR.resolve_url(base, "/fr/home") == "https://www.example.com/fr/home"
        assert DomainFR.resolve_url(base, "../other") == "https://www.example.com/other"
    
    def test_resolve_url_absolute(self):
        """URL absolue doit être retournée telle quelle"""
        base = "https://www.example.com"
        url = "https://www.other.fr/page"
        assert DomainFR.resolve_url(base, url) == url


class TestLanguageDetector:
    """Tests unitaires pour LanguageDetector"""
    
    def setup_method(self):
        self.detector = LanguageDetector()
    
    def test_detect_html_lang_fr(self):
        """Détection de <html lang="fr">"""
        html = '<html lang="fr"><head></head><body>Contenu</body></html>'
        result = self.detector.detect_from_html_tags(html)
        assert result is not None
        assert result['value'] == 'fr'
        assert result['method'] == 'langHtml'
    
    def test_detect_html_lang_fr_FR(self):
        """Détection de <html lang="fr-FR"> (avec région)"""
        html = '<html lang="fr-FR"><head></head><body>Contenu</body></html>'
        result = self.detector.detect_from_html_tags(html)
        assert result is not None
        assert result['value'] == 'fr'
    
    def test_detect_meta_og_locale(self):
        """Détection de <meta property="og:locale" content="fr_FR">"""
        html = '''
        <html>
        <head><meta property="og:locale" content="fr_FR"></head>
        <body>Contenu</body>
        </html>
        '''
        result = self.detector.detect_from_html_tags(html)
        assert result is not None
        assert result['value'] == 'fr'
        assert result['method'] == 'matchMeta'
    
    def test_detect_meta_http_equiv(self):
        """Détection de <meta http-equiv="content-language" content="fr">"""
        html = '''
        <html>
        <head><meta http-equiv="content-language" content="fr"></head>
        <body>Contenu</body>
        </html>
        '''
        result = self.detector.detect_from_html_tags(html)
        assert result is not None
        assert result['value'] == 'fr'
        assert result['method'] == 'matchHttpEquiv'
    
    def test_detect_no_language(self):
        """HTML sans indicateur de langue"""
        html = '<html><head></head><body>Content</body></html>'
        result = self.detector.detect_from_html_tags(html)
        assert result is None
    
    def test_nlp_detection_french_text(self):
        """Détection NLP de texte français"""
        html = '''
        <html><body>
        <p>Bonjour et bienvenue sur notre site. Nous sommes heureux de vous accueillir. 
        Ce texte est écrit en français pour tester la détection automatique de la langue.
        Notre entreprise est spécialisée dans les solutions innovantes.</p>
        </body></html>
        '''
        result = self.detector.detect_from_text_content(html)
        assert result is not None
        assert result['lang'] == 'fr'
        assert result['confidence'] > 0.5
    
    def test_nlp_detection_english_text(self):
        """Détection NLP de texte anglais"""
        html = '''
        <html><body>
        <p>Welcome to our website. We are happy to have you here.
        This text is written in English to test the automatic language detection.
        Our company specializes in innovative solutions.</p>
        </body></html>
        '''
        result = self.detector.detect_from_text_content(html)
        assert result is not None
        assert result['lang'] == 'en'


class TestDetectAlternativeLanguages:
    """Tests pour la détection des liens alternatifs"""
    
    def test_detect_hreflang(self):
        """Détection de liens hreflang"""
        html = '''
        <html>
        <head>
            <link rel="alternate" hreflang="fr" href="https://example.com/fr/">
            <link rel="alternate" hreflang="en" href="https://example.com/en/">
        </head>
        <body></body>
        </html>
        '''
        detector = DomainFR("https://example.com")
        alternatives = detector.detect_alternative_languages(html)
        assert len(alternatives) > 0
        assert "https://example.com/fr/" in alternatives
    
    def test_detect_data_lang(self):
        """Détection d'éléments avec data-lang"""
        html = '''
        <html>
        <body>
            <a href="/fr/home" data-lang="fr">Français</a>
            <a href="/en/home" data-lang="en">English</a>
        </body>
        </html>
        '''
        detector = DomainFR("https://example.com")
        alternatives = detector.detect_alternative_languages(html)
        assert len(alternatives) > 0
