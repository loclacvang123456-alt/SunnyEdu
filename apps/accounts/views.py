import json
from django.contrib.auth import login, logout
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST
from .services import find_student, initialize_session
from .ratelimit import consume, check_code


def error(code, message, status=400):
    return JsonResponse({"error": {"code": code, "message": message}}, status=status)


@never_cache
@ensure_csrf_cookie
@require_GET
def student_login_page(request):
    return render(request, "accounts/student_login.html")


@never_cache
@ensure_csrf_cookie
@require_GET
def csrf(request):
    return JsonResponse({"data": {"ok": True}})


@never_cache
@require_POST
def student_login(request):
    try:
        body = json.loads(request.body)
        code = body["code"]
        remember = body.get("remember_device", False)
        if not isinstance(code, str) or len(code) > 100 or not isinstance(remember, bool):
            raise ValueError
    except (ValueError, KeyError, TypeError):
        return error("INVALID_INPUT", "Thông tin không hợp lệ.", 400)
    ip = request.META.get("REMOTE_ADDR", "")
    for kind, value, limit in (("global", "all", 3000), ("ip", ip, 300)):
        retry = consume(kind, value, limit)
        if retry:
            response = error("RATE_LIMIT", "Em hãy thử lại sau.", 429)
            response["Retry-After"] = str(retry)
            return response
    student, retry = check_code(code)
    if retry:
        response = error("RATE_LIMIT", "Em hãy thử lại sau.", 429)
        response["Retry-After"] = str(retry)
        return response
    if student is None:
        return error("INVALID_CODE", "Mã chưa đúng hoặc đã được đổi.", 401)
    login(request, student, backend="django.contrib.auth.backends.ModelBackend")
    initialize_session(request, student, remember)
    return JsonResponse({"data": {"user": {"id": str(student.pk), "display_name": student.display_name, "role": student.role}, "session_expires_at": request.session.get_expiry_date().isoformat()}})


@never_cache
@require_POST
def student_logout(request):
    logout(request)
    return JsonResponse({"data": {"ok": True}})


@never_cache
@require_GET
def me(request):
    if not request.user.is_authenticated:
        return error("UNAUTHENTICATED", "Vui lòng đăng nhập.", 401)
    return JsonResponse({"data": {"id": str(request.user.pk), "display_name": request.user.display_name, "role": request.user.role, "remember_device": request.session.get("remember_device", False), "server_time": timezone.now().isoformat()}})
