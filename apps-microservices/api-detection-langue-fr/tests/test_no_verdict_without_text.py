"""N1 : aucun verdict « non francophone » sur une page qu'on n'a pas pu lire.
N2 : signature AWS WAF absente de `detect_challenge_page`.

Diagnostiqués sur une sonde de production du 2026-08-13 (`324automatismes.net`,
`/detect-debug`) : `fetch.status_code=202`, `fetch.raw_html_length=2397`,
`cleaning.cleaned_text_length=0`, `nlp.available=false`,
`debug.decision="Case 9: No French indicators found"` — un verdict "pas
français" publié sur zéro caractère de texte visible. Voir
`.superpowers/brief-no-verdict-without-text.md`.
"""
import pytest

from app.core.domain_fr import DomainFR
from app.models.schemas import AlternativeUrl, DetectionMode
from app.services.language_detector import detect_challenge_page
from app.services.language_detector import LanguageDetector

# HTML réel constaté par la sonde /detect-debug du 13 : challenge AWS WAF,
# aucun texte visible (script only, body vide).
AWS_WAF_HTML = """<html lang="en"><head><script>
window.awsWafCookieDomainList = [];
window.gokuProps = {"key":"AQIDAHjcYu...","iv":"abc123","context":"xyz"};
</script></head><body></body></html>"""


def _make_detector(homepage, validate_alternatives=True):
    return DomainFR(
        homepage=homepage,
        use_nlp_detection=True,
        validate_alternatives=validate_alternatives,
    )


def _stub_alternatives(detector, monkeypatch, candidates=None):
    async def fake(_content):
        return candidates or []
    monkeypatch.setattr(detector, "detect_alternative_languages", fake)


class TestN2AwsWafSignature:
    """N2 : `detect_challenge_page` ne connaissait ni `awsWafCookieDomainList`
    ni `gokuProps` — deux marqueurs exclusifs au script CAPTCHA/challenge AWS
    WAF (nom de code interne « Goku »)."""

    def test_aws_waf_html_detected_as_challenge(self):
        assert detect_challenge_page(AWS_WAF_HTML) == 'AWS_WAF'

    def test_single_marker_on_real_page_is_not_a_false_positive(self):
        """Garde-fou faux positif : UN SEUL des deux marqueurs (ici
        awsWafCookieDomainList, sans gokuProps) sur une page au contenu
        français réel ne doit pas déclencher le challenge — c'est
        précisément le cas sur lequel porte le seuil >= 2 (leçon Turnstile :
        un composant isolé peut apparaître sur un vrai site)."""
        html = """<html lang="fr"><head><script>
        window.awsWafCookieDomainList = [];
        </script></head><body><p>
        Notre plateforme est hebergee sur AWS et deployee en haute
        disponibilite, avec un contenu francais riche et detaille sur nos
        services cloud et nos solutions d'hebergement pour entreprises.
        </p></body></html>"""
        assert detect_challenge_page(html) is None


