from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from .models import Assignment, AssignmentRecipient, Attempt, PracticeShot, Response, ResponseOption
from apps.content.models import QuestionOption


class ConflictError(Exception):
    pass


def course_access_allowed(assignment_id, student):
    """Keep old assignments accessible; course assignments need an active class opening."""
    from apps.content.models import CourseExercise
    exercises = CourseExercise.objects.filter(assignment_id=assignment_id)
    if not exercises.exists():
        return True
    return exercises.filter(
        course__is_published=True,
        course__english_classes__archived_at__isnull=True,
        course__english_classes__memberships__student=student,
        course__english_classes__memberships__start_at__lte=timezone.now(),
        course__english_classes__memberships__end_at__isnull=True,
    ).exists()


def check_window(recipient):
    a = recipient.assignment
    now = timezone.now()
    eff_due = recipient.due_at_override or a.due_at
    eff_late = max(a.late_until, eff_due)
    if (recipient.state != 'ASSIGNED' or a.status != 'PUBLISHED' or not a.opens_at <= now < eff_late
            or not course_access_allowed(a.id, recipient.student)):
        raise PermissionDenied('Bài này hiện không nhận câu trả lời.')


@transaction.atomic
def start_attempt(recipient_id, student):
    recipient = AssignmentRecipient.objects.select_for_update().select_related('assignment__version').get(pk=recipient_id, student=student)
    check_window(recipient)
    if recipient.current_attempt_id:
        current = recipient.current_attempt
        allowed_tries = min(recipient.max_attempts or 1, 5)
        if current.status in ('SUBMITTED', 'GRADED') and current.attempt_no < allowed_tries:
            attempt = Attempt.objects.create(recipient=recipient, attempt_no=current.attempt_no + 1)
            Response.objects.bulk_create([Response(attempt=attempt, question=q) for q in recipient.assignment.version.questions.all()])
            recipient.current_attempt = attempt
            recipient.save(update_fields=['current_attempt'])
            return attempt, True
        return current, False
    attempt = Attempt.objects.create(recipient=recipient, attempt_no=1)
    Response.objects.bulk_create([Response(attempt=attempt, question=q) for q in recipient.assignment.version.questions.all()])
    recipient.current_attempt = attempt
    recipient.save(update_fields=['current_attempt'])
    return attempt, True


