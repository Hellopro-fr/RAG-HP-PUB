"""
Derive d'affichage des logos fournisseurs — recette « r1m0 ».

Ce module produit, A COTE du master heberge par ``process_logo``, une ou deux
vignettes PNG 200x200 destinees a la carte de listing fournisseur (cadre CSS
reel : 70x44, bordure 1px, radius 6px, fond BLANC PUR, padding 5px, soit une
boite utile de 58x32 px). Il est NON DESTRUCTIF : il ne touche jamais le master,
ne l'ecrit pas, ne le remplace pas.

``process_logo`` est LOGO-SAFE par contrat (SVG verbatim, ICO->PNG, raster en
passthrough d'octets) et le sha256 de ses octets sert de ``content_hash`` a tout
le cycle de vie cote BO : ce module ne doit surtout pas etre greffe dedans.

Contraintes structurelles (ne pas « simplifier » sans les relire) :
  - AUCUN etat, AUCUN reseau, AUCUNE BDD, AUCUN acces disque : entree = octets,
    sortie = octets. C'est l'appelant (worker) qui ecrit les variantes.
  - AUCUNE exception ne sort de :func:`derive_logo`. Le worker ne doit jamais
    echouer a cause du derive : toute defaillance remplit ``error``, vide
    ``variants`` et pose le flag ``derivation_failed``.
  - AUCUN import intra-paquet : le module est importe sous deux noms selon le
    contexte (``core.logo_derive`` en test via ``pythonpath = app tests``,
    ``image_download_service.core.logo_derive`` en prod). Seuls la stdlib et
    ``pyvips`` sont importes.
  - Cible Python 3.11 (image de prod ``python:3.11-slim``) : aucune syntaxe
    superieure. Aucune dependance nouvelle.

PIEGES pyvips mesures dans le venv du service (pyvips 3.1.1 / libvips 8.15.1).
Chacun a coute une mesure : ils sont referencees P1..P15 dans le code.
  P1  ``thumbnail_buffer(svg, 200, height=200)`` rend 200x200 ; le MEME appel
      avec ``size="down"`` rend 32x32 pour un SVG declare 32x32. Symetriquement,
      sans ``size="down"`` un raster 50x30 est AGRANDI a 200x120. Le branchement
      sur le format doit donc preceder l'appel et aucun helper partage ne porte
      ``size`` en valeur par defaut.
  P2  ``find_trim`` sur du RGBA est faux EXACTEMENT sur la population sensible :
      encre BLANCHE sur transparent -> [200, 120, 0, 0] (bbox VIDE), encre
      sombre -> bbox correcte. La bande alpha extraite est correcte dans les
      deux cas. Et ``find_trim`` ne leve pas : il signale par width/height == 0
      en laissant left/top aux dimensions de l'image (extract_area hors cadre
      si on s'y fie).
  P3  « pngload_buffer: out of order read » se declenche sur la SORTIE de
      ``thumbnail_buffer`` des le 2e passage de mesure. ``copy_memory()`` est
      obligatoire sur cette sortie, pas seulement au chargement.
  P4  Un JPEG CMYK rend bands=4 / interpretation='cmyk' / hasalpha()=False :
      tester ``bands == 4`` confond CMYK et RGBA. Et ``hasalpha()`` MENT sur une
      image 2 bandes d'interpretation 'multiband'. Ordre imperatif :
      ``colourspace("srgb")`` D'ABORD, ``addalpha()`` ensuite.
  P5  Un masque relationnel pyvips vaut 0 ou 255, PAS 0 ou 1 : tout pourcentage
      se calcule ``mask.avg() / 255 * 100``. Oublier le /255 rend les mesures
      255x trop grandes et fait tomber tous les verdicts en « any ».
  P6  ``gravity("centre", 200, 200)`` sur une entree PLUS GRANDE que la cible ne
      leve pas et ne redimensionne pas : elle RECADRE au centre en silence
      (300x250 -> 200x200, 50 px perdus de chaque cote). Il faut garantir
      <= 200x200 AVANT gravity.
  P7  ``composite2`` exige une interpretation connue : ``Image.black(w,h,bands=4)``
      est 'multiband' et fait echouer l'appel. Les canvas se fabriquent par
      ``embed``/``gravity`` depuis une image srgb, ou par ``new_from_image`` +
      ``copy(interpretation="srgb")``.
  P8  Le profil ICC de la source SURVIT a ``thumbnail_buffer`` et a
      ``colourspace("srgb")``, et — CORRECTION du 31/08 — ``colourspace`` ne
      fait AUCUNE transformation ICC : il ne convertit qu'entre interpretations
      libvips. ``thumbnail_buffer`` n'en fait une que pour le CMJN. Sur une
      source RGB a profil non-sRGB, les pixels sortent donc INCHANGES : les
      retirer sans convertir publie du AdobeRGB etiquete sRGB (mesure : bloc
      (200,30,40) en AdobeRGB -> ``icc_transform`` rend (233,24,36), l'ancien
      code publiait (200,30,40) sans profil, soit 33 niveaux d'ecart sur le
      rouge de marque). Il faut donc ``icc_transform("srgb", embedded=True)``
      D'ABORD, ``remove()`` ensuite.
  P10 Un SVG sans width/height NI viewBox n'est PAS mis a l'echelle par
      librsvg : ``thumbnail_buffer`` a 200, 250 puis 500 rend une encre qui
      reste a 80x80, seul le CADRE grandit. Une 2e passe de rendu plus grande
      est donc, sur ces fichiers, une pure perte : elle fait CHUTER la part
      d'encre dans le cadre. Tout supersampling doit etre verifie a posteriori,
      jamais suppose.
  P11 Le cadre d'un rendu vectoriel est choisi par CE module (supersampling) :
      il ne peut donc pas servir de preuve qu'un trim est degenere. Appliquer
      la regle ``trim_degenerate`` a la branche vecteur est circulaire, et sa
      consequence (« garder le cadre entier ») viole directement la marge 0 de
      l'etape 7 : un SVG dont l'encre occupe moins de 5 % du viewBox ressortait
      en vignette minuscule perdue au centre du canvas, avec fill_pct = 100.
  P9  ``pngsave_buffer(keep=...)`` n'existe qu'a partir de libvips 8.15, et une
      option inconnue LEVE (« pngsave_buffer does not support optional argument »).
      L'image de prod part de ``python:3.11-slim`` + ``libvips-dev`` apt (8.14.x) :
      le nettoyage des metadonnees passe donc par ``remove()``, pas par ``keep=``.
      ``strip=True`` en revanche existe des la 8.14 : il supprime le chunk eXIf
      que ``pngsave_buffer`` RESYNTHETISE a partir de la resolution meme quand
      tous les champs exif-* ont ete retires (mesure : 706 -> 538 octets).
  P12 ``find_trim`` ne calcule PAS une boite englobante exacte : il cherche les
      bords par recherche sous-echantillonnee (median 3x3 interne) et rate
      l'encre dont le pas vaut 1 a 3 px. Mesures : lockup hachure 1 px / gap
      2 px sur y=20..380 -> ``find_trim`` rend (30, 290, 341, 91), soit les 2/3
      du logo perdus, sans aucun flag ; code-barres 240x80 a 33 % d'encre ->
      (0, 0, 1, 80), donc ``ink_too_small`` (BLOQUANT) ; 900x900 raye a 33 % ->
      (0, 0, 900, 1). Toute boite rendue par ``find_trim`` doit etre CROISEE
      avec une mesure exacte (``project()`` sur les deux axes) avant d'etre
      publiee sous une URL immutable 30 jours. Et le croisement doit porter sur
      la CONTENANCE, pas sur l'aire : un seuil d'aire a 90 % laissait encore
      passer une troncature de 10 % de l'encre, sans flag (mesure dans
      :func:`_crosschecked_box`). D'ou l'UNION des deux boites.
  P13 ``find_trim`` applique un median 3x3 : il LEVE « rank: window too large »
      des qu'une arete de l'image fait moins de 3 px (mesure : 1x1, 2x2, 1x200,
      200x1, 200x2, 2x200). Un master 6000x4 tombe dedans APRES le plafond
      MAX_WORK_EDGE (image de travail 2000x1). Il faut garder l'arete avant
      l'appel, sinon un ``ink_too_small`` propre devient un
      ``derivation_failed`` avec un message libvips crypitque en base.
  P14 La branche SVG n'a pas de cout borne par la taille de SORTIE : il est
      pilote par le NOMBRE D'ELEMENTS du fichier. Mesures a canvas 200x200 :
      1,7 Mo / 30 000 ``<rect>`` -> +122 Mo RSS ; 6,7 Mo / 120 000 -> +462 Mo ;
      16,8 Mo / 300 000 -> +1 098 Mo. Et sous pression memoire librsvg/glib
      n'echoue pas par exception : il ABORTE le processus (mesure sous
      RLIMIT_AS 600 Mo : returncode 134, SIGABRT, « memory allocation of 1168
      bytes failed »). Le contrat « aucune exception ne sort » ne protege donc
      PAS le worker : en prod (1 CPU / 2 Go, 10 replicas, RabbitMQ) le message
      n'est jamais acquitte, il est redelivre, et il tue la replica suivante.
      D'ou :data:`MAX_SVG_CONTENT_BYTES`, un refus AVANT rasterisation.
      COMPLEMENT : le plafond d'octets n'est PAS le seul garde de complexite, et
      il ne peut pas l'etre — l'amplification par ``<use>`` imbriques tient dans
      2 215 octets (16 niveaux x4) et c'est la limite INTERNE de librsvg qui
      l'arrete, par « exceeded more than 500000 referenced elements ». Ce refus
      remontait en ``derivation_failed`` avec ce message en base, alors qu'un
      refus de complexite n'est pas une defaillance : il est desormais reclasse
      en ``svg_too_complex``, ``error`` a None
      (:data:`_SVG_COMPLEXITY_MARKERS`).
  P15 ``_is_svg`` (10 premiers octets, miroir de ``_detect_extension``) est bon
      pour le NOMMAGE, pas pour le ROUTAGE : un DOCTYPE ou un commentaire de
      generateur Illustrator/Inkscape le fait rendre False alors que libvips
      renifle bien du SVG. Le fichier partait alors en branche RASTER, donc
      avec ``size="down"`` (P1) ET sans le garde ``svg_text`` (mesure : un SVG
      a ``<text>`` precede d'un DOCTYPE publiait une vignette de texte
      rasterise SANS police, flags ['low_res', 'no_upscale'] ; le meme sans
      DOCTYPE rendait variants=[] + 'svg_text'). C'est le seul endroit du
      module ou les deux garanties structurantes tombaient ensemble.
      Et une FENETRE d'octets, quelle que soit sa taille, ne fait que DEPLACER
      la frontiere : mesure a l'octet, ``<svg`` a l'offset 1020 partait en
      vecteur, a 1030 en raster. Le ROUTAGE se tranche donc sur le champ
      ``vips-loader`` de la sonde (:func:`_route_is_vector`), qui EST la
      decision de libvips ; le reniflage d'octets n'est plus qu'un repli.

Note:
    Detection GIF : le seul champ fiable est ``vips-loader == 'gifload_buffer'``,
    lu AU CHARGEMENT (``bits-per-sample`` decrit la palette, pas la
    transparence ; et un GIF relu rend bands=4/srgb/hasalpha=True, donc l'image
    normalisee ne trahit plus son origine). Mais ce champ dit le FORMAT, pas la
    matte : ``gif_1bit`` exige en plus une transparence binaire REELLEMENT
    presente, mesuree sur l'image de travail (:func:`_has_binary_transparency`),
    sinon un GIF entierement opaque etait ecarte la ou le MEME visuel en PNG
    etait publie.

    Detection SVG : le champ ``vips-loader`` de la sonde tranche aussi le
    ROUTAGE vecteur/raster (P15), le reniflage d'octets ne servant plus que de
    repli.
"""

import hashlib
import logging
import math
import re

import pyvips

logger = logging.getLogger(__name__)


# =============================================================================
# Identite de la recette
# =============================================================================

#: Nom de recette : « r1 » = recette 1, « m0 » = marge 0. Il entre dans le h12 du
#: nommage adresse par contenu, donc dans des URL CDN declarees immutables
#: 30 jours : le changer invalide tous les noms de fichiers deja publies (c'est
#: le but, mais ca se decide).
#:
#: Il ne porte VOLONTAIREMENT AUCUN numero de version de libvips (il s'appelait
#: « r1m0v8151 », mesure en 8.15.1). L'image de prod part de ``python:3.11-slim``
#: + ``libvips-dev`` apt, soit une 8.14.x : le jeton mentait, et si deux versions
#: de libvips coexistaient un jour, des octets DIFFERENTS seraient servis sous la
#: MEME URL immutable. La version reelle est relevee a l'execution et exposee
#: dans ``metrics["libvips_version"]``, qui n'entre pas dans le nom de fichier.
#:
#: CONTRAT D'IMMUTABILITE — a respecter a la lettre, le CDN sert ces fichiers en
#: ``Cache-Control: public, max-age=2592000, immutable`` SANS moyen de purge :
#: TOUT ce qui change les octets d'une variante DOIT changer ce jeton. Cela
#: couvre les constantes de la recette (canvas, marges, seuils, couleur de
#: plaque), et cela couvre aussi un changement de version de libvips ou de son
#: zlib — donc un rebuild de l'image de base. Un nom de fichier ne porte que
#: ``h12(content_hash|RECIPE)`` + ``RECIPE`` : rien d'autre ne peut faire la
#: difference. C'est pourquoi la couleur de plaque n'est PLUS un argument
#: d'appel (cf. :func:`derive_logo`) : un parametre par appel produisait des
#: octets differents sous le meme nom, ce que ce contrat interdit.
RECIPE = "r1m0"

