"""Teacher (OWNER) authentication and mandatory TOTP views built on django-two-factor-auth."""
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import redirect
from django.utils import timezone
from django.views import View
from two_factor.forms import AuthenticationTokenForm, BackupTokenForm
from two_factor.utils import default_device
from two_factor.views import LoginView, SetupView

from .models import AuditEvent, User
from .ratelimit import check_bucket, consume


class OwnerAuthenticationForm(AuthenticationForm):
    """Restrict password authentication exclusively to active OWNER accounts."""

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if user.role != User.Role.OWNER or user.status != User.Status.ACTIVE:
            raise ValidationError(self.error_messages["invalid_login"], code="invalid_login")


class OwnerLoginView(LoginView):
    """Two-factor login view for OWNER with IP and per-account rate limiting."""

    form_list = (
        (LoginView.AUTH_STEP, OwnerAuthenticationForm),
        (LoginView.TOKEN_STEP, AuthenticationTokenForm),
        (LoginView.BACKUP_STEP, BackupTokenForm),
    )

    condition_dict = {
        LoginView.TOKEN_STEP: lambda wizard: not settings.TEACHER_OTP_BYPASS and wizard.has_token_step(),
        LoginView.BACKUP_STEP: lambda wizard: not settings.TEACHER_OTP_BYPASS and wizard.has_backup_step(),
    }

    def _target_username(self):
        user = self.get_user() if self.steps.current != self.AUTH_STEP else None
        if user and getattr(user, "username", None):
            return user.username.strip().lower()
        return self.request.POST.get("auth-username", "").strip().lower()

    def post(self, *args, **kwargs):
        ip = self.request.META.get("REMOTE_ADDR", "")
        retry = consume("ip", ip, 300)
        if retry:
            resp = HttpResponse("Quá nhiều yêu cầu đăng nhập. Vui lòng thử lại sau.", status=429)
            resp["Retry-After"] = str(retry)
            return resp
        username = self._target_username()
        if username:
            retry = check_bucket("owner_login", username, 5, minutes=15)
            if retry:
                resp = HttpResponse("Tài khoản tạm thời giới hạn thử đăng nhập. Vui lòng thử lại sau.", status=429)
                resp["Retry-After"] = str(retry)
                return resp
        return super().post(*args, **kwargs)

    def render(self, form=None, **kwargs):
        if form and form.is_bound and not form.is_valid():
            username = self._target_username()
            if username:
                consume("owner_login", username, 5, minutes=15)
        return super().render(form=form, **kwargs)

    def process_step(self, form):
        if self.steps.current == self.AUTH_STEP:
            self.storage.extra_data["remember_device"] = self.request.POST.get("remember_device") == "on"
        return super().process_step(form)

    def done(self, form_list, **kwargs):
        remember_device = self.storage.extra_data.get("remember_device", False)
        response = super().done(form_list, **kwargs)
        if remember_device:
            self.request.session["remember_device"] = True
            self.request.session.set_expiry(30 * 86400)
        user = self.get_user()
        AuditEvent.objects.create(actor=user, action="owner.login", target_type="user", target_id=user.pk)
        if not settings.TEACHER_OTP_BYPASS and not default_device(user):
            return redirect("two_factor:setup")
        return response


class OwnerSetupView(SetupView):
    """TOTP setup view restricted to authenticated active OWNER."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("owner_login")
        if request.user.role != User.Role.OWNER or request.user.status != User.Status.ACTIVE:
            return HttpResponseForbidden("Không có quyền truy cập.")
        return super().dispatch(request, *args, **kwargs)

    def done(self, form_list, **kwargs):
        response = super().done(form_list, **kwargs)
        self.request.session["mfa_verified_at"] = timezone.now().isoformat()
        AuditEvent.objects.create(actor=self.request.user, action="owner.mfa.setup", target_type="user", target_id=self.request.user.pk)
        return response


class OwnerDisableView(View):
    """Prevent OWNER from disabling mandatory TOTP from the web UI."""

    def get(self, request, *args, **kwargs):
        messages.warning(request, "Tài khoản giáo viên bắt buộc xác thực hai bước (TOTP). Liên hệ vận hành khi mất thiết bị.")
        return redirect("two_factor:profile")

    def post(self, request, *args, **kwargs):
        return HttpResponseForbidden("Không được tắt TOTP qua giao diện web.")
