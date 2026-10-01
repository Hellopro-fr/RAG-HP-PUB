"""Le boilerplate de consentement ne doit jamais atteindre le NLP.

Cas réel : pesage88.com (DSPI 39) — la modale WebToffee « Privacy Overview »
(anglaise) pesait 75% du texte de la page et faisait basculer fastText sur
`en` alors que le site est français. Voir spec 2026-07-28.
"""
from app.services.language_detector import LanguageDetector

# Anglais dans 3 conteneurs de consentement + français dans le body
# + français dans un slider aria-hidden (qui DOIT survivre).
HTML = """
<html lang="fr-FR"><body>
  <div id="content">
    Nos produits balances industrielles et bascules au sol pour la region Lorraine.
  </div>

  <div class="gdpr-widget" data-nosnippet="true">
    WESHOULDSTRIP_NOSNIPPET We use cookies on our website to give you the most
    relevant experience by remembering your preferences and repeat visits.
  </div>

  <div class="cli-modal" id="cliSettingsPopup" aria-hidden="true">
    WESHOULDSTRIP_CLIMODAL Privacy Overview This website uses cookies to improve
    your experience while you navigate through the website.
  </div>

  <div class="cky-consent-container">
    WESHOULDSTRIP_CKY This website uses cookies to improve your experience.
  </div>

  <div class="slick-slide" aria-hidden="true">
    WEMUSTKEEP_SLIDER Merci a l equipe pour la reactivite et la qualite du travail.
  </div>

  <div class="sticky-header" id="sticky-nav">
    WEMUSTKEEP_STICKY Accueil Nos produits Contact
  </div>

  <div class="sticky-modal">WEMUSTKEEP_STICKYMODAL Nos references clients</div>
  <div class="sticky-consent-bar">WEMUSTKEEP_STICKYCONSENT Devis gratuit sous 24h</div>
  <div class="sticky-overlay">WEMUSTKEEP_STICKYOVERLAY Zone d intervention Lorraine</div>
  <div class="sticky-notice-box">WEMUSTKEEP_STICKYNOTICE Horaires d ouverture</div>
  <div class="promo-banner cky-modal">WESHOULDSTRIP_CKYMULTI This site uses cookies.</div>
</body></html>
"""


def test_consent_boilerplate_stripped_but_hidden_slider_kept():
    text = LanguageDetector().clean_html_to_text(HTML)
    assert text is not None

    # Consentement retiré (data-nosnippet + filets vendeurs)
    assert "WESHOULDSTRIP_NOSNIPPET" not in text
    assert "WESHOULDSTRIP_CLIMODAL" not in text
    assert "WESHOULDSTRIP_CKY" not in text
    assert "Privacy Overview" not in text

    # Contenu réel conservé
    assert "balances industrielles" in text
    # aria-hidden n'est PAS un critère de suppression : les clones de carrousel
    # (slick-slide) portent du vrai contenu — cf. sumca.fr, 1288 caractères de
    # témoignages. Ce garde-fou verrouille le refus de l'option écartée.
    assert "WEMUSTKEEP_SLIDER" in text
    # `cky-` en substring attraperait `sticky-header`/`sticky-nav` : la nav
    # collante est du vrai contenu et doit survivre.
    assert "WEMUSTKEEP_STICKY" in text
    # `sticky-*` finit par `cky-` : ces variantes doivent TOUTES survivre.
    assert "WEMUSTKEEP_STICKYMODAL" in text
    assert "WEMUSTKEEP_STICKYCONSENT" in text
    assert "WEMUSTKEEP_STICKYOVERLAY" in text
    assert "WEMUSTKEEP_STICKYNOTICE" in text
    # ...mais un token de classe `cky-*` est retiré même en multi-classes.
    assert "WESHOULDSTRIP_CKYMULTI" not in text