@transaction.atomic
def save_response(attempt_id, question_id, student, expected_revision, text_answer=None, option_ids=None, ordered_option_ids=None, match_pairs=None):
    attempt = Attempt.objects.select_for_update().select_related('recipient__assignment').get(pk=attempt_id, recipient__student=student)
    recipient = attempt.recipient
    check_window(recipient)
    if attempt.status != 'IN_PROGRESS' or recipient.current_attempt_id != attempt.id:
        raise PermissionDenied('Bài này không thể sửa.')
    response = Response.objects.select_for_update().select_related('question').get(attempt=attempt, question_id=question_id)
    if PracticeShot.objects.filter(response=response).exists():
        raise ConflictError('SHOT_LOCKED')
    if response.revision != expected_revision:
        raise ConflictError(response.revision)
    question = response.question
    if question.type in ('SINGLE_CHOICE', 'MULTIPLE_CHOICE', 'STRESS_CHOICE'):
        if not isinstance(option_ids, list) or len(set(option_ids)) != len(option_ids):
            raise ValidationError('Lựa chọn không hợp lệ.')
        if question.type in ('SINGLE_CHOICE', 'STRESS_CHOICE') and len(option_ids) > 1:
            raise ValidationError('Chỉ chọn một đáp án.')
        options = list(QuestionOption.objects.filter(question=question, pk__in=option_ids))
        if len(options) != len(option_ids):
            raise ValidationError('Lựa chọn không thuộc câu hỏi.')
        ResponseOption.objects.filter(response=response).delete()
        ResponseOption.objects.bulk_create([ResponseOption(response=response, option=o) for o in options])
    elif question.type == 'MATCH_IMAGE':
        import uuid
        if not isinstance(match_pairs, list) or len(match_pairs) > 6:
            raise ValidationError('Danh sách nối tranh không hợp lệ.')
        normalized = []
        try:
            for pair in match_pairs:
                if not isinstance(pair, dict) or set(pair) != {'image_id', 'word_id'}:
                    raise ValueError
                normalized.append({'image_id': str(uuid.UUID(pair['image_id'])), 'word_id': str(uuid.UUID(pair['word_id']))})
        except (ValueError, TypeError, AttributeError, KeyError) as exc:
            raise ValidationError('Mã tranh hoặc từ không hợp lệ.') from exc
        image_ids = [pair['image_id'] for pair in normalized]
        word_ids = [pair['word_id'] for pair in normalized]
        if len(set(image_ids)) != len(image_ids) or len(set(word_ids)) != len(word_ids):
            raise ValidationError('Mỗi tranh và từ chỉ được nối một lần.')
        if not set(image_ids) <= {str(image.id) for image in question.match_images.all()} or not set(word_ids) <= {str(word.id) for word in question.match_words.all()}:
            raise ValidationError('Tranh hoặc từ không thuộc câu hỏi.')
        response.match_pairs = normalized
    elif question.type == 'WORD_ORDER':
        if not isinstance(ordered_option_ids, list) or len(ordered_option_ids) > 20 or any(not isinstance(item, str) for item in ordered_option_ids):
            raise ValidationError('Thứ tự các ô từ không hợp lệ.')
        try:
            import uuid
            normalized = [str(uuid.UUID(item)) for item in ordered_option_ids]
        except ValueError as exc:
            raise ValidationError('Ô từ không hợp lệ.') from exc
        if len(set(normalized)) != len(normalized):
            raise ValidationError('Không được dùng một ô từ hai lần.')
        allowed = {str(option.pk) for option in question.options.all()}
        if not set(normalized) <= allowed:
            raise ValidationError('Ô từ không thuộc câu hỏi.')
        response.ordered_option_ids = normalized
    elif question.type in ('TEXT', 'SENTENCE_TRANSFORM'):
        if not isinstance(text_answer, str) or len(text_answer) > 10000:
            raise ValidationError('Câu trả lời không hợp lệ.')
        response.text_answer = text_answer
    else:
        raise ValidationError('Ghi âm chưa được hỗ trợ trong phần này.')
    response.revision += 1
    response.save()
    attempt.revision += 1
    attempt.save(update_fields=['revision'])
    return response, attempt


