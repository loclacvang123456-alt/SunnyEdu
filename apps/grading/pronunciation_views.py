"""Authenticated pronunciation practice, with consent per recording."""
import os

from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.ratelimit import consume
from .pronunciation import (MAX_AUDIO_BYTES, InvalidPractice, PronunciationBusy,
                            PronunciationUnavailable, assess, configured, validate_reference, validate_wav)


def active_student(request):
    return request.user.is_authenticated and request.user.role == 'STUDENT' and request.user.status == 'ACTIVE'


def unavailable():
    return JsonResponse({'error': {'code': 'UNAVAILABLE', 'message': 'Chức năng luyện phát âm hiện chưa khả dụng.'}}, status=503)


def threshold():
    try:
        value = float(os.environ.get('AZURE_PRONUNCIATION_THRESHOLD', '75'))
        return value if 0 <= value <= 100 else 75
    except ValueError:
        return 75


@never_cache
@ensure_csrf_cookie
@require_GET
def practice(request):
    if not active_student(request):
        return redirect('/login/') if not request.user.is_authenticated else JsonResponse({'error': {'code': 'FORBIDDEN'}}, status=403)
    available = configured(os.environ.get('AZURE_SPEECH_KEY', ''), os.environ.get('AZURE_SPEECH_REGION', ''))
    return render(request, 'student/speaking_practice.html', {'available': available, 'threshold': threshold(), 'active': 'speaking'})


@never_cache
@require_POST
def check(request):
    if not active_student(request):
        return JsonResponse({'error': {'code': 'UNAUTHENTICATED', 'message': 'Hãy đăng nhập để luyện nói.'}}, status=401)
    key = os.environ.get('AZURE_SPEECH_KEY', '')
    region = os.environ.get('AZURE_SPEECH_REGION', '')
    if not configured(key, region):
        return unavailable()
    try:
        content_length = int(request.META.get('CONTENT_LENGTH', '0'))
    except (ValueError, TypeError):
        content_length = 0
    if content_length <= 0 or content_length > MAX_AUDIO_BYTES + 16384:
        return JsonResponse({'error': {'code': 'INVALID_INPUT', 'message': 'Bản ghi không hợp lệ hoặc quá lớn.'}}, status=422)
    # The checkbox applies to this request only. Do not persist consent or audio.
    if request.POST.get('consent') != 'yes':
        return JsonResponse({'error': {'code': 'CONSENT_REQUIRED', 'message': 'Hãy xác nhận trước khi gửi bản ghi.'}}, status=422)
    upload = request.FILES.get('audio')
    if not upload or upload.size > MAX_AUDIO_BYTES:
        return JsonResponse({'error': {'code': 'INVALID_INPUT', 'message': 'Bản ghi không hợp lệ hoặc quá lớn.'}}, status=422)
    try:
        reference = validate_reference(request.POST.get('reference', ''))
        blob = upload.read(MAX_AUDIO_BYTES + 1)
        validate_wav(blob)
    except InvalidPractice:
        return JsonResponse({'error': {'code': 'INVALID_INPUT', 'message': 'Câu mẫu hoặc tệp ghi âm không hợp lệ.'}}, status=422)
    retry_after = consume('pronunciation-student', str(request.user.pk), 12, minutes=10)
    if retry_after:
        response = JsonResponse({'error': {'code': 'RATE_LIMIT', 'message': 'Em đã thử nhiều lần. Hãy đợi một chút rồi thử lại.'}}, status=429)
        response['Retry-After'] = str(retry_after)
        return response
    try:
        result = assess(reference, blob, key, region)
    except PronunciationBusy:
        response = JsonResponse({'error': {'code': 'BUSY', 'message': 'Có bạn đang luyện nói. Em hãy thử lại sau.'}}, status=429)
        response['Retry-After'] = '5'
        return response
    except (PronunciationUnavailable, InvalidPractice):
        return unavailable()
    return JsonResponse({'data': {**result, 'threshold': threshold()}})
