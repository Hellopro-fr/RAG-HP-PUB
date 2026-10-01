"""Tests for detect_challenge_page patterns and clean_html_to_text noscript repair.

Covers the 2026-07-25 detect-debug deep-dive fixes:
- Rescaled_WAF + JS_PoW_bot_check challenge patterns (real captures: lagff.com, probst-handling.com)
- noscript-unwrap fallback for unclosed nested <noscript> (real capture: outilbox.fr,
  LiteSpeed lazy-loader wrapping the GTM noscript iframe)
Spec: docs/superpowers/specs/2026-07-25-detection-langue-fr-challenge-noscript-altprobe-design.md
"""
import pytest

from app.services.language_detector import LanguageDetector, detect_challenge_page
from app.core.config import settings


# ---------------------------------------------------------------------------
# detect_challenge_page — new WAF patterns
# ---------------------------------------------------------------------------

class TestRescaledWafPattern:
    def test_rescaled_waf_interstitial_detected(self):
        # Minimal analogue of the captured lagff.com interstitial (HTTP 403)
        html = """<!DOCTYPE html><html class="h-full" lang="en"><head>
        <meta charset="UTF-8"><title>rescaled WAF · Verifying Browser</title>
        <script type="application/json" id="challenge_data">{"verifyURL":"/.well-known/rescaled-waf/verify?token=abc","alg":"pow"}</script>
        <script>window.dispatchEvent(new Event('rescaled-waf:challenge-started'));</script>
        </head><body><p>Verifying your browser. Our web application firewall (WAF) is
        verifying that this request is coming from a real browser.</p></body></html>"""
        assert detect_challenge_page(html) == 'Rescaled_WAF'

    def test_single_rescaled_marker_not_enough(self):
        # A blog article merely mentioning the verify path must not match (2-of-3 rule)
        html = ("<html><head><title>Comment fonctionne un WAF</title></head><body>"
                "<p>Certains WAF exposent /.well-known/rescaled-waf/ pour leur challenge.</p>"
                + "<p>Contenu éditorial normal.</p>" * 50 + "</body></html>")
        assert detect_challenge_page(html) is None

    def test_exactly_two_markers_detected(self):
        # Boundary pin: 2 of 3 markers must suffice (an interstitial variant
        # without the title must still engage the scraper resolution poll)
        html = ('<html><head><title>Checking…</title>'
                '<script id="challenge_data">{"verifyURL":"/.well-known/rescaled-waf/verify"}</script>'
                '<script>dispatchEvent(new Event("rescaled-waf:challenge-started"))</script>'
                '</head><body>One moment.</body></html>')
        assert detect_challenge_page(html) == 'Rescaled_WAF'


class TestJsPowBotCheckPattern:
    def test_bot_check_page_detected(self):
        # Minimal analogue of the captured probst-handling.com gate (HTTP 401)
        html = """<!DOCTYPE html><html lang="en"><head><title>Bot check</title>
        <!-- https://github.com/brix/crypto-js -->
        <script>fetch('?create_challenge').then(r => r.json());</script>
        </head><body><p>Your request is being verified. Please wait...</p>
        <noscript>Javascript is needed to access this site.</noscript></body></html>"""
        assert detect_challenge_page(html) == 'JS_PoW_bot_check'

    def test_title_plus_single_confirmation_detected(self):
        # Boundary pin: anchor + exactly 1 confirmation must suffice
        html = ('<html><head><title>Bot check</title></head>'
                '<body><p>Your request is being verified.</p></body></html>')
        assert detect_challenge_page(html) == 'JS_PoW_bot_check'

    def test_bot_check_title_alone_not_enough(self):
        # Title anchor without any PoW confirmation must not match
        html = ("<html><head><title>Bot check</title></head><body>"
                "<p>Article sur la détection de bots.</p>" * 30 + "</body></html>")
        assert detect_challenge_page(html) is None

    def test_confirmations_without_title_not_enough(self):
        html = ("<html><head><title>Sécurité web</title></head><body>"
                "<p>Le endpoint ?create_challenge sert un challenge crypto-js.</p>"
                + "<p>Contenu.</p>" * 50 + "</body></html>")
        assert detect_challenge_page(html) is None


# ---------------------------------------------------------------------------
# clean_html_to_text — noscript-unwrap fallback (unclosed nested noscript)
# ---------------------------------------------------------------------------

FRENCH_PARAGRAPH = (
    "<p>Bienvenue dans notre boutique en ligne d'outillage professionnel. "
    "Nous proposons une large gamme de machines et d'équipements pour vos "
    "ateliers : perceuses, fraiseuses, tours à métaux et accessoires de "
    "levage. Livraison rapide partout en France métropolitaine.</p>"
)


def _page_with_unclosed_nested_noscript(filler_kb: int = 30) -> str:
    """Reproduces the outilbox.fr breakage: LiteSpeed wraps GTM's <noscript>
    inside another <noscript>; the single </noscript> closes the inner one,
    the outer never closes, and parsers swallow the rest of the body."""
    filler = ("<script>var x = '" + "a" * 1024 + "';</script>") * filler_kb
    return (
        "<!DOCTYPE html><html lang=\"fr-FR\"><head><title>OutilBox</title>"
        + filler
        + "</head><body>"
        + "<a class=\"skip-link\" href=\"#content\">Aller au contenu</a>"
        # LiteSpeed lazy-load wrapper (outer, never closed) around GTM (inner)
        + "<noscript><iframe data-litespeed-src=\"https://www.googletagmanager.com/ns.html\">"
        + "</iframe><noscript><iframe src=\"https://www.googletagmanager.com/ns.html\">"
        + "</iframe></noscript>"
        + "<header>" + FRENCH_PARAGRAPH * 10 + "</header>"
        + "</body></html>"
    )