#: Version de libvips reellement liee, pour l'audit UNIQUEMENT (jamais dans un
#: nom de fichier, cf. :data:`RECIPE`).
try:
    LIBVIPS_VERSION = "{0}.{1}.{2}".format(
        pyvips.version(0), pyvips.version(1), pyvips.version(2)
    )
except Exception:  # pragma: no cover - defensif : une metrique ne doit rien casser
    LIBVIPS_VERSION = "unknown"

#: Canvas fixe, arrete par le porteur du chantier. Ne pas le rendre variable :
#: l'affichage sera retravaille ensuite, la vignette reste le contrat.
CANVAS = 200
CANVAS_AREA = CANVAS * CANVAS  # 40000

VARIANT_PLAIN = "sq200a"  # logo sur fond transparent (toujours produit)
VARIANT_PLATE = "sq200d"  # logo sur plaque sombre (uniquement si dark_required)

#: Liste FERMEE et ORDONNEE des flags. Toute valeur posee par ce module en fait
#: partie (verrouille par un test qui l'enumere). L'ordre est celui du tri de
#: ``metrics["flags"]`` : il ne depend PAS de l'ordre d'insertion, sinon la meme
#: image pourrait produire deux chaines differentes selon le chemin de code, et
#: la colonne SQL cesserait d'etre regroupable.
FLAG_ORDER = (
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
    "elongated",
    "derivation_failed",
)

FLAGS = frozenset(FLAG_ORDER)

#: Rang de chaque flag, pour un tri stable en O(n log n) sans recherche lineaire.
_FLAG_RANK = {flag: rank for rank, flag in enumerate(FLAG_ORDER)}

#: Flags BLOQUANTS pour la publication du derive. Sous-ensemble ferme de
#: :data:`FLAGS`, expose pour que le consommateur n'ait pas a chercher une
#: sous-chaine dans une colonne CSV : une telle recherche laisserait un flag
#: ajoute plus tard ne rien bloquer, en silence.
#:
#:   - svg_text / svg_too_complex / ink_too_small / derivation_failed : aucune
#:     variante produite.
#:   - elongated : variante produite mais inutilisable dans le cadre 58x32
#:     (au-dela d'un ratio 6, aucune geometrie realiste ne donne 20 px d'encre) ;
#:     le consommateur doit afficher son repli.
#:   - no_usable_variant : ``surface == "dark_required"`` et AUCUNE ``sq200d``
#:     produite (plaque refusee ou en echec). La seule variante publiable est
#:     alors de l'encre claire sur transparent, donc INVISIBLE sur le cadre
#:     #FFFFFF de la carte, qui n'a pas de mode sombre. Sans ce flag, un
#:     consommateur qui n'applique que BLOCKING_FLAGS publie une vignette vide.
#:
#: Les autres flags sont informatifs : ils qualifient le derive sans l'interdire
#: (``matte_suspect``, ``gif_1bit`` et ``plate_failed`` n'empechent que la
#: plaque — et declenchent alors ``no_usable_variant`` s'il fallait une plaque —,
#: ``low_res`` / ``pale`` / ``no_upscale`` / ``vector_upscaled`` /
#: ``baked_background`` / ``svg_wraps_raster`` / ``trim_degenerate`` alimentent
#: l'audit qualite).
#:
#: ``trim_degenerate`` A ETE RETIRE de cette liste. Il se declenche sur le
#: rapport encre/cadre de la SOURCE (moins de 5 % d'aire), c'est-a-dire sur la
#: taille du CADRE et non sur la lisibilite du resultat : la MEME encre de 300 px
#: sortait a fill_pct = 100 sans aucun flag dans un cadre de 320 px, et refusee
#: a la publication dans un cadre de 1350 px (mesures : cadre 1350 -> 46 px
#: d'encre publiee, 1600 -> 38, 2000 -> 32, 3000 -> 22, 4000 -> 16, tous
#: bloques). Il reste un excellent signal d'AUDIT — il dit que le cadrage a ete
#: refuse — mais ce qui interdit la publication est desormais une mesure de
#: l'encre REELLEMENT AFFICHEE : cf. :data:`MIN_DISPLAYED_INK_EDGE`, qui
#: pose ``ink_too_small``.
BLOCKING_FLAGS = frozenset({
    "svg_text",
    "svg_too_complex",
    "ink_too_small",
    "no_usable_variant",
    "elongated",
    "derivation_failed",
})


# =============================================================================
# Seuils de la recette (aucun n'existait dans le depot : tous crees ici)
# =============================================================================

# --- Etape 2 : tri des SVG ---------------------------------------------------
#: Motifs qui trahissent du texte a rasteriser. Le conteneur de prod n'embarque
#: AUCUN paquet de polices (Dockerfile : libjpeg/zlib/libvips/libwebp/librsvg,
#: pas de fonts-*) : le rendu serveur serait silencieusement FAUX. On preserve
#: alors le master SVG et on ne produit aucun raster.
SVG_TEXT_PATTERNS = ("<text", "<tspan", "<textpath", "<altglyph", "font-family", "@font-face")

#: Un SVG qui enveloppe un bitmap en data: URI doit passer par la branche
#: RASTER : sinon librsvg agrandit le bitmap embarque en douceur et contourne la
#: garantie de non-agrandissement.
SVG_DATA_HREF_RE = re.compile(r"href\s*=\s*[\"']\s*data:")

#: Fenetre de reniflage pour le ROUTAGE vecteur/raster (P15). ``_is_svg`` reste
#: sur 10 octets pour rester aligne sur le NOMMAGE de ``_detect_extension``,
#: mais un DOCTYPE ou un commentaire de generateur decale le ``<svg`` bien
#: au-dela : sans cette fenetre, le garde ``svg_text`` est contournable par une
#: ligne d'en-tete tres courante des exports Illustrator/Inkscape.
SVG_SNIFF_BYTES = 1024

#: Signatures RASTER connues. Un fichier qui commence par l'une d'elles n'est
#: JAMAIS route vers la branche vecteur, meme s'il contient ``<svg`` dans ses
#: 1024 premiers octets (un commentaire, un profil, un bloc XMP le peuvent).
_RASTER_MAGICS = (
    b"\x89PNG\r\n\x1a\n",   # PNG
    b"\xff\xd8\xff",        # JPEG
    b"GIF87a", b"GIF89a",   # GIF
    b"RIFF",                # WebP (RIFF....WEBP)
    b"BM",                  # BMP
    b"\x00\x00\x01\x00",    # ICO
    b"\x00\x00\x02\x00",    # CUR
    b"II\x2a\x00", b"MM\x00\x2a",  # TIFF
)

#: Plafond DUR de la branche SVG, en octets de CONTENU (P14). Ce n'est pas une
#: defaillance mais un REFUS : au-dela, aucun derive, flag ``svg_too_complex``
#: (bloquant) et ``error`` reste None. Le cout memoire de librsvg est pilote par
#: le nombre d'elements, pas par la taille de sortie, et sous contrainte il
#: ABORTE le processus : un seul SVG lourd empoisonnerait toute la file logo.
MAX_SVG_CONTENT_BYTES = 2 * 1024 * 1024

#: Le supersampling rasterise le fichier UNE 2e FOIS : les deux passes sont
#: comptees dans le meme plafond (P14). Au-dela de la moitie du plafond, la 1re
#: passe est conservee telle quelle.
MAX_SVG_TWO_PASS_BYTES = MAX_SVG_CONTENT_BYTES // 2

#: Marqueurs, en minuscules, des messages par lesquels librsvg REFUSE un
#: document trop complexe au lieu d'echouer dessus (P14). Le plafond d'octets ne
#: peut pas les attraper : l'amplification par ``<use>`` imbriques tient dans un
#: fichier minuscule (mesure : 2 215 octets, 16 niveaux x4, refus a 500 000
#: elements references). Un REFUS de complexite doit ressortir comme
#: ``svg_too_complex`` avec ``error`` a None, exactement comme le plafond
#: d'octets : le compter comme une DEFAILLANCE polluerait la colonne des causes
#: d'echec du CSV d'audit avec un cas ou le module a fait son travail.
#: « referenced elements » est le libelle MESURE ici (librsvg 2.54, message
#: « SVG rendering failed glib: exceeded more than 500000 referenced elements ») ;
#: « instancing limit » est le libelle du MEME garde dans les librsvg plus
#: recentes, ajoute pour que l'image de prod ne change pas la classification.
_SVG_COMPLEXITY_MARKERS = ("referenced elements", "instancing limit")

# --- Etape 3 : chargement ----------------------------------------------------
#: Plafond de l'image de travail. Purement memoire : le replica tourne a 1 CPU /
#: 2 Go et 177 masters depassent 2000 px. Le shrink-on-load de thumbnail_buffer
#: evite de decoder plein cadre.
MAX_WORK_EDGE = 2000

#: Supersampling du rendu SVG. Un SVG dont le viewBox porte de la marge rendrait
#: une encre plus petite que 200 px ; la remonter serait un agrandissement
#: raster (flou). On re-rend alors le vecteur plus grand, puis on reduit.
#:
#: Ce plafond est purement MEMOIRE, pas qualitatif : il vaut exactement ce qu'il
#: faut pour que la 2e passe reste dans :data:`MAX_WORK_EDGE`. Il valait 4,0 en
#: dur, ce qui laissait un agrandissement raster silencieux sur tout SVG dont
#: l'encre occupait moins d'un quart de l'artboard (mesure : artboard 800 /
#: marque 100 -> 30 niveaux de gris la ou le vecteur n'en donne que 2).
MAX_SVG_SUPERSAMPLE = MAX_WORK_EDGE / float(CANVAS)  # 10.0
SVG_SUPERSAMPLE_MIN_GAIN = 1.05  # en dessous, la 2e passe ne vaut pas son cout

# --- Etape 4 : boite d'encre -------------------------------------------------
ALPHA_OPAQUE_LIMIT = 250      # un pixel est « non pleinement opaque » sous ce seuil
ALPHA_USED_PCT_MIN = 0.5      # part de pixels non opaques au-dela de laquelle l'alpha est « reellement utilise »
ALPHA_INK_THRESHOLD = 8       # alpha > 8 = de l'encre
OPAQUE_CORNER_TOLERANCE = 6   # concordance des 4 coins, en niveaux (0-255), par canal
OPAQUE_TRIM_THRESHOLD = 10    # ecart au fond au-dela duquel une ligne/colonne est conservee
INK_MIN_AREA_PCT = 1.0        # sous 1 % de la surface : ink_too_small, aucun derive
#: Trim retirant plus de 95 % de l'aire : refuse, cadre entier conserve. Le flag
#: ``trim_degenerate`` qui en decoule est un signal d'AUDIT (« le cadrage a ete
#: refuse »), plus un motif de refus : le refus se decide sur l'encre affichee,
#: cf. :data:`MIN_DISPLAYED_INK_EDGE`.
TRIM_DEGENERATE_AREA_PCT = 5.0

#: Arete minimale pour appeler ``find_trim`` (P13 : median 3x3, il LEVE en
#: dessous). Sous ce seuil il n'y a de toute facon pas de vignette a produire.
MIN_TRIM_EDGE = 3

#: Plancher ABSOLU qui exempte de ``ink_too_small``. La regle relative (1 % du
#: cadre) est pervertie par les exports a canvas genereux : plus le master est
#: grand, plus le rejet est probable (mesure : cadre 4000 / logo 300 = 0,56 %
#: -> ink_too_small, alors que 300 px font 1,5 fois le canvas cible). Au-dela de
#: cette arete courte, l'encre porte assez de pixels par construction : c'est le
#: meme seuil que :data:`LOW_RES_MIN_EDGE`, la boite utile 58x32 en ecran 3x.
INK_MIN_EDGE_ABSOLUTE = 96