@transaction.atomic
def fire_practice_shot(attempt_id, question_id, student, option_id, expected_revision, key):
    """Save one irrevocable choice before returning its result to the student."""
    from apps.reporting.models import RankingAssignment

    if student.role != 'STUDENT' or student.status != 'ACTIVE':
        raise PermissionDenied
    target = Attempt.objects.filter(pk=attempt_id, recipient__student=student).values('recipient_id', 'recipient__assignment_id').first()
    if target is None:
        raise Attempt.DoesNotExist
    assignment = Assignment.objects.select_for_update().get(pk=target['recipient__assignment_id'])
    recipient = AssignmentRecipient.objects.select_for_update().get(pk=target['recipient_id'], student=student)
    attempt = Attempt.objects.select_for_update().get(pk=attempt_id, recipient=recipient)
    response = Response.objects.select_for_update().select_related('question').get(attempt=attempt, question_id=question_id)
    if (assignment.status != 'PUBLISHED' or assignment.mode != 'PRACTICE' or not assignment.game_feedback_enabled
            or recipient.state != 'ASSIGNED' or recipient.current_attempt_id != attempt.id
            or response.question.version_id != assignment.version_id or response.question.type != 'SINGLE_CHOICE' or response.question.pirate_game is False
              or attempt.status not in ('IN_PROGRESS', 'SUBMITTED', 'GRADED')
              or not course_access_allowed(assignment.id, student)):
        raise PermissionDenied
    # A shared ranked assignment must never reveal per-answer results early.
    if RankingAssignment.objects.filter(assignment=assignment).exists():
        raise PermissionDenied
    previous = PracticeShot.objects.filter(response=response).first()
    if previous:
        if previous.idempotency_key != key or str(previous.option_id) != str(option_id) or previous.expected_revision != expected_revision:
            raise ConflictError('SHOT_LOCKED')
        return previous
    if attempt.status != 'IN_PROGRESS':
        raise PermissionDenied
    check_window(recipient)
    if response.revision != expected_revision:
        raise ConflictError(response.revision)
    option = QuestionOption.objects.filter(pk=option_id, question=response.question).first()
    if option is None:
        raise ValidationError('Đáp án không thuộc câu hỏi này.')
    answer_ids = list(response.question.answer_keys.values_list('option_id', flat=True))
    if len(answer_ids) != 1 or not response.question.options.filter(pk=answer_ids[0]).exists() or not 2 <= response.question.options.count() <= 6:
        raise ValidationError('Câu hỏi chưa có đáp án hợp lệ.')
    # A globally reused key must fail cleanly rather than leak another receipt.
    if PracticeShot.objects.filter(idempotency_key=key).exists():
        raise ConflictError('IDEMPOTENCY_CONFLICT')
    correct = answer_ids[0] == option.id
    ResponseOption.objects.filter(response=response).delete()
    ResponseOption.objects.create(response=response, option=option)
    response.revision += 1
    response.save(update_fields=['revision', 'updated_at'])
    attempt.revision += 1
    attempt.save(update_fields=['revision'])
    try:
        with transaction.atomic():
            return PracticeShot.objects.create(response=response, option=option, idempotency_key=key,
                                               expected_revision=expected_revision, response_revision=response.revision,
                                               attempt_revision=attempt.revision, correct=correct)
    except IntegrityError as exc:
        raise ConflictError('IDEMPOTENCY_CONFLICT') from exc

