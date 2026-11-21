import json
import os
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from django.utils import timezone
from apps.assignments.models import Response
from apps.assignments.services import course_access_allowed
from apps.accounts.ratelimit import consume
from .writing_assistance import AssistanceUnavailable, check_writing


def error(code, message, status):
    return JsonResponse({'error': {'code': code, 'message': message}}, status=status)


@never_cache
@require_POST
def check(request, response_id):
    user = request.user
    if not user.is_authenticated or user.role != 'STUDENT' or user.status != 'ACTIVE':
        return error('UNAUTHENTICATED', 'Vui lòng đăng nhập.', 401)
    response = Response.objects.select_related('attempt__recipient__assignment', 'question').filter(
        pk=response_id, attempt__recipient__student=user,
    ).first()
    if not response:
        return error('NOT_FOUND', 'Không tìm thấy câu trả lời.', 404)
    attempt = response.attempt
    recipient = attempt.recipient
    assignment = recipient.assignment
    now = timezone.now()
    if (getattr(assignment, 'mode', None) != 'PRACTICE' or assignment.status != 'PUBLISHED'
            or recipient.state != 'ASSIGNED' or recipient.current_attempt_id != attempt.id
            or attempt.status != 'IN_PROGRESS' or response.question.type != 'TEXT'
            or response.question.version_id != assignment.version_id
            or not assignment.opens_at <= now < assignment.late_until
            or not course_access_allowed(assignment.id, user)):
        return error('NOT_AVAILABLE', 'Không thể kiểm tra câu trả lời này.', 403)
    if len(request.body) > 65536:
        return error('INVALID_INPUT', 'Bài viết quá dài.', 422)
    try:
        data = json.loads(request.body)
        if not isinstance(data, dict) or not isinstance(data.get('text'), str):
            raise ValueError
        retry = consume('writing-user', str(user.pk), 12, minutes=1) or consume('writing-global', 'all', 120, minutes=1)
        if retry:
            result = error('RATE_LIMIT', 'Em hãy đợi một chút rồi kiểm tra lại.', 429)
            result['Retry-After'] = str(retry)
            return result
        result = check_writing(data['text'], os.environ.get('LANGUAGETOOL_URL', ''))
    except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
        return error('INVALID_INPUT', 'Hãy nhập bài viết tối đa 10.000 ký tự.', 422)
    except AssistanceUnavailable:
        return error('UNAVAILABLE', 'Chức năng kiểm tra bài viết hiện chưa khả dụng.', 503)
    return JsonResponse({'data': result})
