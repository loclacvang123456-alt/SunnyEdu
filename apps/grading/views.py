import json

from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import F
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.accounts.permissions import is_verified_owner
from apps.assignments.models import Attempt, Response
from apps.content.models import Tag

from .models import ErrorOccurrence
from .services import grade_response, publish_result, teacher_review_error, upsert_teacher_error, void_attempt


def error(code, message, status):
    return JsonResponse({'error': {'code': code, 'message': message}}, status=status)


def authorize(request):
    return is_verified_owner(request.user)


def body(request):
    data = json.loads(request.body)
    if not isinstance(data, dict):
        raise ValueError('Expected object')
    return data


def conflict_or_validation(exc):
    text = '; '.join(exc.messages)
    return error('CONFLICT' if 'revision conflict' in text else 'INVALID_INPUT', text, 409 if 'revision conflict' in text else 422)


@never_cache
@require_GET
def queue(request):
    if not authorize(request):
        return error('FORBIDDEN', 'Cần tài khoản giáo viên đã xác thực hai bước.', 403)
    status_filter = request.GET.get('status', 'SUBMITTED')
    statuses = ['SUBMITTED', 'GRADED'] if status_filter == 'ALL' else [status_filter if status_filter in ('SUBMITTED', 'GRADED') else 'SUBMITTED']
    rows = Attempt.objects.filter(
        status__in=statuses,
        recipient__state='ASSIGNED',
        recipient__current_attempt_id=F('id'),
    ).select_related('recipient__student', 'recipient__assignment').order_by('submitted_at')[:100]
    return JsonResponse({'data': [{
        'attempt_id': str(a.id),
        'status': a.status,
        'status_label': 'Cần chấm' if a.status == 'SUBMITTED' else ('Đã chấm' if a.status == 'GRADED' else a.status),
        'student_name': a.recipient.student.display_name,
        'assignment_title': a.recipient.assignment.title,
        'submitted_at': a.submitted_at.isoformat() if a.submitted_at else None,
        'is_late': a.is_late,
        'published': a.grade_releases.exists(),
    } for a in rows]})


