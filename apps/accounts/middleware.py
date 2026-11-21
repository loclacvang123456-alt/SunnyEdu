from datetime import timedelta
from django.contrib.auth import logout
from django.utils import timezone
from django.utils.dateparse import parse_datetime


class SessionValidityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            now = timezone.now()
            issued = parse_datetime(request.session.get("issued_at", ""))
            last = parse_datetime(request.session.get("last_activity", ""))
            student = request.user.role == "STUDENT"
            remembered = request.session.get("remember_device", False)
            absolute = timedelta(days=30) if remembered else timedelta(hours=2 if student else 8)
            idle = timedelta(days=14) if remembered else timedelta(minutes=30)
            if (request.user.status != "ACTIVE" or request.session.get("auth_epoch") != request.user.auth_epoch or not issued or not last or timezone.is_naive(issued) or timezone.is_naive(last) or now - issued >= absolute or now - last >= idle):
                logout(request)
            else:
                request.session["last_activity"] = now.isoformat()
        return self.get_response(request)