class TestN1NoVerdictWithoutText:
    """N1 : les trois méthodes que le BO traite comme « jugées »
    (`DETECTION_LANGUAGE_VERDICTS`) ne peuvent plus conclure « pas français »
    sur une page dont le texte visible est sous `NLP_MIN_TEXT_LENGTH`."""

    @pytest.mark.asyncio
    async def test_production_case_returns_fetch_empty_content_not_check_nok_v2(self):
        """Le cas du 13 : Cas 9 (aucun indicateur) sans aucun mock NLP — le
        vrai pipeline (fastText absent localement -> fallback langdetect/
        langid) échoue naturellement sur un texte visible de longueur 0."""
        d = _make_detector("https://324automatismes.net/")
        res = await d.check_page_if_french(AWS_WAF_HTML, DetectionMode.COMPLETE)

        assert res.method == 'fetch_empty_content'
        assert res.method != 'Check_nok_v2'
        assert res.ok is False
        assert '0 caractères' in (res.error or '')
        # Contrat Cas 9 (documenté juste au-dessus du garde) : alternative_urls
        # reste vide même en `fetch_empty_content` — sinon crawler routes.ts
        # publierait "alternative FR trouvée" pour une page illisible.
        assert res.alternative_urls == []

    @pytest.mark.asyncio
    async def test_case9_guard_never_emits_alternative_urls_even_when_found(self, monkeypatch):
        """Contrat Cas 9 (non-régression du garde N1, finding #3 revue) :
        même quand des candidates existent (mais non fiables -> le Cas 6 ne
        les consomme pas), le garde `fetch_empty_content` de Cas 9 ne doit
        JAMAIS les exposer — `routes.ts` + `not_french_signal.php` liraient
        "ok=false + alternatives non vides" comme un signal distinct de
        not_french sur une page qu'on n'a même pas pu lire."""
        d = _make_detector("https://324automatismes.net/")
        _stub_alternatives(d, monkeypatch, [
            AlternativeUrl(url="https://324automatismes.net/en/", method="data-lang",
                            reliability="low", validated=False),
        ])

        res = await d.check_page_if_french(AWS_WAF_HTML, DetectionMode.COMPLETE)

        assert res.method == 'fetch_empty_content'
        assert res.alternative_urls == []

    @pytest.mark.asyncio
    async def test_case9_no_regression_when_real_text_present(self, monkeypatch):
        """NON-RÉGRESSION (la plus importante) : une page avec du texte,
        jugée `Check_nok_v2` (anglais clair, .com, lang="en"), doit le
        rester — le garde ne doit pas transformer un vrai verdict en
        indéterminé."""
        html = """<html lang="en"><body><p>
        This is a genuine English homepage with plenty of real content
        describing our products and services in clear English prose,
        nothing French about it at all.
        </p></body></html>"""
        d = _make_detector("https://example.com/")
        _stub_alternatives(d, monkeypatch, [])

        def fake_nlp(_text):
            return {
                "lang": "en", "confidence": 0.95, "method": "nlp_detection_fasttext",
                "details": {"french_exclusive_distinct": 0, "french_signal": 0.0},
            }
        monkeypatch.setattr(d.language_detector, "detect_from_text_content_fasttext", fake_nlp)
        monkeypatch.setattr(d.language_detector, "detect_from_text_content", fake_nlp)

        res = await d.check_page_if_french(html, DetectionMode.COMPLETE)

        assert res.ok is False
        assert res.method == 'Check_nok_v2'

    @pytest.mark.asyncio
    async def test_case7_nlp_not_confirmed_gated_when_no_text(self, monkeypatch):
        """Porte 2 : Cas 7 (`nlp_not_confirmed`). HTML indique FR (`lang="fr"`)
        mais quasi aucun texte visible ; NLP mocké répond confiant en anglais
        (ce qui atteindrait Cas 7 sans le garde) -> doit devenir
        `fetch_empty_content`."""
        html = '<html lang="fr"><body>x</body></html>'
        d = _make_detector("https://example.com/")
        _stub_alternatives(d, monkeypatch, [])

        def fake_nlp(_text):
            return {"lang": "en", "confidence": 0.6, "method": "nlp_detection_fasttext", "details": {}}
        monkeypatch.setattr(d.language_detector, "detect_from_text_content_fasttext", fake_nlp)
        monkeypatch.setattr(d.language_detector, "detect_from_text_content", fake_nlp)

        res = await d.check_page_if_french(html, DetectionMode.COMPLETE)

        assert res.method == 'fetch_empty_content'
        assert res.method != 'nlp_not_confirmed'

    @pytest.mark.asyncio
    async def test_case2a_nlp_override_tld_fr_gated_when_no_text(self, monkeypatch):
        """Porte 3 : Cas 2a (`nlp_override_tld_fr`). TLD .fr + NLP mocké
        contredit fortement (>0.9), mais quasi aucun texte visible (ce qui
        atteindrait Cas 2a sans le garde) -> doit devenir
        `fetch_empty_content`."""
        html = '<html lang="en"><body>x</body></html>'
        d = _make_detector("https://example.fr/")
        _stub_alternatives(d, monkeypatch, [])

        def fake_nlp(_text):
            return {"lang": "en", "confidence": 0.95, "method": "nlp_detection_fasttext", "details": {}}
        monkeypatch.setattr(d.language_detector, "detect_from_text_content_fasttext", fake_nlp)
        monkeypatch.setattr(d.language_detector, "detect_from_text_content", fake_nlp)

        res = await d.check_page_if_french(html, DetectionMode.COMPLETE)

        assert res.method == 'fetch_empty_content'
        assert res.method != 'nlp_override_tld_fr'
        # `method` seul ne distingue pas CE garde (Cas 2a) du garde
        # pré-existant du Cas 2b, qui rend le même method sur la même URL —
        # leurs messages diffèrent ("verdict non fiable sur texte vide" vs
        # "site probablement inaccessible").
        assert 'verdict non fiable sur texte vide' in (res.error or '')

    @pytest.mark.asyncio
    async def test_positive_verdict_without_confirmable_text_stays_ok_true(self, monkeypatch):
        """NON-RÉGRESSION POSITIVE (frontière du périmètre) : Cas 5
        (`/fr/` dans le path + `lang="fr"`, NLP indisponible) reste ok=True à
        **1 caractère visible** — la vraie frontière que le garde ne doit
        JAMAIS toucher. Le chemin `.fr` ne peut pas exprimer ce cas : le
        garde pré-existant du Cas 2b y rejette déjà une page sans texte."""
        html = '<html lang="fr"><body>x</body></html>'
        d = _make_detector("https://example.com/fr/")
        _stub_alternatives(d, monkeypatch, [])

        def unavailable(_text):
            return None
        monkeypatch.setattr(d.language_detector, "detect_from_text_content_fasttext", unavailable)
        monkeypatch.setattr(d.language_detector, "detect_from_text_content", unavailable)

        res = await d.check_page_if_french(html, DetectionMode.COMPLETE)

        assert res.ok is True
        assert res.method == 'pattern_match_path+langHtml+nlp_skipped'


def test_coarse_helper_diverges_from_fine_cleaner_on_head_only_content():
    """Sémantique load-bearing du garde N1 : `_extract_visible_text_coarse`
    (l'oracle des 3 portes) retient `<head>` — donc `<title>` — alors que
    `clean_html_to_text` (le nettoyage NLP) le retire. Sans cette assertion
    directe, un swap silencieux des deux décapages ferait basculer les 4
    portes (Cas 2a/2b/7/9) avec toute la suite encore verte."""
    html = '<html><head><title>' + ('mot ' * 40) + '</title></head><body></body></html>'

    coarse = DomainFR._extract_visible_text_coarse(html)
    fine = LanguageDetector().clean_html_to_text(html)

    assert len(coarse) >= 100
    assert fine is None