@never_cache
@require_GET
def attempt_detail(request, attempt_id):
    if not authorize(request):
        return error('FORBIDDEN', 'Cần tài khoản giáo viên đã xác thực hai bước.', 403)
    attempt = Attempt.objects.select_related('recipient__student', 'recipient__assignment__version').filter(pk=attempt_id).first()
    if not attempt:
        return error('NOT_FOUND', 'Không tìm thấy bài.', 404)
    if attempt.status not in ('SUBMITTED', 'GRADED', 'VOID'):
        return error('NOT_AVAILABLE', 'Bài chưa thể chấm.', 403)

    # Self-heal missing responses if attempt was created without responses
    if not attempt.responses.exists() and attempt.recipient and attempt.recipient.assignment and attempt.recipient.assignment.version:
        questions = list(attempt.recipient.assignment.version.questions.all())
        if questions:
            Response.objects.bulk_create([Response(attempt=attempt, question=q) for q in questions], ignore_conflicts=True)

    error_tags = [
        {'id': str(t.id), 'skill': t.skill, 'name': t.name}
        for t in Tag.objects.filter(kind=Tag.Kind.ERROR, archived_at__isnull=True).order_by('skill', 'name')
    ]
    latest_release = attempt.grade_releases.order_by('-number').first()
    rows = []
    for response in attempt.responses.select_related('question__passage').prefetch_related('question__options', 'errors__tag').order_by('question__position'):
        q = response.question
        grade = getattr(response, 'grade', None)
        rows.append({
            'response_id': str(response.id),
            'question_id': str(q.id),
            'position': q.position,
            'type': q.type,
            'skill': q.skill,
            'prompt': q.prompt,
            'passage_text': q.passage.text_body if q.passage_id else '',
            'max_points': str(q.max_points),
            'text_answer': response.text_answer,
            'audio_asset_id': str(response.audio_asset_id) if response.audio_asset_id else None,
            'selected_options': [str(i) for i in response.options.values_list('id', flat=True)],
            'ordered_option_ids': response.ordered_option_ids if q.type == 'WORD_ORDER' else [],
            'match_pairs': response.match_pairs if q.type == 'MATCH_IMAGE' else [],
            'match_images': [{'id': str(i.id), 'url': f'/api/v1/owner/image-assets/{i.image_asset_id}/content/', 'correct_word_id': str(i.answer_key.word_id)} for i in q.match_images.select_related('answer_key').all()] if q.type == 'MATCH_IMAGE' else [],
            'match_words': [{'id': str(w.id), 'text': w.text} for w in q.match_words.all()] if q.type == 'MATCH_IMAGE' else [],
            'options': [{'id': str(o.id), 'key': o.key, 'content': o.content} for o in q.options.all()],
            'criteria': [{'id': str(c.id), 'label': c.label, 'level_descriptions': c.level_descriptions} for c in q.criteria.order_by('position')],
            'grade': {
                'revision': grade.revision,
                'source': grade.source,
                'points': str(grade.points),
                'feedback': grade.feedback,
                'criteria': [{'id': str(c.criterion_id), 'level': c.level, 'note': c.note} for c in grade.criterion_scores.all()],
            } if grade else None,
            'errors': [{
                'id': str(e.id),
                'tag_id': str(e.tag_id),
                'tag_name': e.tag.name,
                'source': e.source,
                'confidence': e.confidence,
                'note': e.note,
                'start_char': e.start_char,
                'end_char': e.end_char,
                'start_ms': e.start_ms,
                'end_ms': e.end_ms,
                'withdrawn_at': e.withdrawn_at.isoformat() if e.withdrawn_at else None,
            } for e in response.errors.all()],
        })
    return JsonResponse({'data': {
        'attempt_id': str(attempt.id),
        'revision': attempt.revision,
        'status': attempt.status,
        'student_name': attempt.recipient.student.display_name,
        'assignment_title': attempt.recipient.assignment.title,
        'is_current': attempt.recipient.current_attempt_id == attempt.id,
        'latest_release': {
            'number': latest_release.number,
            'total_points': str(latest_release.total_points),
            'max_points': str(latest_release.max_points),
            'published_at': latest_release.published_at.isoformat(),
        } if latest_release else None,
        'error_tags': error_tags,
        'responses': rows,
    }})


@never_cache
@require_http_methods(['PUT'])
def grade(request, response_id):
    if not authorize(request):
        return error('FORBIDDEN', 'Cần tài khoản giáo viên đã xác thực hai bước.', 403)
    try:
        data = body(request)
        if (type(data.get('expected_revision')) is not int or type(data.get('grade_revision')) is not int
                or not isinstance(data.get('criterion_levels'), dict) or not isinstance(data.get('criterion_notes', {}), dict)
                or not isinstance(data.get('feedback', ''), str) or not isinstance(data.get('reason', ''), str)
                or any(not isinstance(k, str) or type(v) is not int for k, v in data['criterion_levels'].items())
                or any(not isinstance(k, str) or not isinstance(v, str) for k, v in data.get('criterion_notes', {}).items())):
            raise ValueError('Invalid fields')
        item = grade_response(response_id, request.user, data['expected_revision'], data['grade_revision'], data['criterion_levels'], data.get('feedback', ''), data.get('criterion_notes', {}), data.get('reason', ''))
    except (ValueError, TypeError, json.JSONDecodeError):
        return error('INVALID_INPUT', 'Dữ liệu không hợp lệ.', 422)
    except Response.DoesNotExist:
        return error('NOT_FOUND', 'Không tìm thấy câu trả lời.', 404)
    except PermissionDenied:
        return error('FORBIDDEN', 'Không có quyền.', 403)
    except ValidationError as exc:
        return conflict_or_validation(exc)
    return JsonResponse({'data': {'grade_id': str(item.id), 'grade_revision': item.revision, 'points': str(item.points), 'attempt_revision': item.response.attempt.revision, 'attempt_status': item.response.attempt.status}})


