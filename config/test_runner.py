import shutil
import tempfile
from pathlib import Path

from django.conf import settings
from django.test.runner import DiscoverRunner


def remove_test_media(directory):
    """Remove only prefixed media directories under temporary storage."""
    target = Path(directory).resolve()
    temporary_root = Path(tempfile.gettempdir()).resolve()
    if target.parent != temporary_root:
        raise ValueError("Test media must be inside the temporary root")
    if not target.name.startswith("videoflix-test-"):
        raise ValueError("Refusing to remove a directory without test prefix")
    shutil.rmtree(target)


class IsolatedRunner(DiscoverRunner):
    """Remove isolated media directories after the test environment stops."""

    def teardown_test_environment(self, **kwargs):
        """Release test resources and remove both isolated media trees."""
        try:
            super().teardown_test_environment(**kwargs)
        finally:
            remove_test_media(settings.MEDIA_ROOT)
            remove_test_media(settings.PRIVATE_MEDIA_ROOT)
