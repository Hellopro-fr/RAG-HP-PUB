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
        ...
        Returns:
            dict: Paths to the saved main image and thumbnail
        """
        try:
# ... (omitted lines)
            # Normalize filename
            normalized_name = self._normalize_name(product_name)
            
            # Suffix with index if provided (e.g., product-123-1.jpg)
            # Index is usually 0-based from enumerate, so we use index+1 for filename if needed?
            # User requirement: Multi-image support. Convention usually starts at 1.
            # Let's use index + 1
            if index > 0:
                 filename = f"{normalized_name}-{product_id}-{index}{extension}"
            else:
                 # Backward compatibility or first image
                 # But if we have multiple images, even the first one should probably have -1?
                 # Or keep original format for the first one?
                 # User accepted "suffixe -1, -2", so let's use it for ALL images if we are in multi-mode.
                 # Actually, logic in downloader will control 'index'.
                 # If index=0 (default), maybe no suffix?
                 # Let's assume passed index logic.
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