@never_cache
@require_POST
def publish(request, attempt_id):
    if not authorize(request):
        return error('FORBIDDEN', 'Cần tài khoản giáo viên đã xác thực hai bước.', 403)
    try:
        data = body(request)
        if type(data.get('expected_revision')) is not int or not isinstance(data.get('reason', ''), str):
            raise ValueError('Invalid fields')
        release = publish_result(attempt_id, request.user, data['expected_revision'], data.get('reason', ''))
    except (ValueError, TypeError, json.JSONDecodeError):
        return error('INVALID_INPUT', 'Dữ liệu không hợp lệ.', 422)
    except Attempt.DoesNotExist:
        return error('NOT_FOUND', 'Không tìm thấy bài.', 404)
    except PermissionDenied:
        return error('FORBIDDEN', 'Không có quyền.', 403)
    except ValidationError as exc:
        return conflict_or_validation(exc)
    return JsonResponse({'data': {'release_id': str(release.id), 'number': release.number, 'published_at': release.published_at.isoformat(), 'total_points': str(release.total_points), 'max_points': str(release.max_points)}})


@never_cache
@require_http_methods(['POST', 'PATCH'])
def errors(request, response_id):
    if not authorize(request):
        return error('FORBIDDEN', 'Cần tài khoản giáo viên đã xác thực hai bước.', 403)
    try:
        data = body(request)
        if type(data.get('expected_revision')) is not int or not data.get('tag_id'):
            raise ValueError('Invalid fields')
        anchor = data.get('anchor') or {}
        occ, attempt = upsert_teacher_error(
            response_id,
            request.user,
            data['expected_revision'],
            data['tag_id'],
            note=data.get('note', ''),
            start_char=anchor.get('start_char'),
            end_char=anchor.get('end_char'),
            start_ms=anchor.get('start_ms'),
            end_ms=anchor.get('end_ms'),
            withdraw=bool(data.get('withdraw', False)),
        )
    except (ValueError, TypeError, json.JSONDecodeError):
        return error('INVALID_INPUT', 'Dữ liệu không hợp lệ.', 422)
    except (Response.DoesNotExist, Tag.DoesNotExist):
        return error('NOT_FOUND', 'Không tìm thấy câu trả lời hoặc tag lỗi.', 404)
    except PermissionDenied:
        return error('FORBIDDEN', 'Không có quyền.', 403)
    except ValidationError as exc:
        return conflict_or_validation(exc)
    return JsonResponse({'data': {'id': str(occ.id), 'attempt_revision': attempt.revision, 'withdrawn_at': occ.withdrawn_at.isoformat() if occ.withdrawn_at else None}})


@never_cache
@require_POST
def teacher_review(request, occurrence_id):
    if not authorize(request):
        return error('FORBIDDEN', 'Cần tài khoản giáo viên đã xác thực hai bước.', 403)
    try:
        data = body(request)
        review = teacher_review_error(occurrence_id, request.user, bool(data.get('reviewed', True)), data.get('teacher_note', ''))
    except (ValueError, TypeError, json.JSONDecodeError):
        return error('INVALID_INPUT', 'Dữ liệu không hợp lệ.', 422)
    except ErrorOccurrence.DoesNotExist:
        return error('NOT_FOUND', 'Không tìm thấy lỗi.', 404)
    except PermissionDenied:
        return error('FORBIDDEN', 'Không có quyền.', 403)
    return JsonResponse({'data': {'occurrence_id': str(review.occurrence_id), 'teacher_reviewed_at': review.teacher_reviewed_at.isoformat() if review.teacher_reviewed_at else None}})


@never_cache
@require_POST
def void(request, attempt_id):
    if not authorize(request):
        return error('FORBIDDEN', 'Cần tài khoản giáo viên đã xác thực hai bước.', 403)
    try:
        data = body(request)
        if type(data.get('expected_revision')) is not int:
            raise ValueError('Invalid fields')
        attempt = void_attempt(attempt_id, request.user, data['expected_revision'], data.get('reason', ''))
    except (ValueError, TypeError, json.JSONDecodeError):
        return error('INVALID_INPUT', 'Dữ liệu không hợp lệ.', 422)
    except Attempt.DoesNotExist:
        return error('NOT_FOUND', 'Không tìm thấy bài.', 404)
    except PermissionDenied:
        return error('FORBIDDEN', 'Không có quyền.', 403)
    except ValidationError as exc:
        return conflict_or_validation(exc)
    return JsonResponse({'data': {'id': str(attempt.id), 'status': attempt.status, 'revision': attempt.revision}})
