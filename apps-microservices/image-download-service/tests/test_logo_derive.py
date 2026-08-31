#!/usr/bin/env python3
"""Tests de la derive d'affichage des logos fournisseurs — recette « r1m0 ».

Le nom de recette ci-dessus est celui de :data:`core.logo_derive.RECIPE`, et il
entre dans des URL CDN declarees immutables 30 jours : ce fichier annoncait
encore « r1m0v8151 » alors que le jeton de version de libvips avait ete RETIRE du
nom (la prod tourne en 8.14.x, le jeton mentait). Un test le verrouille
desormais, pour que l'entete ne puisse plus deriver de l'identite reelle.

Les attentes de ce fichier viennent de la SPEC de la recette (canvas 200x200 fixe,
marge 0, non-agrandissement raster, tri des SVG, verdict de surface, plaque
conditionnelle, nommage adresse par contenu), PAS de la lecture du module. Quand
une assertion tombe, le defaut est presume dans ``app/core/logo_derive.py``.

Les fixtures sont fabriquees programmatiquement (PIL / pyvips / SVG en chaine) :
aucun fichier binaire n'est versionne, et chaque cas de la spec en a une.

Rappel du consommateur, qui justifie les seuils testes ici : carte de listing
fournisseur, cadre 70x44 avec padding 5px et bordure 1px, soit une boite utile de
58x32 px sur fond BLANC PUR (pas de mode sombre).
"""

import hashlib
import io

import pyvips
import pytest
from PIL import Image, ImageDraw

from core.logo_derive import (
    BLOCKING_FLAGS,
    CANVAS,
    FLAG_ORDER,
    FLAGS,
    MAX_SVG_CONTENT_BYTES,
    MIN_DISPLAYED_INK_EDGE,
    RECIPE,
    SVG_SNIFF_BYTES,
    derive_logo,
)


# Deux hash de reference : le nommage est adresse par contenu, il faut pouvoir
# verifier qu'il est stable a hash egal et different a hash different.
HASH_A = "a" * 64
HASH_B = "b" * 64
KEY = "acme.fr"

#: Les 14 cles que ``metrics`` doit TOUJOURS porter, y compris en echec.
#: ``libvips_version`` a ete ajoutee le 31/08 : la version de libvips a ete
#: RETIREE du nom de recette (elle entrait dans une URL immutable 30 jours alors
#: que la prod tourne en 8.14.x), et l'audit doit pouvoir la relire quelque part.
METRIC_KEYS = {
    "recipe", "libvips_version", "source_hash", "surface", "flags", "fill_pct",
    "ratio_x100", "master_width", "master_height", "ink_bbox", "alpha_ratio",
    "ink_on_white", "ink_on_black", "is_light",
}


# =============================================================================
# Fabrique de fixtures
# =============================================================================

def _png(img):
    """Encode une image PIL en octets PNG."""
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _svg(body, attrs=''):
    return ('<svg xmlns="http://www.w3.org/2000/svg" %s>%s</svg>' % (attrs, body)).encode("utf-8")


# --- SVG ---------------------------------------------------------------------

def svg_32x32():
    """SVG DECLARE 32x32 : un disque centre, sans marge dans le viewBox."""
    return _svg('<circle cx="16" cy="16" r="16" fill="#0A2E5C"/>',
                'width="32" height="32" viewBox="0 0 32 32"')


def svg_damier_32x32():
    """SVG declare 32x32 portant un damier 8x8 : sert de temoin de NETTETE.

    Chaque case fait 4 unites : rendue a 200 px l'echelle vaut 6,25 et les
    frontieres tombent sur des pixels entiers, donc un rendu VECTORIEL ne doit
    produire que 2 niveaux de gris. Un upscale d'un raster 32x32 en produirait
    des dizaines (degrade d'interpolation sur chaque frontiere).
    """
    cells = []
    for gy in range(8):
        for gx in range(8):
            color = "#000000" if (gx + gy) % 2 == 0 else "#ffffff"
            cells.append('<rect x="%d" y="%d" width="4" height="4" fill="%s"/>'
                         % (gx * 4, gy * 4, color))
    return _svg("".join(cells), 'width="32" height="32" viewBox="0 0 32 32"')


def svg_sans_dimensions():
    """SVG sans viewBox NI width/height : les dimensions ne sont pas declarees."""
    return _svg('<circle cx="50" cy="50" r="40" fill="#123456"/>')


def svg_viewbox_avec_marge():
    """SVG 200x200 dont l'encre n'occupe que 40x40 : viewBox genereux.

    Cas d'export tres courant. La spec exige marge 0 (etape 7) : le derive doit
    remplir le canvas, pas recopier la marge du viewBox.
    """
    return _svg('<circle cx="100" cy="100" r="20" fill="#101820"/>',
                'width="200" height="200" viewBox="0 0 200 200"')


def svg_avec_texte():
    """SVG contenant du <text> : le conteneur de prod n'a AUCUNE police."""
    return _svg('<text x="10" y="40" font-size="30">ACME</text>',
                'width="200" height="60"')


def svg_avec_font_face():
    """SVG sans <text> mais avec une @font-face : meme risque de rendu faux."""
    return _svg('<style>@font-face{src:url(a.woff)}</style>'
                '<rect x="0" y="0" width="80" height="40" fill="#000"/>',
                'width="200" height="60"')


def svg_enveloppant_un_raster():
    """SVG dont le seul contenu est un bitmap en data: URI (forme non uniforme)."""
    import base64
    inner = Image.new("RGBA", (120, 60), (0, 0, 0, 0))
    ImageDraw.Draw(inner).ellipse([5, 5, 114, 54], fill=(0, 60, 160, 255))
    b64 = base64.b64encode(_png(inner)).decode("ascii")
    return ('<svg xmlns="http://www.w3.org/2000/svg" '
            'xmlns:xlink="http://www.w3.org/1999/xlink" width="120" height="60">'
            '<image width="120" height="60" xlink:href="data:image/png;base64,%s"/>'
            '</svg>' % b64).encode("ascii")


def svg_enveloppant_un_raster_href_simple():
    """Meme cas, forme reelle alternative : href sans xlink et apostrophes simples."""
    import base64
    inner = Image.new("RGBA", (120, 60), (0, 0, 0, 0))
    ImageDraw.Draw(inner).ellipse([5, 5, 114, 54], fill=(0, 60, 160, 255))
    b64 = base64.b64encode(_png(inner)).decode("ascii")
    return ("<svg xmlns='http://www.w3.org/2000/svg' width='120' height='60'>"
            "<image width='120' height='60' href='data:image/png;base64,%s'/>"
            "</svg>" % b64).encode("ascii")


def svg_prolog_xml():
    """SVG precede du prolog XML : la detection porte sur les 10 premiers octets."""
    return (b'<?xml version="1.0" encoding="UTF-8"?>\n'
            b'<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" '
            b'viewBox="0 0 64 64"><circle cx="32" cy="32" r="32" fill="#0A2E5C"/></svg>')


# --- Raster : formats et profondeurs ----------------------------------------

def gif_transparence_1bit():
    """GIF a transparence 1 bit portant une encre BLANCHE (donc dark_required).

    Palette explicite : index 0 declare transparent, index 1 blanc.
    """
    pal = Image.new("P", (200, 120), 0)
    pal.putpalette([0, 0, 0, 255, 255, 255] + [0] * (254 * 3))
    ImageDraw.Draw(pal).ellipse([20, 10, 180, 110], outline=1, width=18)
    buf = io.BytesIO()
    pal.save(buf, "GIF", transparency=0)
    return buf.getvalue()


def jpeg_cmyk():
    """JPEG en CMJN : 4 bandes mais PAS de canal alpha (piege de normalisation)."""
    img = Image.new("CMYK", (240, 120), (0, 0, 0, 0))          # CMYK 0,0,0,0 = blanc
    ImageDraw.Draw(img).rectangle([40, 30, 199, 89], fill=(0, 0, 0, 255))  # noir
    buf = io.BytesIO()
    img.save(buf, "JPEG")
    return buf.getvalue()


def png_gris_1_bande():
    """PNG en niveaux de gris : 1 seule bande, aucun alpha."""
    img = Image.new("L", (200, 120), 255)
    ImageDraw.Draw(img).ellipse([30, 20, 169, 99], fill=40)
    return _png(img)


def png_la_2_bandes():
    """PNG gris + alpha : 2 bandes, cas ou hasalpha() ne suffit pas."""
    img = Image.new("LA", (200, 120), (0, 0))
    ImageDraw.Draw(img).ellipse([30, 20, 169, 99], fill=(30, 255))
    return _png(img)


def png_palette():
    """PNG palettise (mode P)."""
    img = Image.new("RGB", (200, 120), (255, 255, 255))
    ImageDraw.Draw(img).rectangle([30, 20, 169, 99], fill=(200, 30, 30))
    return _png(img.convert("P", palette=Image.ADAPTIVE, colors=8))


# --- Raster : geometries ----------------------------------------------------

def png_900x60():
    """PNG tres large : 900x60, encre 900x40 (ratio 22,5)."""
    img = Image.new("RGBA", (900, 60), (0, 0, 0, 0))
    ImageDraw.Draw(img).rectangle([0, 10, 899, 49], fill=(20, 40, 90, 255))
    return _png(img)


