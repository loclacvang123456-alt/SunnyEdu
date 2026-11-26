import json
import hashlib
import hmac
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from .models import AssignmentRecipient, Attempt, PracticeShot, Response
from .services import ConflictError, course_access_allowed, fire_practice_shot, start_attempt, save_response


def error(code, message, status):
    return JsonResponse({'error': {'code': code, 'message': message}}, status=status)


def student_required(request):
    return request.user.is_authenticated and request.user.role == 'STUDENT' and request.user.status == 'ACTIVE'


@never_cache
@require_GET
def assignments(request):
    if not student_required(request):
        return error('UNAUTHENTICATED', 'Vui lòng đăng nhập.', 401)
    rows = AssignmentRecipient.objects.filter(student=request.user, state='ASSIGNED', assignment__status='PUBLISHED').select_related('assignment').order_by('assignment__due_at')
    return JsonResponse({'data': [{'id': str(r.assignment_id), 'title': r.assignment.title, 'due_at': r.assignment.due_at.isoformat(), 'late_until': r.assignment.late_until.isoformat() if r.assignment.late_until else None, 'current_attempt_id': str(r.current_attempt_id) if r.current_attempt_id else None} for r in rows if course_access_allowed(r.assignment_id, request.user)]})


@never_cache
@require_POST
def start(request, assignment_id):
    if not student_required(request):
        return error('UNAUTHENTICATED', 'Vui lòng đăng nhập.', 401)
    recipient = get_object_or_404(AssignmentRecipient, assignment_id=assignment_id, student=request.user)
    try:
        attempt, created = start_attempt(recipient.id, request.user)
    except PermissionDenied:
        return error('NOT_AVAILABLE', 'Bài này chưa mở hoặc đã đóng.', 403)
    return JsonResponse({'data': {'attempt_id': str(attempt.id), 'revision': attempt.revision}}, status=201 if created else 200)


@never_cache
@require_GET
def attempt_detail(request, attempt_id):
    if not student_required(request):
        return error('UNAUTHENTICATED', 'Vui lòng đăng nhập.', 401)
    attempt = get_object_or_404(Attempt.objects.select_related('recipient__assignment'), pk=attempt_id, recipient__student=request.user)
    if (attempt.recipient.state != 'ASSIGNED' or attempt.recipient.assignment.status != 'PUBLISHED'
            or not course_access_allowed(attempt.recipient.assignment_id, request.user)):
        return error('NOT_AVAILABLE', 'Bài này không còn khả dụng.', 403)
    assignment = attempt.recipient.assignment
    result = []
    for response in attempt.responses.select_related('question__passage', 'practice_shot').prefetch_related('question__options', 'options', 'question__answer_keys'):
        question = response.question
        options = list(question.options.all())
        if question.type == 'WORD_ORDER':
            correct_words = [option.content for option in options]
            options.sort(key=lambda option: hmac.new(settings.SECRET_KEY.encode(), f'{attempt.id}:{option.id}'.encode(), hashlib.sha256).digest())
            if [option.content for option in options] == correct_words:
                for index in range(1, len(options)):
                    if options[index].content != options[0].content:
                        options[0], options[index] = options[index], options[0]
                        break
        elif question.type in ('SINGLE_CHOICE', 'MULTIPLE_CHOICE'):
            options.sort(key=lambda option: hmac.new(settings.SECRET_KEY.encode(), f'{attempt.id}:option:{option.id}'.encode(), hashlib.sha256).digest())
        item = {'response_id': str(response.id), 'question_id': str(question.id), 'position': question.position, 'type': question.type, 'pirate_game': question.pirate_game, 'prompt': question.prompt, 'max_points': str(question.max_points), 'passage_text': question.passage.text_body if question.passage_id else '', 'options': [{'id': str(o.id), 'content': o.content} for o in options] if question.type in ('SINGLE_CHOICE', 'MULTIPLE_CHOICE', 'STRESS_CHOICE', 'WORD_ORDER') else [], 'response_revision': response.revision, 'text_answer': response.text_answer, 'selected_options': [str(o.id) for o in response.options.all()], 'ordered_option_ids': response.ordered_option_ids if question.type == 'WORD_ORDER' else [], 'image_url': question.image_url}
        if assignment.instant_feedback:
            item['correct_option_ids'] = [str(k.option_id) for k in question.answer_keys.all()]
        try:
            shot = response.practice_shot
        except PracticeShot.DoesNotExist:
            shot = None
        item['shot'] = shot_receipt(shot) if shot else None
        if question.type == 'MATCH_IMAGE':
            images = list(question.match_images.all())
            words = list(question.match_words.all())
            images.sort(key=lambda image: hmac.new(settings.SECRET_KEY.encode(), f'{attempt.id}:image:{image.id}'.encode(), hashlib.sha256).digest())
            words.sort(key=lambda word: hmac.new(settings.SECRET_KEY.encode(), f'{attempt.id}:word:{word.id}'.encode(), hashlib.sha256).digest())
            item['match_images'] = [{'id': str(image.id), 'url': f'/api/v1/attempts/{attempt.id}/images/{image.id}/'} for image in images]
            item['match_words'] = [{'id': str(word.id), 'text': word.text} for word in words]
            item['match_pairs'] = response.match_pairs
        result.append(item)
    return JsonResponse({'data': {'id': str(attempt.id), 'status': attempt.status, 'revision': attempt.revision, 'game_feedback_enabled': assignment.mode == 'PRACTICE' and assignment.game_feedback_enabled, 'instant_feedback': bool(assignment.instant_feedback), 'questions': result}})


