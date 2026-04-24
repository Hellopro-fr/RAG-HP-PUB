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