class TestNoscriptUnwrapFallback:
    def setup_method(self):
        self.detector = LanguageDetector()

    def test_unclosed_nested_noscript_recovers_french_text(self):
        html = _page_with_unclosed_nested_noscript()
        text = self.detector.clean_html_to_text(html)
        assert text is not None
        assert len(text) >= settings.NLP_MIN_TEXT_LENGTH
        assert "outillage professionnel" in text

    def test_thin_page_stays_rejected(self):
        # <20KB page whose noscript boilerplate alone exceeds
        # NLP_MIN_TEXT_LENGTH: without the 20KB guard the fallback would
        # unwrap it and return EN text — must stay None (fetch_empty_content).
        boilerplate = ("Please enable JavaScript to view this site. "
                       "This website requires JavaScript to function properly. ") * 3
        html = ("<html><head><title>x</title></head><body>"
                f"<noscript>{boilerplate}</noscript>"
                "<p>Court.</p></body></html>")
        assert len(html) < 20_000
        assert self.detector.clean_html_to_text(html) is None

    def test_large_thin_page_boilerplate_below_floor_stays_rejected(self):
        # >20KB page (fallback fires) whose unwrapped noscript yields only
        # ~170 chars of EN boilerplate: below the 5x acceptance floor, the
        # repaired text must be discarded — a thin page must NOT flip from
        # transient fetch_empty_content to a definitive NLP verdict.
        filler = ("<script>var x = '" + "a" * 1024 + "';</script>") * 25
        boilerplate = ("You need to enable JavaScript to run this app. "
                       "Please activate JavaScript in your browser settings to continue. "
                       "JavaScript is required.")
        html = ("<html><head><title>x</title>" + filler + "</head><body>"
                f"<noscript>{boilerplate}</noscript>"
                "<p>Court.</p></body></html>")
        assert len(html) > 20_000
        assert self.detector.clean_html_to_text(html) is None

    def test_normal_page_does_not_leak_noscript_boilerplate(self):
        # Well-formed page with enough text: primary path succeeds, noscript
        # boilerplate must stay excluded from the result.
        html = ("<html><head><title>Site</title></head><body>"
                "<noscript>Abilitare i Javascript per visualizzare l'e-mail</noscript>"
                + FRENCH_PARAGRAPH * 5 + "</body></html>")
        text = self.detector.clean_html_to_text(html)
        assert text is not None
        assert "Abilitare" not in text


# ---------------------------------------------------------------------------
class TestFasttextModelIsClassScoped:
    """Le modèle fastText est chargé une fois par PROCESS, pas par instance.

    Régression 2026-08-13 : stocké sur `self`, le modèle était rechargé pour
    chaque LanguageDetector. DomainFR en construit un par instance
    (domain_fr.py) et routes.py construit un DomainFR par item de batch, par
    variante du rattrapage et par repli homepage — soit autant de copies
    simultanées du modèle en mémoire, et autant de lectures disque synchrones,
    que d'items analysés en parallèle.
    """

    @staticmethod
    def _purge_class_model():
        # État porté par la classe : le purger avant ET après, sinon le faux
        # modèle de ce test fuit vers ses voisins.
        if '_fasttext_model' in LanguageDetector.__dict__:
            delattr(LanguageDetector, '_fasttext_model')

    def setup_method(self, method=None):
        self._purge_class_model()

    def teardown_method(self, method=None):
        self._purge_class_model()

    @staticmethod
    def _fake_fasttext(monkeypatch):
        """Installe un faux module fasttext et retourne la liste des chargements."""
        import os
        import sys
        import types

        loads = []

        class _FakeModel:
            def predict(self, text, k=3):
                return (['__label__fr'], [0.99])

        fake = types.ModuleType('fasttext')
        fake.FastText = types.SimpleNamespace(eprint=lambda x: None)
        fake.load_model = lambda path: (loads.append(path), _FakeModel())[1]
        monkeypatch.setitem(sys.modules, 'fasttext', fake)
        # Le modèle n'existe pas sur la machine de test.
        monkeypatch.setattr(os.path, 'exists', lambda p: True)
        return loads

    def test_model_loaded_once_across_instances(self, monkeypatch):
        loads = self._fake_fasttext(monkeypatch)
        html = "<html><body>" + FRENCH_PARAGRAPH * 5 + "</body></html>"

        first = LanguageDetector().detect_from_text_content_fasttext(html)
        second = LanguageDetector().detect_from_text_content_fasttext(html)

        # Les deux verdicts aboutissent : le partage ne casse pas la détection.
        assert first is not None and second is not None
        assert first['lang'] == 'fr' and second['lang'] == 'fr'
        # Le point du test : un seul chargement pour deux instances.
        assert len(loads) == 1, f"modèle chargé {len(loads)} fois au lieu d'une"

    def test_model_object_shared_not_copied_per_instance(self, monkeypatch):
        self._fake_fasttext(monkeypatch)
        html = "<html><body>" + FRENCH_PARAGRAPH * 5 + "</body></html>"

        loader, follower = LanguageDetector(), LanguageDetector()
        loader.detect_from_text_content_fasttext(html)

        # `follower` n'a jamais chargé : il voit le modèle à travers la classe,
        # et rien n'est écrit dans son __dict__ d'instance.
        assert follower._fasttext_model is loader._fasttext_model
        assert '_fasttext_model' not in follower.__dict__
        assert '_fasttext_model' not in loader.__dict__
