import os
import io
from PIL import Image
import pyvips
import logging

logger = logging.getLogger(__name__)

# Threshold: above this pixel count, delegate to pyvips for shrink-on-load
LARGE_IMAGE_THRESHOLD = 50_000_000  # 50M pixels

class ImageProcessor:
    def __init__(self):
        pass

    def process_image(self, content: bytes, domain: str, product_id: str, product_name: str, base_storage_dir: str, index: int = 0):
        """
        Processes the image:
        1. Converts to RGBA/RGB
        2. Resizes main image (max 800x800)
        3. Creates thumbnail (110x110)
        4. Saves both in sharded directory structure
        
        Returns:
            dict: Paths to the saved main image and thumbnail
        """
        try:
            if not content:
                raise ValueError("Image content is empty")

            # Create fresh BytesIO stream
            image_stream = io.BytesIO(content)
            image_stream.seek(0)

            # Debug: Log first few bytes to check header
            header_bytes = content[:10]
            logger.info(f"Processing image {product_id} - Size: {len(content)} bytes - Header: {header_bytes}")

            # --- SVG: Detect early and delegate to pyvips (librsvg) ---
            if b'<svg' in header_bytes or b'<?xml' in header_bytes:
                logger.info(f"🔄 SVG detected for product {product_id} ({len(content)} bytes). Rasterizing via pyvips/librsvg.")
                return self._process_with_vips(content, 'SVG', domain, product_id, product_name, base_storage_dir, index)

            try:
                # Suppress DecompressionBombWarning as we handle it manually
                Image.MAX_IMAGE_PIXELS = None

                image = Image.open(image_stream)

                width, height = image.size
                total_pixels = width * height
                original_format = image.format.upper() if image.format else "JPEG"

                # --- LARGE IMAGE: Delegate to pyvips (shrink-on-load, ~2-5MB RAM) ---
                if total_pixels > LARGE_IMAGE_THRESHOLD:
                    logger.info(f"🔄 Large image detected ({width}x{height} = {total_pixels} px, format={original_format}). Using pyvips shrink-on-load.")
                    image.close()
                    return self._process_with_vips(content, original_format, domain, product_id, product_name, base_storage_dir, index)

                # OPTIMIZATION: For JPEGs, we can load a draft (thumbnail) directly
                if total_pixels > 50_000_000 and image.format == 'JPEG':
                     logger.info(f"⚠️ Large JPEG detected ({width}x{height}). Using draft mode to save RAM.")
                     image.draft('RGB', (800, 800))

                image.load() # Force load (or load draft)
            except Exception as pil_error:
                raise pil_error

            original_format = image.format.upper() if image.format else "JPEG"
            
            # Determine output format and extension based on PHP logic
            # Case 1 (GIF) -> .gif
            # Case 2 (JPEG) -> .jpg
            # Case 3 (PNG) -> .png
            # Case 18 (WEBP) -> .png
            
            if original_format == 'GIF':
                output_format = 'GIF'
                extension = '.gif'
            elif original_format in ('JPEG', 'JPG'):
                output_format = 'JPEG'
                extension = '.jpg'
                # JPEGs don't support alpha
                if image.mode in ('RGBA', 'LA', 'P'):
                    image = image.convert('RGB')
            elif original_format == 'WEBP':
                # PHP converts WebP to PNG
                output_format = 'PNG'
                extension = '.png'
            else:
                # Default to PNG for PNG and others
                output_format = 'PNG'
                extension = '.png'
            
            # --- 1. Flatten sur fond blanc (parité PHP creer_image) ---
            # PHP cases 3 (PNG) et 18 (WEBP) : imagecreatetruecolor + imagefill(255,255,255)
            # avant resize → les zones transparentes deviennent blanches à la sortie.
            # Appliqué AVANT thumbnail() pour que main_image ET thumb_image héritent du flatten.
            if output_format == 'PNG':
                if image.mode != 'RGBA':
                    image = image.convert('RGBA')
                canvas = Image.new('RGB', image.size, (255, 255, 255))
                canvas.paste(image, mask=image.split()[-1])
                image = canvas

            # Préservation de la transparence GIF (parité PHP case 1 :
            # imagetruecolortopalette + imagepalettecopy + imagecolortransparent)
            gif_transparency = image.info.get('transparency') if output_format == 'GIF' else None

            # --- 2. Main Image Processing (Max 800x800) ---
            image_max_size = (800, 800)
            main_image = image.copy()
            main_image.thumbnail(image_max_size, Image.Resampling.LANCZOS)
            
            # Build paths
            paths = self._build_paths(domain, product_id, product_name, base_storage_dir, index, extension)
            
            main_file_path = paths["main_file_path"]
            thumb_file_path = paths["thumb_file_path"]
            filename = paths["filename"]
            
            # Save Main Image
            save_kwargs = {"optimize": True}
            if output_format == 'GIF':
                save_kwargs["save_all"] = True  # Preserve frames if possible, though thumbnail might flatten
                if gif_transparency is not None:
                    save_kwargs["transparency"] = gif_transparency

            main_image.save(main_file_path, output_format, **save_kwargs)
            logger.info(f"✅ PIL: Main image saved for {product_id}: {main_file_path}")

            # --- 3. Thumbnail Creation (110x110) ---
            thumb_max_size = (110, 110)
            thumb_image = image.copy()
            thumb_image.thumbnail(thumb_max_size, Image.Resampling.LANCZOS)
            
            # For thumbnails, PHP usually uses same format unless specified otherwise.
            # The PHP code: case 1->gif, case 2->jpg, case 3/18->png.
            # So we stick to the determined output_format.
            
            thumb_image.save(thumb_file_path, output_format, **save_kwargs)
            logger.info(f"✅ PIL: Thumbnail saved for {product_id}: {thumb_file_path}")

            return {
                "main_path": main_file_path,
                "thumb_path": thumb_file_path,
                "filename": filename
            }
            
        except Exception as e:
            logger.error(f"Error processing image for product {product_id}: {e}")
            raise e

    def _process_with_vips(self, content: bytes, original_format: str, domain: str, product_id: str, product_name: str, base_storage_dir: str, index: int = 0):
        """
        Processes large images using pyvips (libvips) with shrink-on-load.
        Uses streaming decode+resize in a single pass, ~2-5MB RAM regardless of input size.
        
        This is used as a fallback for images that would OOM with PIL's full decompression.
        """
        try:
            # Determine output format and extension based on PHP logic
            if original_format == 'GIF':
                output_format_suffix = '.gif'
                extension = '.gif'
            elif original_format in ('JPEG', 'JPG'):
                output_format_suffix = '.jpg'
                extension = '.jpg'
            elif original_format == 'WEBP':
                # PHP converts WebP to PNG
                output_format_suffix = '.png'
                extension = '.png'
            else:
                output_format_suffix = '.png'
                extension = '.png'
            
            # Build paths
            paths = self._build_paths(domain, product_id, product_name, base_storage_dir, index, extension)
            
            main_file_path = paths["main_file_path"]
            thumb_file_path = paths["thumb_file_path"]
            filename = paths["filename"]

            # --- Main Image (800x800) using shrink-on-load ---
            main_vips = pyvips.Image.thumbnail_buffer(content, 800, height=800)

            # Flatten sur fond blanc (parité PHP cases 3 PNG et 18 WEBP)
            if output_format_suffix == '.png' and main_vips.hasalpha():
                main_vips = main_vips.flatten(background=[255, 255, 255])

            if output_format_suffix == '.jpg':
                main_vips.jpegsave(main_file_path, optimize_coding=True)
            elif output_format_suffix == '.png':
                main_vips.pngsave(main_file_path)
            elif output_format_suffix == '.gif':
                # pyvips gif support: save as png if gif causes issues
                main_vips.pngsave(main_file_path)
            
            logger.info(f"✅ pyvips: Main image saved for {product_id}: {main_file_path}")
            
            # --- Thumbnail (110x110) using shrink-on-load ---
            thumb_vips = pyvips.Image.thumbnail_buffer(content, 110, height=110)

            # Flatten sur fond blanc (parité PHP cases 3 PNG et 18 WEBP)
            if output_format_suffix == '.png' and thumb_vips.hasalpha():
                thumb_vips = thumb_vips.flatten(background=[255, 255, 255])

            if output_format_suffix == '.jpg':
                thumb_vips.jpegsave(thumb_file_path, optimize_coding=True)
            elif output_format_suffix == '.png':
                thumb_vips.pngsave(thumb_file_path)
            elif output_format_suffix == '.gif':
                thumb_vips.pngsave(thumb_file_path)
            
            logger.info(f"✅ pyvips: Thumbnail saved for {product_id}: {thumb_file_path}")
            
            return {
                "main_path": main_file_path,
                "thumb_path": thumb_file_path,
                "filename": filename
            }
            
        except Exception as e:
            logger.error(f"Error processing large image with pyvips for product {product_id}: {e}")
            raise e

    def _build_paths(self, domain: str, product_id: str, product_name: str, base_storage_dir: str, index: int, extension: str):
        """
        Builds the sharded directory paths and filename for a product image.
        Shared between PIL and pyvips processing paths.
        """
        # Create sharded path components
        product_id_str = str(product_id)
        if len(product_id_str) < 3:
            product_id_str = product_id_str.zfill(3)
            
        rep1 = product_id_str[-1]
        rep2 = product_id_str[-2]
        rep3 = product_id_str[-3]
        
        # Normalize filename
        normalized_name = self._normalize_name(product_name)
        
        # Suffix with index if provided (e.g., product-123-1.jpg)
        if index > 0:
             filename = f"{normalized_name}-{product_id}-{index}{extension}"
        else:
             if index == 0:
                  filename = f"{normalized_name}-{product_id}{extension}"
             else:
                  filename = f"{normalized_name}-{product_id}-{index}{extension}"
        
        # Define paths
        # /images/{domain}/produit-2/X/Y/Z/ (Main)
        main_rel_dir = os.path.join("images", domain, "produit-2", rep1, rep2, rep3)
        main_full_dir = os.path.join(base_storage_dir, main_rel_dir)
        
        # /images/{domain}/produit-3/X/Y/Z/ (Thumbnail)
        thumb_rel_dir = os.path.join("images", domain, "produit-3", rep1, rep2, rep3)
        thumb_full_dir = os.path.join(base_storage_dir, thumb_rel_dir)
        
        # Create directories
        os.makedirs(main_full_dir, exist_ok=True)
        os.makedirs(thumb_full_dir, exist_ok=True)
        
        main_file_path = os.path.join(main_full_dir, filename)
        thumb_file_path = os.path.join(thumb_full_dir, filename)
        
        return {
            "main_file_path": main_file_path,
            "thumb_file_path": thumb_file_path,
            "filename": filename
        }

    def _normalize_name(self, name: str) -> str:
        """
        Simple slugification to match PHP's normaliser_mot_expression roughly.
        """
        import re
        import unicodedata
        
        # Lowercase
        name = name.lower()
        
        # Remove accents
        nfkd_form = unicodedata.normalize('NFKD', name)
        name = "".join([c for c in nfkd_form if not unicodedata.combining(c)])
        
        # Replace non-alphanumeric with -
        name = re.sub(r'[^a-z0-9]+', '-', name)
        
        # Trim dashes
        name = name.strip('-')
        
        return name