# --- Etape 7 : plancher sur ce qui est REELLEMENT AFFICHE -------------------
#: Arete la plus GRANDE, en pixels du canvas 200x200, que l'encre reellement
#: visible dans la vignette finale doit atteindre. C'est le seul critere de
#: blocage geometrique mesure sur la SORTIE et non sur la source, et il REMPLACE
#: ``trim_degenerate`` comme motif de refus (cf. :data:`BLOCKING_FLAGS`).
#:
#: P17 — POURQUOI LA PLUS GRANDE ARETE ET NON LA PLUS PETITE. Un critere sur
#: l'arete COURTE confond deux populations opposees : une TACHE (12x16 px, rien a
#: voir) et un LOGOTYPE FIN (13x200 px, parfaitement identifiable). Mesure : un
#: seuil de 16 px sur l'arete courte refusait la fixture png_900x60, dont l'encre
#: affichee vaut 200x13 — or ce logo a une variante legitime et son inaptitude au
#: cadre est deja dite par ``elongated``, qui est bloquant. Ce qui distingue une
#: tache d'un logotype, c'est que ses DEUX aretes sont petites : la plus grande
#: suffit donc a trancher, et elle laisse ``elongated`` faire son travail.
#:
#: P16 — POURQUOI UNE ARETE ET NON UNE AIRE. La premiere version de ce plancher
#: portait sur l'aire (0,25 % du canvas, soit 100 px2) et elle etait INERTE :
#: mise a 0,0, aucune issue ne changeait sur un balayage de 209 couples
#: cadre x encre. Raison structurelle mesuree : l'etape 4 refuse deja toute
#: encre dont l'arete courte est sous :data:`INK_MIN_EDGE_ABSOLUTE` (96 px du
#: master), et :data:`MAX_WORK_EDGE` (2000) borne l'image de travail — l'encre
#: affichee vaut donc au minimum 96 x 200 / 2000 = 9,6 px d'arete, soit environ
#: 92 px2, quand le test etait un « < 100 » STRICT. Le seuil tombait pile sur sa
#: frontiere : la plus petite encre publiee mesuree valait EXACTEMENT 100 px2.
#: Un module dont la credibilite tient a des notes mesurees ne peut pas affirmer
#: qu'un garde protege quand il ne se declenche jamais.
#:
#: CALIBRATION sur les 60 masters reels du parc (releve du 31/08). Les huit plus
#: petites encres affichees, en (courte x longue) : 12x16, 14x18, 19x108, 20x120,
#: 22x200, 23x200, 25x25, 29x29. Un plancher de 24 px sur la plus GRANDE arete
#: ecarte donc exactement les DEUX premieres (3,3 % du parc) — 1,9 et 2,2 px CSS
#: dans la boite utile 58x32 de la carte, rien de distinguable — et laisse passer
#: les logotypes fins mais longs, dont l'inaptitude au cadre est deja dite par
#: ``elongated``.
#:
#: A NOTER, pour ne pas se croire mieux protege qu'on ne l'est : ce plancher est
#: une ceinture de securite sur la SORTIE, pas le garde principal. Les deux cas
#: qu'il ecarte portent DEJA ``low_res`` et ``no_upscale``, et leurs masters de
#: 16 px sont de toute facon recales par le gate de publication du BO
#: (max >= 64 ET min >= 24 sur les dimensions du master). L'essentiel du travail
#: est fait a l'etape 4 par :data:`INK_MIN_EDGE_ABSOLUTE` ; ``low_res`` et
#: ``fill_pct`` restent les signaux d'audit d'un master simplement petit.
MIN_DISPLAYED_INK_EDGE = 24

# --- Etape 5 : mesures de surface -------------------------------------------
#: Luminance Rec.709, pour rester comparable a la mesure de reference du 27/08
#: qui a isole les 205 logos invisibles sur blanc.
LUMA_R, LUMA_G, LUMA_B = 0.2126, 0.7152, 0.0722
LUM_INK_ON_WHITE_MAX = 235    # sous cette luminance (composee sur blanc) : de l'encre visible
LUM_INK_ON_BLACK_MIN = 20     # au-dessus (composee sur noir) : de l'encre visible
LIGHTNESS_LEVEL = 178         # 0,7 * 255
LIGHTNESS_COVERAGE = 0.70     # part des pixels opaques a depasser pour is_light
OPAQUE_ALPHA_MIN = 128        # « pixel opaque » au sens de is_light

# --- Etape 6 : verdict de surface -------------------------------------------
ALPHA_RATIO_SELF_BACKGROUND = 10.0  # sous ce taux d'alpha, le logo porte deja son fond
INK_ON_WHITE_STRONG = 8.0
INK_ON_WHITE_WEAK = 2.0
INK_ON_BLACK_WEAK = 2.0

# --- Etape 7 : geometrie ----------------------------------------------------
#: La boite utile du conteneur vaut 58x32 CSS, soit 174x96 en ecran 3x : sous
#: 96 px d'arete courte, le master ne porte pas assez de pixels.
LOW_RES_MIN_EDGE = 96
#: Au-dela de ce ratio, aucune geometrie realiste ne donne 20 px d'encre dans le
#: cadre : le consommateur affichera un repli.
ELONGATED_RATIO_MAX = 6.0

# --- Etape 8 : plaque sombre ------------------------------------------------
#: Couleur de la plaque sombre — CONSTANTE DE RECETTE, pas un parametre d'appel.
#: Elle determine les octets de la variante ``sq200d`` et n'entre PAS dans le nom
#: de fichier : la faire varier a l'appel produisait deux fichiers d'octets
#: differents sous le MEME nom (mesure du 01/09/2026 sur le meme master :
#: (31,41,51) -> sha256 aee472cc..., (10,20,30) -> 3721f70b..., et dans les deux
#: cas le nom logo-...--79fbdabe4c8d-r1m0-sq200d.png), donc une URL declaree
#: immutable 30 jours servant deux images selon l'appelant. La changer est une
#: decision de CHARTE : elle passe par un bump de :data:`RECIPE`, ce qui renomme
#: proprement toutes les variantes.
DEFAULT_PLATE_COLOR = (31, 41, 51)
PLATE_PADDING = 6          # la plaque epouse la boite d'encre + cette marge
PLATE_CORNER_RADIUS = 8    # coins arrondis, pour se lire comme intentionnelle dans un cadre radius 6
MATTE_EDGE_ALPHA_MIN = 8   # bord = alpha strictement entre ces deux bornes
MATTE_EDGE_ALPHA_MAX = 248
MATTE_MIN_EDGE_PIXELS = 32  # sous ce compte, le bord est trop dur pour franger
MATTE_SAT_FLOOR_PCT = 15.0  # un bord quasi neutre n'est jamais suspect
MATTE_SAT_DELTA_PCT = 12.0  # ecart de saturation bord/interieur au-dela duquel la matte est suspecte

#: Champs de metadonnees a retirer avant sauvegarde (cf. P8/P9).
_META_FIELDS_TO_DROP = ("icc-profile-data", "xmp-data", "iptc-data", "orientation")

# --- Etape 9 : bornes de ce qui part en BASE --------------------------------
#: ``error``, ``filename`` et ``source_hash`` sont ecrits dans des colonnes SQL.
#: Trois exigences distinctes, toutes mesurees comme violees avant correctif :
#:   - ``error`` etait recopie tel quel : multi-ligne, non borne (201 caracteres
#:     mesures) et NON DETERMINISTE — libvips y recopie le chemin d'un fichier
#:     temporaire ImageMagick, donc trois derives des MEMES octets rendaient
#:     trois textes differents (dedup et idempotence du backfill casses, et
#:     fuite d'un chemin hote).
#:   - ``filename`` : une cle de 400 caracteres donnait un nom de 440, au-dela
#:     de NAME_MAX (255) et d'un VARCHAR(255).
#:   - ``source_hash`` : recopie sans validation, donc 5000 caracteres ou un int
#:     passaient, alors que toute l'immutabilite CDN repose sur sa forme.
MAX_ERROR_LEN = 255
MAX_SLUG_LEN = 120
#: Un sha256 hexadecimal minuscule, rien d'autre : c'est ce qui rend vraie
#: l'immutabilite de 30 jours annoncee par le CDN.
_CONTENT_HASH_RE = re.compile(r"\A[0-9a-f]{64}\Z")
#: Motifs a effacer de ``error`` pour le rendre DETERMINISTE : chemins ABSOLUS
#: (``/tmp/magick-XXXX``) et adresses memoire (``0x7f...``). Le garde arriere
#: exige que le chemin ne soit pas colle a un mot, sinon les references de
#: source de libvips (``error/mvg.c/ReadMVGImage/186``), elles deterministes et
#: utiles au diagnostic, seraient effacees avec.
_ERROR_PATH_RE = re.compile(r"(?<![\w.])(?:/[\w.+-]+){2,}")
_ERROR_ADDR_RE = re.compile(r"0x[0-9a-fA-F]{4,}")


# =============================================================================
# Helpers — format et nommage
# =============================================================================

def _is_svg(content: bytes) -> bool:
    """
    Detecte un SVG sur les 10 PREMIERS OCTETS, comme ``_detect_extension``.

    Args:
        content: Octets du master heberge.

    Returns:
        bool: True si les octets ressemblent a du SVG/XML.

    Note:
        Test repris VERBATIM de image_processor._detect_extension (meme tranche,
        meme operateur, memes deux motifs) pour que le derive et le master
        s'accordent toujours sur la nature du fichier.
        RESERVE au NOMMAGE : le ROUTAGE vecteur/raster passe par
        :func:`_looks_like_svg`, sur une fenetre large (P15). Les deux usages
        etaient confondus, et la difference suffisait a contourner le garde
        ``svg_text``.
    """
    header_bytes = content[:10]
    return b'<svg' in header_bytes or b'<?xml' in header_bytes


def _looks_like_svg(content: bytes) -> bool:
    """
    Tranche le ROUTAGE vecteur/raster, sur une fenetre large (P15).

    Args:
        content: Octets du master heberge.

    Returns:
        bool: True si le fichier doit partir en branche VECTEUR.

    Note:
        ``_is_svg`` (10 octets) est le miroir du NOMMAGE et le reste ; ici on
        cherche ``<svg`` dans les :data:`SVG_SNIFF_BYTES` premiers octets, ce qui
        couvre le prolog XML, un BOM, l'indentation, un DOCTYPE et les
        commentaires de generateur — les quatre formes mesurees ou ``_is_svg``
        rendait False alors que libvips reniflait bel et bien du SVG.
        Un fichier qui commence par une signature RASTER connue est exclu
        d'office : le reniflage large ne doit pas pouvoir detourner un PNG dont
        un bloc de metadonnees contiendrait la chaine ``<svg``.
    """
    head = content[:SVG_SNIFF_BYTES]
    if head.startswith(_RASTER_MAGICS):
        return False
    return b'<svg' in head or _is_svg(content)


def _probe_loader(content: bytes):
    """
    Rend le nom du loader que libvips choisit pour ces octets, ou None.

    Args:
        content: Octets du master heberge.

    Returns:
        str | None: p. ex. ``'svgload_buffer'``, ``'pngload_buffer'``, ou None
        si libvips refuse le tampon ou n'expose pas le champ.

    Note:
        ``new_from_buffer`` ne lit que l'EN-TETE (chargement paresseux) : aucun
        pixel n'est produit ici, aucune rasterisation n'est declenchee. Le champ
        ``vips-loader`` est exactement la decision de libvips, donc la seule
        source de verite sur ce que la suite du module fera reellement des
        octets. Ne leve jamais : un tampon illisible rend None et l'appelant
        retombe sur le reniflage d'octets.
    """
    try:
        probe = pyvips.Image.new_from_buffer(content, "")
        if probe.get_typeof("vips-loader") == 0:
            return None
        return probe.get("vips-loader")
    except Exception as exc:  # pragma: no cover - defensif : un repli existe
        logger.debug("logo_derive: sonde de loader impossible (%s)", _short_error(exc))
        return None


def _route_is_vector(content: bytes) -> bool:
    """
    Tranche DEFINITIVEMENT le routage vecteur/raster (P15).

    Args:
        content: Octets du master heberge.

    Returns:
        bool: True si le fichier doit partir en branche VECTEUR.

    Note:
        Ordre imperatif, et chaque etape a sa raison :
          1. une signature RASTER connue tranche seule : le reniflage large ne
             doit pas pouvoir detourner un PNG dont un bloc de metadonnees
             contiendrait la chaine ``<svg`` (mesure conservee de P15) ;
          2. le reniflage d'octets ensuite, parce qu'il est GRATUIT et couvre le
             cas nominal ;
          3. la sonde ``vips-loader`` en dernier, qui tranche juste 10 fois sur
             10 la ou le reniflage se trompe.

        CORRECTIF : la detection SVG etait DEPLACEE, pas fermee. La fenetre de
        reniflage vaut :data:`SVG_SNIFF_BYTES` octets, et un ``<svg`` au-dela
        repartait en branche RASTER — donc avec ``size="down"`` (P1) ET sans le
        garde ``svg_text`` : un SVG a ``<text>`` publiait encore une vignette de
        texte rasterise SANS police, ``error`` a None, sous une URL immutable 30
        jours. Frontiere mesuree A L'OCTET : ``<svg`` a l'offset 1020 partait en
        branche vecteur, a l'offset 1030 en branche raster. Un commentaire de
        generateur un peu bavard suffisait donc.

        La sonde est un GAIN de surete meme sur un fichier enorme : elle ne fait
        que PARSER l'en-tete la ou la branche raster, elle, PARSE PUIS REND. Un
        SVG lourd detecte ici est refuse par :data:`MAX_SVG_CONTENT_BYTES`
        (P14) au lieu d'etre rasterise en silence.
    """
    head = content[:SVG_SNIFF_BYTES]
    if head.startswith(_RASTER_MAGICS):
        return False
    if b'<svg' in head or _is_svg(content):
        return True
    return _probe_loader(content) == "svgload_buffer"


def _short_error(exc: BaseException) -> str:
    """
    Rend un message d'erreur BORNE, mono-ligne et DETERMINISTE.

    Args:
        exc: Exception attrapee par le contrat « rien ne sort ».

    Returns:
        str: au plus :data:`MAX_ERROR_LEN` caracteres, sans chemin absolu ni
        adresse memoire, donc identique d'une execution a l'autre.

    Note:
        Ce texte part dans une colonne SQL et sert a REGROUPER les echecs d'un
        backfill de 3762 logos. Le message brut de libvips contient le chemin
        d'un temporaire ImageMagick (``/tmp/magick-<aleatoire>``) : sans ce
        nettoyage, deux echecs identiques comptent pour deux causes distinctes.
        Le texte integral reste dans le log.
    """
    text = str(exc)
    if not text.strip():
        text = exc.__class__.__name__
    text = _ERROR_ADDR_RE.sub("0xADDR", text)
    text = _ERROR_PATH_RE.sub("<path>", text)
    text = " ".join(text.split())  # aplatit \n, \t et les blancs multiples
    if len(text) > MAX_ERROR_LEN:
        text = text[:MAX_ERROR_LEN - 3] + "..."
    return text or exc.__class__.__name__