def shot_receipt(shot):
    return {'option_id': str(shot.option_id), 'correct': shot.correct,
            'response_revision': shot.response_revision, 'attempt_revision': shot.attempt_revision}


@never_cache
@require_POST
def fire_shot(request, attempt_id, question_id):
    import uuid
    if not student_required(request):
        return error('UNAUTHENTICATED', 'Vui lòng đăng nhập.', 401)
    try:
        data = json.loads(request.body)
        if not isinstance(data, dict) or type(data.get('expected_revision')) is not int or data['expected_revision'] < 0:
            raise ValueError
        option_id = uuid.UUID(data.get('option_id', ''))
        key = uuid.UUID(request.headers.get('Idempotency-Key', ''))
        shot = fire_practice_shot(attempt_id, question_id, request.user, option_id, data['expected_revision'], key)
    except (ValueError, TypeError, AttributeError, json.JSONDecodeError):
        return error('INVALID_INPUT', 'Dữ liệu không hợp lệ.', 422)
    except (Attempt.DoesNotExist, Response.DoesNotExist):
        return error('NOT_FOUND', 'Không tìm thấy bài.', 404)
    except ConflictError as exc:
        return JsonResponse({'error': {'code': 'CONFLICT', 'message': 'Câu trả lời đã thay đổi hoặc đã bắn.', 'current_revision': exc.args[0]}}, status=409)
    except PermissionDenied:
        return error('NOT_AVAILABLE', 'Câu này không cho biết kết quả ngay.', 403)
    except ValidationError as exc:
        return error('INVALID_INPUT', '; '.join(exc.messages), 422)
    return JsonResponse({'data': shot_receipt(shot)})


@never_cache
@require_http_methods(['PUT'])
def save(request, attempt_id, question_id):
    if not student_required(request):
        return error('UNAUTHENTICATED', 'Vui lòng đăng nhập.', 401)
    try:
        data = json.loads(request.body)
        if not isinstance(data, dict) or type(data.get('expected_revision')) is not int:
            raise ValueError
        response, attempt = save_response(attempt_id, question_id, request.user, data['expected_revision'], data.get('text_answer'), data.get('option_ids'), data.get('ordered_option_ids'), data.get('match_pairs'))
    except (ValueError, TypeError, json.JSONDecodeError):
        return error('INVALID_INPUT', 'Dữ liệu không hợp lệ.', 422)
    except (Attempt.DoesNotExist, Response.DoesNotExist):
        return error('NOT_FOUND', 'Không tìm thấy bài.', 404)
    except ConflictError as exc:
        return JsonResponse({'error': {'code': 'CONFLICT', 'message': 'Câu trả lời đã thay đổi.', 'current_revision': exc.args[0]}}, status=409)
    except PermissionDenied:
        return error('NOT_AVAILABLE', 'Bài này không thể sửa.', 403)
    except ValidationError as exc:
        return error('INVALID_INPUT', '; '.join(exc.messages), 422)
    return JsonResponse({'data': {'response_revision': response.revision, 'attempt_revision': attempt.revision, 'saved_at': response.updated_at.isoformat()}})