@transaction.atomic
def submit_attempt(attempt_id, student, expected_revision, key):
    import hashlib
    from decimal import Decimal
    from .models import SubmissionRequest
    from apps.grading.models import Grade, CriterionScore, ErrorOccurrence
    digest = hashlib.sha256(str(expected_revision).encode()).hexdigest()
    attempt = Attempt.objects.select_for_update().select_related('recipient__assignment').get(pk=attempt_id, recipient__student=student)
    if not course_access_allowed(attempt.recipient.assignment_id, student):
        raise PermissionDenied('Khóa học chưa mở.')
    previous = SubmissionRequest.objects.filter(attempt=attempt, idempotency_key=key).first()
    if previous:
        if previous.payload_digest != digest:
            raise ConflictError('IDEMPOTENCY_CONFLICT')
        return previous.result
    if attempt.status in ('SUBMITTED', 'GRADED'):
        return {'attempt_id': str(attempt.id), 'status': attempt.status, 'submitted_at': attempt.submitted_at.isoformat()}
    check_window(attempt.recipient)
    if attempt.recipient.current_attempt_id != attempt.id or attempt.status != 'IN_PROGRESS':
        raise PermissionDenied
    if attempt.revision != expected_revision:
        raise ConflictError(attempt.revision)
    responses = list(attempt.responses.select_related('question', 'audio_asset').prefetch_related('options', 'question__answer_keys', 'question__criteria', 'question__question_tags__tag'))
    if not responses:
        raise ValidationError('Bài không có câu hỏi.')
    if any(r.audio_asset_id and r.audio_asset.status != 'READY' for r in responses):
        raise ValidationError('Bản ghi âm chưa sẵn sàng.')
    now = timezone.now()
    pending = False
    for response in responses:
        q = response.question
        if q.type in ('SINGLE_CHOICE', 'MULTIPLE_CHOICE', 'STRESS_CHOICE'):
            selected = {o.id for o in response.options.all()}
            correct = {x.option_id for x in q.answer_keys.all()}
            points = q.max_points if selected == correct and bool(correct) else Decimal('0')
            Grade.objects.create(response=response, source='AUTO', points=points, graded_at=now)
            if points == 0 and selected:
                for item in q.question_tags.all():
                    if item.tag.kind == 'ERROR':
                        ErrorOccurrence.objects.create(response=response, tag=item.tag, source='RULE', confidence='SIGNAL')
        elif q.type == 'MATCH_IMAGE':
            images = list(q.match_images.select_related('answer_key', 'image_asset'))
            if any(image.image_asset.status != 'READY' for image in images):
                raise ValidationError('Ảnh trong câu nối chưa sẵn sàng.')
            correct = {str(image.id): str(image.answer_key.word_id) for image in images}
            selected = {pair['image_id']: pair['word_id'] for pair in response.match_pairs}
            points = q.max_points if selected == correct and len(correct) >= 2 else Decimal('0')
            Grade.objects.create(response=response, source='AUTO', points=points, graded_at=now)
            if points == 0 and selected:
                for item in q.question_tags.all():
                    if item.tag.kind == 'ERROR':
                        ErrorOccurrence.objects.create(response=response, tag=item.tag, source='RULE', confidence='SIGNAL')
        elif q.type == 'WORD_ORDER':
            options = list(q.options.all())
            selected = response.ordered_option_ids
            by_id = {str(option.pk): option.content for option in options}
            correct = [option.content for option in options]
            selected_words = [by_id.get(option_id) for option_id in selected]
            points = q.max_points if len(selected_words) == len(correct) and selected_words == correct else Decimal('0')
            Grade.objects.create(response=response, source='AUTO', points=points, graded_at=now)
            if points == 0 and selected:
                for item in q.question_tags.all():
                    if item.tag.kind == 'ERROR':
                        ErrorOccurrence.objects.create(response=response, tag=item.tag, source='RULE', confidence='SIGNAL')
        elif q.type == 'SENTENCE_TRANSFORM':
            import json
            from .sentence_transform_service import grade_sentence_transform
            options = list(q.options.all())
            standard_answer = options[0].content if options else (q.explanation or '')
            student_answer = response.text_answer or ''
            res = grade_sentence_transform(student_answer, standard_answer, q.max_points)
            Grade.objects.create(
                response=response,
                source='AUTO',
                points=res['points'],
                feedback=json.dumps(res, default=str),
                graded_at=now,
            )
            if res['points'] == 0 and student_answer:
                for item in q.question_tags.all():
                    if item.tag.kind == 'ERROR':
                        ErrorOccurrence.objects.create(response=response, tag=item.tag, source='RULE', confidence='SIGNAL')
        elif (q.type == 'TEXT' and not response.text_answer.strip()) or (q.type == 'AUDIO' and not response.audio_asset_id):
            grade = Grade.objects.create(response=response, source='AUTO', points=Decimal('0'), feedback='Không có câu trả lời', graded_at=now)
            criteria = list(q.criteria.all())
            if len(criteria) != 4:
                raise ValidationError('Thiếu tiêu chí chấm.')
            CriterionScore.objects.bulk_create([CriterionScore(grade=grade, criterion=c, level=0) for c in criteria])
        else:
            pending = True
    attempt.submitted_at = now
    attempt.due_at_at_submit = attempt.recipient.due_at_override or attempt.recipient.assignment.due_at
    attempt.is_late = now > attempt.due_at_at_submit
    attempt.status = 'SUBMITTED' if pending else 'GRADED'
    attempt.graded_at = None if pending else now
    attempt.save(update_fields=['submitted_at', 'due_at_at_submit', 'is_late', 'status', 'graded_at'])
    result = {'attempt_id': str(attempt.id), 'status': attempt.status, 'submitted_at': now.isoformat()}
    SubmissionRequest.objects.create(attempt=attempt, idempotency_key=key, payload_digest=digest, result=result)
    return result
