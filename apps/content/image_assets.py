"""Validate and store exercise illustrations without publicly exposing files."""
import hashlib
import io
import uuid
import warnings
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from PIL import Image, ImageOps, UnidentifiedImageError

from .models import Asset

MAX_INPUT_BYTES = 5 * 1024 * 1024
MAX_OUTPUT_BYTES = 10 * 1024 * 1024
MAX_DIMENSION = 4096
MAX_PIXELS = 4_000_000


def encode_safe_png(uploaded_file):
    """Decode a bounded image then re-encode pixels only, removing metadata."""
    if getattr(uploaded_file, 'size', 0) and uploaded_file.size > MAX_INPUT_BYTES:
        raise ValidationError('Ảnh vượt quá 5 MiB.')
    raw = bytearray()
    for chunk in uploaded_file.chunks():
        raw.extend(chunk)
        if len(raw) > MAX_INPUT_BYTES:
            raise ValidationError('Ảnh vượt quá 5 MiB.')
    if not raw:
        raise ValidationError('Tệp ảnh trống.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw), formats=['JPEG', 'PNG', 'WEBP']) as image:
                width, height = image.size
                if (not 1 <= width <= MAX_DIMENSION or not 1 <= height <= MAX_DIMENSION
                        or width * height > MAX_PIXELS or getattr(image, 'n_frames', 1) != 1):
                    raise ValidationError('Kích thước ảnh không hợp lệ hoặc ảnh động không được hỗ trợ.')
                image.verify()
            with Image.open(io.BytesIO(raw), formats=['JPEG', 'PNG', 'WEBP']) as image:
                image.load()
                oriented = ImageOps.exif_transpose(image)
                mode = 'RGBA' if 'A' in oriented.getbands() or 'transparency' in oriented.info else 'RGB'
                converted = oriented.convert(mode)
                clean = Image.new(mode, converted.size)
                clean.paste(converted)
                out = io.BytesIO()
                clean.save(out, format='PNG', optimize=True)
                data = out.getvalue()
                if len(data) > MAX_OUTPUT_BYTES:
                    raise ValidationError('Ảnh sau xử lý quá lớn.')
                return data
    except ValidationError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombWarning, Image.DecompressionBombError) as exc:
        raise ValidationError('Chỉ nhận ảnh JPEG, PNG hoặc WebP hợp lệ.') from exc


def store_prompt_image(owner, uploaded_file):
    data = encode_safe_png(uploaded_file)
    asset_id = uuid.uuid4()
    object_key = f'prompt_image/{asset_id}'
    root = Path(settings.PRIVATE_MEDIA_ROOT).resolve()
    destination = root / object_key
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.parent.resolve().is_relative_to(root):
        raise ValidationError('Thư mục ảnh không hợp lệ.')
    created = False
    try:
        # Exclusive creation avoids overwriting any other object.
        stream = destination.open('xb')
        created = True
        with stream:
            stream.write(data)
        return Asset.objects.create(
            id=asset_id, uploaded_by=owner, purpose='PROMPT_IMAGE',
            object_key=object_key, original_name=Path(uploaded_file.name or '').name[:255],
            detected_mime='image/png', bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(), status=Asset.Status.READY,
        )
    except Exception:
        if created:
            destination.unlink(missing_ok=True)
        raise