def _is_svg_complexity_refusal(exc: BaseException) -> bool:
    """
    Dit si ``exc`` est un REFUS de complexite de librsvg, pas une defaillance.

    Args:
        exc: Exception levee par la rasterisation d'un SVG.

    Returns:
        bool: True si le message porte l'un des :data:`_SVG_COMPLEXITY_MARKERS`.

    Note:
        Le test porte sur le MESSAGE parce que libvips n'expose pas de code
        d'erreur : ``pyvips.Error`` est le meme objet pour un fichier corrompu et
        pour un garde de complexite. La liste de marqueurs est donc volontairement
        ETROITE — deux libelles, tous deux ceux du plafond d'instanciation de
        librsvg — pour ne jamais requalifier en refus une vraie defaillance, qui
        doit rester ``derivation_failed`` avec son ``error``.
    """
    text = str(exc).lower()
    return any(marker in text for marker in _SVG_COMPLEXITY_MARKERS)


def _scan_svg(content: bytes) -> tuple:
    """
    Trie un SVG par scan d'octets, JAMAIS par parsing XML.

    Le parsing est refuse volontairement : un master SVG peut etre malforme,
    enorme, ou porter des entites externes ; un scan ne peut ni lever ni couter
    cher.

    Args:
        content: Octets du SVG.

    Returns:
        tuple[bool, bool]: (contient du texte, enveloppe un raster en data: URI).
    """
    # latin-1 ne leve jamais et preserve les octets 1:1 ; on abaisse la casse
    # pour attraper aussi <textPath>/<altGlyph> et les proprietes CSS.
    text = content.decode("latin-1", errors="ignore").lower()
    has_text = any(pattern in text for pattern in SVG_TEXT_PATTERNS)
    wraps_raster = ("<image" in text) and bool(SVG_DATA_HREF_RE.search(text))
    return has_text, wraps_raster


def _slug(key: str) -> str:
    """
    Sanitise ``key`` exactement comme ``downloader._build_logo_filename``.

    Args:
        key: Cle du logo portee par le message RabbitMQ.

    Returns:
        str: Slug sans caractere hors [A-Za-z0-9_-].

    Note:
        REGLE REELLE du depot : ``re.sub(r'[^A-Za-z0-9_-]', '_', key)``. Donc
        PAS de lower(), remplacement par SOULIGNE, et le POINT est remplace lui
        aussi ('acme.fr' -> 'acme_fr'). La spec de la recette annoncait
        « minuscules + classe [a-z0-9._-] + remplacement par tiret » : c'est
        faux sur les trois points, et s'en servir ferait diverger le nom du
        derive de celui du master ``logo-{slug}{ext}`` sur tout domaine
        contenant un point, c'est-a-dire tous. Le slug « produit »
        (image_processor._normalize_name) ne concerne pas les logos.

        BORNE ajoutee : le nom du derive ajoute 35 caracteres a celui du master,
        donc une cle qui tenait dans ``logo-{slug}{ext}`` pouvait deborder de
        NAME_MAX (255) et d'un VARCHAR(255) dans le derive (mesure : cle de 400
        caracteres -> nom de 440). La troncature est deterministe, donc le nom
        reste adresse par contenu.
    """
    return re.sub(r'[^A-Za-z0-9_-]', '_', key)[:MAX_SLUG_LEN]


def _content_key(content_hash: str) -> str:
    """
    Calcule le h12 du nommage adresse par contenu.

    Args:
        content_hash: sha256 des octets REELLEMENT heberges (celui du master).

    Returns:
        str: 12 caracteres hexadecimaux.

    Note:
        ``sha256(f"{content_hash}|{RECIPE}")[:12]``. C'est ce qui rend vrai le
        Cache-Control immutable de 30 jours du CDN : une URL de derive ne doit
        JAMAIS etre reutilisee pour d'autres octets. Un content_hash vide est
        donc une erreur dure, pas un cas a rattraper silencieusement.
    """
    return hashlib.sha256("{0}|{1}".format(content_hash, RECIPE).encode("utf-8")).hexdigest()[:12]


def _variant_filename(slug: str, h12: str, variant: str) -> str:
    """Construit ``logo-{slug}--{h12}-{recipe}-{variant}.png``."""
    return "logo-{0}--{1}-{2}-{3}.png".format(slug, h12, RECIPE, variant)


# =============================================================================
# Helpers — pyvips
# =============================================================================

def _normalize(im):
    """
    Ramene une image a du sRGB 8 bits a 4 bandes, dans le BON ordre (P4).

    Args:
        im: Image pyvips fraichement chargee.

    Returns:
        pyvips.Image: srgb, uchar, exactement 4 bandes.

    Note:
        ``colourspace("srgb")`` D'ABORD : c'est le seul test correct contre le
        CMYK (4 bandes, hasalpha() False) et contre les images 2 bandes
        'multiband' ou ``hasalpha()`` ment. Il rescale aussi correctement un PNG
        16 bits (alpha comprise : verifie, 32896 -> 128). ``addalpha()`` ne sert
        plus qu'aux sources opaques.

        CORRIGE le 31/08 : l'alpha est la DERNIERE bande, pas la 4e.
        ``extract_band(0, n=4)`` sur une image sRGB a 5 bandes promouvait la
        bande surnumeraire au rang d'alpha et jetait la vraie (mesure : R=10
        G=20 B=30 extra=99 alpha=255 -> [10, 20, 30, 99], soit 61 % de
        transparence inventee).

        LIMITE ASSUMEE, mesuree : ``cast("uchar")`` clippe au lieu de rescaler,
        mais forcer ``colourspace("srgb")`` sur le format n'y change RIEN —
        libvips clippe exactement pareil quand l'interpretation est DEJA 'srgb'
        (mesure : srgb/float [300, 500, 700] -> [255, 255, 255] par colourspace
        comme par cast ; srgb/ushort idem). Il n'y a pas d'echelle a deviner
        pour un 'srgb' hors bornes. Le cas reste inatteignable depuis un master
        reel : les loaders PNG/JPEG rendent 'rgb16'/'grey16', que
        ``colourspace`` rescale bien (verifie : alpha 32896 -> 128).
    """
    if im.interpretation != "srgb":
        im = im.colourspace("srgb")
    if not im.hasalpha():
        im = im.addalpha()
    if im.bands > 4:
        # sRGB + alpha + canaux surnumeraires (rare) : 3 bandes chromatiques
        # plus la DERNIERE bande comme alpha, sinon pngsave ecrirait des bandes
        # etrangeres et l'alpha serait fausse.
        im = im.extract_band(0, n=3).bandjoin(im.extract_band(im.bands - 1))
    if im.format != "uchar":
        im = im.cast("uchar")
    return im


def _pct(mask):
    """
    Convertit un masque relationnel pyvips en pourcentage (P5).

    Args:
        mask: Resultat d'une comparaison pyvips (valeurs 0 ou 255).

    Returns:
        float: Part de pixels vrais, en pourcentage.
    """
    return mask.avg() / 255.0 * 100.0


def _count(mask, npix):
    """Compte les pixels vrais d'un masque 0/255 (P5)."""
    return mask.avg() / 255.0 * npix


def _luma(im):
    """Luminance Rec.709 des 3 premieres bandes (alpha ignoree)."""
    return (im.extract_band(0) * LUMA_R
            + im.extract_band(1) * LUMA_G
            + im.extract_band(2) * LUMA_B)


def _conditional_mean_rgb(im, selection, n_selected):
    """
    Moyenne RGB sur un sous-ensemble de pixels designe par un masque 0/255.

    Args:
        im:          Image srgb 4 bandes.
        selection:   Masque 0/255 des pixels a moyenner.
        n_selected:  Nombre de pixels selectionnes (deja calcule).

    Returns:
        list[float] | None: [R, G, B] moyens, ou None si la selection est vide.
    """
    if n_selected <= 0:
        return None
    npix = im.width * im.height
    weight = selection / 255.0
    return [(im.extract_band(band) * weight).avg() * npix / n_selected for band in range(3)]


def _svg_render(content, target):
    """
    Rasterise un SVG A LA TAILLE CIBLE (P1 : jamais ``size="down"`` ici).

    Args:
        content: Octets du SVG.
        target:  Arete cible du rendu (le ratio est preserve).

    Returns:
        pyvips.Image: rendu normalise, materialise en memoire.

    Note:
        C'est l'unique agrandissement legitime de la recette : rendre un vecteur
        a 200 px n'est pas un upscale, c'est une rasterisation a la bonne
        resolution. Passer ``size="down"`` ici ferait sortir un SVG declare
        32x32 en 32x32 (mesure).
    """
    target = max(1, int(target))
    raw = pyvips.Image.thumbnail_buffer(content, target, height=target)
    # P3 : la sortie de thumbnail_buffer doit etre materialisee avant les mesures
    # multiples (find_trim + plusieurs avg()), sinon « out of order read ».
    return _normalize(raw).copy_memory()


def _has_binary_transparency(im):
    """
    Dit si l'alpha de ``im`` est REELLEMENT binaire et REELLEMENT utilisee.

    Args:
        im: Image de travail normalisee (srgb, 4 bandes, en memoire).

    Returns:
        bool: True s'il existe au moins un pixel transparent ET aucune valeur
        d'alpha intermediaire.

    Note:
        C'est la definition d'une matte 1 bit, et le seul predicat qui justifie
        ``gif_1bit``. Le loader ``gifload_buffer`` ne la porte PAS : il est vrai
        de tout GIF, transparent ou non. Le test est fait sur l'image de TRAVAIL
        parce que c'est elle qui sera cadree puis posee : si notre propre
        reduction a lisse la matte, l'alpha n'est plus binaire et la plaque ne
        crenellera plus — le flag doit alors tomber, pas survivre a la mesure
        qui le contredit.
    """
    alpha = im.extract_band(3)
    if alpha.min() > ALPHA_INK_THRESHOLD:
        return False  # aucun pixel transparent : rien a mater
    intermediate = (alpha > ALPHA_INK_THRESHOLD) & (alpha < ALPHA_OPAQUE_LIMIT)
    return intermediate.max() == 0


def _load_raster(content):
    """
    Charge un raster en shrink-on-load, borne en memoire.

    Args:
        content: Octets du master.

    Returns:
        tuple: (image de travail normalisee, facteur d'echelle travail/master,
        liste de flags poses au chargement).

    Note:
        Le passage systematique par ``thumbnail_buffer(..., size="down")``
        garantit trois choses d'un coup : shrink-on-load (memoire), rotation
        EXIF appliquee, et gestion couleur (un JPEG CMYK ressort deja en sRGB).
        Une image plus petite que la cible n'est PAS agrandie (P1).
        Le facteur est calcule sur l'arete MAXIMALE des deux images : cette
        grandeur est invariante par rotation EXIF, contrairement a la largeur.
    """
    flags = []

    # Sonde : dimensions + loader, sans travail sur les pixels.
    probe = pyvips.Image.new_from_buffer(content, "")
    is_gif = (probe.get_typeof("vips-loader") != 0
              and probe.get("vips-loader") == "gifload_buffer")

    source_max_edge = max(probe.width, probe.height)
    target = min(source_max_edge, MAX_WORK_EDGE) if source_max_edge > 0 else MAX_WORK_EDGE

    work = pyvips.Image.thumbnail_buffer(content, target, height=target, size="down")
    work = _normalize(work).copy_memory()  # P3

    if is_gif and _has_binary_transparency(work):
        # Transparence 1 bit REELLE : les escaliers viennent de la matte, pas du
        # fond, et ils crenelleront donc aussi sur une plaque. Le loader seul ne
        # suffit PAS a le dire (correctif) : il est vrai de tout GIF, y compris
        # d'un GIF entierement OPAQUE (mesure : GIF 400x400 sans aucune
        # transparence -> loader gifload_buffer, bands=3, hasalpha() False,
        # alpha reconstruite a 255 partout). Le flag posait alors gif_1bit sur
        # un visuel sans matte, la plaque etait refusee, ``no_usable_variant``
        # (BLOQUANT) tombait, et le MEME visuel etait donc publie en PNG et
        # ECARTE en GIF a pixels identiques : la decision de publication
        # dependait du format du conteneur, pas du contenu.
        flags.append("gif_1bit")

    work_max_edge = max(work.width, work.height)
    scale = (float(work_max_edge) / float(source_max_edge)) if source_max_edge > 0 else 1.0
    if scale <= 0:  # garde-fou : le facteur sert de diviseur chez l'appelant
        scale = 1.0
    return work, scale, flags


