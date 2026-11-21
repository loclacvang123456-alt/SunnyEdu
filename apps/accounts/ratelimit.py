import hashlib
import hmac
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from .models import LoginBucket


def key_for(kind, value):
    return hmac.new(settings.RATE_LIMIT_HMAC_KEY.encode(), f"{kind}:{value}".encode(), hashlib.sha256).hexdigest()


def window(now, minutes=10):
    return now.replace(minute=(now.minute // minutes) * minutes, second=0, microsecond=0)


def consume(kind, value, limit, minutes=10):
    now = timezone.now()
    start = window(now, minutes=minutes)
    key = key_for(kind, value)
    with transaction.atomic():
        bucket, _ = LoginBucket.objects.get_or_create(bucket_key=key, window_start=start)
        bucket = LoginBucket.objects.select_for_update().get(pk=bucket.pk)
        if bucket.count >= limit:
            return max(1, int((start + timedelta(minutes=minutes) - now).total_seconds()))
        bucket.count = F("count") + 1
        bucket.save(update_fields=["count"])
    return 0


def check_bucket(kind, value, limit, minutes=10):
    """Return Retry-After seconds if bucket reached limit without incrementing."""
    now = timezone.now()
    start = window(now, minutes=minutes)
    bucket = LoginBucket.objects.filter(bucket_key=key_for(kind, value), window_start=start).first()
    if bucket and bucket.count >= limit:
        return max(1, int((start + timedelta(minutes=minutes) - now).total_seconds()))
    return 0


def check_code(code):
    from .services import find_student
    now = timezone.now()
    start = window(now)
    key = key_for("code", code.upper().replace("-", "").replace(" ", ""))
    with transaction.atomic():
        bucket, _ = LoginBucket.objects.get_or_create(bucket_key=key, window_start=start)
        bucket = LoginBucket.objects.select_for_update().get(pk=bucket.pk)
        if bucket.count >= 10:
            return None, max(1, int((start + timedelta(minutes=10) - now).total_seconds()))
        student = find_student(code)
        if student is None:
            bucket.count = F("count") + 1
            bucket.save(update_fields=["count"])
        return student, 0
