from django.core.files.storage import FileSystemStorage


def safe_media_url(file_field, missing_value=None):
    if not file_field or not getattr(file_field, 'name', ''):
        return missing_value

    storage = getattr(file_field, 'storage', None)
    if isinstance(storage, FileSystemStorage) and not storage.exists(file_field.name):
        return missing_value

    try:
        return file_field.url
    except ValueError:
        return missing_value