def _line_span(line, length, horizontal):
    """
    Premier et dernier index non nul d'une projection de 1 px d'epaisseur.

    Args:
        line:       Projection pyvips (1 x length ou length x 1).
        length:     Nombre d'echantillons.
        horizontal: True si la projection est couchee (1 ligne, length colonnes).

    Returns:
        tuple[int, int] | None: (premier, dernier) index non nul, ou None si la
        projection est entierement nulle.

    Note:
        Recherche DICHOTOMIQUE sur le predicat « le prefixe (resp. le suffixe)
        contient au moins un echantillon non nul », qui est monotone meme quand
        la projection ne l'est pas. Cout : ~2 x log2(length) appels ``max()`` sur
        une image de 1 px de haut, soit une vingtaine d'operations triviales.
        On evite ainsi une boucle Python par pixel ET un import supplementaire
        (``array``/``struct``/numpy) : le module n'importe que stdlib + pyvips,
        et le test qui l'enumere doit rester vrai.
    """
    def _slice_max(start, count):
        if horizontal:
            return line.extract_area(start, 0, count, 1).max()
        return line.extract_area(0, start, 1, count).max()

    if length <= 0 or line.max() <= 0:
        return None

    low, high = 0, length - 1
    while low < high:
        middle = (low + high) // 2
        if _slice_max(0, middle + 1) > 0:
            high = middle
        else:
            low = middle + 1
    first = low

    low, high = first, length - 1
    while low < high:
        middle = (low + high + 1) // 2
        if _slice_max(middle, length - middle) > 0:
            low = middle
        else:
            high = middle - 1
    return first, low


def _projection_bbox(mask):
    """
    Boite englobante EXACTE d'un masque 0/255, par projection (P12).

    Args:
        mask: Masque relationnel pyvips a 1 bande (0 ou 255).

    Returns:
        tuple | None: (left, top, width, height), ou None si le masque est vide.

    Note:
        ``project()`` somme les colonnes puis les lignes en UNE passe C sur une
        image deja en memoire : la boite obtenue est exacte, contrairement a
        celle de ``find_trim`` qui sous-echantillonne (P12). Sert de
        contre-mesure, jamais de remplacement pur : le median 3x3 de
        ``find_trim`` ignore la poussiere isolee d'un scan, ce qu'une projection
        exacte ne fait pas.
    """
    columns, rows = mask.project()
    horizontal_span = _line_span(columns, mask.width, True)
    vertical_span = _line_span(rows, mask.height, False)
    if horizontal_span is None or vertical_span is None:
        return None
    left, right = horizontal_span
    top, bottom = vertical_span
    return (left, top, right - left + 1, bottom - top + 1)


def _crosschecked_box(found, mask, width, height):
    """
    UNIT la boite de ``find_trim`` et la boite exacte du masque (P12).

    Args:
        found:  Boite rendue par ``find_trim`` (left, top, w, h), ou None si
                l'appel a ete refuse.
        mask:   Masque 0/255 de l'encre, 1 bande.
        width:  Largeur de l'image de travail.
        height: Hauteur de l'image de travail.

    Returns:
        tuple | None: boite retenue, ou None si le masque ne contient aucune
        encre.

    Note:
        La boite de ``project()`` est EXACTE : elle CONTIENT toute l'encre, par
        construction. Il n'y a donc aucune raison de lui preferer une boite plus
        petite, et l'UNION des deux est la seule combinaison qui ne puisse
        jamais perdre de pixel : elle contient l'exacte (rien n'est tronque) et
        elle contient celle de ``find_trim`` (dont le median 3x3 peut deborder
        d'une ligne sur du texte antialiase — mesure : couverture 101,2 %).

        CORRIGE : la version precedente comparait les seules AIRES et gardait
        la boite de ``find_trim`` des qu'elle couvrait 90 % de l'aire exacte,
        SANS jamais verifier la CONTENANCE. Une troncature jusqu'a 10 % de
        l'aire d'encre etait donc publiee sans aucun flag, sous une URL
        immutable 30 jours (mesure : bloc de marque plein sur y=0..359 +
        baseline hachuree 1 px / gap 2 px sur y=365..398 dans un 400x400 ->
        boite exacte (0, 0, 400, 399), boite publiee (0, 0, 400, 360),
        couverture 90,2 % donc acceptee, et la baseline DISPARAISSAIT du
        sq200a). Le seuil d'aire a disparu avec le defaut.

        Les deux issues deja corrigees avant lui tiennent toujours (cf. P12) :
          (a) ``find_trim`` rend une boite VIDE alors que le masque porte de
              l'encre (code-barres a 33 % d'encre) : l'union vaut la boite
              exacte, sinon le logo est ecarte par ``ink_too_small``, bloquant ;
          (b) ``find_trim`` tronque (lockup hachure : 2/3 du logo hors boite) :
              l'union restaure les 2/3 perdus.
    """
    exact = _projection_bbox(mask)
    if exact is None:
        return found if (found is not None and found[2] > 0 and found[3] > 0) else None
    if found is None or found[2] <= 0 or found[3] <= 0:
        return exact

    left = min(int(found[0]), exact[0])
    top = min(int(found[1]), exact[1])
    right = max(int(found[0]) + int(found[2]), exact[0] + exact[2])
    bottom = max(int(found[1]) + int(found[3]), exact[1] + exact[3])
    union = (left, top, right - left, bottom - top)
    if union != tuple(int(value) for value in found):
        logger.info(
            "logo_derive: boite de find_trim %s elargie a l'union %s avec la "
            "boite exacte %s dans %sx%s",
            found, union, exact, width, height,
        )
    return union


def _ink_bbox(im, allow_trim_degenerate=True, allow_ink_min_area=True):
    """
    Delimite la boite d'encre (etape 4).

    Args:
        im: Image de travail normalisee (srgb, 4 bandes).
        allow_trim_degenerate: applique la regle « trim retirant plus de 95 % ».
            Doit valoir False sur la branche VECTEUR (P11) : le cadre d'un rendu
            vectoriel est choisi par ce module, il ne prouve rien sur l'image.
        allow_ink_min_area: applique le seuil RELATIF ``INK_MIN_AREA_PCT``.
            Doit valoir False sur la branche VECTEUR, pour la meme raison de
            circularite que ``allow_trim_degenerate`` — et en pire : le rapport
            encre/cadre d'un rendu vectoriel est INVARIANT D'ECHELLE, donc aucun
            supersampling ne pourra jamais le faire passer (mesure : artboard
            800 / marque 60 -> variants=[] + ink_too_small, flag BLOQUANT, et le
            supersampling ne se declenchait meme pas puisque la 1re passe
            rendait None). La boite VIDE reste refusee dans tous les cas.

    Returns:
        tuple: (boite de CADRAGE ou None, boite de MESURE ou None, liste de
        flags, part de pixels non opaques en %). Les deux boites sont identiques
        sauf quand le trim est refuse (``trim_degenerate`` / ``baked_background``) :
        le cadrage garde alors le cadre entier, mais la MESURE doit continuer a
        porter sur la vraie encre.

    Note:
        P2 : la bbox alpha se calcule sur la BANDE ALPHA EXTRAITE, jamais par
        ``find_trim`` sur du RGBA — celui-ci aplatit contre blanc et recadre a
        vide precisement les logos en version blanche (205 lignes, la population
        la plus sensible du chantier). Et ``find_trim`` ne leve pas : il signale
        par width/height == 0 en laissant left/top aux dimensions de l'image.
        P12 : sa boite est ensuite CROISEE avec la boite exacte du masque.
        P13 : sous 3 px d'arete il LEVE, on ne l'appelle donc pas.
    """
    flags = []
    width, height = im.width, im.height
    full_area = width * height
    alpha = im.extract_band(3)
    alpha_used_pct = _pct(alpha < ALPHA_OPAQUE_LIMIT)

    if width < MIN_TRIM_EDGE or height < MIN_TRIM_EDGE:
        # P13 : find_trim leverait (« rank: window too large »), et le worker
        # recevrait un derivation_failed avec un message libvips cryptique en
        # base la ou ink_too_small (error=None) est la reponse honnete : une
        # arete de moins de 3 px ne porte aucune vignette.
        flags.append("ink_too_small")
        return None, None, flags, alpha_used_pct

    uniform_opaque = False
    if alpha_used_pct > ALPHA_USED_PCT_MIN:
        mask = alpha > ALPHA_INK_THRESHOLD
        found = tuple(alpha.find_trim(threshold=ALPHA_INK_THRESHOLD, background=[0]))
    else:
        # Source opaque : trim par consensus des 4 coins.
        corners = [im(0, 0), im(width - 1, 0), im(0, height - 1), im(width - 1, height - 1)]
        channels = [[c[band] for c in corners] for band in range(3)]
        agree = all(
            (max(values) - min(values)) <= OPAQUE_CORNER_TOLERANCE for values in channels
        )
        if not agree:
            # Les coins divergent : le fond n'est pas uniforme, le derive
            # centrerait un rectangle de fond etranger. On garde le cadre entier.
            # Le fond fait alors partie du logo : cadrage ET mesure portent sur
            # le cadre, il n'y a pas d'encre distincte a isoler.
            flags.append("baked_background")
            return (0, 0, width, height), (0, 0, width, height), flags, alpha_used_pct
        background = [sum(values) / float(len(values)) for values in channels]
        rgb = im.extract_band(0, n=3)
        # Meme predicat que find_trim(threshold, background) : max|canal - fond|.
        mask = ((rgb - background).abs() > OPAQUE_TRIM_THRESHOLD).bandor()
        found = tuple(rgb.find_trim(threshold=OPAQUE_TRIM_THRESHOLD, background=background))
        uniform_opaque = True

    # P12 : ne jamais faire confiance seule a find_trim.
    box = _crosschecked_box(found, mask, width, height)

    if box is None:
        if uniform_opaque:
            # Les 4 coins concordent ET aucun pixel ne s'ecarte du fond : l'image
            # est UNIFORME. La bonne conclusion n'est pas « on n'a pas su lire
            # l'encre » (ink_too_small, flag BLOQUANT, aucun derive) mais « pas
            # d'encre distincte du fond », qui appelle le meme traitement que des
            # coins divergents : cadre entier + baked_background. Mesure du
            # defaut : PNG 300x300 uni #123456 -> variants=[], et idem pour un
            # SVG dont un <rect> couvre tout le viewBox.
            flags.append("baked_background")
            return (0, 0, width, height), (0, 0, width, height), flags, alpha_used_pct
        flags.append("ink_too_small")
        return None, None, flags, alpha_used_pct

    left, top, box_w, box_h = box
    # Ceinture : la boite peut toucher la limite du cadre, et extract_area LEVE
    # hors cadre (« bad extract area »).
    left = max(0, min(int(left), width - 1))
    top = max(0, min(int(top), height - 1))
    box_w = max(1, min(int(box_w), width - left))
    box_h = max(1, min(int(box_h), height - top))
    box = (left, top, box_w, box_h)
    box_area = box_w * box_h
    short_edge = min(box_w, box_h)

    if (allow_ink_min_area
            and box_area < full_area * INK_MIN_AREA_PCT / 100.0
            and short_edge < INK_MIN_EDGE_ABSOLUTE):
        # Encre derisoire : aucun derive. Cette regle PRIME sur trim_degenerate
        # (les deux plages se recouvrent : sous 1 %, le trim retire aussi plus de
        # 95 %). Le plancher ABSOLU l'empeche de rejeter un logo largement
        # definissable au seul motif que son cadre transparent est grand.
        flags.append("ink_too_small")
        return None, None, flags, alpha_used_pct

    if allow_trim_degenerate and box_area < full_area * TRIM_DEGENERATE_AREA_PCT / 100.0:
        # P11 : desactive sur la branche vecteur, ou « garder le cadre entier »
        # reviendrait a publier la marge du viewBox (violation de la marge 0).
        # La boite de MESURE reste la vraie encre : mesurer sur un cadre a 98 %
        # transparent decrivait le fond, pas l'encre — exactement le biais que
        # l'etape 5 doit eviter (mesure : cadre 4000 / encre BLANCHE 500 ->
        # surface « unknown » au lieu de dark_required, et l'encre sombre du
        # meme cadre recevait un flag « pale » faux).
        flags.append("trim_degenerate")
        return (0, 0, width, height), box, flags, alpha_used_pct

    return box, box, flags, alpha_used_pct


def _measure_surface(crop):
    """
    Mesure la surface exigee par l'encre (etape 5), SUR LA BOITE RECADREE.

    Args:
        crop: Boite d'encre extraite de l'image de travail (srgb, 4 bandes).

    Returns:
        dict: alpha_ratio, ink_on_white, ink_on_black (en %) et is_light (bool).

    Note:
        Mesurer sur l'image brute serait tricher : un JPG blanc-sur-noir
        compterait son propre rectangle noir comme de l'encre et sortirait
        « any ». Tous les pourcentages passent par _pct (P5).
        ``is_light`` se lit sur les bandes BRUTES (non composees) des seuls
        pixels opaques : c'est la clarte de l'encre elle-meme, pas celle du fond
        de composition.
    """
    npix = crop.width * crop.height
    alpha = crop.extract_band(3)

    alpha_ratio = _pct(alpha < ALPHA_OPAQUE_LIMIT)
    ink_on_white = _pct(_luma(crop.flatten(background=[255, 255, 255])) < LUM_INK_ON_WHITE_MAX)
    ink_on_black = _pct(_luma(crop.flatten(background=[0, 0, 0])) > LUM_INK_ON_BLACK_MIN)

    opaque = alpha >= OPAQUE_ALPHA_MIN
    n_opaque = _count(opaque, npix)
    if n_opaque > 0:
        light_and_opaque = ((_luma(crop) > LIGHTNESS_LEVEL) / 255.0) * (opaque / 255.0)
        n_light = light_and_opaque.avg() * npix
        is_light = (n_light / n_opaque) >= LIGHTNESS_COVERAGE
    else:
        is_light = False

    return {
        "alpha_ratio": alpha_ratio,
        "ink_on_white": ink_on_white,
        "ink_on_black": ink_on_black,
        "is_light": bool(is_light),
    }


