import os
import io
from PIL import Image
import pyvips
import logging

logger = logging.getLogger(__name__)

# Threshold: above this pixel count, delegate to pyvips for shrink-on-load
LARGE_IMAGE_THRESHOLD = 50_000_000  # 50M pixels


def _detect_extension(content: bytes, image_stream: io.BytesIO) -> tuple[str, str | None]:
    """
    Detect output format and file extension from raw image bytes.

    Reads the first 10 bytes for SVG detection, then uses PIL to sniff the
    format (without full decode). Returns early for SVG.

    Args:
        content:      Raw image bytes.
        image_stream: Seekable BytesIO wrapping the same bytes (seek(0) assumed).

    Returns:
        Tuple (extension, original_format) where:
          - extension is one of '.jpg', '.png', '.gif'
          - original_format is the PIL format string (e.g. 'JPEG', 'PNG', 'GIF',
            'WEBP', 'SVG') or None if unknown.

    Note:
        WEBP is mapped to '.png' (parité PHP case 18 — conversion WebP→PNG).
        SVG is detected from byte-level header inspection (no PIL involved).
        All unknown formats default to '.png'.
    """
    header_bytes = content[:10]

    # SVG: detected from raw bytes before PIL involvement
    if b'<svg' in header_bytes or b'<?xml' in header_bytes:
        return '.png', 'SVG'

    # Use PIL to sniff format without full decode
    image_stream.seek(0)
    with Image.open(image_stream) as img:
        original_format = img.format.upper() if img.format else None

    if original_format == 'GIF':
        return '.gif', 'GIF'
    elif original_format in ('JPEG', 'JPG'):
        return '.jpg', 'JPEG'
    elif original_format == 'WEBP':
        # PHP converts WebP to PNG (case 18)
        return '.png', 'WEBP'
    else:
        # PNG and all others → .png
        return '.png', original_format or 'PNG'


