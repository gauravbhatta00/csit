import io
import mimetypes
import os

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from PIL import Image, ImageOps, UnidentifiedImageError


IMAGE_FORMAT_EXTENSIONS = {
    'AVIF': '.avif',
    'WEBP': '.webp',
}


def get_target_image_format():
    requested_format = getattr(settings, 'MEDIA_IMAGE_FORMAT', 'WEBP').upper()
    if requested_format == 'AVIF' and '.avif' not in Image.registered_extensions():
        return 'WEBP'
    return requested_format if requested_format in IMAGE_FORMAT_EXTENSIONS else 'WEBP'


def optimize_uploaded_image(name, content):
    if getattr(settings, 'MEDIA_IMAGE_FORMAT', 'WEBP').strip().upper() == 'ORIGINAL':
        return name, content

    position = None
    if hasattr(content, 'tell') and hasattr(content, 'seek'):
        try:
            position = content.tell()
        except (OSError, ValueError):
            position = None

    try:
        raw_content = content.read()
    except AttributeError:
        return name, content

    try:
        image = Image.open(io.BytesIO(raw_content))
        image.load()
    except (OSError, UnidentifiedImageError):
        if position is not None:
            content.seek(position)
        return name, content

    image = ImageOps.exif_transpose(image)
    target_format = get_target_image_format()

    if image.mode not in ('RGB', 'RGBA'):
        image = image.convert('RGBA' if 'A' in image.getbands() else 'RGB')
    if target_format == 'AVIF' and image.mode == 'P':
        image = image.convert('RGBA')

    output = io.BytesIO()
    try:
        image.save(output, **get_image_save_kwargs(target_format))
    except (OSError, ValueError):
        if target_format != 'AVIF':
            raise
        target_format = 'WEBP'
        output = io.BytesIO()
        image.save(output, **get_image_save_kwargs(target_format))
    output.seek(0)

    root, _extension = os.path.splitext(name)
    optimized_name = f'{root}{IMAGE_FORMAT_EXTENSIONS[target_format]}'
    optimized_content = ContentFile(output.read(), name=optimized_name)
    optimized_content.content_type = mimetypes.types_map.get(
        IMAGE_FORMAT_EXTENSIONS[target_format],
        f'image/{target_format.lower()}',
    )
    return optimized_name, optimized_content


def get_image_save_kwargs(image_format):
    save_kwargs = {
        'format': image_format,
        'quality': getattr(settings, 'MEDIA_IMAGE_QUALITY', 82),
        'optimize': True,
    }
    if image_format == 'WEBP':
        save_kwargs['method'] = getattr(settings, 'MEDIA_WEBP_METHOD', 6)
    return save_kwargs


class MediaOptimizingMixin:
    def save(self, name, content, max_length=None):
        name, content = optimize_uploaded_image(name, content)
        return super().save(name, content, max_length=max_length)


class OptimizedFileSystemStorage(MediaOptimizingMixin, FileSystemStorage):
    pass


try:
    from storages.backends.s3 import S3Storage
except ImportError:
    S3Storage = None


if S3Storage:
    class R2MediaStorage(MediaOptimizingMixin, S3Storage):
        default_acl = None
        querystring_auth = False

        def get_object_parameters(self, name):
            parameters = super().get_object_parameters(name)
            parameters.setdefault('CacheControl', 'max-age=31536000, public')
            return parameters
else:
    class R2MediaStorage(MediaOptimizingMixin, FileSystemStorage):
        def __init__(self, *args, **kwargs):
            raise ImportError(
                'django-storages and boto3 are required when Cloudflare R2 media storage is enabled.'
            )
