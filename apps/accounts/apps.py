from django.apps import AppConfig
from django.utils import timezone


def _on_user_logged_in(sender, request, user, **kwargs):
    if request and user.role == "OWNER":
        from .services import initialize_session
        initialize_session(request, user, remember_device=False)


def _on_user_verified(sender, request, user, device, **kwargs):
    if request and user.role == "OWNER":
        request.session["mfa_verified_at"] = timezone.now().isoformat()


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
    label = "accounts"

    def ready(self):
        from django.contrib.auth.signals import user_logged_in
        from two_factor.signals import user_verified
        user_logged_in.connect(_on_user_logged_in, dispatch_uid="eduweb_owner_logged_in")
        user_verified.connect(_on_user_verified, dispatch_uid="eduweb_owner_mfa_verified")
