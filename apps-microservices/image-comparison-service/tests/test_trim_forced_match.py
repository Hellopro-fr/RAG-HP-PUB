"""
Tolerant trim_borders + forced_match at pHash distance 0 — regression tests for
the two residual false-negative mechanisms found on the .jpg.webp/.png.webp
double-extension pairs (2026-07-08):
- euromag terra-et-mera.jpg vs .jpg.webp: near-white pixels (253/254) sown by
  the WebP re-encoding extended the strict invert+getbbox crop to the image
  edge -> pHash 34/64 on identical visuals. Fixed by thresholding the
  background at >= 240 grayscale.
- pacamodul IMG-20211108-WA0017.jpg vs .jpg.webp: pHash distance 0 but HSV
  histogram 70 < 85 -> no forced_match -> score 94 < threshold 100. Choix
  conservateur : NON corrige (aucun elargissement du forced_match), faux
  negatif assume pour garantir zero nouveau chemin d acceptation.
"""
import cv2
import numpy as np
import imagehash
from PIL import Image, ImageDraw

from app.core.image_processor import ImageProcessor


def _photo_on_white():
    img = Image.new("RGB", (400, 233), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.rectangle([80, 15, 305, 225], fill=(120, 90, 40))
    draw.ellipse([140, 60, 250, 170], fill=(30, 120, 200))
    return img


def test_trim_ignores_near_white_compression_noise():
    clean = _photo_on_white()
    noisy = clean.copy()
    # bruit de recompression quasi-blanc au bord oppose au contenu
    noisy.putpixel((399, 232), (253, 253, 253))
    noisy.putpixel((398, 2), (250, 252, 251))

    t_clean = ImageProcessor.trim_borders(clean)
    t_noisy = ImageProcessor.trim_borders(noisy)
    assert t_clean.size == t_noisy.size, (t_clean.size, t_noisy.size)
    assert imagehash.phash(t_clean) - imagehash.phash(t_noisy) == 0


def test_trim_still_crops_white_borders():
    img = _photo_on_white()
    trimmed = ImageProcessor.trim_borders(img)
    # le crop doit serrer le contenu (rect 80..305 x 15..225), pas garder les 400x233
    assert trimmed.size[0] <= 306 - 80 + 2 and trimmed.size[1] <= 226 - 15 + 2
    assert trimmed.size[0] >= 220 and trimmed.size[1] >= 205


def _hist_pair_medium_correlation():
    # Vecteurs deterministes : correlation Pearson ~0.73 -> hist_score dans [60, 85)
    x = np.tile(np.array([1.0, 0.0], dtype=np.float32), 256)
    y = x.copy()
    zeros = np.where(y == 0.0)[0]
    y[zeros[:77]] = 1.0
    return x, y


def test_zero_distance_with_medium_hist_is_deliberately_not_forced():
    # Choix conservateur (2026-07-09) : PAS d elargissement du forced_match a
    # distance 0 avec hist moyen — zero nouveau chemin d acceptation vs l etat
    # d avant les fixes. La classe pacamodul (dist 0, hist ~70 apres
    # recompression) reste un faux negatif ASSUME (score ~94 < threshold 100).
    img = _photo_on_white()
    ph = imagehash.phash(img)
    h1, h2 = _hist_pair_medium_correlation()
    raw = max(0, cv2.compareHist(h1, h2, cv2.HISTCMP_CORREL)) * 100
    assert 60 <= raw < 85, f"precondition hist medium ratee : {raw}"

    score, details = ImageProcessor.calculate_similarity(
        {"phash": ph, "hist": h1}, {"phash": ph, "hist": h2}
    )
    assert score < 100.0 and not details.get("forced_match"), (score, details)


def test_no_forced_match_when_structure_differs():
    a = _photo_on_white()
    b = _photo_on_white().transpose(Image.ROTATE_90)
    pa, pb = imagehash.phash(a), imagehash.phash(b)
    assert pa - pb > 3, "precondition : structures differentes attendues"
    h1, h2 = _hist_pair_medium_correlation()
    score, details = ImageProcessor.calculate_similarity(
        {"phash": pa, "hist": h1}, {"phash": pb, "hist": h2}
    )
    assert score < 100.0 and not details.get("forced_match")