def _surface_verdict(measures, self_background=False):
    """
    Rend le verdict de surface (etape 6), dans l'ordre exact de la recette.

    Args:
        measures: Sortie de :func:`_measure_surface`.
        self_background: True quand la SOURCE est opaque et porte donc son
            propre fond CUIT (cf. :func:`_ink_bbox` : soit l'alpha n'est pas
            reellement utilisee, soit le trim a ete tranche par consensus des
            coins, soit le fond a ete declare partie du logo).

    Returns:
        tuple[str, list[str]]: (verdict, flags additionnels).

    Note:
        AMENDEMENT du 31/08 a la regle 1, arbitre par le porteur du chantier.
        « alpha_ratio < 10 % => any » s'appliquait SANS regarder la couleur de
        l'encre : un logotype BLANC PLEIN (ou un badge blanc a coins arrondis)
        n'a pas de fond, c'est de l'encre claire opaque. Il sortait donc « any »
        avec ink_on_white = 0,00, c'est-a-dire declare utilisable sur le cadre
        #FFFFFF de la carte alors que 0 % de ses pixels y sont visibles, et sans
        aucun flag — exactement la population que le chantier existe pour sauver
        (205 logos invisibles sur blanc). La regle ne s'applique donc plus que si
        l'encre est REELLEMENT visible sur blanc ; sinon les regles suivantes
        tranchent, le cas bascule en ``dark_required``, et la plaque est
        produite. Non-regression verifiee sur les 6 cas legitimement « any » du
        depot : jpeg_opaque 78,62 ; jpeg_cmyk 100 ; png_fond_opaque_blanc 100 ;
        png_fond_opaque_colore 100 ; png_palette 100 ; png_gris_1_bande 78,43.

        CORRECTIF du meme amendement : la condition sur ``on_white`` seule etait
        TROP LARGE. Elle faisait aussi basculer en ``dark_required`` des logos
        OPAQUES qui portent leur PROPRE FOND CLAIR CUIT et dont l'encre est
        rare — cas ou le taux d'encre ne dit RIEN de la lisibilite, puisque le
        fond du logo le porte (mesure : PNG 400x400 blanc opaque + filet sombre
        de 2/3/4 px -> ink_on_white 0,88 / 1,25 / 1,63 % -> dark_required, donc
        une plaque sombre sous un logo a fond blanc, et ``no_usable_variant``
        BLOQUANT des que la plaque etait refusee, par exemple en GIF).
        L'intention de l'amendement visait les logos TRANSPARENTS a encre
        claire : un logo opaque n'est jamais invisible, son fond le porte. D'ou
        ``self_background``, qui ROUVRE la regle 1 pour eux seuls. La population
        du chantier (logotype BLANC PLEIN sur TRANSPARENT) n'est pas touchee :
        son alpha est reellement utilisee au niveau de la SOURCE, donc
        ``self_background`` y vaut False et le verdict reste ``dark_required``.

        CORRECTIF du 02/09/2026 : la regle 3 compare desormais ``on_white`` a
        :data:`INK_ON_WHITE_STRONG` (8) et non plus a
        :data:`INK_ON_WHITE_WEAK` (2). Elle laissait un TROU exactement large
        de la bande ``pale`` : pour 2 <= on_white < 8, la regle 2 echoue
        (elle exige on_white >= 8), la regle 3 echouait aussi (elle exigeait
        on_white < 2) et la regle 4 echoue des que l'encre est franche sur
        noir (elle exige on_black < 2). Il ne restait que le repli
        ``unknown`` — donc AUCUNE plaque (l'etape 8 ne s'arme que sur
        ``dark_required``), AUCUN flag bloquant, et un logo qu'on ne voit pas
        declare publiable.

        Le cas qui l'a montre est witeck.fr (domaine 4621), sorti du backfill
        du 02/09 en ``outcome=ok surface=unknown publishable=oui flags=pale``
        alors que sa vignette est VIDE sur le damier de l'ecran de validation
        comme dans la carte blanche du front. Mesure de son master :
        ink_on_white 4,83 / ink_on_black 29,10 / alpha_ratio 77,36 — un
        logotype tres pale, invisible sur blanc et FRANC sur noir, c'est-a-dire
        la definition meme de ``dark_required``.

        Ce que devient ``unknown`` : la SPEC (artifact « Cadre 200 et fond des
        logos », section 06) le reserve aux « 2 irrecuperables » — invisible
        sur blanc ET sur noir. C'est ce que la regle rend enfin vrai : les
        regles 1 a 4 couvrent desormais tout le plan (on_white, on_black) SAUF
        le coin on_white < 2 ET on_black < 2, et ce coin est le seul repli.
        Cf. le test d'enumeration qui verrouille cet invariant.
        A NOTER : ``metrics["surface"]`` vaut aussi ``"unknown"`` par DEFAUT
        quand la derivation s'arrete AVANT l'etape 6 (``svg_text``,
        ``svg_too_complex``, ``ink_too_small``, ``derivation_failed``) ; ces
        lignes portent alors un flag BLOQUANT, elles ne sont donc jamais un
        « unknown publiable ». L'invariant porte sur le VERDICT rendu ici.

        La bande pale n'est pas perdue pour autant : le flag ``pale`` reste
        pose independamment du verdict, et continue de dire « encre visible
        mais tenue sur blanc » a l'audit.

        MESURE de la bascule (02/09/2026), en derivant 913 masters REELS du
        parc avec ce module, AVANT puis APRES le changement de seuil : 74
        lignes basculent ``unknown`` -> ``dark_required``, et il ne reste 0
        ``unknown`` rendu par cette fonction. Population : les 426 domaines
        dont la revue du 27/08 mesure la visibilite sur blanc sous 16 %, les 6
        lignes scrapees apres cette revue, et un tirage ALEATOIRE de 500 sur
        les 3763 — ce tirage n'a trouve AUCUNE bascule hors du recensement, et
        sur ses 435 masters au-dela de 16 % aucun n'a meme ``on_white`` < 8.
        Il extrapole 2,21 % du parc, soit 83 lignes, cadrant les 74 recensees.

        Le doute « et un logo mediocre PARTOUT ? » est tranche par la mesure
        et non par le raisonnement : sur ces 74 cas, on_white va de 2,07 a
        7,89 et on_black de 9,06 a 87,34 ; le rapport on_black/on_white vaut
        6,25x en median et ne descend jamais sous 2,03x ; il n'existe AUCUN
        cas ou on_black <= on_white, ni aucun ou on_black < 8. Les deux
        garde-fous envisages sont donc soit inertes, soit nuisibles :
        « on_black > on_white » ne change RIEN (0 divergence sur les 906
        verdicts rendus), et « on_black >= 8 » ferait REGRESSER un cas deja
        correct — soudax.com (on_white 0,00 / on_black 3,90), aujourd'hui
        ``dark_required``, repasserait en ``unknown``. Aucune condition
        supplementaire n'est donc retenue : le seul seuil deplace suffit.

        CONSEQUENCE A CONNAITRE, mesuree elle aussi : sur les 74 bascules, 57
        gagnent leur plaque et restent publiables (c'est le but), 10 etaient
        DEJA refusees par ``elongated`` (le verdict n'y change que l'audit),
        et 7 PASSENT DE PUBLIABLE A REFUSEES. Ces 7 ont un bord de matte
        suspect : l'etape 8 refuse la plaque, donc ``no_usable_variant`` tombe
        et il est BLOQUANT. Ce n'est pas une regression du seuil mais la
        politique de plaque qui s'applique enfin a une population qui
        court-circuitait l'etape 8 (``matte_suspect`` n'y etait meme jamais
        mesure) ; et refuser vaut mieux que publier une vignette vide, ce que
        le defaut faisait pour les 74. Les 7 : cabs-industries.com,
        distributeur-automatique-lot-...com, etancogroup.com,
        hexagone-air-concept.com, lanef-pro.fr, sachot-acces.fr, valtra.fr.

        INVARIANT VERIFIE sur ces 913 masters, et non suppose : les 900 qui
        produisent une ``sq200a`` la produisent au MEME nom et aux MEMES
        octets (0 ecart de sha256, 0 ecart de taille) avant et apres, et
        aucune ``sq200d`` preexistante ne change d'octets. Le verdict ne peut
        pas deplacer la variante principale : elle est construite et encodee
        AVANT l'etape 8. C'est ce qui rend ce correctif compatible avec le
        ``Cache-Control: immutable`` de 30 jours du CDN et dispense de bumper
        :data:`RECIPE` — 67 plaques apparaissent, rien n'est renomme.
    """
    alpha_ratio = measures["alpha_ratio"]
    on_white = measures["ink_on_white"]
    on_black = measures["ink_on_black"]
    flags = []

    if (alpha_ratio < ALPHA_RATIO_SELF_BACKGROUND
            and (on_white >= INK_ON_WHITE_WEAK or self_background)):
        surface = "any"                      # le logo porte deja son fond
    elif on_white >= INK_ON_WHITE_STRONG and on_black >= INK_ON_BLACK_WEAK:
        surface = "any"
    elif on_white < INK_ON_WHITE_STRONG and on_black >= INK_ON_BLACK_WEAK:
        surface = "dark_required"            # pas lisible sur blanc, franc sur noir
    elif on_black < INK_ON_BLACK_WEAK and on_white >= INK_ON_WHITE_WEAK:
        surface = "light_required"           # invisible sur noir
    else:
        surface = "unknown"

    # Regle independante du verdict : encre visible mais tenue sur blanc.
    if INK_ON_WHITE_WEAK <= on_white < INK_ON_WHITE_STRONG:
        flags.append("pale")

    return surface, flags


def _fit(im, target, allow_upscale):
    """
    Met l'encre a l'echelle en CONTAIN, sans marge propre.

    Args:
        im:            Boite d'encre (srgb, 4 bandes, en memoire).
        target:        Arete de la boite d'accueil.
        allow_upscale: True uniquement pour un vecteur rasterise.

    Returns:
        tuple: (image mise a l'echelle, agrandissement REFUSE, agrandissement
        raster REELLEMENT applique).

    Note:
        Le non-agrandissement est impose PAR L'APPEL pyvips (``size="down"``),
        pas par une convention commentee (P1). La marge est nulle : le
        conteneur d'affichage porte deja padding:5px, une marge dans le canvas
        s'y ajouterait.
        Le 3e retour existe parce que ``no_upscale`` etait structurellement
        impossible sur la branche vecteur (il teste ``not allow_upscale``) : un
        crop de rendu vectoriel agrandi en Lanczos jusqu'a 200 px sortait donc
        FLOU sans aucun flag (mesure : artboard 800 / marque 100 -> 30 niveaux
        de gris la ou le meme damier rendu au vecteur n'en donne que 2, et
        metrics['flags'] == []). L'appelant en fait ``vector_upscaled``.
    """
    source_long_edge = max(im.width, im.height)
    if allow_upscale:
        fitted = im.thumbnail_image(target, height=target)
    else:
        fitted = im.thumbnail_image(target, height=target, size="down")

    fitted = _normalize(fitted).copy_memory()  # P3

    no_upscale = (not allow_upscale) and fitted.width < target and fitted.height < target
    upscaled = max(fitted.width, fitted.height) > source_long_edge

    # P6 : gravity recadrerait en silence. On verrouille ici, jamais plus tard.
    if fitted.width > target or fitted.height > target:
        logger.warning(
            "logo_derive: mise a l'echelle inattendue (%sx%s > %s), re-reduction defensive",
            fitted.width, fitted.height, target,
        )
        fitted = _normalize(
            fitted.thumbnail_image(target, height=target, size="down")
        ).copy_memory()

    return fitted, no_upscale, upscaled


def _alpha_bbox_size(im):
    """
    Dimensions de la boite d'encre REELLE d'une image finale.

    Args:
        im: Image posee (srgb, 4 bandes, en memoire).

    Returns:
        tuple[int, int]: (largeur, hauteur) de l'encre visible ; (0, 0) si
        l'image est entierement transparente.

    Note:
        Sert a calculer ``fill_pct``, qui se lisait sur les DIMENSIONS de
        l'image adaptee — toujours 200x200 apres un contain sur le cadre entier.
        Une vignette dont l'encre visible mesurait 30x30 px etait donc publiee
        avec fill_pct = 100 (mesures : cadre 1000/encre 200 -> 46 px ;
        2000/300 -> 36 ; 3000/500 -> 38 ; 4000/500 -> 30, tous a fill_pct = 100).
    """
    box = _projection_bbox(im.extract_band(3) > ALPHA_INK_THRESHOLD)
    if box is None:
        return 0, 0
    return box[2], box[3]


def _center_on_canvas(im):
    """
    Pose l'image au centre d'un canvas transparent EXACTEMENT 200x200 (etape 7).

    Raises:
        RuntimeError: si le canvas ne fait pas 200x200x4 (P6 : gravity recadre
            en silence, on refuse de publier une vignette tronquee).
    """
    if im.width == CANVAS and im.height == CANVAS:
        out = im
    else:
        out = im.gravity("centre", CANVAS, CANVAS, extend="background", background=[0, 0, 0, 0])
    if out.width != CANVAS or out.height != CANVAS or out.bands != 4:
        raise RuntimeError(
            "canvas inattendu {0}x{1}x{2} bandes".format(out.width, out.height, out.bands)
        )
    return out