def png_96x32():
    """PNG plus petit que la cible : ne doit JAMAIS etre agrandi."""
    img = Image.new("RGBA", (96, 32), (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse([2, 2, 93, 29], fill=(10, 10, 10, 255))
    return _png(img)


def png_3000x3000():
    """PNG tres grand : eprouve le shrink-on-load et le referentiel master."""
    img = Image.new("RGBA", (3000, 3000), (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse([100, 100, 2899, 2899],
                                outline=(0, 0, 0, 255), width=200)
    return _png(img)


def png_bar(ink_w, ink_h):
    """Barre opaque ink_w x ink_h, entouree d'une marge transparente de 10 px."""
    img = Image.new("RGBA", (ink_w + 20, ink_h + 20), (0, 0, 0, 0))
    ImageDraw.Draw(img).rectangle([10, 10, 10 + ink_w - 1, 10 + ink_h - 1],
                                  fill=(20, 60, 140, 255))
    return _png(img)


# --- Raster : surfaces ------------------------------------------------------

def _forme_sur_transparent(color):
    """Anneau + bloc de la couleur donnee sur fond transparent (240x120)."""
    img = Image.new("RGBA", (240, 120), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([20, 10, 120, 110], outline=color, width=14)
    draw.rectangle([140, 30, 219, 89], fill=color)
    return _png(img)


def png_blanc_sur_transparent():
    """LE CAS DES 205 : encre blanche sur transparent, invisible sur blanc."""
    return _forme_sur_transparent((255, 255, 255, 255))


def png_noir_sur_transparent():
    """Encre sombre sur transparent : lisible sur le fond blanc de la carte."""
    return _forme_sur_transparent((30, 30, 30, 255))


def png_noir_pur_sur_transparent():
    """Encre #000000 exactement : cas limite mathematique de ink_on_black."""
    return _forme_sur_transparent((0, 0, 0, 255))


def png_bloc_blanc_sur_transparent():
    """Logotype en bloc plein blanc : l'encre remplit toute sa boite englobante."""
    img = Image.new("RGBA", (240, 120), (0, 0, 0, 0))
    ImageDraw.Draw(img).rectangle([40, 20, 199, 99], fill=(255, 255, 255, 255))
    return _png(img)


def png_fond_opaque_blanc():
    """Encre sombre sur fond BLANC opaque : les 4 coins concordent."""
    img = Image.new("RGB", (240, 120), (255, 255, 255))
    ImageDraw.Draw(img).rectangle([40, 20, 199, 99], fill=(15, 25, 60))
    return _png(img)


def png_fond_opaque_colore():
    """Encre sombre sur fond COLORE uniforme : les 4 coins concordent aussi."""
    img = Image.new("RGB", (240, 120), (240, 120, 20))
    ImageDraw.Draw(img).rectangle([40, 20, 199, 99], fill=(15, 25, 60))
    return _png(img)


def png_fond_opaque_bicolore():
    """Fond opaque dont les 4 coins DIVERGENT : le trim doit etre refuse."""
    img = Image.new("RGB", (240, 120), (240, 120, 20))
    draw = ImageDraw.Draw(img)
    draw.rectangle([120, 0, 239, 119], fill=(20, 80, 200))
    draw.rectangle([80, 40, 159, 79], fill=(15, 15, 15))
    return _png(img)


def png_tout_transparent():
    """PNG entierement transparent : aucune encre a cadrer."""
    return _png(Image.new("RGBA", (200, 120), (0, 0, 0, 0)))


def jpeg_opaque():
    """JPEG opaque : encre sombre sur blanc, aucun alpha possible."""
    img = Image.new("RGB", (240, 120), (255, 255, 255))
    ImageDraw.Draw(img).ellipse([40, 20, 199, 99], fill=(10, 20, 40))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=95)
    return buf.getvalue()


def png_disque_blanc_contour_sombre():
    """Disque blanc cercle d'un filet sombre : encre a peine visible sur blanc."""
    img = Image.new("RGBA", (240, 140), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([20, 20, 219, 119], fill=(255, 255, 255, 255))
    draw.ellipse([20, 20, 219, 119], outline=(20, 20, 20, 255), width=2)
    return _png(img)


def png_matte_saturee():
    """Encre blanche dont le bord a alpha partiel porte encore une teinte saturee.

    C'est la signature d'un detourage sur un ancien fond colore : sur une plaque
    sombre, ce bord ressortirait en lisere sale.
    """
    img = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([10, 10, 389, 389], fill=(255, 255, 255, 255))
    draw.ellipse([10, 10, 389, 389], outline=(255, 0, 200, 128), width=2)
    return _png(img)


def png_matte_neutre():
    """Meme geometrie, bord NEUTRE : anodin sur une plaque sombre."""
    img = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([10, 10, 389, 389], fill=(255, 255, 255, 255))
    draw.ellipse([10, 10, 389, 389], outline=(128, 128, 128, 128), width=2)
    return _png(img)


def png_carre(ink, frame=120):
    """Carre opaque ink x ink centre dans un cadre transparent."""
    img = Image.new("RGBA", (frame, frame), (0, 0, 0, 0))
    off = (frame - ink) // 2
    ImageDraw.Draw(img).rectangle([off, off, off + ink - 1, off + ink - 1],
                                  fill=(20, 60, 140, 255))
    return _png(img)


def png_point_dans_grand_cadre(dot, frame=400):
    """Petit disque dans un tres grand cadre transparent."""
    img = Image.new("RGBA", (frame, frame), (0, 0, 0, 0))
    off = (frame - dot) // 2
    ImageDraw.Draw(img).ellipse([off, off, off + dot - 1, off + dot - 1],
                                fill=(0, 0, 0, 255))
    return _png(img)


# --- Fixtures des defauts corriges le 31/08 ---------------------------------

def png_lockup_hachure():
    """Lockup : marque HACHUREE 1 px / gap 2 px + signature pleine dessous.

    ``find_trim`` sous-echantillonne et rend (30, 290, 341, 91) : la marque, soit
    les DEUX TIERS du logo, disparaissait du derive, sans erreur et sans flag,
    sous un nom adresse par contenu declare immutable 30 jours. La vraie bande
    d'encre va de y=20 a y=380.
    """
    img = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    for y in range(20, 281, 3):
        draw.line([(30, y), (370, y)], fill=(20, 20, 20, 255))
    draw.rectangle([30, 290, 370, 380], fill=(20, 20, 20, 255))
    return _png(img)


def png_code_barres():
    """Barres verticales BLANCHES de 1 px espacees de 2 px : 33 % d'encre.

    ``find_trim`` rend (0, 0, 1, 80), soit 80 px sur 19 200 : le logo tombait
    sous ``ink_too_small``, un flag BLOQUANT, et etait ecarte de la publication.
    """
    img = Image.new("RGBA", (240, 80), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    for x in range(0, 240, 3):
        draw.line([(x, 0), (x, 79)], fill=(255, 255, 255, 255))
    return _png(img)


def png_1x1():
    """Master de 1x1 : ``find_trim`` LEVE (« rank: window too large »)."""
    return _png(Image.new("RGBA", (1, 1), (0, 0, 0, 255)))


def png_encre_blanche_dans_grand_cadre():
    """Encre BLANCHE de 300 px dans un cadre transparent de 2000 (2,25 %).

    Le trim est refuse (``trim_degenerate``), le cadre entier conserve : l'encre
    reellement visible ne fait plus que 36 px dans le canvas 200x200, mais
    ``fill_pct`` annoncait 100 et le verdict etait mesure sur un cadre a 98 %
    transparent, donc il decrivait le FOND.
    """
    img = Image.new("RGBA", (2000, 2000), (0, 0, 0, 0))
    ImageDraw.Draw(img).rectangle([850, 850, 1149, 1149], fill=(255, 255, 255, 255))
    return _png(img)


def png_uniforme_opaque():
    """PNG entierement uni et opaque : aucune encre distincte du fond.

    Les 4 coins concordent, ``find_trim`` ne trouve rien, et le module concluait
    ``ink_too_small`` — flag bloquant — alors que la bonne reponse est « le fond
    fait partie du logo » : cadre entier + ``baked_background``.
    """
    return _png(Image.new("RGBA", (300, 300), (18, 52, 86, 255)))


def svg_doctype_avec_texte():
    """SVG a ``<text>`` precede d'un DOCTYPE : le garde svg_text etait contourne.

    ``_is_svg`` ne regarde que 10 octets : avec ce prefixe le fichier partait en
    branche RASTER, donc librsvg rasterisait le texte SANS police (le conteneur
    de prod n'embarque aucun paquet fonts-*) et la vignette etait publiee.
    """
    return (b'<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" '
            b'"http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">\n'
            b'<svg xmlns="http://www.w3.org/2000/svg" width="200" height="60">'
            b'<text x="10" y="40" font-size="30">ACME</text></svg>')


def svg_commentaire_generateur():
    """SVG vectoriel precede d'un commentaire Adobe Illustrator, declare 32x32.

    Meme cause : route en raster, donc rendu 32x32 par ``size="down"`` (P1) au
    lieu d'etre rasterise a 200 — violation directe de la marge 0 de l'etape 7.
    """
    return (b'<!-- Generator: Adobe Illustrator 27.0.0, SVG Export Plug-In -->\n'
            b'<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" '
            b'viewBox="0 0 32 32"><circle cx="16" cy="16" r="16" fill="#0A2E5C"/></svg>')


def svg_grand_artboard_petite_marque():
    """SVG artboard 800 dont la marque fait 60 unites (0,56 % de l'aire).

    ``ink_too_small`` etait applique relativement au CADRE, or le rapport
    encre/cadre d'un rendu vectoriel est INVARIANT D'ECHELLE : aucun
    supersampling ne pouvait le faire passer, et le flag etant bloquant le logo
    etait ecarte DEFINITIVEMENT.
    """
    return _svg('<circle cx="400" cy="400" r="30" fill="#123456"/>',
                'width="800" height="800" viewBox="0 0 800 800"')


def svg_trop_lourd():
    """SVG au-dela du plafond de contenu : refus AVANT toute rasterisation.

    Mesures : 1,7 Mo / 30 000 elements -> +122 Mo RSS ; 6,7 Mo / 120 000 ->
    +462 Mo ; 16,8 Mo / 300 000 -> +1 098 Mo. Sous contrainte memoire librsvg
    ABORTE le processus (SIGABRT, non rattrapable) : le message RabbitMQ n'est
    jamais acquitte, il est redelivre, et il tue la replica suivante.
    """
    rect = '<rect x="1" y="1" width="3" height="3" fill="#123456"/>'
    nb = MAX_SVG_CONTENT_BYTES // len(rect) + 1000
    return _svg(rect * nb, 'width="800" height="800" viewBox="0 0 800 800"')


# =============================================================================
# Registre des cas + cache des derives (derive_logo est pure : on memoise)
# =============================================================================

CASES = {
    # --- les 19 cas explicitement demandes par la spec ---------------------
    "svg_32x32": svg_32x32(),
    "svg_sans_dimensions": svg_sans_dimensions(),
    "svg_avec_texte": svg_avec_texte(),
    "svg_enveloppant_un_raster": svg_enveloppant_un_raster(),
    "gif_transparence_1bit": gif_transparence_1bit(),
    "jpeg_cmyk": jpeg_cmyk(),
    "png_gris_1_bande": png_gris_1_bande(),
    "png_la_2_bandes": png_la_2_bandes(),
    "png_palette": png_palette(),
    "png_900x60": png_900x60(),
    "png_96x32": png_96x32(),
    "png_3000x3000": png_3000x3000(),
    "png_blanc_sur_transparent": png_blanc_sur_transparent(),
    "png_noir_sur_transparent": png_noir_sur_transparent(),
    "png_fond_opaque_blanc": png_fond_opaque_blanc(),
    "png_fond_opaque_colore": png_fond_opaque_colore(),
    "png_tout_transparent": png_tout_transparent(),
    "pas_une_image": b"this is definitely not an image nor an svg file",
    "vide": b"",
    # --- cas complementaires exiges par les regles de la spec -------------
    "svg_damier_32x32": svg_damier_32x32(),
    "svg_viewbox_avec_marge": svg_viewbox_avec_marge(),
    "svg_avec_font_face": svg_avec_font_face(),
    "svg_enveloppant_un_raster_href_simple": svg_enveloppant_un_raster_href_simple(),
    "svg_prolog_xml": svg_prolog_xml(),
    "jpeg_opaque": jpeg_opaque(),
    "png_noir_pur_sur_transparent": png_noir_pur_sur_transparent(),
    "png_bloc_blanc_sur_transparent": png_bloc_blanc_sur_transparent(),
    "png_fond_opaque_bicolore": png_fond_opaque_bicolore(),
    "png_disque_blanc_contour_sombre": png_disque_blanc_contour_sombre(),
    "png_matte_saturee": png_matte_saturee(),
    "png_matte_neutre": png_matte_neutre(),
    "png_carre_96": png_carre(96),
    "png_carre_95": png_carre(95),
    "png_bar_700x100": png_bar(700, 100),
    "png_bar_500x100": png_bar(500, 100),
    "png_point_60_dans_400": png_point_dans_grand_cadre(60),
    "png_point_20_dans_400": png_point_dans_grand_cadre(20),
    # --- temoins des defauts corriges le 31/08 ----------------------------
    "png_lockup_hachure": png_lockup_hachure(),
    "png_code_barres": png_code_barres(),
    "png_1x1": png_1x1(),
    "png_encre_blanche_dans_grand_cadre": png_encre_blanche_dans_grand_cadre(),
    "png_uniforme_opaque": png_uniforme_opaque(),
    "svg_doctype_avec_texte": svg_doctype_avec_texte(),
    "svg_commentaire_generateur": svg_commentaire_generateur(),
    "svg_grand_artboard_petite_marque": svg_grand_artboard_petite_marque(),
    "svg_trop_lourd": svg_trop_lourd(),
}

#: Cas dont la spec exige QU'AUCUNE variante ne soit produite.
SANS_VARIANTE = {
    "svg_avec_texte",           # aucune police dans le conteneur
    "svg_avec_font_face",       # idem
    "svg_doctype_avec_texte",   # idem, malgre le DOCTYPE qui masquait le tri
    "svg_trop_lourd",           # refus memoire, pas defaillance
    "png_tout_transparent",     # aucune encre
    "png_point_20_dans_400",    # encre < 1 % de la surface
    "png_1x1",                  # arete sous 3 px : rien a cadrer
    "pas_une_image",            # defaillance
    "vide",                     # defaillance
}

#: Cas dont la spec exige que ``error`` soit renseigne.
EN_ERREUR = {"pas_une_image", "vide"}

_DERIVED = {}


def derived(name, key=KEY, content_hash=HASH_A, **kwargs):
    """Derive memoise (les fixtures 3000x3000 et 400x400 coutent cher)."""
    cache_key = (name, key, content_hash, tuple(sorted(kwargs.items())))
    if cache_key not in _DERIVED:
        _DERIVED[cache_key] = derive_logo(CASES[name], key, content_hash, **kwargs)
    return _DERIVED[cache_key]


def variant(result, name):
    """Retourne la variante nommee, ou None."""
    for item in result["variants"]:
        if item["variant"] == name:
            return item
    return None


def as_pil(variant_dict):
    return Image.open(io.BytesIO(variant_dict["bytes"])).convert("RGBA")


def ink_box(variant_dict):
    """Boite englobante de l'alpha non nul dans une variante (left, top, w, h)."""
    box = as_pil(variant_dict).split()[3].getbbox()
    if box is None:
        return None
    return (box[0], box[1], box[2] - box[0], box[3] - box[1])


def gray_levels(variant_dict):
    """Nombre de niveaux de gris distincts dans une variante."""
    img = as_pil(variant_dict).convert("L")
    return len(set(img.tobytes()))


# =============================================================================
# 1. Contrat de sortie — invariants valables pour TOUS les cas
# =============================================================================

@pytest.mark.parametrize("name", sorted(CASES))
def test_derive_logo_ne_leve_jamais(name):
    """Contrat dur : aucune exception ne sort de derive_logo, quoi qu'on entre."""
    result = derived(name)
    assert isinstance(result, dict)
    assert set(result) == {"variants", "metrics", "error"}


@pytest.mark.parametrize("name", sorted(CASES))
def test_metrics_porte_toujours_les_memes_cles(name):
    """metrics garde ses 14 cles meme quand aucune variante n'est produite."""
    metrics = derived(name)["metrics"]
    assert set(metrics) == METRIC_KEYS
    assert metrics["recipe"] == RECIPE
    assert metrics["source_hash"] == HASH_A


@pytest.mark.parametrize("name", sorted(CASES))
def test_toute_variante_fait_exactement_200x200_avec_alpha(name):
    """Toute variante produite fait 200x200, 4 bandes, alpha, PNG sRGB non palettise."""
    for item in derived(name)["variants"]:
        assert item["width"] == CANVAS and item["height"] == CANVAS
        assert item["format"] == "png"
        assert item["bytes"][:8] == b"\x89PNG\r\n\x1a\n", "octets PNG attendus"

        vips_img = pyvips.Image.new_from_buffer(item["bytes"], "")
        assert (vips_img.width, vips_img.height) == (CANVAS, CANVAS)
        assert vips_img.bands == 4, "4 bandes attendues (RGBA)"
        assert vips_img.hasalpha()
        assert vips_img.interpretation == "srgb"
        assert as_pil(item).mode == "RGBA"


@pytest.mark.parametrize("name", sorted(CASES))
def test_les_flags_poses_appartiennent_a_la_liste_fermee(name):
    """Aucun flag hors de FLAGS ne peut apparaitre, et aucun doublon."""
    flags = derived(name)["metrics"]["flags"]
    assert isinstance(flags, list)
    assert set(flags) <= FLAGS, "flag hors liste fermee : %s" % (set(flags) - FLAGS)
    assert len(flags) == len(set(flags)), "flags dupliques : %s" % flags


@pytest.mark.parametrize("name", sorted(CASES))
def test_variantes_attendues_ou_non(name):
    """La spec fixe exactement quels cas ne produisent aucune variante."""
    result = derived(name)
    if name in SANS_VARIANTE:
        assert result["variants"] == [], "aucune variante attendue pour %s" % name
    else:
        assert result["variants"], "au moins une variante attendue pour %s" % name
        assert result["variants"][0]["variant"] == "sq200a"


@pytest.mark.parametrize("name", sorted(CASES))
def test_error_renseigne_uniquement_en_defaillance(name):
    """svg_text et ink_too_small ne sont pas des erreurs : error reste None."""
    result = derived(name)
    if name in EN_ERREUR:
        assert result["error"], "error attendu pour %s" % name
        assert "derivation_failed" in result["metrics"]["flags"]
    else:
        assert result["error"] is None, "error inattendu pour %s : %r" % (name, result["error"])
        assert "derivation_failed" not in result["metrics"]["flags"]


# =============================================================================
# 2. Etapes 1-2 — detection de format et tri des SVG
# =============================================================================

def test_svg_a_texte_ne_produit_aucun_derive_et_porte_svg_text():
    """Le conteneur de prod n'a aucune police : on preserve le master SVG."""
    result = derived("svg_avec_texte")
    assert result["variants"] == []
    assert "svg_text" in result["metrics"]["flags"]
    assert result["error"] is None, "svg_text n'est pas une defaillance"


def test_svg_a_font_face_est_traite_comme_du_texte():
    """@font-face est l'un des motifs de la spec, meme sans balise <text>."""
    result = derived("svg_avec_font_face")
    assert result["variants"] == []
    assert "svg_text" in result["metrics"]["flags"]


@pytest.mark.parametrize("name", [
    "svg_enveloppant_un_raster",
    "svg_enveloppant_un_raster_href_simple",
])
def test_svg_enveloppant_un_raster_est_route_vers_la_branche_raster(name):
    """Un bitmap en data: URI ne doit pas beneficier de l'agrandissement vectoriel."""
    result = derived(name)
    flags = result["metrics"]["flags"]
    assert "svg_wraps_raster" in flags
    assert "svg_text" not in flags
    assert result["variants"], "le derive doit tout de meme etre produit"
    # Branche raster => non-agrandissement : l'encre (110x50) reste sous la cible.
    assert "no_upscale" in flags, "la branche raster interdit l'agrandissement"


def test_svg_detecte_via_le_prolog_xml():
    """Detection sur les 10 premiers octets : `<?xml` compte comme du SVG."""
    result = derived("svg_prolog_xml")
    assert result["error"] is None
    assert "svg_wraps_raster" not in result["metrics"]["flags"]
    # Traite en vecteur : un disque declare 64x64 doit remplir le canvas.
    box = ink_box(variant(result, "sq200a"))
    assert box[2] >= CANVAS - 4 and box[3] >= CANVAS - 4, box


# =============================================================================
# 3. Etape 3 — rendu vectoriel natif (le piege size="down")
# =============================================================================

def test_svg_32x32_rendu_net_et_non_upscale():
    """Un SVG declare 32x32 doit etre RASTERISE a 200, pas agrandi depuis 32.

    Temoin : un damier dont les frontieres tombent sur des pixels entiers. Le
    rendu vectoriel ne donne que les 2 tons du damier ; un upscale d'un raster
    32x32 interpole et en produit des dizaines.
    """
    result = derived("svg_damier_32x32")
    sq200a = variant(result, "sq200a")
    assert sq200a is not None

    niveaux_derive = gray_levels(sq200a)

    # Temoin : le MEME damier rasterise a 32x32 puis agrandi naivement.
    raster32 = pyvips.Image.thumbnail_buffer(CASES["svg_damier_32x32"], 32, height=32)
    naif = Image.open(io.BytesIO(raster32.copy_memory().pngsave_buffer()))
    naif = naif.convert("L").resize((CANVAS, CANVAS), Image.BICUBIC)
    niveaux_naif = len(set(naif.tobytes()))

    assert niveaux_derive <= 4, "rendu vectoriel attendu net, %d niveaux" % niveaux_derive
    assert niveaux_naif >= 20, "temoin d'upscale invalide (%d niveaux)" % niveaux_naif
    assert niveaux_naif >= 5 * niveaux_derive, (
        "ecart insuffisant : derive=%d, upscale naif=%d" % (niveaux_derive, niveaux_naif)
    )


def test_svg_32x32_remplit_le_canvas_sans_marge():
    """Etape 7, marge 0 : un SVG sans marge dans son viewBox remplit 200x200."""
    result = derived("svg_32x32")
    box = ink_box(variant(result, "sq200a"))
    assert box[2] >= CANVAS - 2 and box[3] >= CANVAS - 2, box
    assert result["metrics"]["fill_pct"] >= 98


def test_svg_avec_marge_dans_le_viewbox_remplit_quand_meme_le_canvas():
    """Marge 0 : la marge du viewBox ne doit PAS etre recopiee dans le derive.

    Le conteneur porte deja padding:5px ; une marge dans le canvas s'y ajoute.
    """
    result = derived("svg_viewbox_avec_marge")
    flags = result["metrics"]["flags"]
    sq200a = variant(result, "sq200a")
    assert sq200a is not None, flags
    box = ink_box(sq200a)
    assert box[2] >= CANVAS - 12 and box[3] >= CANVAS - 12, (
        "encre %s dans un canvas %d : la marge du viewBox a ete recopiee (flags=%s)"
        % (box, CANVAS, flags)
    )
    assert "trim_degenerate" not in flags, (
        "le cadre d'un rendu vectoriel est choisi par le module : il ne peut pas "
        "servir de preuve que le trim est degenere"
    )
    assert result["metrics"]["fill_pct"] >= 90


def test_svg_sans_viewbox_ni_dimensions_produit_un_derive_utilisable():
    """Un SVG sans dimensions declarees doit quand meme remplir le canvas."""
    result = derived("svg_sans_dimensions")
    flags = result["metrics"]["flags"]
    sq200a = variant(result, "sq200a")
    assert sq200a is not None, flags
    box = ink_box(sq200a)
    assert box[2] >= CANVAS - 12 and box[3] >= CANVAS - 12, (
        "encre %s dans un canvas %d (flags=%s)" % (box, CANVAS, flags)
    )
    assert "trim_degenerate" not in flags


# =============================================================================
# 4. Etape 7 — non-agrandissement raster (AUCUN, jamais)
# =============================================================================

def test_png_96x32_nest_pas_agrandi():
    """Non-agrandissement : flag no_upscale et encre a sa TAILLE NATIVE."""
    result = derived("png_96x32")
    flags = result["metrics"]["flags"]
    assert "no_upscale" in flags, flags

    ink = result["metrics"]["ink_bbox"]
    box = ink_box(variant(result, "sq200a"))
    assert (box[2], box[3]) == (ink[2], ink[3]), (
        "l'encre affichee %s doit rester a la taille du master %s" % (box[:], ink)
    )
    assert box[2] <= 96 and box[3] <= 32


def test_png_900x60_est_reduit_et_non_agrandi():
    """Une source plus grande que la cible est REDUITE : pas de flag no_upscale."""
    result = derived("png_900x60")
    flags = result["metrics"]["flags"]
    assert "no_upscale" not in flags, flags
    box = ink_box(variant(result, "sq200a"))
    assert box[2] == CANVAS, "l'arete longue doit atteindre la cible : %s" % (box,)


def test_png_3000x3000_reduit_et_metrics_dans_le_referentiel_master():
    """Le shrink-on-load ne doit pas fausser master_width/master_height."""
    result = derived("png_3000x3000")
    metrics = result["metrics"]
    assert (metrics["master_width"], metrics["master_height"]) == (3000, 3000)
    assert "no_upscale" not in metrics["flags"]
    assert metrics["ink_bbox"][2] > 2000, metrics["ink_bbox"]


@pytest.mark.parametrize("name,attendu", [
    ("png_900x60", (900, 60)),
    ("png_96x32", (96, 32)),
    ("png_blanc_sur_transparent", (240, 120)),
    ("png_fond_opaque_blanc", (240, 120)),
])
def test_master_width_height_donnent_les_dimensions_du_master(name, attendu):
    metrics = derived(name)["metrics"]
    assert (metrics["master_width"], metrics["master_height"]) == attendu


# =============================================================================
# 5. Etapes 4-5 — boite d'encre et mesures
# =============================================================================

def test_boite_dencre_est_lue_sur_la_bande_alpha_pour_une_encre_blanche():
    """P2 : sur du RGBA, un trim contre blanc recadrerait A VIDE l'encre blanche."""
    metrics = derived("png_blanc_sur_transparent")["metrics"]
    left, top, width, height = metrics["ink_bbox"]
    assert width > 100 and height > 50, "boite d'encre vide ou derisoire : %s" % (metrics["ink_bbox"],)
    assert (left, top) == (20, 10), metrics["ink_bbox"]


def test_fond_opaque_uniforme_est_trime_par_consensus_des_coins():
    """4 coins concordants : le fond est retire, l'encre seule est cadree."""
    for name in ("png_fond_opaque_blanc", "png_fond_opaque_colore"):
        metrics = derived(name)["metrics"]
        assert "baked_background" not in metrics["flags"], name
        assert metrics["ink_bbox"] == [40, 20, 160, 80], (name, metrics["ink_bbox"])


def test_fond_opaque_aux_coins_divergents_pose_baked_background():
    """Coins discordants : on garde le cadre entier plutot que centrer un fond."""
    metrics = derived("png_fond_opaque_bicolore")["metrics"]
    assert "baked_background" in metrics["flags"]
    assert metrics["ink_bbox"] == [0, 0, 240, 120], metrics["ink_bbox"]


def test_png_entierement_transparent_ne_produit_aucun_derive():
    """Aucune encre : ink_too_small, aucune variante, aucune erreur."""
    result = derived("png_tout_transparent")
    assert "ink_too_small" in result["metrics"]["flags"]
    assert result["variants"] == []
    assert result["error"] is None


def test_encre_sous_1_pourcent_pose_ink_too_small():
    """Garde-fou de l'etape 4 : sous 1 % de la surface, aucun derive."""
    result = derived("png_point_20_dans_400")
    assert "ink_too_small" in result["metrics"]["flags"]
    assert result["variants"] == []


def test_trim_retirant_plus_de_95_pourcent_est_refuse():
    """Entre 1 % et 5 % : trim refuse, cadre entier conserve, flag pose."""
    result = derived("png_point_60_dans_400")
    metrics = result["metrics"]
    assert "trim_degenerate" in metrics["flags"]
    assert "ink_too_small" not in metrics["flags"]
    assert metrics["ink_bbox"] == [0, 0, 400, 400], metrics["ink_bbox"]


def test_ratio_x100_reflete_la_boite_dencre():
    for name in ("png_900x60", "png_blanc_sur_transparent", "png_96x32"):
        metrics = derived(name)["metrics"]
        _l, _t, width, height = metrics["ink_bbox"]
        attendu = round(100.0 * max(width, height) / min(width, height))
        assert abs(metrics["ratio_x100"] - attendu) <= 1, (name, metrics)


def test_fill_pct_est_la_part_du_canvas_couverte():
    for name in ("png_96x32", "png_900x60", "png_blanc_sur_transparent"):
        result = derived(name)
        box = ink_box(variant(result, "sq200a"))
        attendu = round(100.0 * box[2] * box[3] / (CANVAS * CANVAS))
        assert abs(result["metrics"]["fill_pct"] - attendu) <= 2, (name, box, result["metrics"])


# =============================================================================
# 6. Etape 6 — verdict de surface
# =============================================================================

def test_png_blanc_sur_transparent_exige_une_surface_sombre():
    """LE CAS DES 205 : encre blanche => dark_required, et une plaque."""
    result = derived("png_blanc_sur_transparent")
    metrics = result["metrics"]
    assert metrics["surface"] == "dark_required", metrics
    assert metrics["is_light"] is True
    assert metrics["ink_on_white"] < 2.0, metrics
    assert metrics["ink_on_black"] >= 2.0, metrics
    assert variant(result, "sq200d") is not None, "plaque attendue pour dark_required"


def test_png_noir_sur_transparent_est_lisible_sur_blanc():
    """Encre sombre => any (lisible sur le fond blanc), jamais de plaque."""
    result = derived("png_noir_sur_transparent")
    metrics = result["metrics"]
    assert metrics["surface"] == "any", metrics
    assert variant(result, "sq200d") is None


def test_png_noir_pur_ne_recoit_jamais_de_plaque():
    """Cas limite #000000 : ink_on_black vaut 0 par construction.

    Le verdict basculle alors en light_required (invisible sur noir), ce qui est
    exact. L'invariant qui compte pour le consommateur reste : jamais de plaque
    sombre sous une encre noire.
    """
    result = derived("png_noir_pur_sur_transparent")
    metrics = result["metrics"]
    assert metrics["surface"] != "dark_required", metrics
    assert variant(result, "sq200d") is None


def test_jpg_opaque_sort_en_any_et_jamais_de_plaque():
    """Un opaque porte deja son fond : any, et aucune plaque."""
    for name in ("jpeg_opaque", "jpeg_cmyk", "png_fond_opaque_blanc",
                 "png_fond_opaque_colore", "png_palette", "png_gris_1_bande"):
        result = derived(name)
        assert result["metrics"]["surface"] == "any", (name, result["metrics"])
        assert result["metrics"]["alpha_ratio"] < 10.0, (name, result["metrics"])
        assert variant(result, "sq200d") is None, name


def test_encre_tenue_sur_blanc_pose_pale():
    """Entre 2 % et 8 % d'encre visible sur blanc : flag pale."""
    metrics = derived("png_disque_blanc_contour_sombre")["metrics"]
    assert 2.0 <= metrics["ink_on_white"] < 8.0, metrics
    assert "pale" in metrics["flags"], metrics


def test_verdict_est_toujours_une_des_quatre_valeurs():
    autorises = {"any", "dark_required", "light_required", "unknown"}
    for name in CASES:
        assert derived(name)["metrics"]["surface"] in autorises, name


# =============================================================================
# 7. Etape 8 — variante sur plaque
# =============================================================================

@pytest.mark.parametrize("name", sorted(CASES))
def test_sq200d_seulement_si_dark_required(name):
    """La plaque n'existe QUE pour dark_required."""
    result = derived(name)
    if variant(result, "sq200d") is not None:
        assert result["metrics"]["surface"] == "dark_required", (name, result["metrics"])


def test_gif_1bit_ne_recoit_jamais_de_plaque():
    """Transparence 1 bit : les escaliers viennent de la matte, pas du fond."""
    result = derived("gif_transparence_1bit")
    metrics = result["metrics"]
    assert metrics["surface"] == "dark_required", metrics
    assert "gif_1bit" in metrics["flags"], metrics
    assert variant(result, "sq200d") is None, "aucune plaque sous un GIF 1 bit"
    assert variant(result, "sq200a") is not None


def test_matte_saturee_refuse_la_plaque():
    """Un bord qui SE SATURE trahit un ancien fond colore : pas de plaque."""
    result = derived("png_matte_saturee")
    metrics = result["metrics"]
    assert metrics["surface"] == "dark_required", metrics
    assert "matte_suspect" in metrics["flags"], metrics
    assert variant(result, "sq200d") is None


def test_matte_neutre_autorise_la_plaque():
    """Un bord qui s'assombrit est anodin sur un neutre sombre : plaque produite."""
    result = derived("png_matte_neutre")
    metrics = result["metrics"]
    assert metrics["surface"] == "dark_required", metrics
    assert "matte_suspect" not in metrics["flags"], metrics
    assert variant(result, "sq200d") is not None


def test_plaque_est_opaque_a_coins_arrondis_et_dans_le_canvas():
    """La plaque epouse l'encre + une marge, ses coins sont arrondis dans l'alpha."""
    plaque = variant(derived("png_blanc_sur_transparent"), "sq200d")
    img = as_pil(plaque)
    assert img.size == (CANVAS, CANVAS)

    # Les coins du CANVAS restent transparents (la plaque ne remplit pas 200x200).
    for point in ((0, 0), (CANVAS - 1, 0), (0, CANVAS - 1), (CANVAS - 1, CANVAS - 1)):
        assert img.getpixel(point)[3] == 0, "coin de canvas opaque en %s" % (point,)

    box = img.split()[3].getbbox()
    assert box is not None
    x0, y0, x1, y1 = box
    # Coin de la PLAQUE : arrondi => transparent, alors que le milieu du bord
    # est opaque.
    assert img.getpixel((x0, y0))[3] == 0, "coin de plaque non arrondi"
    assert img.getpixel(((x0 + x1) // 2, y0))[3] == 255, "bord haut de plaque non opaque"


def test_plaque_utilise_la_couleur_demandee():
    """plate_color est respectee, et le defaut est l'anthracite de la carte."""
    defaut = variant(derived("png_blanc_sur_transparent"), "sq200d")
    box = as_pil(defaut).split()[3].getbbox()
    sonde = (box[0] + 3, (box[1] + box[3]) // 2)
    assert as_pil(defaut).getpixel(sonde) == (31, 41, 51, 255)

    custom = variant(
        derived("png_blanc_sur_transparent", content_hash=HASH_A, plate_color=(10, 20, 30)),
        "sq200d",
    )
    assert as_pil(custom).getpixel(sonde) == (10, 20, 30, 255)


def test_plate_color_invalide_ne_fait_pas_echouer_le_derive():
    """Contrat dur : le worker ne doit jamais echouer a cause du derive."""
    result = derive_logo(CASES["png_blanc_sur_transparent"], KEY, HASH_A, plate_color="nawak")
    assert result["error"] is None
    assert variant(result, "sq200d") is not None


# =============================================================================
# 8. Flags — listes fermees
# =============================================================================

def test_flags_est_la_liste_fermee_de_la_spec():
    """Enumeration explicite : un flag ajoute plus tard doit casser ce test.

    Quatre flags ont ete ajoutes le 31/08, tous en reponse a un defaut mesure :
      - svg_too_complex : refus de rasteriser un SVG lourd (SIGABRT du processus,
        donc poison pill RabbitMQ) ;
      - vector_upscaled : le crop d'un rendu vectoriel a ete agrandi en RASTER,
        vignette molle qui ne portait aucun signal ;
      - plate_failed    : l'etape 8 a echoue, sq200a est conservee ;
      - no_usable_variant : dark_required sans plaque, donc rien de visible sur
        le cadre blanc de la carte.
    """
    assert FLAGS == frozenset({
        "svg_text",
        "svg_too_complex",
        "svg_wraps_raster",
        "gif_1bit",
        "baked_background",
        "no_upscale",
        "vector_upscaled",
        "low_res",
        "pale",
        "matte_suspect",
        "plate_failed",
        "trim_degenerate",
        "ink_too_small",
        "no_usable_variant",
        "derivation_failed",
        "elongated",
    })
    assert len(FLAGS) == 16
    assert frozenset(FLAG_ORDER) == FLAGS, "FLAG_ORDER doit enumerer exactement FLAGS"
    assert len(FLAG_ORDER) == len(FLAGS), "FLAG_ORDER sans doublon"


def test_blocking_flags_est_enumere_explicitement():
    """Les flags bloquants sont un sous-ensemble FERME et nomme de FLAGS.

    Le consommateur ne doit pas chercher une sous-chaine dans une colonne CSV :
    une telle recherche laisserait un flag ajoute plus tard ne rien bloquer.

    Deux ajouts du 31/08, tous « variante produite mais pas affichable » — le
    meme motif qu'``elongated`` :
      - svg_too_complex    : aucune variante (refus, pas defaillance) ;
      - no_usable_variant  : dark_required sans plaque, invisible sur #FFFFFF.

    Et un RETRAIT : ``trim_degenerate`` bloquait sur le rapport encre/cadre de la
    SOURCE, donc sur la taille du CADRE et non sur la lisibilite du resultat (la
    MEME encre de 300 px sortait a fill_pct = 100 sans flag dans un cadre de
    320 px et etait refusee dans un cadre de 1350 px). Il reste un signal
    d'AUDIT ; ce qui interdit la publication est desormais une mesure de l'encre
    REELLEMENT AFFICHEE, qui pose ``ink_too_small``.
    """
    assert BLOCKING_FLAGS == frozenset({
        "svg_text",
        "svg_too_complex",
        "ink_too_small",
        "no_usable_variant",
        "elongated",
        "derivation_failed",
    })
    assert BLOCKING_FLAGS <= FLAGS
    assert isinstance(BLOCKING_FLAGS, frozenset), "immutabilite attendue"
    assert "trim_degenerate" not in BLOCKING_FLAGS, (
        "trim_degenerate decrit le CADRE de la source, pas la lisibilite du derive"
    )


def test_les_trois_flags_sans_variante_sont_bloquants():
    """Coherence : si aucune variante n'est produite, la publication est bloquee."""
    for name in SANS_VARIANTE:
        flags = set(derived(name)["metrics"]["flags"])
        assert flags & BLOCKING_FLAGS, (name, flags)


def test_low_res_sous_96_px_darete_courte():
    """96 px = boite utile 58x32 CSS en ecran 3x (174x96)."""
    assert "low_res" not in derived("png_carre_96")["metrics"]["flags"]
    assert "low_res" in derived("png_carre_95")["metrics"]["flags"]


def test_elongated_au_dela_dun_ratio_6():
    assert "elongated" in derived("png_bar_700x100")["metrics"]["flags"]
    assert "elongated" not in derived("png_bar_500x100")["metrics"]["flags"]
    assert derived("png_bar_700x100")["metrics"]["ratio_x100"] == 700


# =============================================================================
# 9. Etape 9 — nommage adresse par contenu
# =============================================================================

def test_filename_suit_le_gabarit_de_la_spec():
    """logo-{slug}--{h12}-{recipe}-{variant}.png, h12 = sha256(hash|recipe)[:12]."""
    h12 = hashlib.sha256(("%s|%s" % (HASH_A, RECIPE)).encode("utf-8")).hexdigest()[:12]
    nom = variant(derived("png_blanc_sur_transparent"), "sq200a")["filename"]
    assert nom == "logo-acme_fr--%s-%s-sq200a.png" % (h12, RECIPE)

    plaque = variant(derived("png_blanc_sur_transparent"), "sq200d")["filename"]
    assert plaque == "logo-acme_fr--%s-%s-sq200d.png" % (h12, RECIPE)


def test_filename_est_deterministe_a_content_hash_egal():
    a = derive_logo(CASES["png_96x32"], KEY, HASH_A)["variants"][0]["filename"]
    b = derive_logo(CASES["png_96x32"], KEY, HASH_A)["variants"][0]["filename"]
    assert a == b


def test_filename_change_avec_le_content_hash():
    """Immutabilite CDN : une URL de derive ne doit jamais servir d'autres octets."""
    a = derive_logo(CASES["png_96x32"], KEY, HASH_A)["variants"][0]["filename"]
    b = derive_logo(CASES["png_96x32"], KEY, HASH_B)["variants"][0]["filename"]
    assert a != b


def test_slug_reprend_la_regle_reelle_de_build_logo_filename():
    """Le derive et le master doivent s'accorder sur le slug, sinon ils divergent."""
    from core.downloader import _build_logo_filename

    for key in ("acme.fr", "Logo-Principal.SVG (v2)/etc", "ACME_FR-1", "a b.c"):
        nom = derive_logo(CASES["png_96x32"], key, HASH_A)["variants"][0]["filename"]
        assert nom.startswith(_build_logo_filename(key) + "--"), (key, nom)


# =============================================================================
# 10. Robustesse
# =============================================================================

def test_contenu_invalide_ne_leve_pas_et_remplit_error():
    result = derived("pas_une_image")
    assert result["error"], "error attendu"
    assert isinstance(result["error"], str)
    assert result["variants"] == []
    assert "derivation_failed" in result["metrics"]["flags"]


def test_contenu_vide_ne_leve_pas_et_remplit_error():
    result = derived("vide")
    assert result["error"]
    assert result["variants"] == []
    assert "derivation_failed" in result["metrics"]["flags"]


def test_content_hash_absent_est_une_erreur_dure():
    """Tout le nommage adresse par contenu repose dessus : pas de rattrapage."""
    result = derive_logo(CASES["png_96x32"], KEY, "")
    assert result["error"]
    assert result["variants"] == []


def test_module_nimporte_que_la_stdlib_et_pyvips():
    """Le module est greffe sous deux noms de paquet : aucun import intra-paquet.

    On n'inspecte que les instructions d'import reelles : les docstrings citent
    legitimement ``image_download_service.core.logo_derive``.
    """
    import core.logo_derive as module

    with open(module.__file__, "r", encoding="utf-8") as handle:
        lignes = [ligne.strip() for ligne in handle]

    imports = [
        ligne for ligne in lignes
        if ligne.startswith("import ") or ligne.startswith("from ")
    ]
    autorises = {"hashlib", "logging", "math", "re", "pyvips"}
    for ligne in imports:
        racine = ligne.split()[1].split(".")[0]
        assert racine in autorises, "import non autorise : %r" % ligne
    assert "import pyvips" in imports


# =============================================================================
# 11. Etape 3 — normalisation sRGB / 4 bandes
# =============================================================================

@pytest.mark.parametrize("name", [
    "jpeg_cmyk", "png_gris_1_bande", "png_la_2_bandes", "png_palette",
    "gif_transparence_1bit",
])
def test_toutes_les_profondeurs_sortent_en_rgba(name):
    """1, 2, 3, 4 bandes et CMJN convergent vers du sRGB 4 bandes."""
    item = variant(derived(name), "sq200a")
    assert item is not None, name
    vips_img = pyvips.Image.new_from_buffer(item["bytes"], "")
    assert vips_img.bands == 4 and vips_img.interpretation == "srgb"


def test_jpeg_cmyk_nest_pas_inverti():
    """Un CMJN mal converti ressortirait en negatif : l'encre doit rester sombre."""
    result = derived("jpeg_cmyk")
    img = as_pil(variant(result, "sq200a"))
    centre = img.getpixel((CANVAS // 2, CANVAS // 2))
    assert centre[3] == 255, centre
    luma = 0.2126 * centre[0] + 0.7152 * centre[1] + 0.0722 * centre[2]
    assert luma < 100, "encre CMJN noire ressortie claire : %s" % (centre,)


# =============================================================================
# 12. Non-regression des 4 defauts BLOQUANTS corriges le 31/08
# =============================================================================

def test_b1_encre_a_pas_fin_nest_pas_tronquee_par_find_trim():
    """P12 : la boite d'encre doit couvrir la VRAIE bande d'encre, pas celle que
    ``find_trim`` sous-echantillonne.

    AVANT : ink_bbox = [30, 290, 341, 91], flags = ['low_res'], sq200a publie
    avec les deux tiers du logo absents et AUCUN flag pour le dire.
    """
    result = derived("png_lockup_hachure")
    left, top, width, height = result["metrics"]["ink_bbox"]
    # La vraie encre va de y=20 a y=380 inclus, sur x=30..370.
    assert top <= 21, "haut de boite %d : la marque hachuree a ete perdue" % top
    assert top + height >= 380, (
        "bas de boite %d : la boite ne couvre pas la signature" % (top + height)
    )
    assert height >= 355, "hauteur %d au lieu de ~361" % height
    assert 29 <= left <= 31 and width >= 335, (left, width)
    assert result["variants"], "un derive est attendu"


def test_b1_motif_code_barres_nest_plus_ecarte_en_ink_too_small():
    """P12, deuxieme forme : ``find_trim`` rendait (0, 0, 1, 80) sur 33 % d'encre.

    AVANT : variants = [], flags = ['ink_too_small'] (BLOQUANT) — le logo etait
    ecarte de la publication.
    """
    result = derived("png_code_barres")
    metrics = result["metrics"]
    assert "ink_too_small" not in metrics["flags"], metrics
    assert result["variants"], metrics
    assert metrics["ink_bbox"][2] >= 230 and metrics["ink_bbox"][3] == 80, metrics["ink_bbox"]


def test_b1_find_trim_ne_leve_plus_sous_trois_px_darete():
    """P13 : ``find_trim`` applique un median 3x3 et LEVE sous 3 px d'arete.

    AVANT : error = 'unable to call find_trim\\n  rank: window too large\\n',
    flags = ['derivation_failed'] — un message libvips cryptique stocke en base
    la ou ``ink_too_small`` (error=None) est la reponse honnete.
    """
    for width, height in ((1, 1), (2, 2), (1, 200), (200, 1), (200, 2), (2, 200)):
        octets = _png(Image.new("RGBA", (width, height), (0, 0, 0, 255)))
        result = derive_logo(octets, KEY, HASH_A)
        assert result["error"] is None, (width, height, result["error"])
        assert "derivation_failed" not in result["metrics"]["flags"], (width, height)
        assert "ink_too_small" in result["metrics"]["flags"], (width, height)
        assert result["variants"] == []


def test_b1_boite_exacte_et_find_trim_saccordent_sur_les_cas_nominaux():
    """La contre-mesure ne doit RIEN changer aux cas ou find_trim est juste."""
    attendus = {
        "png_blanc_sur_transparent": [20, 10, 200, 101],
        "png_fond_opaque_blanc": [40, 20, 160, 80],
        "png_fond_opaque_colore": [40, 20, 160, 80],
        "png_96x32": [2, 2, 92, 28],
        "png_900x60": [0, 10, 900, 40],
    }
    for name, attendu in attendus.items():
        assert derived(name)["metrics"]["ink_bbox"] == attendu, name


def test_b2_logotype_blanc_plein_exige_une_surface_sombre():
    """A1 : la regle 1 de l'etape 6 ne s'applique que si l'encre est VISIBLE sur blanc.

    AVANT : surface = 'any' avec ink_on_white = 0,00 et flags = ['low_res',
    'no_upscale'] — le module declarait utilisable sur n'importe quelle surface
    un bloc blanc dont 0 % des pixels sont visibles sur le cadre #FFFFFF de la
    carte, et sans aucun flag. C'est exactement la population que le chantier
    existe pour sauver (205 logos invisibles sur blanc).
    """
    result = derived("png_bloc_blanc_sur_transparent")
    metrics = result["metrics"]
    assert metrics["alpha_ratio"] < 10.0, "la boite d'encre est bien pleine"
    assert metrics["ink_on_white"] < 2.0, metrics
    assert metrics["surface"] == "dark_required", metrics
    assert variant(result, "sq200d") is not None, "la plaque doit etre produite"
    assert "no_usable_variant" not in metrics["flags"], metrics


def test_b2_les_opaques_legitimes_restent_en_any():
    """Non-regression de A1 sur les 6 cas legitimement « any » du depot."""
    for name in ("jpeg_opaque", "jpeg_cmyk", "png_fond_opaque_blanc",
                 "png_fond_opaque_colore", "png_palette", "png_gris_1_bande"):
        metrics = derived(name)["metrics"]
        assert metrics["surface"] == "any", (name, metrics)
        assert metrics["ink_on_white"] >= 2.0, (
            "%s : la regle 1 ne doit s'appliquer que sur de l'encre visible" % name
        )


def test_b3_svg_trop_lourd_est_refuse_sans_defaillance():
    """P14 : au-dela du plafond de contenu, REFUS et non rasterisation.

    AVANT : aucune borne. 6,7 Mo -> +462 Mo RSS ; sous RLIMIT_AS 600 Mo, librsvg
    ABORTE le processus (SIGABRT, returncode 134), donc le message RabbitMQ n'est
    jamais acquitte et tue la replica suivante : poison pill sur toute la file.
    """
    result = derived("svg_trop_lourd")
    metrics = result["metrics"]
    assert len(CASES["svg_trop_lourd"]) > MAX_SVG_CONTENT_BYTES
    assert result["variants"] == []
    assert "svg_too_complex" in metrics["flags"], metrics
    assert result["error"] is None, "un refus n'est pas une defaillance"
    assert "svg_too_complex" in BLOCKING_FLAGS


def test_b3_svg_sous_le_plafond_reste_derive():
    """Le plafond ne doit pas refuser les SVG normaux."""
    for name in ("svg_32x32", "svg_viewbox_avec_marge", "svg_prolog_xml"):
        result = derived(name)
        assert "svg_too_complex" not in result["metrics"]["flags"], name
        assert result["variants"], name


def test_b3_deuxieme_passe_svg_est_evitee_sur_un_contenu_lourd(monkeypatch):
    """P14 : la 2e passe reparse tout le DOM et double le pic memoire.

    Les deux passes sont comptees dans le meme plafond : au-dela de la moitie,
    la 1re passe est conservee. On compte les rasterisations reelles.
    """
    import pyvips as _pyvips

    appels = []
    original = _pyvips.Image.thumbnail_buffer

    def _compte(content, target, **kwargs):
        appels.append(target)
        return original(content, target, **kwargs)

    monkeypatch.setattr(_pyvips.Image, "thumbnail_buffer", staticmethod(_compte))

    # Temoin : un SVG leger a marge dans le viewBox merite bien 2 passes.
    appels[:] = []
    derive_logo(CASES["svg_viewbox_avec_marge"], KEY, HASH_A)
    assert len(appels) == 2, appels

    # Meme geometrie, contenu gonfle au-dela de la moitie du plafond.
    remplissage = '<rect x="0" y="0" width="1" height="1" fill="none"/>'
    nb = (MAX_SVG_CONTENT_BYTES // 2) // len(remplissage) + 10
    lourd = _svg('<circle cx="100" cy="100" r="20" fill="#101820"/>' + remplissage * nb,
                 'width="200" height="200" viewBox="0 0 200 200"')
    assert MAX_SVG_CONTENT_BYTES // 2 < len(lourd) <= MAX_SVG_CONTENT_BYTES
    appels[:] = []
    result = derive_logo(lourd, KEY, HASH_A)
    assert len(appels) == 1, "2e passe attendue evitee, appels=%s" % (appels,)
    assert result["variants"], result["metrics"]


def test_b4_fill_pct_reflete_lencre_reellement_visible():
    """B4 : ``fill_pct`` se lisait sur les DIMENSIONS de l'image adaptee.

    AVANT : cadre 2000 / encre 300 -> fill_pct = 100 alors que l'encre visible
    dans le PNG publie mesure 36x36 px sur 200x200, soit 8,7 px CSS dans la
    boite 58x32 de la carte.
    """
    result = derived("png_encre_blanche_dans_grand_cadre")
    metrics = result["metrics"]
    assert "trim_degenerate" in metrics["flags"], metrics
    box = ink_box(variant(result, "sq200a"))
    attendu = round(100.0 * box[2] * box[3] / (CANVAS * CANVAS))
    assert abs(metrics["fill_pct"] - attendu) <= 2, (box, metrics)
    assert metrics["fill_pct"] <= 10, (
        "fill_pct = %s pour une encre de %sx%s px" % (metrics["fill_pct"], box[2], box[3])
    )


def test_b4_verdict_porte_sur_lencre_meme_quand_le_trim_est_refuse():
    """B4 : l'etape 5 mesurait sur un cadre a 98 % transparent, donc sur le FOND.

    AVANT : encre BLANCHE de 300 px dans 2000 -> surface = 'dark_required' par
    chance a cette taille, mais 'unknown' des 4000 px de cadre ; et une encre
    SOMBRE du meme cadre recevait un flag 'pale' faux (ink_on_white = 2,25 %
    mesure sur le cadre au lieu de 100 % sur l'encre).
    """
    blanc = derived("png_encre_blanche_dans_grand_cadre")["metrics"]
    assert blanc["surface"] == "dark_required", blanc
    assert blanc["ink_on_white"] < 2.0 and blanc["ink_on_black"] > 50.0, blanc

    # Encre SOMBRE, meme geometrie : parfaitement lisible sur blanc.
    img = Image.new("RGBA", (2000, 2000), (0, 0, 0, 0))
    ImageDraw.Draw(img).rectangle([850, 850, 1149, 1149], fill=(20, 20, 20, 255))
    metrics = derive_logo(_png(img), KEY, HASH_A)["metrics"]
    assert "trim_degenerate" in metrics["flags"], metrics
    assert metrics["ink_on_white"] > 50.0, metrics
    assert "pale" not in metrics["flags"], metrics

    # Cadre encore plus grand : le verdict ne doit pas se diluer.
    img = Image.new("RGBA", (4000, 4000), (0, 0, 0, 0))
    ImageDraw.Draw(img).rectangle([1750, 1750, 2249, 2249], fill=(255, 255, 255, 255))
    metrics = derive_logo(_png(img), KEY, HASH_A)["metrics"]
    assert metrics["surface"] == "dark_required", metrics


def test_b4_trim_degenerate_est_un_signal_daudit_non_bloquant():
    """P5 : le flag reste pose, mais il n'interdit plus la publication.

    AVANT : ``trim_degenerate`` etait BLOQUANT et se declenchait sur le rapport
    encre/cadre de la SOURCE. La MEME encre de 300 px sortait a fill_pct = 100
    sans aucun flag dans un cadre de 320 px, et etait REFUSEE des que le cadre
    depassait 1341 px (mesures de l'encre publiee : cadre 1350 -> 46x46 px,
    1600 -> 38, 2000 -> 32, 3000 -> 22, 4000 -> 16, toutes bloquees). Le blocage
    portait donc sur la taille du cadre, pas sur la lisibilite du resultat.
    """
    for name in ("png_encre_blanche_dans_grand_cadre", "png_point_60_dans_400"):
        result = derived(name)
        flags = set(result["metrics"]["flags"])
        assert "trim_degenerate" in flags, name          # le signal d'audit reste
        assert not flags & BLOCKING_FLAGS, (name, sorted(flags))
        assert result["variants"], name


# =============================================================================
# 13. Non-regression des defauts IMPORTANTS corriges le 31/08
# =============================================================================

def test_profil_icc_non_srgb_est_reellement_converti():
    """P8 : ``colourspace`` ne fait AUCUNE transformation ICC.

    AVANT : les pixels sortaient inchanges et le profil qui seul permettait de
    les interpreter etait jete -> le PNG etait declare implicitement sRGB avec
    des valeurs qui ne l'etaient pas (mesure : (200, 30, 40) en AdobeRGB publie
    tel quel au lieu de (233, 24, 36), 33 niveaux d'ecart sur le rouge).
    """
    import os

    profils = [
        "/usr/share/color/icc/ghostscript/a98.icc",
        "/usr/share/color/icc/colord/AdobeRGB1998.icc",
    ]
    chemin = next((p for p in profils if os.path.exists(p)), None)
    if chemin is None:
        pytest.skip("aucun profil ICC AdobeRGB sur la machine")

    img = Image.new("RGB", (300, 200), (255, 255, 255))
    ImageDraw.Draw(img).rectangle([60, 40, 239, 159], fill=(200, 30, 40))
    base = pyvips.Image.new_from_buffer(_png(img), "").copy()
    with open(chemin, "rb") as handle:
        base.set_type(pyvips.GValue.blob_type, "icc-profile-data", handle.read())
    octets = base.pngsave_buffer(compression=1)

    attendu = pyvips.Image.new_from_buffer(octets, "").icc_transform("srgb", embedded=True)
    attendu_rgb = tuple(int(round(v)) for v in attendu(150, 100)[:3])
    assert attendu_rgb != (200, 30, 40), "temoin invalide : le profil ne change rien"

    result = derive_logo(octets, KEY, HASH_A)
    assert result["variants"], result["metrics"]
    publie = as_pil(result["variants"][0])
    assert "icc_profile" not in publie.info, "le profil doit etre retire APRES conversion"
    centre = publie.getpixel((CANVAS // 2, CANVAS // 2))[:3]
    for attendue, obtenue in zip(attendu_rgb, centre):
        assert abs(attendue - obtenue) <= 3, (attendu_rgb, centre)


def test_svg_prefixe_dun_doctype_reste_trie_par_svg_text():
    """P15 : le ROUTAGE ne doit pas dependre des 10 octets du NOMMAGE.

    AVANT : ce fichier partait en branche raster, donc sans le garde svg_text ET
    avec ``size="down"``. Il publiait une vignette de texte rasterise SANS
    police, flags = ['low_res', 'no_upscale'], error = None.
    """
    result = derived("svg_doctype_avec_texte")
    assert result["variants"] == []
    assert "svg_text" in result["metrics"]["flags"], result["metrics"]
    assert result["error"] is None
    # Temoin : le MEME contenu sans DOCTYPE donnait deja le bon verdict.
    sans = CASES["svg_doctype_avec_texte"]
    sans = sans[sans.index(b"<svg"):]
    assert "svg_text" in derive_logo(sans, KEY, HASH_A)["metrics"]["flags"]


def test_svg_prefixe_dun_commentaire_est_rasterise_a_la_bonne_taille():
    """P15, 2e forme : un SVG declare 32x32 sortait a 32x32 au lieu de 200x200."""
    result = derived("svg_commentaire_generateur")
    assert result["variants"], result["metrics"]
    box = ink_box(variant(result, "sq200a"))
    assert box[2] >= CANVAS - 4 and box[3] >= CANVAS - 4, (
        "encre %s : le SVG a ete traite en raster (flags=%s)"
        % (box, result["metrics"]["flags"])
    )
    assert "no_upscale" not in result["metrics"]["flags"], result["metrics"]


def test_echec_de_letape_8_ne_detruit_pas_sq200a(monkeypatch):
    """L'etape 8 est OPTIONNELLE : son echec ne doit pas couter sq200a.

    AVANT : toute exception de l'etape 8 tombait dans l'except global, qui rend
    ``_result([], error=...)`` — la variante OBLIGATOIRE, DEJA encodee en octets,
    etait jetee, et le worker comptait en echec un logo parfaitement derivable.
    """
    import core.logo_derive as module

    def _explose(*args, **kwargs):
        raise pyvips.Error("plaque en panne")

    monkeypatch.setattr(module, "_plate_image", _explose)
    result = derive_logo(CASES["png_blanc_sur_transparent"], KEY, HASH_A)

    assert [item["variant"] for item in result["variants"]] == ["sq200a"]
    assert result["error"] is None, "l'echec accessoire n'est pas une defaillance globale"
    flags = result["metrics"]["flags"]
    assert "plate_failed" in flags, flags
    assert "derivation_failed" not in flags, flags
    assert "no_usable_variant" in flags, flags


def test_dark_required_sans_plaque_pose_un_flag_bloquant():
    """A3 : sans plaque, la seule variante est invisible sur le cadre #FFFFFF.

    AVANT : gif_1bit et matte_suspect laissaient BLOCKING_FLAGS vide, donc un
    consommateur qui n'applique que BLOCKING_FLAGS publiait une vignette vide.
    """
    assert "no_usable_variant" in BLOCKING_FLAGS
    for name in ("gif_transparence_1bit", "png_matte_saturee"):
        result = derived(name)
        metrics = result["metrics"]
        assert metrics["surface"] == "dark_required", (name, metrics)
        assert variant(result, "sq200d") is None, name
        assert "no_usable_variant" in metrics["flags"], (name, metrics)
        assert set(metrics["flags"]) & BLOCKING_FLAGS, (name, metrics)

    # Symetrie : quand la plaque EST produite, le flag ne doit pas tomber.
    plaque = derived("png_matte_neutre")
    assert variant(plaque, "sq200d") is not None
    assert "no_usable_variant" not in plaque["metrics"]["flags"]


def test_matte_est_mesuree_meme_sur_un_gif(monkeypatch):
    """Ordre de la spec : mesurer le matting D'ABORD, trancher ensuite.

    AVANT : gif_1bit court-circuitait ``_matte_is_suspect``, donc matte_suspect
    n'etait JAMAIS enregistre sur la population GIF — impossible de compter les
    GIF qui cumulent les deux defauts.
    """
    import core.logo_derive as module

    appels = []
    original = module._matte_is_suspect

    def _espion(crop):
        appels.append(True)
        return original(crop)

    monkeypatch.setattr(module, "_matte_is_suspect", _espion)
    derive_logo(CASES["gif_transparence_1bit"], KEY, HASH_A)
    assert appels, "le matting doit etre mesure meme quand gif_1bit tranche deja"


def test_svg_a_marque_petite_dans_un_grand_artboard_produit_un_derive():
    """``ink_too_small`` etait CIRCULAIRE sur la branche vecteur (P11).

    AVANT : artboard 800 / marque 60 -> variants = [], flags = ['ink_too_small'],
    flag BLOQUANT. Le rapport encre/cadre d'un rendu vectoriel est invariant
    d'echelle : aucun supersampling ne pouvait le rattraper.
    """
    result = derived("svg_grand_artboard_petite_marque")
    metrics = result["metrics"]
    assert "ink_too_small" not in metrics["flags"], metrics
    assert result["variants"], metrics
    box = ink_box(variant(result, "sq200a"))
    assert box[2] >= CANVAS - 6 and box[3] >= CANVAS - 6, (box, metrics)
    # La boite VIDE reste refusee : le garde-fou n'a pas ete supprime, seulement
    # rendu non circulaire.
    vide = derive_logo(_svg('', 'width="200" height="200" viewBox="0 0 200 200"'),
                       KEY, HASH_A)
    assert vide["variants"] == []
    assert "ink_too_small" in vide["metrics"]["flags"], vide["metrics"]


def test_agrandissement_raster_du_vecteur_est_signale():
    """``no_upscale`` est structurellement impossible sur la branche vecteur.

    AVANT : le crop d'un rendu vectoriel etait agrandi en Lanczos jusqu'a 200 px
    sans aucun flag (metrics['flags'] == []), donc une vignette FLOUE sans
    signal d'audit.
    """
    assert "vector_upscaled" in FLAGS
    # librsvg refuse d'echelonner un SVG sans dimensions : agrandissement force.
    flags = derived("svg_sans_dimensions")["metrics"]["flags"]
    assert "vector_upscaled" in flags, flags
    # Un SVG sans marge est rasterise pile a la cible : aucun agrandissement.
    assert "vector_upscaled" not in derived("svg_32x32")["metrics"]["flags"]


def test_referentiel_svg_est_celui_du_rendu_de_reference():
    """Deux SVG comparables doivent rendre des metriques comparables.

    AVANT : ``work_scale`` restait a 1,0 sur la branche vecteur, donc
    master_width/ink_bbox etaient exprimes dans le referentiel du rendu RETENU
    (200 a 800 px selon le supersampling) : le meme dessin sortait 800x800 sans
    low_res ou 200x200 avec low_res selon que librsvg acceptait de l'echelonner.
    """
    marge = derived("svg_viewbox_avec_marge")["metrics"]
    sans_dim = derived("svg_sans_dimensions")["metrics"]
    for metrics in (marge, sans_dim):
        assert (metrics["master_width"], metrics["master_height"]) == (CANVAS, CANVAS), metrics
        assert metrics["ink_bbox"][2] <= CANVAS and metrics["ink_bbox"][3] <= CANVAS, metrics


def test_error_est_borne_mono_ligne_et_deterministe():
    """A5 : ``error`` part dans une colonne SQL et sert a REGROUPER les echecs.

    AVANT : non borne (201 caracteres mesures), MULTI-LIGNE, et non deterministe
    — libvips y recopie le chemin d'un temporaire ImageMagick, donc trois derives
    des MEMES octets rendaient trois textes differents.
    """
    from core.logo_derive import MAX_ERROR_LEN

    octets = b"<?xml version='1.0'?><notsvg>ceci n'est pas une image</notsvg>"
    messages = [derive_logo(octets, KEY, HASH_A)["error"] for _ in range(3)]
    assert all(messages), messages
    assert len(set(messages)) == 1, "error non deterministe : %s" % (messages,)
    for message in messages:
        assert len(message) <= MAX_ERROR_LEN, len(message)
        assert "\n" not in message and "\r" not in message and "\t" not in message
        assert "/tmp/" not in message, message

    # Message tres long : borne appliquee.
    long_result = derive_logo(CASES["png_96x32"], KEY, "z" * 5000)
    assert len(long_result["error"]) <= MAX_ERROR_LEN


def test_filename_reste_borne_avec_une_cle_hostile():
    """A5 : ``filename`` doit tenir dans NAME_MAX et dans un VARCHAR(255).

    AVANT : une cle de 400 caracteres donnait un nom de 440 caracteres.
    """
    result = derive_logo(CASES["png_96x32"], "k" * 400, HASH_A)
    assert result["variants"]
    for item in result["variants"]:
        assert len(item["filename"]) <= 200, len(item["filename"])
        assert item["filename"].endswith("-%s-%s.png" % (RECIPE, item["variant"]))


def test_source_hash_hors_forme_est_une_erreur_dure():
    """A5 : toute l'immutabilite CDN de 30 jours repose sur la forme du hash.

    AVANT : 5000 caracteres ou un int traversaient jusqu'a metrics, et donc
    jusqu'a l'INSERT.
    """
    for mauvais in ("z" * 5000, 12345, "abc", "A" * 64, HASH_A + "0"):
        result = derive_logo(CASES["png_96x32"], KEY, mauvais)
        assert result["variants"] == [], mauvais
        assert result["error"], mauvais
        assert result["metrics"]["source_hash"] == "", mauvais
    # Le cas valide n'est pas touche.
    assert derive_logo(CASES["png_96x32"], KEY, HASH_A)["metrics"]["source_hash"] == HASH_A


def test_flags_sont_tries_sur_lordre_de_la_liste_fermee():
    """A5 : l'ordre d'insertion dependait du chemin de code parcouru."""
    rangs = {flag: rang for rang, flag in enumerate(FLAG_ORDER)}
    for name in CASES:
        flags = derived(name)["metrics"]["flags"]
        assert flags == sorted(flags, key=lambda flag: rangs[flag]), (name, flags)


def test_nom_de_recette_ne_porte_aucun_numero_de_version():
    """A2 : la version de libvips entrait dans une URL immutable 30 jours.

    L'image de prod part de ``python:3.11-slim`` + ``libvips-dev`` apt (8.14.x)
    alors que le jeton disait « v8151 » : le nom mentait, et deux versions de
    libvips coexistantes auraient servi des octets DIFFERENTS sous la MEME URL.
    """
    import re as _re

    assert RECIPE == "r1m0"
    assert not _re.search(r"\d+[._]\d+", RECIPE), RECIPE
    assert "v8" not in RECIPE and "815" not in RECIPE and "8.14" not in RECIPE
    nom = variant(derived("png_96x32"), "sq200a")["filename"]
    assert "8151" not in nom and "8.15" not in nom, nom


def test_libvips_version_est_exposee_dans_les_metriques_seulement():
    """La version reste auditable, mais hors du nommage."""
    metrics = derived("png_96x32")["metrics"]
    version = metrics["libvips_version"]
    assert isinstance(version, str) and version, version
    assert version == "%d.%d.%d" % (pyvips.version(0), pyvips.version(1), pyvips.version(2))
    assert version not in variant(derived("png_96x32"), "sq200a")["filename"]


def test_contenu_bytes_like_est_accepte():
    """bytearray et memoryview sont des types bytes-like legitimes.

    AVANT : error = "initializer for ctype 'void *' must be a cdata pointer,
    not bytearray", variants = [], flags = ['derivation_failed'].
    """
    reference = derive_logo(CASES["png_96x32"], KEY, HASH_A)
    for enveloppe in (bytearray, memoryview):
        result = derive_logo(enveloppe(CASES["png_96x32"]), KEY, HASH_A)
        assert result["error"] is None, (enveloppe, result["error"])
        assert len(result["variants"]) == len(reference["variants"])
        assert result["variants"][0]["bytes"] == reference["variants"][0]["bytes"]


def test_png_publie_ne_porte_aucune_metadonnee():
    """P9 : ``pngsave_buffer`` RESYNTHETISE un chunk eXIf apres ``remove()``.

    AVANT : le PNG derive portait encore un eXIf de ~170 octets, relisible en 12
    champs exif-*, alors que la docstring annoncait « metadonnees nettoyees ».
    """
    buffer = io.BytesIO()
    source = Image.new("RGB", (300, 200), (255, 255, 255))
    ImageDraw.Draw(source).ellipse([60, 40, 239, 159], fill=(10, 20, 40))
    source.save(buffer, "JPEG", quality=95, exif=Image.Exif())

    result = derive_logo(buffer.getvalue(), KEY, HASH_A)
    assert result["variants"], result["metrics"]
    for item in result["variants"]:
        assert b"eXIf" not in item["bytes"], "chunk eXIf resynthetise"
        assert b"iCCP" not in item["bytes"], "profil ICC laisse dans le PNG"
        relu = pyvips.Image.new_from_buffer(item["bytes"], "")
        restants = [champ for champ in relu.get_fields() if champ.startswith("exif-")]
        assert restants == [], restants


def test_source_uniforme_opaque_produit_un_derive():
    """Coins concordants ET aucune encre distincte = image UNIFORME.

    AVANT : variants = [], flags = ['ink_too_small'] (BLOQUANT), alors que la
    bonne conclusion est « le fond fait partie du logo ».
    """
    result = derived("png_uniforme_opaque")
    metrics = result["metrics"]
    assert result["variants"], metrics
    assert "ink_too_small" not in metrics["flags"], metrics
    assert "baked_background" in metrics["flags"], metrics
    assert metrics["ink_bbox"] == [0, 0, 300, 300], metrics["ink_bbox"]


def test_cinq_bandes_gardent_la_derniere_comme_alpha():
    """``extract_band(0, n=4)`` supposait l'alpha en position 3.

    AVANT : R=10 G=20 B=30 extra=99 alpha=255 -> [10, 20, 30, 99], soit 61 % de
    transparence inventee et la vraie alpha opaque perdue.
    """
    from core.logo_derive import _normalize

    bandes = [
        pyvips.Image.black(20, 10).new_from_image([valeur])
        for valeur in (10, 20, 30, 99, 255)
    ]
    image = bandes[0].bandjoin(bandes[1:]).copy(interpretation="srgb").cast("uchar")
    assert image.bands == 5
    normalisee = _normalize(image)
    assert normalisee.bands == 4
    assert [int(round(v)) for v in normalisee(0, 0)] == [10, 20, 30, 255]


def test_profondeur_16_bits_est_rescalee_et_non_clippee():
    """Le cas ATTEIGNABLE de la profondeur : un loader rend 'rgb16', pas 'srgb'.

    ``colourspace`` sait alors rescaler. Le cas 'srgb' hors bornes reste une
    limite assumee : mesure faite, ``colourspace`` y clippe EXACTEMENT comme
    ``cast`` (srgb/float [300, 500, 700] -> [255, 255, 255] dans les deux cas),
    donc le correctif propose par la revue est un no-op — il n'y a pas d'echelle
    a deviner pour un 'srgb'. Inatteignable depuis un master reel.
    """
    from core.logo_derive import _normalize

    fond = pyvips.Image.black(20, 10, bands=3).cast("ushort")
    seize = (fond + [50000, 20000, 10000]).cast("ushort").copy(interpretation="rgb16")
    assert seize(0, 0)[:3] == [50000.0, 20000.0, 10000.0], "temoin 16 bits invalide"
    normalisee = _normalize(seize)
    assert normalisee.format == "uchar" and normalisee.bands == 4
    pixel = [int(round(valeur)) for valeur in normalisee(0, 0)]
    assert pixel[0] != 255, "16 bits clippe au lieu d'etre rescale : %s" % (pixel,)
    assert 180 <= pixel[0] <= 210, pixel   # 50000/65535*255 = 194,5
    assert pixel[3] == 255, pixel

    # Et la limite assumee, figee telle qu'elle est mesuree.
    bandes = [
        pyvips.Image.black(20, 10).new_from_image([valeur]).cast("float")
        for valeur in (300.0, 500.0, 700.0)
    ]
    hors_bornes = bandes[0].bandjoin(bandes[1:]).copy(interpretation="srgb")
    assert [int(round(v)) for v in _normalize(hors_bornes)(0, 0)][:3] == [255, 255, 255]
    assert [int(round(v)) for v in hors_bornes.colourspace("srgb")(0, 0)][:3] == [255, 255, 255]


# =============================================================================
# 14. Non-regression des 7 points de la passe du 31/08 (P1 a P7)
#
# Un correctif sans preuve avant/apres ne compte pas : chaque test porte dans son
# docstring la MESURE du defaut, telle qu'elle a ete relevee avant correctif.
# =============================================================================

def _png_encre_dans_cadre(cadre, encre, couleur=(18, 52, 86), hauteur=None):
    """PNG transparent de ``cadre`` px portant un bloc opaque de ``encre`` px.

    Construit en pyvips et non en PIL : un cadre de 4000 px en RGBA cote Python
    couterait 64 Mo de tampon pour une fixture.

    Args:
        cadre: cote du cadre transparent.
        encre: largeur du bloc opaque.
        couleur: couleur du bloc.
        hauteur: hauteur du bloc ; par defaut egale a ``encre`` (bloc carre).
            Sert a fabriquer un logotype FIN, dont l'arete courte est derisoire
            mais la grande arete non (contre-epreuve de P17).
    """
    hauteur = encre if hauteur is None else hauteur
    alpha = pyvips.Image.black(cadre, cadre).cast("uchar")
    alpha = alpha.insert((pyvips.Image.black(encre, hauteur) + 255).cast("uchar"),
                         (cadre - encre) // 2, (cadre - hauteur) // 2)
    rgb = (pyvips.Image.black(cadre, cadre) + list(couleur)).cast("uchar")
    return rgb.bandjoin(alpha).copy(interpretation="srgb").pngsave_buffer(compression=1)


def _png_fond_blanc_encre_rare(epaisseur, cadre=400):
    """Logo OPAQUE portant son PROPRE FOND BLANC cuit, a encre tres rare.

    L'encre touche le bord haut : les 4 coins divergent, donc le trim est refuse
    et la MESURE porte sur le cadre entier. C'est la geometrie exacte qui faisait
    basculer ces logos en ``dark_required``.
    """
    img = Image.new("RGBA", (cadre, cadre), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, cadre - 1, epaisseur - 1], fill=(15, 15, 15, 255))
    draw.rectangle([cadre // 4, cadre // 2, cadre - cadre // 4, cadre // 2 + epaisseur],
                   fill=(15, 15, 15, 255))
    return img


def test_p1_croisement_des_boites_ne_tronque_plus_lencre():
    """P1/P12 : le croisement find_trim/project ne comparait que des AIRES.

    AVANT : bloc de marque plein sur y=0..359 + baseline hachuree 1 px / gap 2 px
    sur y=365..398 dans un 400x400 -> boite exacte (0, 0, 400, 399), boite
    PUBLIEE (0, 0, 400, 360), couverture 90,2 % donc ACCEPTEE parce que le seuil
    valait 90 % d'aire et que la CONTENANCE n'etait jamais verifiee. Dans le
    sq200a publie, l'encre s'arretait a la ligne 189 sur 200 : la baseline avait
    disparu, sans aucun flag, sous une URL immutable 30 jours.
    """
    img = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, 399, 359], fill=(20, 20, 20, 255))          # bloc de marque
    for y in range(365, 400, 3):                                      # baseline hachuree
        draw.line([(0, y), (399, y)], fill=(20, 20, 20, 255), width=1)

    exacte = img.split()[3].getbbox()
    assert exacte == (0, 0, 400, 399), "temoin invalide : %s" % (exacte,)

    result = derive_logo(_png(img), KEY, HASH_A)
    metrics = result["metrics"]
    left, top, width, height = metrics["ink_bbox"]
    assert (left <= exacte[0] and top <= exacte[1]
            and left + width >= exacte[2] and top + height >= exacte[3]), (
        "la boite publiee %s ne CONTIENT pas la boite exacte %s : troncature"
        % (metrics["ink_bbox"], exacte)
    )
    box = ink_box(variant(result, "sq200a"))
    assert box[1] + box[3] >= CANVAS - 1, (
        "l'encre publiee s'arrete a la ligne %d sur %d : la baseline est perdue"
        % (box[1] + box[3], CANVAS)
    )


def test_p1_lunion_ne_perd_jamais_la_boite_de_find_trim():
    """L'union doit CONTENIR les deux boites, pas seulement l'exacte.

    Le median 3x3 de ``find_trim`` peut deborder d'une ligne sur du texte
    antialiase (mesure : couverture 101,2 % de la boite exacte). Prendre l'exacte
    seule perdrait ce debord.
    """
    from core.logo_derive import _crosschecked_box

    mask = (pyvips.Image.black(200, 200)
            .insert((pyvips.Image.black(40, 40) + 255).cast("uchar"), 80, 80)
            .cast("uchar")).copy_memory()
    assert _crosschecked_box((80, 80, 40, 40), mask, 200, 200) == (80, 80, 40, 40)
    # find_trim tronque -> l'union restaure
    assert _crosschecked_box((80, 80, 40, 20), mask, 200, 200) == (80, 80, 40, 40)
    # find_trim deborde -> l'union garde le debord
    assert _crosschecked_box((78, 78, 44, 44), mask, 200, 200) == (78, 78, 44, 44)
    # find_trim vide -> boite exacte
    assert _crosschecked_box((200, 200, 0, 0), mask, 200, 200) == (80, 80, 40, 40)


def test_p2_logo_opaque_a_fond_clair_cuit_reste_utilisable_sur_blanc():
    """P2 : l'amendement de la regle 1 etait TROP LARGE.

    AVANT : PNG 400x400 blanc OPAQUE + filet sombre de 2 / 3 / 4 px ->
    ink_on_white 0,88 / 1,25 / 1,63 % -> ``dark_required``, donc une plaque
    SOMBRE sous un logo a fond BLANC, et ``no_usable_variant`` (BLOQUANT) des que
    la plaque etait refusee. Or un logo opaque n'est jamais invisible : son
    propre fond le porte, et le taux d'encre ne dit rien de sa lisibilite.
    """
    for epaisseur in (2, 3, 4):
        data = _png(_png_fond_blanc_encre_rare(epaisseur))
        result = derive_logo(data, KEY, HASH_A)
        metrics = result["metrics"]
        assert metrics["ink_on_white"] < 2.0, (
            "temoin invalide : %s %% d'encre visible sur blanc" % metrics["ink_on_white"]
        )
        assert metrics["alpha_ratio"] < 10.0, metrics
        assert metrics["surface"] == "any", (epaisseur, metrics)
        assert variant(result, "sq200d") is None, (
            "plaque sombre sous un logo a fond blanc (trait %d px)" % epaisseur
        )
        assert not set(metrics["flags"]) & BLOCKING_FLAGS, (epaisseur, metrics)

    # Et la population du chantier n'est PAS touchee : un logotype BLANC PLEIN
    # sur TRANSPARENT n'a pas de fond, il reste dark_required et recoit sa plaque.
    for name in ("png_blanc_sur_transparent", "png_bloc_blanc_sur_transparent"):
        result = derived(name)
        assert result["metrics"]["surface"] == "dark_required", (name, result["metrics"])
        assert variant(result, "sq200d") is not None, name
        assert result["metrics"]["ink_on_white"] < 2.0, (name, result["metrics"])


def test_p3_gif_sans_transparence_ne_recoit_pas_gif_1bit():
    """P3 : ``gif_1bit`` etait pose au seul vu du LOADER.

    AVANT : un GIF SANS aucune transparence (loader gifload_buffer, bands=3,
    hasalpha() False) recevait quand meme ``gif_1bit`` ; la plaque etait refusee
    et ``no_usable_variant`` (BLOQUANT) tombait. Le MEME visuel etait donc publie
    en PNG et ECARTE en GIF, a pixels identiques : la decision de publication
    dependait du format du conteneur, pas du contenu.
    """
    img = _png_fond_blanc_encre_rare(3)
    buf = io.BytesIO()
    img.convert("P", palette=Image.ADAPTIVE, colors=64).save(buf, "GIF")
    en_gif = buf.getvalue()

    sonde = pyvips.Image.new_from_buffer(en_gif, "")
    assert sonde.get("vips-loader") == "gifload_buffer", "temoin : ce n'est pas un GIF"
    assert not sonde.hasalpha(), "temoin invalide : ce GIF declare de la transparence"

    resultat_gif = derive_logo(en_gif, KEY, HASH_A)
    resultat_png = derive_logo(_png(img), KEY, HASH_A)
    assert "gif_1bit" not in resultat_gif["metrics"]["flags"], resultat_gif["metrics"]
    assert ([item["variant"] for item in resultat_gif["variants"]]
            == [item["variant"] for item in resultat_png["variants"]]), (
        "meme visuel, decision differente selon le conteneur : GIF=%s PNG=%s"
        % (resultat_gif["metrics"]["flags"], resultat_png["metrics"]["flags"])
    )
    assert not set(resultat_gif["metrics"]["flags"]) & BLOCKING_FLAGS, resultat_gif["metrics"]

    # Symetrie : une matte 1 bit REELLE garde son flag, et sa plaque reste refusee.
    reference = derived("gif_transparence_1bit")
    assert "gif_1bit" in reference["metrics"]["flags"], reference["metrics"]
    assert variant(reference, "sq200d") is None


def test_p3_transparence_binaire_est_mesuree_et_non_supposee():
    """Le predicat est « au moins un pixel transparent ET aucun alpha partiel »."""
    from core.logo_derive import _has_binary_transparency

    def _image(valeurs):
        alpha = pyvips.Image.black(len(valeurs), 1).cast("uchar")
        for index, valeur in enumerate(valeurs):
            alpha = alpha.insert(
                (pyvips.Image.black(1, 1) + valeur).cast("uchar"), index, 0)
        rgb = (pyvips.Image.black(len(valeurs), 1) + [255, 255, 255]).cast("uchar")
        return rgb.bandjoin(alpha).copy(interpretation="srgb").copy_memory()

    assert _has_binary_transparency(_image([0, 255, 0, 255]))
    assert not _has_binary_transparency(_image([255, 255, 255]))       # rien de transparent
    assert not _has_binary_transparency(_image([0, 128, 255]))         # alpha intermediaire


def test_p4_svg_a_texte_est_trie_au_dela_de_la_fenetre_de_reniflage():
    """P4 : la detection SVG etait DEPLACEE, pas fermee.

    AVANT : la fenetre valait SVG_SNIFF_BYTES octets et un ``<svg`` au-dela
    repartait en branche RASTER — donc avec ``size="down"`` (P1) ET sans le garde
    ``svg_text``. Frontiere mesuree A L'OCTET : offset 1020 -> branche vecteur,
    offset 1030 -> branche raster, qui publiait une vignette de texte rasterise
    SANS police, error=None, sous URL immutable.
    """
    from core.logo_derive import _looks_like_svg, _route_is_vector

    corps = ('<svg xmlns="http://www.w3.org/2000/svg" width="240" height="120">'
             '<text x="10" y="70" font-family="Helvetica" font-size="48">ACME</text></svg>')
    for bourrage in (1024, 4096, 60000):
        octets = b"<!-- " + b"x" * bourrage + b" -->\n" + corps.encode()
        assert octets.find(b"<svg") > SVG_SNIFF_BYTES, octets.find(b"<svg")
        assert not _looks_like_svg(octets), "temoin : le reniflage d'octets doit echouer"
        assert _route_is_vector(octets), "la sonde vips-loader doit trancher"
        result = derive_logo(octets, KEY, HASH_A)
        assert result["variants"] == [], bourrage
        assert result["metrics"]["flags"] == ["svg_text"], (bourrage, result["metrics"])
        assert result["error"] is None, result["error"]

    # Et la sonde ne detourne AUCUN raster vers la branche vecteur.
    for name in ("png_96x32", "jpeg_opaque", "gif_transparence_1bit", "png_palette"):
        assert "svg_text" not in derived(name)["metrics"]["flags"], name
        assert not _route_is_vector(CASES[name]), name


def test_p5_plancher_porte_sur_lencre_reellement_affichee():
    """P5 : le refus se decidait sur le rapport encre/cadre de la SOURCE.

    AVANT (encre de 300 px, flag bloquant ``trim_degenerate``) : cadre 1350 ->
    46x46 px d'encre publiee, 1600 -> 38, 2000 -> 32, 3000 -> 22, 4000 -> 16,
    TOUTES refusees, alors que la meme encre dans un cadre de 320 px sortait a
    fill_pct = 100 sans aucun flag. Desormais le refus se mesure sur l'encre
    REELLEMENT AFFICHEE dans le canvas de 200 px.
    """
    # Tant que l'encre AFFICHEE reste distinguable, la vignette est publiee et
    # ``trim_degenerate`` n'est plus qu'un signal d'audit : cadre 1350 -> 44 px
    # d'encre affichee, 1600 -> 37, 2000 -> 30. Tous au-dessus du plancher.
    for cadre in (1350, 1600, 2000):
        data = _png_encre_dans_cadre(cadre, 300)
        result = derive_logo(data, KEY, hashlib.sha256(data).hexdigest())
        metrics = result["metrics"]
        assert "trim_degenerate" in metrics["flags"], (cadre, metrics)
        assert result["variants"], (cadre, metrics)
        assert not set(metrics["flags"]) & BLOCKING_FLAGS, (cadre, metrics)

    # Mais le plancher n'est pas complaisant : au-dela, il mord. Cadre 4000 ->
    # l'image de travail est d'abord ramenee a MAX_WORK_EDGE (2000), l'encre de
    # 300 px devient 150, et l'encre affichee tombe a 15x15 px dans le canvas de
    # 200 — soit 2,4 px CSS dans la boite utile de la carte. C'est une tache, et
    # elle est refusee. C'est la difference avec la version precedente de ce
    # plancher, qui portait sur l'aire et ne se declenchait JAMAIS.
    data = _png_encre_dans_cadre(4000, 300)
    result = derive_logo(data, KEY, hashlib.sha256(data).hexdigest())
    metrics = result["metrics"]
    assert result["variants"] == [], metrics
    assert "ink_too_small" in metrics["flags"], metrics
    assert result["error"] is None, "un refus n'est pas une defaillance"

    # La degenerescence FRANCHE reste refusee — et ce test verifie que c'est
    # bien le plancher de l'ETAPE 7 qui mord, pas un garde plus precoce.
    #
    # Le cadre doit rester sous MAX_WORK_EDGE (2000) : au-dela, l'image de
    # travail est reduite, l'arete de l'encre tombe sous INK_MIN_EDGE_ABSOLUTE
    # (96) et c'est l'etape 4 qui refuse. C'est precisement ce qui rendait la
    # version precedente de ce test trompeuse : son cadre de 2400 etait reduit a
    # 2000, l'encre de 100 px devenait 83 px, et le refus venait de l'etape 4
    # alors que le commentaire l'attribuait au critere de l'etape 7.
    #
    # Ici : cadre 1600, encre 100 px. L'etape 4 ne mord pas (100 >= 96, donc
    # exemption absolue) et l'encre affichee vaut 100 x 200 / 1600 = 12 px
    # d'arete sur les DEUX axes, donc sous le plancher de 24 applique a la plus
    # grande. Un logotype fin (200x13) le franchit, lui : c'est la difference
    # entre une tache et une signature, cf. P17.
    data = _png_encre_dans_cadre(1600, 100)
    result = derive_logo(data, KEY, hashlib.sha256(data).hexdigest())
    metrics = result["metrics"]
    assert result["variants"] == [], metrics
    assert "ink_too_small" in metrics["flags"], metrics
    assert "ink_too_small" in BLOCKING_FLAGS
    assert result["error"] is None, "un refus n'est pas une defaillance"

    # Et un logotype FIN mais long doit franchir le plancher : son encre a une
    # arete courte derisoire mais une grande arete de 200 px. C'est la
    # contre-epreuve de P17, celle qui distingue une signature d'une tache.
    data = _png_encre_dans_cadre(400, 300, hauteur=20)
    result = derive_logo(data, KEY, hashlib.sha256(data).hexdigest())
    metrics = result["metrics"]
    assert result["variants"], (
        "un logotype fin ne doit pas etre refuse par le plancher d'encre affichee",
        metrics,
    )

    # Le plancher est CALIBRE sur le parc reel : les huit plus petites encres
    # affichees des 60 masters du releve du 31/08 mesurent (courte x longue)
    # 12x16, 14x18, 19x108, 20x120, 22x200, 23x200, 25x25, 29x29. A 24 px sur la
    # plus GRANDE arete, il ecarte exactement les deux premieres et laisse passer
    # les six autres.
    assert 18 < MIN_DISPLAYED_INK_EDGE <= 25, (
        "le plancher doit ecarter les taches (16 et 18 px de grande arete) sans "
        "toucher au master suivant du parc (25x25)"
    )


def test_p6_bombe_svg_par_use_imbriques_est_un_refus_pas_une_defaillance():
    """P6 : le plafond d'octets n'est pas le seul garde de complexite (P14).

    AVANT : une amplification par ``<use>`` imbriques (2 215 octets, 16 niveaux
    x4) passait le plafond de 2 Mo et etait arretee par la limite INTERNE de
    librsvg. Elle ressortait en ``derivation_failed`` avec error « unable to copy
    to memory svgload_buffer: SVG rendering failed glib: exceeded more than
    500000 referenced elements » — un refus de complexite compte comme une
    DEFAILLANCE dans le CSV d'audit.
    """
    from core.logo_derive import _is_svg_complexity_refusal

    defs = ['<g id="l0"><rect x="0" y="0" width="4" height="4" fill="#204060"/></g>']
    for niveau in range(1, 16):
        reprises = "".join('<use href="#l%d" x="%d" y="%d"/>' % (niveau - 1, k * 3, k * 5)
                           for k in range(4))
        defs.append('<g id="l%d">%s</g>' % (niveau, reprises))
    bombe = _svg('<defs>%s</defs><use href="#l15"/>' % "".join(defs),
                 'width="800" height="800" viewBox="0 0 800 800"')
    assert len(bombe) < MAX_SVG_CONTENT_BYTES // 100, (
        "temoin invalide : %d octets, le plafond d'octets suffirait" % len(bombe)
    )

    result = derive_logo(bombe, KEY, HASH_A)
    metrics = result["metrics"]
    assert result["variants"] == [], metrics
    assert "svg_too_complex" in metrics["flags"], metrics
    assert "derivation_failed" not in metrics["flags"], metrics
    assert result["error"] is None, result["error"]
    assert "svg_too_complex" in BLOCKING_FLAGS

    # Le requalificateur reste ETROIT : une vraie defaillance en reste une.
    assert _is_svg_complexity_refusal(
        pyvips.Error("SVG rendering failed glib: exceeded more than 500000 "
                     "referenced elements"))
    assert not _is_svg_complexity_refusal(pyvips.Error("pngload: not a PNG file"))
    casse = derived("pas_une_image")
    assert "derivation_failed" in casse["metrics"]["flags"], casse["metrics"]
    assert casse["error"], casse


def test_p7_lentete_de_ce_fichier_nomme_la_recette_reelle():
    """P7 : l'entete annoncait encore « r1m0v8151 » alors que RECIPE vaut « r1m0 ».

    Cosmetique, mais elle documente l'IDENTITE de la recette, celle qui entre
    dans le h12 du nommage adresse par contenu et donc dans des URL declarees
    immutables 30 jours.
    """
    premiere_ligne = (__doc__ or "").splitlines()[0]
    assert "« %s »" % RECIPE in premiere_ligne, premiere_ligne
    assert "8151" not in premiere_ligne and "v8" not in premiere_ligne, premiere_ligne
