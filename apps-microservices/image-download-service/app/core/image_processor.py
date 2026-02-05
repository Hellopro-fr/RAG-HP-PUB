import os
import io
from PIL import Image
import logging

logger = logging.getLogger(__name__)

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

            try:
                # Suppress DecompressionBombWarning as we handle it manually
                Image.MAX_IMAGE_PIXELS = None 
                
                image = Image.open(image_stream)
                
                # --- SAFETY CHECK: OOM Protection ---
                # Increased limit to 200 Million pixels (~600MB) since container has 1GB RAM
                MAX_PIXELS = 200_000_000 
                
                width, height = image.size
                total_pixels = width * height
                
                if total_pixels > MAX_PIXELS:
                    logger.warning(f"⛔ Skipping image {product_id}: Too large ({width}x{height} = {total_pixels} px). Limit: {MAX_PIXELS} px.")
                    return None

                # OPTIMIZATION: For JPEGs, we can load a draft (thumbnail) directly
                if total_pixels > 50_000_000 and image.format == 'JPEG':
                     logger.info(f"⚠️ Large JPEG detected ({width}x{height}). Using draft mode to save RAM.")
                     image.draft('RGB', (800, 800))
                elif total_pixels > 50_000_000:
                     logger.info(f"⚠️ Large {image.format} detected ({width}x{height}). Processing with caution (High RAM usage).")

                image.load() # Force load (or load draft)
            except Exception as pil_error:
                # If SVG, it might start with <svg
                if b'<svg' in header_bytes or b'<?xml' in header_bytes:
                     logger.warning(f"SVG detected for {product_id}, skipping (PIL does not support SVG).")
                     return None
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
            
            # --- 1. Normalization & Conversion for specific cases ---
            if output_format == 'PNG' and image.mode in ('P', 'CMYK'):
                 image = image.convert('RGBA')

            # --- 2. Main Image Processing (Max 800x800) ---
            image_max_size = (800, 800)
            main_image = image.copy()
            main_image.thumbnail(image_max_size, Image.Resampling.LANCZOS)
            
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
            
            # Save Main Image
            save_kwargs = {"optimize": True}
            if output_format == 'GIF':
                 save_kwargs["save_all"] = True # Preserve frames if possible, though thumbnail might flatten
            
            main_image.save(main_file_path, output_format, **save_kwargs)
            
            # --- 3. Thumbnail Creation (110x110) ---
            thumb_max_size = (110, 110)
            thumb_image = image.copy()
            thumb_image.thumbnail(thumb_max_size, Image.Resampling.LANCZOS)
            
            # For thumbnails, PHP usually uses same format unless specified otherwise.
            # The PHP code: case 1->gif, case 2->jpg, case 3/18->png.
            # So we stick to the determined output_format.
            
            thumb_image.save(thumb_file_path, output_format, **save_kwargs)
            
            return {
                "main_path": main_file_path,
                "thumb_path": thumb_file_path,
                "filename": filename
            }
            
        except Exception as e:
            logger.error(f"Error processing image for product {product_id}: {e}")
            raise e

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