def _png_bytes(im):
    """
    Sauvegarde en PNG, metadonnees nettoyees (P8/P9).

    Note:
        ``palette=False`` : pas de quantification. Alterer une couleur de marque
        pour quelques kilo-octets est precisement ce que les chartes de marque
        interdisent.
        Le profil ICC de la source survit a thumbnail et a colourspace, et
        ``colourspace`` ne CONVERTIT pas (P8) : on transforme donc reellement en
        sRGB par ``icc_transform`` AVANT de retirer le profil, sinon le PNG
        derive porte des pixels non-sRGB etiquetes sRGB. Le profil est ensuite
        retire par ``remove()`` sur une copie (l'option ``keep=`` n'existe qu'a
        partir de libvips 8.15 et une option inconnue LEVE, or l'image de prod
        embarque une 8.14.x). ``strip=True`` acheve le nettoyage : sans lui
        pngsave RESYNTHETISE un chunk eXIf a partir de la resolution (P9).
    """
    out = im.copy()

    if out.get_typeof("icc-profile-data") != 0:
        try:
            # P8 : conversion REELLE. Le profil peut etre corrompu ou refuse par
            # lcms : on retombe alors sur les pixels tels quels, comme avant.
            out = _normalize(
                out.icc_transform("srgb", embedded=True, intent="relative")
            ).copy_memory()
        except Exception as exc:
            logger.warning(
                "logo_derive: conversion ICC impossible (%s), pixels conserves tels quels",
                _short_error(exc),
            )
            out = im.copy()

    for field in list(out.get_fields()):
        if field.startswith("exif-") or field in _META_FIELDS_TO_DROP:
            out.remove(field)

    try:
        return out.pngsave_buffer(compression=9, palette=False, strip=True)
    except (TypeError, pyvips.Error):  # pragma: no cover - libvips sans `strip`
        logger.debug("logo_derive: pngsave_buffer sans option strip")
        return out.pngsave_buffer(compression=9, palette=False)


def _matte_is_suspect(crop):
    """
    Detecte un detourage dont le bord porte encore la teinte de l'ancien fond.

    Args:
        crop: Boite d'encre (srgb, 4 bandes, en memoire).

    Returns:
        bool: True si la plaque doit etre refusee.

    Note:
        Un logo blanc detoure sur une couleur saturee porte une frange de cette
        couleur, qui sur un neutre sombre apparait en lisere sale. On compare la
        SATURATION moyenne des pixels de bord (alpha partiel) a celle de
        l'interieur opaque : un assombrissement du bord (matte contre noir) est
        anodin sur une plaque sombre, une saturation qui apparait ne l'est pas.
        Un bord trop peu peuple (alpha quasi 1 bit) ne peut pas franger : test
        neutralise.
    """
    npix = crop.width * crop.height
    alpha = crop.extract_band(3)

    edge = (alpha > MATTE_EDGE_ALPHA_MIN) & (alpha < MATTE_EDGE_ALPHA_MAX)
    n_edge = _count(edge, npix)
    if n_edge < MATTE_MIN_EDGE_PIXELS:
        return False

    inner = alpha >= MATTE_EDGE_ALPHA_MAX
    n_inner = _count(inner, npix)
    if n_inner <= 0:
        return False

    mean_edge = _conditional_mean_rgb(crop, edge, n_edge)
    mean_inner = _conditional_mean_rgb(crop, inner, n_inner)
    if mean_edge is None or mean_inner is None:
        return False

    sat_edge = (max(mean_edge) - min(mean_edge)) / 255.0 * 100.0
    sat_inner = (max(mean_inner) - min(mean_inner)) / 255.0 * 100.0
    return sat_edge > MATTE_SAT_FLOOR_PCT and (sat_edge - sat_inner) > MATTE_SAT_DELTA_PCT


def _plate_image(logo, plate_color):
    """
    Compose le logo sur une plaque opaque a coins arrondis (etape 8).

    Args:
        logo:        Logo mis a l'echelle (srgb, 4 bandes), deja borne a la
                     boite d'accueil de la plaque.
        plate_color: Couleur de la plaque (R, G, B).

    Returns:
        pyvips.Image: plaque + logo, 4 bandes, alpha conservee.

    Note:
        La plaque epouse la boite d'encre plus une petite marge : elle ne prend
        PAS le ratio du conteneur, sinon l'artefact serait recouple a une carte
        unique. Les coins arrondis viennent d'un ``<rect rx ry>`` rasterise par
        librsvg (antialiasing propre, librsvg2-dev est bien dans le Dockerfile).
        ``composite2`` et non ``flatten`` : flatten consomme l'alpha et la
        plaque perdrait ses coins arrondis (P7 : les deux operandes doivent
        avoir une interpretation connue, d'ou new_from_image + copy(srgb)).
    """
    plate_w = min(CANVAS, logo.width + 2 * PLATE_PADDING)
    plate_h = min(CANVAS, logo.height + 2 * PLATE_PADDING)
    radius = max(0, min(PLATE_CORNER_RADIUS, min(plate_w, plate_h) // 4))

    rect_svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}">'
        '<rect x="0" y="0" width="{w}" height="{h}" rx="{r}" ry="{r}" fill="#ffffff"/>'
        '</svg>'
    ).format(w=plate_w, h=plate_h, r=radius).encode("ascii")

    rendered = pyvips.Image.svgload_buffer(rect_svg)
    if rendered.hasalpha():
        mask = rendered.extract_band(rendered.bands - 1)
    else:
        mask = rendered.colourspace("b-w")
    mask = mask.copy_memory()
    if mask.format != "uchar":
        mask = mask.cast("uchar")

    plate = (pyvips.Image.black(plate_w, plate_h)
             .new_from_image(list(plate_color))
             .copy(interpretation="srgb")
             .bandjoin(mask))

    offset_x = (plate_w - logo.width) // 2
    offset_y = (plate_h - logo.height) // 2
    return plate.composite2(logo, "over", x=offset_x, y=offset_y)


def _sanitize_plate_color(plate_color):
    """Valide/borne la couleur de plaque, sans jamais faire echouer le derive."""
    try:
        values = [int(round(float(component))) for component in tuple(plate_color)[:3]]
        if len(values) != 3:
            raise ValueError("3 composantes attendues")
        return tuple(max(0, min(255, value)) for value in values)
    except Exception:
        logger.warning(
            "logo_derive: plate_color invalide (%r), retour au defaut %r",
            plate_color, DEFAULT_PLATE_COLOR,
        )
        return DEFAULT_PLATE_COLOR


def _ordered_flags(flags):
    """
    Deduplique et trie les flags sur l'ordre de :data:`FLAG_ORDER`.

    Args:
        flags: Flags poses au fil du traitement, dans l'ordre d'insertion.

    Returns:
        list[str]: liste dedupliquee, triee, donc STABLE d'une execution a
        l'autre et d'un chemin de code a l'autre.

    Note:
        L'ordre d'insertion dependait du chemin parcouru : la meme image pouvait
        rendre deux chaines differentes dans la colonne SQL, ce qui casse tout
        regroupement d'audit. Un flag inconnu (impossible : liste fermee) serait
        renvoye en fin de liste plutot que de faire lever un tri.
    """
    unknown_rank = len(FLAG_ORDER)
    return sorted(set(flags), key=lambda flag: (_FLAG_RANK.get(flag, unknown_rank), flag))


def _variant(variant, slug, h12, image):
    """Emballe une variante prete a ecrire."""
    return {
        "variant": variant,
        "filename": _variant_filename(slug, h12, variant),
        "bytes": _png_bytes(image),
        "width": CANVAS,
        "height": CANVAS,
        "format": "png",
    }


# =============================================================================
# API publique
# =============================================================================