class ImageProcessor:
    def __init__(self):
        pass

    def process_image(self, content: bytes, domain: str, product_id: str, product_name: str, base_storage_dir: str, filename: str = "", index: int = 0):
        """
        Processes the image:
        1. Detects format from content bytes (not from filename extension)
        2. Converts to RGBA/RGB
        3. Resizes main image (max 800x800)
        4. Creates thumbnail (110x110)
        5. Saves both in sharded directory structure (produit-2 / produit-3)

        Pre-refactor behavior preserved: _build_paths is called AFTER format
        detection so the correct extension is applied to the stored filename.
        This mirrors the original code where ``extension`` was computed before
        the _build_paths call.

        Args:
            filename: Nom de fichier explicite pré-construit (ex: via _build_filename).
                      Prend la priorité sur index si fourni.
            index:    Paramètre legacy conservé pour compatibilité ; ignoré quand
                      filename est fourni.

        Returns:
            dict: Paths to the saved main image and thumbnail, plus image metadata.
                  Keys: main_path, thumb_path, filename, width, height, format, file_size.
        """
        if not content:
            raise ValueError("Image content is empty")

        # --- C1 FIX: detect format BEFORE calling _build_paths ---
        # Pre-refactor: _build_paths was called after original_format + extension
        # were determined inside the processing loop. The hardcoded ".jpg" that
        # was here caused callers passing ".png"/".webp"/".gif" filenames to have
        # their extension silently overwritten before format was known.
        image_stream = io.BytesIO(content)
        image_stream.seek(0)
        extension, original_format = _detect_extension(content, image_stream)

        paths = self._build_paths(domain, product_id, product_name, base_storage_dir, extension, filename=filename, index=index)
        output_main_dir = os.path.dirname(paths["main_file_path"])
        output_thumb_dir = os.path.dirname(paths["thumb_file_path"])
        resolved_filename = paths["filename"]
        # resolved_filename already has the correct extension set by _build_paths.
        # _process_image_internal will re-apply extension correction for safety
        # (idempotent for the FP path, required for process_image_page callers).

        return self._process_image_internal(
            content=content,
            output_main_dir=output_main_dir,
            output_thumb_dir=output_thumb_dir,
            filename=resolved_filename,
            # Pass FP context for logging (product_id used in log messages)
            _log_context=f"product {product_id}",
        )

    def process_image_page(self, content: bytes, domain: str, storage_subdir: str, filename: str):
        """
        Processes an image for a NON-FP page (Chantier D pipeline).

        Output paths use the pages sharding scheme derived from the filename stem::

            <storage_subdir>/pages/{shard1}/{shard2}/{filename}       (main)
            <storage_subdir>/pages/thumbs/{shard1}/{shard2}/{filename} (thumb)

        Shard derivation (char-based, mirrors produit-2/3 scheme):

            shard1 = last character of the filename stem (highest entropy for
                     sequential names like "page-001" → "1", "page-002" → "2")
            shard2 = second-to-last character of the filename stem

        Note: for sequential filenames (``page-001``, ``page-002``, …) the last
        char has 10 entropy values (0..9) but the second-to-last is correlated
        within a single sequential run (e.g. all "page-00X" share shard2="0").
        Distribution is OK across many pages but skewed within a single batch.
        A future improvement could use ``hash(filename) % 100`` for better
        entropy; for now the spec-aligned char-based scheme is used.

        Note on ``domain``: the ``storage_subdir`` is already rooted at the
        domain directory (caller's responsibility). The ``domain`` parameter is
        used only for log message context — it does NOT influence path computation.

        Args:
            content:        Raw image bytes.
            domain:         Domaine source — metadata only, used in log messages
                            (e.g. ``"example.com"``). Path computation uses
                            ``storage_subdir`` exclusively.
            storage_subdir: Absolute base directory for this page's image storage
                            (e.g. ``/nfs/images/example.com/pages/abc123``).
            filename:       Pre-built filename (with extension) for the output file.
                            The extension will be corrected by ``_process_image_internal``
                            if a format conversion occurs (e.g. WebP→PNG).

        Returns:
            dict: main_path, thumb_path, filename, width, height, format, file_size.
        """
        # Compute pages-scheme sharding from the filename stem.
        # shard1 = last char, shard2 = second-to-last char (see docstring above).
        base, _ = os.path.splitext(filename)
        # Pad to at least 2 characters so indexing [-1]/[-2] is always safe
        padded = base.zfill(2) if len(base) < 2 else base
        shard1 = padded[-1]    # last char  — highest entropy for sequential names
        shard2 = padded[-2]    # second-to-last char

        output_main_dir = os.path.join(storage_subdir, "pages", shard1, shard2)
        output_thumb_dir = os.path.join(storage_subdir, "pages", "thumbs", shard1, shard2)

        # makedirs is delegated to _process_image_internal for symmetric
        # responsibility between FP (makedirs via _build_paths) and pages paths.

        return self._process_image_internal(
            content=content,
            output_main_dir=output_main_dir,
            output_thumb_dir=output_thumb_dir,
            filename=filename,
            _log_context=f"page {domain}/{filename}",
        )

    def _process_image_internal(self, content: bytes, output_main_dir: str, output_thumb_dir: str, filename: str, _log_context: str = ""):
        """
        Shared image-processing core: resize + thumbnail + save.

        This private helper knows nothing about FP vs pages path schemes.
        It receives pre-computed output directories and a resolved filename,
        then performs format detection, flatten-on-white, resize (800x800 main,
        110x110 thumb), and saves both files.

        makedirs responsibility: this helper creates output_main_dir and
        output_thumb_dir so that both callers (FP via _build_paths already
        created dirs, and pages via process_image_page which defers here) have
        symmetric mkdir behaviour. The exist_ok=True makes the FP-side call
        idempotent.

        Args:
            content:          Raw image bytes.
            output_main_dir:  Absolute directory for the main (800x800) image.
            output_thumb_dir: Absolute directory for the thumbnail (110x110).
            filename:         Final filename (with extension). The extension is
                              corrected here when format conversion occurs
                              (e.g. WebP→PNG). For FP callers, _build_paths
                              already applied the correct extension, so this
                              correction is idempotent. For process_image_page
                              callers, this correction is the authoritative one.
            _log_context:     Optional string appended to log messages for traceability.

        Returns:
            dict with keys:
                main_path  – absolute path of saved main image
                thumb_path – absolute path of saved thumbnail
                filename   – final filename (with possibly corrected extension)
                width      – width in pixels of the saved main image
                height     – height in pixels of the saved main image
                format     – output format string (e.g. "JPEG", "PNG", "GIF")
                file_size  – size in bytes of the saved main image file
        """
        try:
            if not content:
                raise ValueError("Image content is empty")

            # I3: Create output directories here so both FP and pages callers have
            # symmetric makedirs responsibility. FP: _build_paths already created
            # dirs; exist_ok makes this idempotent. Pages: this is the only makedirs.
            os.makedirs(output_main_dir, exist_ok=True)
            os.makedirs(output_thumb_dir, exist_ok=True)

            # Create fresh BytesIO stream
            image_stream = io.BytesIO(content)
            image_stream.seek(0)

            # Debug: Log first few bytes to check header
            header_bytes = content[:10]
            logger.info(f"Processing image [{_log_context}] - Size: {len(content)} bytes - Header: {header_bytes}")

            # --- SVG: Detect early and delegate to pyvips (librsvg) ---
            if b'<svg' in header_bytes or b'<?xml' in header_bytes:
                logger.info(f"SVG detected for [{_log_context}] ({len(content)} bytes). Rasterizing via pyvips/librsvg.")
                return self._process_with_vips_internal(content, 'SVG', output_main_dir, output_thumb_dir, filename, _log_context=_log_context)

            try:
                # Suppress DecompressionBombWarning as we handle it manually
                Image.MAX_IMAGE_PIXELS = None

                image = Image.open(image_stream)

                width, height = image.size
                total_pixels = width * height
                original_format = image.format.upper() if image.format else "JPEG"

                # --- LARGE IMAGE: Delegate to pyvips (shrink-on-load, ~2-5MB RAM) ---
                if total_pixels > LARGE_IMAGE_THRESHOLD:
                    logger.info(f"Large image detected [{_log_context}] ({width}x{height} = {total_pixels} px, format={original_format}). Using pyvips shrink-on-load.")
                    image.close()
                    return self._process_with_vips_internal(content, original_format, output_main_dir, output_thumb_dir, filename, _log_context=_log_context)

                # NOTE (M1): The "draft mode" JPEG optimisation that was here
                # (image.draft('RGB', (800, 800))) was unreachable: the
                # total_pixels > LARGE_IMAGE_THRESHOLD branch above already
                # handles all images above 50M pixels and returns early via
                # pyvips. The draft branch can never be reached. Removed.

                image.load()  # Force load
            except Exception as pil_error:
                raise pil_error

            original_format = image.format.upper() if image.format else "JPEG"

            # Determine output format and extension based on PHP logic
            # Case 1 (GIF)  -> .gif
            # Case 2 (JPEG) -> .jpg
            # Case 3 (PNG)  -> .png
            # Case 18 (WEBP)-> .png  (PHP converts WebP to PNG)

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

            # C2: Correct filename extension to match actual output format.
            # For FP callers: _build_paths already applied the correct extension
            # (post C1 fix), so this is idempotent (base + same_ext = unchanged).
            # For process_image_page callers: this is the authoritative correction
            # (caller may pass ".webp" filename that must become ".png").
            base, _ = os.path.splitext(filename)
            filename = base + extension

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

            main_file_path = os.path.join(output_main_dir, filename)
            thumb_file_path = os.path.join(output_thumb_dir, filename)

            # Save Main Image
            save_kwargs = {"optimize": True}
            if output_format == 'GIF':
                save_kwargs["save_all"] = True  # Preserve frames if possible, though thumbnail might flatten
                if gif_transparency is not None:
                    save_kwargs["transparency"] = gif_transparency

            main_image.save(main_file_path, output_format, **save_kwargs)
            logger.info(f"PIL: Main image saved [{_log_context}]: {main_file_path}")

            # Capture dimensions and file size after save
            main_width, main_height = main_image.size
            main_file_size = os.path.getsize(main_file_path)

            # --- 3. Thumbnail Creation (110x110) ---
            thumb_max_size = (110, 110)
            thumb_image = image.copy()
            thumb_image.thumbnail(thumb_max_size, Image.Resampling.LANCZOS)

            # For thumbnails, PHP usually uses same format unless specified otherwise.
            # The PHP code: case 1->gif, case 2->jpg, case 3/18->png.
            # So we stick to the determined output_format.

            thumb_image.save(thumb_file_path, output_format, **save_kwargs)
            logger.info(f"PIL: Thumbnail saved [{_log_context}]: {thumb_file_path}")

            return {
                "main_path": main_file_path,
                "thumb_path": thumb_file_path,
                "filename": filename,
                "width": main_width,
                "height": main_height,
                "format": output_format,
                "file_size": main_file_size,
            }

        except Exception as e:
            logger.error(f"Error processing image [{_log_context}]: {e}")
            raise e

    def _process_with_vips_internal(self, content: bytes, original_format: str, output_main_dir: str, output_thumb_dir: str, filename: str, _log_context: str = ""):
        """
        Shared pyvips processing core: shrink-on-load resize + thumbnail + save.

        Knows nothing about FP vs pages path schemes — receives pre-computed dirs.

        Note (M2): _process_with_vips (the FP-specific wrapper that called
        _build_paths then delegated here) has been removed because process_image()
        now handles format detection and _build_paths itself before calling
        _process_image_internal, which in turn calls this method directly.
        The wrapper was unreachable after the C1/C2 refactor.

        Returns:
            dict with keys: main_path, thumb_path, filename, width, height, format, file_size.
        """
        try:
            # Determine output format and extension based on PHP logic
            if original_format == 'GIF':
                output_format_suffix = '.gif'
                extension = '.gif'
                output_format = 'GIF'
            elif original_format in ('JPEG', 'JPG'):
                output_format_suffix = '.jpg'
                extension = '.jpg'
                output_format = 'JPEG'
            elif original_format == 'WEBP':
                # PHP converts WebP to PNG
                output_format_suffix = '.png'
                extension = '.png'
                output_format = 'PNG'
            else:
                output_format_suffix = '.png'
                extension = '.png'
                output_format = 'PNG'

            # Correct filename extension to match actual output format
            base, _ = os.path.splitext(filename)
            filename = base + extension

            main_file_path = os.path.join(output_main_dir, filename)
            thumb_file_path = os.path.join(output_thumb_dir, filename)

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

            logger.info(f"pyvips: Main image saved [{_log_context}]: {main_file_path}")

            # Capture dimensions and file size after save
            main_width = main_vips.width
            main_height = main_vips.height
            main_file_size = os.path.getsize(main_file_path)

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

            logger.info(f"pyvips: Thumbnail saved [{_log_context}]: {thumb_file_path}")

            return {
                "main_path": main_file_path,
                "thumb_path": thumb_file_path,
                "filename": filename,
                "width": main_width,
                "height": main_height,
                "format": output_format,
                "file_size": main_file_size,
            }

        except Exception as e:
            logger.error(f"Error processing large image with pyvips [{_log_context}]: {e}")
            raise e

    def _build_paths(self, domain: str, product_id: str, product_name: str, base_storage_dir: str, extension: str, filename: str = "", index: int = 0):
        """
        Builds the sharded directory paths and filename for a product image.
        Shared between PIL and pyvips processing paths.
        Used exclusively by the FP flow (process_image).

        Args:
            extension: Extension avec point (ex: ".jpg"). Utilisée pour corriger
                       l'extension du filename ET pour construire le filename
                       legacy quand ``filename`` est vide.
                       Must be the ACTUAL output extension (post format-detection),
                       not a guess based on the input filename.
            filename:  Nom de fichier pré-construit (ex: via _build_filename).
                       Prend la priorité sur index si non vide.
                       The extension will be replaced with ``extension`` to enforce
                       format-content consistency (e.g. webp→png conversion).
            index:     Paramètre legacy ; utilisé uniquement si filename est vide.
        """
        # Create sharded path components
        product_id_str = str(product_id)
        if len(product_id_str) < 3:
            product_id_str = product_id_str.zfill(3)

        rep1 = product_id_str[-1]
        rep2 = product_id_str[-2]
        rep3 = product_id_str[-3]

        # Filename : utilise le filename explicite si fourni, sinon construit depuis index (legacy)
        if filename:
            # Enforce actual output extension to match content (e.g., webp→png conversion)
            base, _ = os.path.splitext(filename)
            filename = base + extension
        else:
            normalized_name = self._normalize_name(product_name)
            if index > 0:
                filename = f"{normalized_name}-{product_id}-{index}{extension}"
            else:
                filename = f"{normalized_name}-{product_id}{extension}"

        # Define paths
        # /images/{domain}/produit-2/X/Y/Z/ (Main)
        main_rel_dir = os.path.join("images", domain, "produit-2", rep1, rep2, rep3)
        main_full_dir = os.path.join(base_storage_dir, main_rel_dir)

        # /images/{domain}/produit-3/X/Y/Z/ (Thumbnail)
        thumb_rel_dir = os.path.join("images", domain, "produit-3", rep1, rep2, rep3)
        thumb_full_dir = os.path.join(base_storage_dir, thumb_rel_dir)

        # Create directories (FP path — _process_image_internal will also call
        # makedirs with exist_ok=True, making this idempotent)
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
