"""Tests garde-fou sur ImageProcessor — couvrent les régressions R1, R2, R3
du fix de parité avec le PHP creer_image() (commit 582fdc6c).
"""

from PIL import Image

from core.image_processor import ImageProcessor


def test_png_transparent_flattened_on_white(transparent_png_bytes, tmp_path):
    """R1 — Un PNG avec pixel transparent doit ressortir opaque sur fond blanc.

    Garde-fou sur : app/core/image_processor.py:99-104
        if output_format == 'PNG':
            if image.mode != 'RGBA':
                image = image.convert('RGBA')
            canvas = Image.new('RGB', image.size, (255, 255, 255))
            canvas.paste(image, mask=image.split()[-1])
            image = canvas

    Parité PHP : case 3 de creer_image() (imagecreatetruecolor + imagefill(blanc)).
    """
    processor = ImageProcessor()

    result = processor.process_image(
        content=transparent_png_bytes,
        domain="test.com",
        product_id="1",
        product_name="produit-test",
        base_storage_dir=str(tmp_path),
        index=1,
    )

    assert result["main_path"].endswith(".png"), \
        f"extension attendue .png, obtenu : {result['main_path']}"

    with Image.open(result["main_path"]) as out:
        out.load()
        assert out.mode == "RGB", \
            f"attendu mode RGB (flatten fait), obtenu : {out.mode}"
        assert out.getpixel((0, 0)) == (255, 255, 255), \
            f"pixel transparent doit devenir blanc, obtenu : {out.getpixel((0, 0))}"


def test_pyvips_path_png_also_flattens(transparent_png_bytes, tmp_path, monkeypatch):
    """R1 via branche pyvips — le flatten sur blanc doit aussi fonctionner
    en shrink-on-load.

    Garde-fou sur : app/core/image_processor.py:187-189
        if output_format_suffix == '.png' and main_vips.hasalpha():
            main_vips = main_vips.flatten(background=[255, 255, 255])

    On force la branche pyvips en réduisant LARGE_IMAGE_THRESHOLD à 10 :
    une image 10×10 (100 pixels) déclenche alors le chemin pyvips.
    """
    from core import image_processor

    monkeypatch.setattr(image_processor, "LARGE_IMAGE_THRESHOLD", 10)

    processor = image_processor.ImageProcessor()

    result = processor.process_image(
        content=transparent_png_bytes,
        domain="test.com",
        product_id="1",
        product_name="produit-test",
        base_storage_dir=str(tmp_path),
        index=1,
    )

    assert result["main_path"].endswith(".png"), \
        f"extension attendue .png, obtenu : {result['main_path']}"

    with Image.open(result["main_path"]) as out:
        out.load()
        assert out.mode == "RGB", \
            f"pyvips flatten attendu (mode RGB), obtenu : {out.mode}"
        assert out.getpixel((0, 0)) == (255, 255, 255), (
            f"pixel transparent doit devenir blanc (branche pyvips), "
            f"obtenu : {out.getpixel((0, 0))}"
        )


def test_webp_transparent_converted_to_png_on_white(transparent_webp_bytes, tmp_path):
    """R2 — Un WebP avec alpha doit ressortir en PNG opaque sur fond blanc.

    Garde-fou sur : app/core/image_processor.py:86-93 (conversion WEBP→PNG)
                  + app/core/image_processor.py:99-104 (flatten blanc)

    Parité PHP : case 18 de creer_image() (WebP → PNG avec imagefill blanc).
    """
    processor = ImageProcessor()

    result = processor.process_image(
        content=transparent_webp_bytes,
        domain="test.com",
        product_id="1",
        product_name="produit-test",
        base_storage_dir=str(tmp_path),
        index=1,
    )

    assert result["main_path"].endswith(".png"), \
        f"WebP doit être converti en PNG, obtenu : {result['main_path']}"

    with Image.open(result["main_path"]) as out:
        out.load()
        assert out.mode == "RGB", \
            f"attendu mode RGB (flatten fait), obtenu : {out.mode}"
        assert out.getpixel((0, 0)) == (255, 255, 255), \
            f"WebP transparent doit être composé sur fond blanc, obtenu : {out.getpixel((0, 0))}"


def test_gif_transparency_preserved(transparent_gif_bytes, tmp_path):
    """R3 — Un GIF avec transparence de palette doit la conserver après process.

    Garde-fou sur : app/core/image_processor.py:125-127
        save_kwargs["save_all"] = True
        if gif_transparency is not None:
            save_kwargs["transparency"] = gif_transparency

    Parité PHP : case 1 de creer_image() (imagecolortransparent + imagepalettecopy).

    Note : si cette assertion échoue malgré un code source correct (piège Pillow
    version-dépendant), le plan B est d'asserter `out.mode == "P"` et que
    `out.getpixel((0,0))` vaut l'index transparent du GIF.
    """
    processor = ImageProcessor()

    result = processor.process_image(
        content=transparent_gif_bytes,
        domain="test.com",
        product_id="1",
        product_name="produit-test",
        base_storage_dir=str(tmp_path),
        index=1,
    )

    assert result["main_path"].endswith(".gif"), \
        f"extension attendue .gif, obtenu : {result['main_path']}"

    with Image.open(result["main_path"]) as out:
        out.load()
        assert "transparency" in out.info, \
            "la transparence GIF doit être préservée au save (info['transparency'])"