@never_cache
@require_POST
def submit(request, attempt_id):
    import uuid
    from .services import submit_attempt
    if not student_required(request):
        return error('UNAUTHENTICATED', 'Vui lòng đăng nhập.', 401)
    try:
        data = json.loads(request.body)
        if not isinstance(data, dict) or type(data.get('expected_attempt_revision')) is not int:
            raise ValueError
        key = uuid.UUID(request.headers.get('Idempotency-Key', ''))
        result = submit_attempt(attempt_id, request.user, data['expected_attempt_revision'], key)
    except (ValueError, TypeError, json.JSONDecodeError):
        return error('INVALID_INPUT', 'Dữ liệu không hợp lệ.', 422)
    except Attempt.DoesNotExist:
        return error('NOT_FOUND', 'Không tìm thấy bài.', 404)
    except ConflictError as exc:
        return JsonResponse({'error': {'code': 'CONFLICT', 'message': 'Bài hoặc yêu cầu nộp đã thay đổi.', 'current_revision': exc.args[0]}}, status=409)
    except PermissionDenied:
        return error('NOT_AVAILABLE', 'Bài này không thể nộp.', 403)
    except ValidationError as exc:
        return error('INVALID_INPUT', '; '.join(exc.messages), 422)
    return JsonResponse({'data': result})


@never_cache
@require_POST
def reset_practice_game(request, attempt_id):
    if not student_required(request):
        return error('UNAUTHENTICATED', 'Vui lòng đăng nhập.', 401)
    return error('NOT_AVAILABLE', 'Muốn làm lại, em hãy nhờ giáo viên.', 410)



@never_cache
@require_POST
def record_visibility(request, attempt_id):
    import uuid
    from django.db import transaction
    from .models import AttemptVisibilityEvent
    if not student_required(request):
        return error('UNAUTHENTICATED', 'Vui lòng đăng nhập.', 401)
    try:
        data = json.loads(request.body)
        event_id = uuid.UUID(data['id'])
        duration = data['duration_ms']
        if type(duration) is not int or not 0 <= duration <= 86400000:
            raise ValueError
    except (KeyError, ValueError, TypeError, AttributeError, json.JSONDecodeError):
        return error('INVALID_INPUT', 'Dữ liệu không hợp lệ.', 422)
    with transaction.atomic():
        attempt = Attempt.objects.select_for_update().filter(pk=attempt_id, recipient__student=request.user).select_related('recipient__assignment').first()
        if not attempt or attempt.status != 'IN_PROGRESS' or attempt.recipient.current_attempt_id != attempt.id:
            return error('NOT_AVAILABLE', 'Bài này không còn nhận thông tin.', 403)
        if attempt.recipient.state != 'ASSIGNED' or attempt.recipient.assignment.status != 'PUBLISHED' or not course_access_allowed(attempt.recipient.assignment_id, request.user):
            return error('NOT_AVAILABLE', 'Bài này không còn khả dụng.', 403)
        event, created = AttemptVisibilityEvent.objects.get_or_create(id=event_id, defaults={'attempt': attempt, 'duration_ms': duration})
        if event.attempt_id != attempt.id or event.duration_ms != duration:
            return error('INVALID_INPUT', 'Mã ghi nhận không hợp lệ.', 409)
        if created and duration > 5000 and attempt.visibility_reviewed_at:
            attempt.visibility_reviewed_at = None
            attempt.save(update_fields=['visibility_reviewed_at'])
    return JsonResponse({'data': {'recorded': True}})
