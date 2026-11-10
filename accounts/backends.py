from django.contrib.auth.backends import ModelBackend

from .models import User


class EmailBackend(ModelBackend):
    """Resolve login identifiers as case-insensitive email addresses."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        """Authenticate credentials and apply the configured account policy."""
        email = username or kwargs.get("email", "")
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            User().set_password(password)
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
