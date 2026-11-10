from django.conf import settings
from django.core.files.storage import FileSystemStorage


def private_storage():
    """Create source storage outside the publicly served media directory."""
    return FileSystemStorage(location=settings.PRIVATE_MEDIA_ROOT)
