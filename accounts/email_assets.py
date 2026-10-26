from email.mime.image import MIMEImage
from pathlib import Path

from django.conf import settings


def attach_logo(message):
    path = Path(settings.BASE_DIR) / "templates/emails/assets/logo.png"
    logo = MIMEImage(path.read_bytes(), _subtype="png")
    logo.add_header("Content-ID", "<videoflix-logo>")
    logo.add_header("Content-Disposition", "inline", filename="videoflix.png")
    message.mixed_subtype = "related"
    message.attach(logo)
