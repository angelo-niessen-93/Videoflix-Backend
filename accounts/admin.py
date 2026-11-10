from django import forms
from django.contrib import admin
from django.contrib.admin.forms import AdminAuthenticationForm
from django.contrib.auth.admin import UserAdmin

from .models import User


class EmailAdminAuthenticationForm(AdminAuthenticationForm):
    """Authenticate staff using the existing email backend."""

    username = forms.EmailField(
        label="Email address",
        widget=forms.EmailInput(
            attrs={"autofocus": True, "autocomplete": "email"}
        ),
    )
    error_messages = {
        **AdminAuthenticationForm.error_messages,
        "invalid_login": (
            "Enter the correct email address and password for a staff account."
        ),
    }


@admin.register(User)
class EmailUserAdmin(UserAdmin):
    """Expose account emails prominently without changing stored identities."""

    list_display = ("email", "username", "is_staff", "is_active")
    ordering = ("email",)


admin.site.login_form = EmailAdminAuthenticationForm
admin.site.site_header = "Videoflix administration"
admin.site.site_title = "Videoflix admin"
admin.site.index_title = "Content and account management"
