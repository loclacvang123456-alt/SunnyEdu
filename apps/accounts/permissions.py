"""Shared owner permission, MFA freshness, and JSON API helpers."""
import json
import uuid
from datetime import timedelta
from functools import wraps
from urllib.parse import urlencode

from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django_otp import match_token
from two_factor.utils import default_device


def is_verified_owner(user):
    """Return True when user is an active OWNER with a verified OTP session."""
    return (
        bool(user)
        and user.is_authenticated
        and user.role == "OWNER"
        and user.status == "ACTIVE"
        and (settings.TEACHER_OTP_BYPASS or (callable(getattr(user, "is_verified", None)) and user.is_verified()))
    )


def recent_mfa_verified(request, max_age_seconds=600):
    """Return True if session MFA verification timestamp is within max_age_seconds."""
    raw = request.session.get("mfa_verified_at")
    verified_at = parse_datetime(raw) if isinstance(raw, str) else None
    if not verified_at or timezone.is_naive(verified_at):
        return False
    return timezone.now() - verified_at <= timedelta(seconds=max_age_seconds)


def verify_recent_mfa(request, otp_token=None, max_age_seconds=600):
    """Check recent MFA or validate a fresh TOTP token and update session timestamp."""
    if not is_verified_owner(request.user):
        return False
    if settings.TEACHER_OTP_BYPASS:
        return True
    if recent_mfa_verified(request, max_age_seconds=max_age_seconds):
        return True
    token = (otp_token or "").strip()
    if token and match_token(request.user, token):
        request.session["mfa_verified_at"] = timezone.now().isoformat()
        return True
    return False


def api_error(code, message, status=400, fields=None):
    """Return standard API error envelope without stack traces or private data."""
    payload = {"code": code, "message": message}
    if fields:
        payload["fields"] = fields
    return JsonResponse({"error": payload}, status=status)


def read_json_body(request):
    """Parse JSON request body as a dictionary or raise ValidationError."""
    try:
        data = json.loads(request.body or b"{}")
        if not isinstance(data, dict):
            raise ValueError
        return data
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        raise ValidationError("JSON không hợp lệ.") from exc


def parse_uuid(value, label="ID"):
    """Validate and convert string to UUID or raise ValidationError."""
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValidationError(f"{label} không hợp lệ.") from exc


def owner_api_required(view):
    """Enforce authenticated, active, OTP-verified OWNER access on API endpoints."""
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return api_error("UNAUTHENTICATED", "Vui lòng đăng nhập.", 401)
        if not is_verified_owner(request.user):
            return api_error("FORBIDDEN", "Cần tài khoản giáo viên đã xác thực hai bước.", 403)
        return view(request, *args, **kwargs)
    return wrapped


def owner_ui_required(view):
    """Enforce active OWNER + mandatory TOTP setup/verification for teacher UI pages."""
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            return redirect(f"{reverse('owner_login')}?{urlencode({'next': request.get_full_path()})}")
        if user.role != "OWNER" or user.status != "ACTIVE":
            return HttpResponseForbidden("Không có quyền truy cập.")
        if not settings.TEACHER_OTP_BYPASS and (not callable(getattr(user, "is_verified", None)) or not user.is_verified()):
            if not default_device(user):
                return redirect("two_factor:setup")
            return redirect(f"{reverse('owner_login')}?{urlencode({'next': request.get_full_path()})}")
        return view(request, *args, **kwargs)
    return wrapped