def derive_logo(content: bytes, key: str, content_hash: str) -> dict:
    """
    Produit les vignettes d'affichage 200x200 d'un logo deja heberge.

    Les octets produits ne dependent que de ``content`` et de :data:`RECIPE` —
    c'est exactement ce que le nom de fichier porte, et c'est ce qui rend vrai le
    ``Cache-Control: immutable`` de 30 jours du CDN. Aucun parametre d'appel ne
    peut plus les faire varier : la couleur de plaque, qui etait un argument
    public, est desormais la constante de recette :data:`DEFAULT_PLATE_COLOR`
    (mesure : deux ``plate_color`` differents produisaient le MEME nom de fichier
    avec des octets DIFFERENTS).

    Args:
        content:      Octets REELLEMENT heberges par ``process_logo``
                      (``result["bytes"]``, donc du PNG pour un ICO d'origine),
                      pas les octets telecharges bruts : c'est sur eux que porte
                      ``content_hash``.
        key:          Cle du logo (celle passee a ``_build_logo_filename``).
        content_hash: sha256 hexadecimal (64 caracteres) des octets ci-dessus.

    Returns:
        dict: ``{"variants": [...], "metrics": {...}, "error": None | str}``.
        Chaque variante porte ``variant``, ``filename``, ``bytes``, ``width``,
        ``height``, ``format``. ``metrics`` porte toujours les memes cles :
        recipe, libvips_version, source_hash, surface, flags, fill_pct,
        ratio_x100, master_width, master_height, ink_bbox, alpha_ratio,
        ink_on_white, ink_on_black, is_light.

    Note:
        Ne leve JAMAIS. Quatre sorties sans variante sont normales et non
        fautives : ``svg_text`` (aucune police dans le conteneur, le master SVG
        est preserve), ``svg_too_complex`` (refus de rasteriser — plafond
        d'octets OU refus de complexite de librsvg, cf. P14),
        ``ink_too_small`` (rien d'exploitable : soit aucune encre a cadrer,
        soit une encre AFFICHEE derisoire, cf.
        :data:`MIN_DISPLAYED_INK_EDGE`) et ``derivation_failed``
        (defaillance, ``error`` renseigne).
        ``master_width``/``master_height``/``ink_bbox`` sont exprimes dans le
        referentiel du MASTER (post-rotation EXIF) ; pour un SVG, dans celui du
        rendu de REFERENCE — la 1re passe a 200 px, PAS le rendu supersample
        finalement retenu : sans cette remise a l'echelle, deux SVG comparables
        ressortaient avec des dimensions et un gate ``low_res`` non comparables
        (mesure : le meme dessin sortait master 800x800 sans low_res ou
        200x200 avec low_res selon que librsvg acceptait de l'echelonner).
        La publication se decide sur :data:`BLOCKING_FLAGS` SEUL : le cas
        « dark_required sans plaque » y est represente par
        ``no_usable_variant``, il n'y a donc rien a croiser a la main.
    """
    # ``source_hash`` part dans une colonne prevue pour un sha256 : on n'y
    # recopie que ce qui EN A LA FORME. Un hash de 5000 caracteres ou un int
    # traversaient sinon jusqu'a l'INSERT, alors meme que le derive est refuse.
    safe_hash = content_hash if (isinstance(content_hash, str)
                                 and _CONTENT_HASH_RE.match(content_hash)) else ""

    metrics = {
        "recipe": RECIPE,
        "libvips_version": LIBVIPS_VERSION,
        "source_hash": safe_hash,
        "surface": "unknown",
        "flags": [],
        "fill_pct": 0,
        "ratio_x100": 0,
        "master_width": 0,
        "master_height": 0,
        "ink_bbox": [0, 0, 0, 0],
        "alpha_ratio": 0.0,
        "ink_on_white": 0.0,
        "ink_on_black": 0.0,
        "is_light": False,
    }
    flags = []

    def _result(variants, error=None):
        metrics["flags"] = _ordered_flags(flags)
        return {"variants": variants, "metrics": metrics, "error": error}

    try:
        if not content:
            raise ValueError("contenu vide")
        if not isinstance(content, bytes):
            # bytearray et memoryview sont des types bytes-like legitimes, mais
            # le cffi de pyvips les refuse (« initializer for ctype 'void *'
            # must be a cdata pointer, not bytearray ») : la conversion coute
            # zero et supprime la classe d'echec entiere.
            content = bytes(content)
        if not content_hash:
            # Le nommage adresse par contenu (et donc l'immutabilite CDN) repose
            # entierement sur ce hash : le remplacer en silence produirait des
            # URL qui ne correspondent plus au master.
            raise ValueError("content_hash requis pour le nommage adresse par contenu")
        if not _CONTENT_HASH_RE.match(str(content_hash)):
            # Meme enjeu, meme durete : un hash de 5000 caracteres ou un int
            # passaient tels quels dans une colonne prevue pour un sha256, et
            # rien ne garantissait plus la forme sur laquelle repose
            # l'immutabilite de 30 jours annoncee par le CDN.
            raise ValueError("content_hash doit etre un sha256 hexadecimal de 64 caracteres")

        slug = _slug(str(key))
        h12 = _content_key(content_hash)
        # Constante de recette, relue ICI pour que ``_sanitize_plate_color``
        # continue de garantir la forme (R, G, B) bornee 0-255.
        plate_rgb = _sanitize_plate_color(DEFAULT_PLATE_COLOR)

        # --- Etape 1/2 : format et tri des SVG ------------------------------
        # P15 : le ROUTAGE se decide sur le loader que libvips choisit vraiment,
        # pas sur les 10 octets du nommage ni sur une fenetre d'octets — sinon un
        # DOCTYPE, ou simplement un commentaire de generateur de plus de 1024
        # octets, suffit a contourner le garde svg_text.
        native_vector = _route_is_vector(content)
        if native_vector:
            has_text, wraps_raster = _scan_svg(content)
            if has_text:
                flags.append("svg_text")
                return _result([])
            if len(content) > MAX_SVG_CONTENT_BYTES:
                # P14 : REFUS, pas defaillance (error reste None). Rasteriser un
                # SVG de cette taille consomme des centaines de Mo et, sous
                # contrainte, ABORTE le processus : le message ne serait jamais
                # acquitte et tuerait la replica suivante.
                logger.warning(
                    "logo_derive: SVG refuse pour key=%r (%d octets > %d)",
                    key, len(content), MAX_SVG_CONTENT_BYTES,
                )
                flags.append("svg_too_complex")
                return _result([])
            if wraps_raster:
                flags.append("svg_wraps_raster")
                native_vector = False  # route vers la branche RASTER

        # --- Etape 3 : chargement et normalisation --------------------------
        if native_vector:
            try:
                work = _svg_render(content, CANVAS)
            except pyvips.Error as exc:
                if not _is_svg_complexity_refusal(exc):
                    raise
                # P14 : librsvg a REFUSE de developper le document, il n'a pas
                # echoue dessus. Meme nature que le plafond d'octets : un refus,
                # pas une defaillance.
                logger.warning(
                    "logo_derive: SVG refuse par librsvg pour key=%r (%s)",
                    key, _short_error(exc),
                )
                flags.append("svg_too_complex")
                return _result([])
            # Un viewBox avec de la marge rendrait une encre plus petite que la
            # cible ; la remonter en raster serait flou. On re-rend le vecteur
            # plus grand (supersampling borne EN MEMOIRE), puis la reduction fera
            # le reste.
            # P11 : ni trim_degenerate ni le seuil relatif ink_too_small ici, le
            # cadre est notre propre choix et le rapport encre/cadre d'un rendu
            # vectoriel est invariant d'echelle.
            first_box, _measure, _first_flags, _alpha = _ink_bbox(
                work, allow_trim_degenerate=False, allow_ink_min_area=False
            )
            work_scale = 1.0
            if first_box is not None and first_box[2] > 0 and first_box[3] > 0:
                # _fit est un CONTAIN : l'arete LONGUE de l'encre doit atteindre
                # 200 px. Utiliser l'arete courte sur-echantillonnerait pour rien
                # (un rendu 200x80 dont l'encre remplit deja le cadre).
                first_long = max(first_box[2], first_box[3])
                gain = CANVAS / float(first_long)
                gain = min(max(gain, 1.0), MAX_SVG_SUPERSAMPLE)
                if gain <= SVG_SUPERSAMPLE_MIN_GAIN:
                    pass
                elif len(content) > MAX_SVG_TWO_PASS_BYTES:
                    # P14 : la 2e passe reparse le DOM entier et double le pic
                    # memoire. Les deux passes sont comptees dans le meme
                    # plafond : au-dela de la moitie, on garde la 1re passe.
                    logger.info(
                        "logo_derive: 2e passe SVG evitee pour key=%r "
                        "(%d octets, gain %.2f abandonne)", key, len(content), gain,
                    )
                else:
                    try:
                        candidate = _svg_render(content, int(math.ceil(CANVAS * gain)))
                    except pyvips.Error as exc:
                        if not _is_svg_complexity_refusal(exc):
                            raise
                        # La 1re passe a deja rendu : un refus de complexite sur
                        # la 2e ne doit pas couter la vignette deja obtenue.
                        logger.info(
                            "logo_derive: 2e passe SVG refusee par librsvg pour "
                            "key=%r (%s), 1re passe conservee", key, _short_error(exc),
                        )
                        candidate = None
                    cand_box, _cm, _cand_flags, _cand_alpha = _ink_bbox(
                        candidate, allow_trim_degenerate=False, allow_ink_min_area=False
                    ) if candidate is not None else (None, None, [], 0.0)
                    # P10 : sur un SVG sans dimensions declarees, librsvg REFUSE
                    # de mettre le dessin a l'echelle — l'encre reste identique
                    # et seul le cadre grandit. Garder ce rendu diluerait l'encre
                    # dans un cadre plus grand pour rien. On ne remplace donc la
                    # 1re passe que si l'encre a REELLEMENT grandi (mesure, pas
                    # suppose).
                    if (cand_box is not None
                            and max(cand_box[2], cand_box[3]) > first_long):
                        # Le referentiel des metriques reste celui du rendu de
                        # REFERENCE (1re passe a CANVAS) : sans ce facteur,
                        # master_width/ink_bbox et le gate low_res dependraient
                        # d'une decision interne de la recette.
                        work_scale = float(candidate.width) / float(work.width)
                        work = candidate
                    else:
                        logger.debug(
                            "logo_derive: supersampling SVG sans effet "
                            "(encre %s px inchangee), 1re passe conservee", first_long,
                        )
        else:
            work, work_scale, load_flags = _load_raster(content)
            flags.extend(load_flags)

        # Referentiel MASTER : l'image de travail a pu etre reduite pour tenir en
        # memoire, on remonte les dimensions au master (le facteur est calcule
        # sur l'arete maximale, invariante par rotation EXIF).
        inverse = 1.0 / work_scale
        metrics["master_width"] = int(round(work.width * inverse))
        metrics["master_height"] = int(round(work.height * inverse))

        # --- Etape 4 : boite d'encre ----------------------------------------
        box, measure_box, box_flags, alpha_used = _ink_bbox(
            work,
            allow_trim_degenerate=not native_vector,
            allow_ink_min_area=not native_vector,
        )
        flags.extend(box_flags)
        if box is None:
            return _result([])

        # La SOURCE est-elle opaque, c'est-a-dire porte-t-elle son propre fond
        # cuit ? C'est exactement le predicat par lequel _ink_bbox choisit le
        # trim par consensus des coins ; ``baked_background`` en est l'autre
        # forme (coins divergents ou image uniforme). L'etape 6 en a besoin :
        # sur un logo opaque, un taux d'encre faible ne dit RIEN de la
        # lisibilite sur blanc, puisque le fond du logo la porte.
        self_background = (alpha_used <= ALPHA_USED_PCT_MIN
                           or "baked_background" in box_flags)

        left, top, box_w, box_h = box
        metrics["ink_bbox"] = [
            int(round(left * inverse)), int(round(top * inverse)),
            int(round(box_w * inverse)), int(round(box_h * inverse)),
        ]

        # Le gate low_res / elongated porte sur l'ENCRE, pas sur le cadre : quand
        # le trim est refuse, la boite de cadrage vaut tout le cadre et decrirait
        # une resolution que l'encre n'a pas.
        m_left, m_top, m_box_w, m_box_h = measure_box
        master_box_w = max(1, int(round(m_box_w * inverse)))
        master_box_h = max(1, int(round(m_box_h * inverse)))
        long_edge = max(master_box_w, master_box_h)
        short_edge = min(master_box_w, master_box_h)
        ratio = long_edge / float(short_edge)
        metrics["ratio_x100"] = int(round(ratio * 100))
        if ratio > ELONGATED_RATIO_MAX:
            flags.append("elongated")
        if short_edge < LOW_RES_MIN_EDGE:
            # Pas d'exemption pour le vecteur : la spec n'en prevoit aucune, et
            # une fois le supersampling verifie (P10) le flag ne tombe plus que
            # sur les SVG dont librsvg a REFUSE d'agrandir le dessin — cas ou
            # l'encre vient bel et bien de trop peu de pixels reels.
            flags.append("low_res")

        crop = work.extract_area(left, top, box_w, box_h).copy_memory()
        if measure_box == box:
            measure_crop = crop
        else:
            # Trim refuse : le cadrage garde le cadre entier, mais mesurer sur un
            # cadre a 98 % transparent decrirait le FOND. C'est exactement le
            # biais que l'etape 5 doit eviter, et c'est la mesure qui isole les
            # 205 logos invisibles sur blanc.
            measure_crop = work.extract_area(m_left, m_top, m_box_w, m_box_h).copy_memory()

        # --- Etape 5/6 : mesures et verdict ---------------------------------
        measures = _measure_surface(measure_crop)
        metrics["alpha_ratio"] = round(measures["alpha_ratio"], 2)
        metrics["ink_on_white"] = round(measures["ink_on_white"], 2)
        metrics["ink_on_black"] = round(measures["ink_on_black"], 2)
        metrics["is_light"] = measures["is_light"]

        surface, verdict_flags = _surface_verdict(measures, self_background=self_background)
        metrics["surface"] = surface
        flags.extend(verdict_flags)

        # --- Etape 7 : mise a l'echelle et canvas ---------------------------
        fitted, no_upscale, upscaled = _fit(crop, CANVAS, native_vector)
        if no_upscale:
            flags.append("no_upscale")
        if upscaled and native_vector:
            # Le rendu vectoriel n'a pas pu atteindre la cible (librsvg refuse
            # d'echelonner, ou le plafond memoire du supersampling a mordu) : le
            # crop a donc ete agrandi en RASTER. La vignette est molle et le
            # consommateur doit pouvoir le savoir — no_upscale est structurellement
            # impossible sur cette branche.
            flags.append("vector_upscaled")
        ink_w, ink_h = _alpha_bbox_size(fitted)
        displayed_ink_pct = 100.0 * ink_w * ink_h / CANVAS_AREA
        metrics["fill_pct"] = int(round(displayed_ink_pct))

        # Le plancher porte sur l'ARETE COURTE et non sur l'aire : un critere
        # d'aire est structurellement inerte ici (cf. P16 sur
        # MIN_DISPLAYED_INK_EDGE). Une encre de 12x200 px a la meme aire qu'une
        # tache de 49x49 mais reste un logotype lisible, alors que la tache ne
        # l'est pas : c'est l'arete la plus courte qui dit s'il reste quelque
        # chose a voir.
        if max(ink_w, ink_h) < MIN_DISPLAYED_INK_EDGE:
            # Le SEUL critere de refus geometrique mesure sur la SORTIE. Il
            # remplace ``trim_degenerate``, qui bloquait sur le rapport
            # encre/cadre de la SOURCE : la meme encre de 300 px etait publiee a
            # fill_pct = 100 dans un cadre de 320 px et refusee dans un cadre de
            # 1350 px, alors que dans les deux cas la vignette est celle que la
            # recette a su produire. Ici on ne juge plus le cadre mais ce que la
            # carte affichera vraiment : sous 24 px sur la plus GRANDE arete dans le
            # canvas de 200, il ne reste que 3,8 px CSS dans la boite utile de la carte —
            # une tache, pas un logo.
            logger.info(
                "logo_derive: encre affichee derisoire pour key=%r (%sx%s px, "
                "%.2f %% du canvas), aucune variante", key, ink_w, ink_h, displayed_ink_pct,
            )
            flags.append("ink_too_small")
            return _result([])

        variants = [_variant(VARIANT_PLAIN, slug, h12, _center_on_canvas(fitted))]

        # --- Etape 8 : variante sur plaque ----------------------------------
        # Encadree LOCALEMENT : sq200a est deja construite et encodee en octets,
        # et l'etape 8 est entierement OPTIONNELLE (matte, plaque, svgload du
        # rect arrondi, composite2, pngsave). Une exception ici tombait dans
        # l'except global et rendait variants=[] : un echec sur l'artefact
        # accessoire coutait l'artefact principal.
        if surface == "dark_required":
            try:
                # Ordre de la spec : on MESURE le matting d'abord, on tranche
                # ensuite. Tester gif_1bit en premier court-circuitait
                # _matte_is_suspect, donc matte_suspect n'etait jamais enregistre
                # sur la population GIF : meme decision, mais signal d'audit perdu.
                if _matte_is_suspect(measure_crop):
                    flags.append("matte_suspect")
                if "gif_1bit" in flags:
                    # Transparence 1 bit : les escaliers viennent de la matte, donc
                    # ils crenellent aussi sur une plaque, quelle que soit sa couleur.
                    logger.info("logo_derive: plaque refusee (gif_1bit) pour key=%r", key)
                elif "matte_suspect" in flags:
                    logger.info("logo_derive: plaque refusee (matte_suspect) pour key=%r", key)
                else:
                    # La plaque doit pouvoir entourer le logo : on borne d'abord le
                    # logo a la boite interieure, sinon la plaque plafonnee a 200
                    # laisserait l'encre depasser de ses coins arrondis.
                    plate_logo, _nu, _up = _fit(crop, CANVAS - 2 * PLATE_PADDING, native_vector)
                    plated = _plate_image(plate_logo, plate_rgb)
                    variants.append(
                        _variant(VARIANT_PLATE, slug, h12, _center_on_canvas(plated))
                    )
            except Exception as exc:
                logger.error(
                    "logo_derive: plaque en echec pour key=%r (%s), sq200a conservee",
                    key, _short_error(exc),
                )
                flags.append("plate_failed")

            if not any(item["variant"] == VARIANT_PLATE for item in variants):
                # Sans plaque, la seule variante est de l'encre claire sur
                # transparent : INVISIBLE sur le cadre #FFFFFF de la carte, qui
                # n'a pas de mode sombre. Le flag est BLOQUANT pour qu'un
                # consommateur n'ait pas a croiser surface et liste de variantes.
                flags.append("no_usable_variant")

        return _result(variants)

    except Exception as exc:
        # Contrat : RIEN ne sort d'ici, d'ou l'except large.
        # pyvips.error.Error herite d'Exception, mais un except cible laisserait
        # s'echapper hashlib/re/ValueError. Le worker appelant ne doit jamais
        # echouer a cause du derive.
        logger.error("logo_derive: echec pour key=%r : %s", key, exc)
        flags.append("derivation_failed")
        return _result([], error=_short_error(exc))
