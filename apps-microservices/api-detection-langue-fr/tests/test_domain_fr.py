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
    
    # ==========================================
    # Tests ciblant les faux positifs (FP) corrigés
    # ==========================================
    
    def test_fp_html_fr_content_en(self):
        """FP-1: <html lang="fr"> avec contenu anglais → NLP doit corriger le HTML"""
        html = '''
        <html lang="fr">
        <head><title>English Page</title></head>
        <body>
        <p>Welcome to our website. We provide the best services in the industry.
        Our team of experts is dedicated to delivering exceptional results.
        Contact us today to learn more about how we can help your business grow.
        We offer a wide range of solutions tailored to your specific needs.
        Our innovative approach sets us apart from the competition.</p>
        </body>
        </html>
        '''
        # detect_combined avec NLP activé doit détecter que le contenu est EN, pas FR
        result = self.detector.detect_combined(html, use_nlp=True)
        # NLP devrait primer sur le HTML tag → is_french devrait être False
        assert result['detected'] is True
        assert result['is_french'] is False
        assert 'nlp_override' in result['method']
    
    def test_fp_french_stopwords_in_spanish(self):
        """FP-2: Texte espagnol avec mots partagés ne doit pas être détecté comme FR"""
        html = '''
        <html><body>
        <p>Bienvenido a nuestra página web. Los servicios que ofrecemos son de la más alta
        calidad. Nuestro equipo de expertos está dedicado a entregar resultados excepcionales.
        La empresa fue fundada en el año 2010 y desde entonces ha crecido de manera constante.
        Contáctenos hoy para obtener más información sobre cómo podemos ayudar a su negocio.</p>
        </body></html>
        '''
        result = self.detector.detect_from_text_content(html)
        assert result is not None
        assert result['lang'] != 'fr'
    
    def test_fp_alternatives_not_auto_ok(self):
        """FP-5: Page EN avec hreflang="fr" ne doit PAS retourner ok=True"""
        html = '''
        <html lang="en">
        <head>
            <link rel="alternate" hreflang="fr" href="https://example.com/fr/">
            <link rel="alternate" hreflang="en" href="https://example.com/en/">
        </head>
        <body>
        <p>Welcome to our website. We provide the best services in the industry.
        Our team of experts is dedicated to delivering exceptional results.
        Contact us today to learn more about how we can help your business grow.
        We offer a wide range of solutions tailored to your specific needs.</p>
        </body>
        </html>
        '''
        # detect_combined détecte que c'est de l'anglais
        result = self.detector.detect_combined(html, use_nlp=True)
        assert result['is_french'] is False
    
    # ==========================================
    # Tests ciblant les faux négatifs (FN) corrigés
    # ==========================================
    
    def test_fn_short_french_page(self):
        """FN-2: Page française minimaliste (~120 chars) doit être détectée"""
        html = '''
        <html><body>
        <p>Bienvenue sur notre site. Nous proposons des solutions innovantes pour votre entreprise.
        Contactez-nous dès aujourd'hui.</p>
        </body></html>
        '''
        result = self.detector.detect_from_text_content(html)
        # Avec NLP_MIN_TEXT_LENGTH=100, ce texte devrait être accepté
        assert result is not None
        assert result['lang'] == 'fr'
    
    def test_fn_french_with_tech_terms(self):
        """FN-3: FR avec termes techniques anglais doit être détecté comme FR"""
        html = '''
        <html><body>
        <p>Notre solution de cloud computing vous permet de déployer vos applications
        avec une architecture microservices. Le machine learning et l'intelligence artificielle
        sont au cœur de notre offre. Nous proposons également des services de data engineering
        et de DevOps pour accompagner votre transformation digitale.</p>
        </body></html>
        '''
        result = self.detector.detect_from_text_content(html)
        assert result is not None
        assert result['lang'] == 'fr'
    
    def test_fn_content_in_header_nav(self):
        """FN-1: Contenu français dans header/nav ne doit plus être ignoré"""
        html = '''
        <html><body>
        <header>
            <h1>Bienvenue sur notre site</h1>
            <nav>
                <a href="/accueil">Accueil</a>
                <a href="/services">Nos Services</a>
                <a href="/contact">Contactez-nous</a>
            </nav>
        </header>
        <p>Découvrez nos services pour votre entreprise.</p>
        </body></html>
        '''
        result = self.detector.detect_from_text_content(html)
        # Avec header/nav conservés, le texte total devrait être suffisant
        assert result is not None
        assert result['lang'] == 'fr'
    
    # ==========================================
    # Tests pour detect_combined (refonte)
    # ==========================================
    
    def test_combined_html_and_nlp_agree(self):
        """detect_combined: HTML et NLP d'accord → confiance haute"""
        html = '''
        <html lang="fr"><body>
        <p>Bienvenue sur notre site. Nous sommes une entreprise française spécialisée
        dans les solutions numériques. Notre équipe vous accompagne dans tous vos projets
        de transformation digitale.</p>
        </body></html>
        '''
        result = self.detector.detect_combined(html, use_nlp=True)
        assert result['is_french'] is True
        assert 'nlp_confirmed' in result['method']
        assert result['confidence'] >= 0.9
    
    def test_combined_html_only_nlp_skipped(self):
        """detect_combined: HTML seul sans NLP → confiance réduite"""
        html = '<html lang="fr"><body><p>Court</p></body></html>'
        result = self.detector.detect_combined(html, use_nlp=True)
        # Texte trop court → NLP retourne None → HTML seul → confiance réduite
        assert result['detected'] is True
        assert result['is_french'] is True
        assert 'nlp_skipped' in result['method']
        assert result['confidence'] <= 0.7
    
    # ==========================================
    # Tests pour le signal français amélioré
    # ==========================================
    
    def test_french_signal_exclusive_words(self):
        """Signal français: mots exclusifs doivent compter plus"""
        detector = LanguageDetector()
        
        # Texte avec beaucoup de mots exclusivement français
        text_fr = "nous sommes très heureux de vous accueillir dans notre entreprise depuis plusieurs années"
        score_fr = detector._compute_french_signal(text_fr)
        
        # Texte avec des mots partagés seulement (pourraient être autre langue romane)
        text_shared = "le la de des un une du sur par sans est et ou si ce ces au aux qui que"
        score_shared = detector._compute_french_signal(text_shared)
        
        # Le texte avec mots exclusifs devrait avoir un score plus élevé
        assert score_fr > score_shared


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
