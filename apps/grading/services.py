from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from apps.accounts.models import AuditEvent
from apps.assignments.models import Assignment, Attempt, AssignmentRecipient, Response
from apps.content.models import Tag
from apps.reporting.models import RankingPeriod, RankingAssignment, RankingMember
from .models import CriterionScore, ErrorOccurrence, ErrorReview, Grade, GradeHistory, GradeRelease


def visibility_deduction(attempt):
    event = AuditEvent.objects.filter(action='attempt.visibility_deduction', target_type='attempt', target_id=attempt.id).order_by('-created_at', '-id').first()
    return Decimal(event.metadata['points']) if event else Decimal('0')


@transaction.atomic
def set_visibility_deduction(attempt_id, actor, value):
    owner_required(actor)
    try:
        points = Decimal(value)
        if not points.is_finite() or points < 0 or points != points.quantize(Decimal('0.01')):
            raise ValueError
    except (InvalidOperation, ValueError, TypeError):
        raise ValidationError('Điểm trừ phải là số không âm, tối đa 2 chữ số thập phân.')
    target = Attempt.objects.select_related('recipient__assignment__version__exam').get(pk=attempt_id)
    if target.recipient.assignment.version.exam.created_by_id != actor.id:
        raise ValidationError('Không có quyền điều chỉnh bài này.')
    period_ids = RankingAssignment.objects.filter(assignment_id=target.recipient.assignment_id).values('period_id')
    member_period_ids = RankingMember.objects.filter(student_id=target.recipient.student_id).values('period_id')
    list(RankingPeriod.objects.select_for_update().filter(pk__in=period_ids).filter(pk__in=member_period_ids).order_by('pk'))
    Assignment.objects.select_for_update().get(pk=target.recipient.assignment_id)
    AssignmentRecipient.objects.select_for_update().get(pk=target.recipient_id)
    attempt = Attempt.objects.select_for_update().select_related('recipient__assignment__version__exam').get(pk=attempt_id)
    if (attempt.recipient.assignment.version.exam.created_by_id != actor.id or attempt.recipient.current_attempt_id != attempt.id
            or attempt.recipient.state != 'ASSIGNED' or attempt.status != 'GRADED'):
        raise ValidationError('Chỉ có thể trừ điểm bài hiện tại đã chấm xong.')
    if not attempt.visibility_events.filter(duration_ms__gt=5000).exists():
        raise ValidationError('Bài không có lần rời trang trên 5 giây.')
    total = Grade.objects.filter(response__attempt=attempt).aggregate(total=Sum('points'))['total'] or Decimal('0')
    if points > total:
        raise ValidationError('Điểm trừ không được lớn hơn tổng điểm học sinh đạt được.')
    previous = visibility_deduction(attempt)
    if points != previous:
        AuditEvent.objects.create(actor=actor, action='attempt.visibility_deduction', target_type='attempt', target_id=attempt.id, reason='Điều chỉnh điểm sau khi xem thời gian rời trang', metadata={'points': str(points), 'previous': str(previous)})
        attempt.revision += 1
        attempt.save(update_fields=['revision'])
        if attempt.grade_releases.exists():
            publish_result(attempt.id, actor, attempt.revision, reason='Điều chỉnh điểm trừ sau khi xem thời gian rời trang')
    attempt.visibility_reviewed_at = timezone.now()
    attempt.save(update_fields=['visibility_reviewed_at'])
    return attempt


def rubric_points(max_points, levels):
    if len(levels) != 4 or any(type(level) is not int or not 0 <= level <= 4 for level in levels):
        raise ValidationError('Four rubric levels between 0 and 4 are required.')
    return (max_points * Decimal(sum(levels)) / Decimal(16)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)


def owner_required(actor):
    if actor.role != 'OWNER' or actor.status != 'ACTIVE':
        raise PermissionDenied


def ensure_suggested_error(response, points):
    """Record an unconfirmed suggestion for an answered, less-than-full-score response."""
    question = response.question
    if points >= question.max_points or response.errors.exists():
        return
    if question.type in ('SINGLE_CHOICE', 'MULTIPLE_CHOICE', 'STRESS_CHOICE'):
        answered = response.options.exists()
    elif question.type == 'WORD_ORDER':
        answered = bool(response.ordered_option_ids)
    elif question.type == 'MATCH_IMAGE':
        answered = bool(response.match_pairs)
    elif question.type == 'AUDIO':
        answered = bool(response.audio_asset_id)
    else:
        answered = bool((response.text_answer or '').strip())
    if not answered:
        return
    link = question.question_tags.filter(tag__kind=Tag.Kind.ERROR, tag__skill=question.skill, tag__archived_at__isnull=True).order_by('created_at', 'id').first()
    if link:
        ErrorOccurrence.objects.get_or_create(response=response, tag_id=link.tag_id, defaults={'source': 'RULE', 'confidence': 'SIGNAL'})


@transaction.atomic
def grade_response(response_id, actor, expected_revision, grade_revision, criterion_levels, feedback='', criterion_notes=None, reason=''):
    owner_required(actor)
    response = Response.objects.select_related('attempt__recipient', 'question').get(pk=response_id)
    recipient = AssignmentRecipient.objects.select_for_update().get(pk=response.attempt.recipient_id)
    attempt = Attempt.objects.select_for_update().get(pk=response.attempt_id)
    response = Response.objects.select_for_update().select_related('question').get(pk=response_id)
    if recipient.current_attempt_id != attempt.id or recipient.state != 'ASSIGNED' or attempt.status not in ('SUBMITTED', 'GRADED'):
        raise ValidationError('Attempt is not eligible for grading.')
    if attempt.revision != expected_revision:
        raise ValidationError('Attempt revision conflict.')
    if response.question.type not in ('TEXT', 'AUDIO'):
        raise ValidationError('Only manual questions can be graded.')
    criteria = list(response.question.criteria.order_by('position'))
    if len(criteria) != 4 or set(criterion_levels) != {str(c.id) for c in criteria}:
        raise ValidationError('Four matching criteria are required.')
    levels = [criterion_levels[str(c.id)] for c in criteria]
    points = rubric_points(response.question.max_points, levels)
    grade = Grade.objects.select_for_update().filter(response=response).first()
    if (grade.revision if grade else 0) != grade_revision:
        raise ValidationError('Grade revision conflict.')
    if grade and not reason.strip():
        raise ValidationError('Reason is required when changing a grade.')
    previous = {'points': str(grade.points), 'feedback': grade.feedback, 'criterion_levels': {str(item.criterion_id): item.level for item in grade.criterion_scores.all()}, 'criterion_notes': {str(item.criterion_id): item.note for item in grade.criterion_scores.all()}} if grade else {}
    if grade is None:
        grade = Grade(response=response, revision=1)
    else:
        grade.revision += 1
    other_total = Grade.objects.filter(response__attempt=attempt).exclude(response=response).aggregate(total=Sum('points'))['total'] or Decimal('0')
    if points + other_total < visibility_deduction(attempt):
        raise ValidationError('Tổng điểm sau khi chấm không được thấp hơn điểm trừ đã lưu.')
    grade.source, grade.points, grade.feedback, grade.graded_by, grade.graded_at = 'TEACHER', points, feedback, actor, timezone.now()
    grade.save()
    ensure_suggested_error(response, points)
    criterion_notes = criterion_notes or {}
    for criterion, level in zip(criteria, levels):
        CriterionScore.objects.update_or_create(grade=grade, criterion=criterion, defaults={'level': level, 'note': criterion_notes.get(str(criterion.id), '')})
    GradeHistory.objects.create(grade=grade, revision=grade.revision, previous=previous, next={'points': str(points), 'feedback': feedback, 'criterion_levels': criterion_levels}, actor=actor, reason=reason)
    attempt.revision += 1
    if not attempt.responses.filter(grade__isnull=True).exists():
        attempt.status, attempt.graded_at = 'GRADED', timezone.now()
    attempt.save(update_fields=['revision', 'status', 'graded_at'])
    return grade


@transaction.atomic
def publish_result(attempt_id, actor, expected_revision, reason=''):
    owner_required(actor)
    attempt = Attempt.objects.select_related('recipient').get(pk=attempt_id)
    period_ids = RankingAssignment.objects.filter(assignment_id=attempt.recipient.assignment_id).values('period_id')
    member_period_ids = RankingMember.objects.filter(student_id=attempt.recipient.student_id).values('period_id')
    periods = list(RankingPeriod.objects.select_for_update().filter(pk__in=period_ids).filter(pk__in=member_period_ids).order_by('pk'))
    Assignment.objects.select_for_update().get(pk=attempt.recipient.assignment_id)
    recipient = AssignmentRecipient.objects.select_for_update().get(pk=attempt.recipient_id)
    attempt = Attempt.objects.select_for_update().get(pk=attempt_id)
    if recipient.current_attempt_id != attempt.id or recipient.state != 'ASSIGNED' or attempt.status != 'GRADED':
        raise ValidationError('Attempt is not eligible for publication.')
    if attempt.revision != expected_revision:
        raise ValidationError('Attempt revision conflict.')
    old = attempt.grade_releases.order_by('-number').first()
    if old and not reason.strip():
        raise ValidationError('Reason is required for republication.')
    rows, total, maximum = [], Decimal('0'), Decimal('0')
    for response in attempt.responses.select_related('question', 'grade').order_by('question__position'):
        try:
            grade = response.grade
        except Grade.DoesNotExist:
            raise ValidationError('Every response must be graded.')
        q = response.question
        if grade.points > q.max_points:
            raise ValidationError('Grade exceeds question maximum.')
        ensure_suggested_error(response, grade.points)
        criteria = [{'id': str(s.criterion_id), 'label': s.criterion.label, 'level': s.level, 'note': s.note, 'level_descriptions': s.criterion.level_descriptions} for s in grade.criterion_scores.select_related('criterion').order_by('criterion__position')]
        if q.type in ('TEXT', 'AUDIO') and len(criteria) != 4:
            raise ValidationError('Manual response needs four rubric levels.')
        topics = [{'id': str(t.tag_id), 'name': t.tag.name} for t in q.question_tags.select_related('tag').filter(tag__kind='TOPIC')]
        errors = [{'id': str(e.id), 'tag_id': str(e.tag_id), 'tag_name': e.tag.name, 'source': e.source, 'confidence': e.confidence, 'note': e.note, 'start_char': e.start_char, 'end_char': e.end_char, 'start_ms': e.start_ms, 'end_ms': e.end_ms} for e in response.errors.select_related('tag').filter(withdrawn_at__isnull=True)]
        rows.append({'response_id': str(response.id), 'question_id': str(q.id), 'points': str(grade.points), 'max_points': str(q.max_points), 'skill': q.skill, 'difficulty': q.difficulty, 'topics': topics, 'criteria': criteria, 'feedback': grade.feedback, 'errors': errors})
        total += grade.points
        maximum += q.max_points
    if not rows:
        raise ValidationError('Attempt has no responses.')
    deduction = visibility_deduction(attempt)
    if deduction > total:
        raise ValidationError('Điểm trừ vượt quá tổng điểm bài làm.')
    release = GradeRelease.objects.create(attempt=attempt, number=(old.number + 1 if old else 1), published_by=actor, total_points=total - deduction, max_points=maximum, snapshot={'schema_version': 1, 'responses': rows, 'reason': reason, 'visibility_deduction': str(deduction)})
    attempt.revision += 1
    attempt.save(update_fields=['revision'])
    for period in periods:
        if period.status == 'FINAL':
            period.status = 'STALE'
            period.revision += 1
            period.save(update_fields=['status', 'revision'])
    return release


@transaction.atomic
def upsert_teacher_error(response_id, actor, expected_revision, tag_id, note='', start_char=None, end_char=None, start_ms=None, end_ms=None, withdraw=False):
    """Create, update, or withdraw a TEACHER-confirmed ErrorOccurrence with text/audio anchors."""
    owner_required(actor)
    target = Response.objects.select_related('attempt__recipient', 'question').get(pk=response_id)
    recipient = AssignmentRecipient.objects.select_for_update().get(pk=target.attempt.recipient_id)
    attempt = Attempt.objects.select_for_update().get(pk=target.attempt_id)
    response = Response.objects.select_for_update().select_related('question').get(pk=response_id)
    if recipient.current_attempt_id != attempt.id or attempt.status not in ('SUBMITTED', 'GRADED'):
        raise ValidationError('Attempt is not eligible for error tagging.')
    if attempt.revision != expected_revision:
        raise ValidationError('Attempt revision conflict.')
    tag = Tag.objects.get(pk=tag_id, kind=Tag.Kind.ERROR, skill=response.question.skill)
    if tag.archived_at and not withdraw:
        raise ValidationError('Tag lỗi đã lưu trữ.')

    if (start_char is not None or end_char is not None) and (start_ms is not None or end_ms is not None):
        raise ValidationError('Không ghi đồng thời khoảng ký tự và khoảng giây.')
    if start_char is not None or end_char is not None:
        if start_char is None or end_char is None or not (0 <= start_char < end_char <= len(response.text_answer)):
            raise ValidationError('Khoảng ký tự lỗi không hợp lệ.')
    if start_ms is not None or end_ms is not None:
        if start_ms is None or end_ms is None or not (0 <= start_ms < end_ms):
            raise ValidationError('Khoảng mili-giây lỗi không hợp lệ.')

    occ = ErrorOccurrence.objects.select_for_update().filter(response=response, tag=tag).first()
    now = timezone.now()
    if withdraw:
        if not occ:
            raise ValidationError('Không tìm thấy lỗi để rút lại.')
        occ.withdrawn_at = now
        occ.save(update_fields=['withdrawn_at'])
    elif occ:
        occ.source, occ.confidence, occ.note = 'TEACHER', 'CONFIRMED', (note or '').strip()
        occ.start_char, occ.end_char, occ.start_ms, occ.end_ms = start_char, end_char, start_ms, end_ms
        occ.withdrawn_at = None
        occ.save()
    else:
        occ = ErrorOccurrence.objects.create(
            response=response,
            tag=tag,
            source='TEACHER',
            confidence='CONFIRMED',
            note=(note or '').strip(),
            start_char=start_char,
            end_char=end_char,
            start_ms=start_ms,
            end_ms=end_ms,
        )
    attempt.revision += 1
    attempt.save(update_fields=['revision'])
    return occ, attempt


@transaction.atomic
def set_single_error(response_id, actor, expected_revision, tag_id):
    owner_required(actor)
    target = Response.objects.select_related('attempt__recipient__assignment__version__exam').get(pk=response_id, attempt__recipient__assignment__version__exam__created_by=actor)
    recipient = AssignmentRecipient.objects.select_for_update().get(pk=target.attempt.recipient_id)
    attempt = Attempt.objects.select_for_update().get(pk=target.attempt_id)
    if recipient.current_attempt_id != attempt.id or recipient.state != 'ASSIGNED' or attempt.status not in ('SUBMITTED', 'GRADED'):
        raise ValidationError('Không thể sửa nhãn lỗi của bài làm này.')
    if attempt.revision != expected_revision:
        raise ValidationError('Attempt revision conflict.')
    if tag_id:
        tag = Tag.objects.get(pk=tag_id, kind=Tag.Kind.ERROR, skill=target.question.skill, archived_at__isnull=True)
        existing = ErrorOccurrence.objects.filter(response=target, tag=tag).first()
        _, attempt = upsert_teacher_error(
            response_id, actor, expected_revision, tag.id, note=existing.note if existing else '',
            start_char=existing.start_char if existing else None, end_char=existing.end_char if existing else None,
            start_ms=existing.start_ms if existing else None, end_ms=existing.end_ms if existing else None,
        )
        other_errors = ErrorOccurrence.objects.filter(response=target, withdrawn_at__isnull=True).exclude(tag=tag)
    else:
        other_errors = ErrorOccurrence.objects.filter(response=target, withdrawn_at__isnull=True)
        if not target.errors.exists():
            suggested = target.question.question_tags.filter(tag__kind=Tag.Kind.ERROR, tag__skill=target.question.skill, tag__archived_at__isnull=True).order_by('created_at', 'id').first()
            if suggested:
                ErrorOccurrence.objects.create(response=target, tag_id=suggested.tag_id, source='TEACHER', confidence='CONFIRMED', withdrawn_at=timezone.now())
        attempt.revision += 1
        attempt.save(update_fields=['revision'])
    other_errors.update(withdrawn_at=timezone.now())
    return attempt


@transaction.atomic
def teacher_review_error(occurrence_id, actor, reviewed, teacher_note=''):
    """Record or clear teacher verification on a student's reviewed error occurrence."""
    owner_required(actor)
    occ = ErrorOccurrence.objects.select_for_update().get(pk=occurrence_id)
    review, _ = ErrorReview.objects.get_or_create(occurrence=occ)
    review.teacher_reviewed_at = timezone.now() if reviewed else None
    if teacher_note is not None:
        review.teacher_note = teacher_note.strip()
    review.save()
    return review


@transaction.atomic
def void_attempt(attempt_id, actor, expected_revision, reason):
    """Mark an attempt VOID with mandatory reason while preserving history."""
    owner_required(actor)
    clean_reason = (reason or '').strip()
    if not clean_reason:
        raise ValidationError('Cần lý do khi hủy hiệu lực bài làm (VOID).')
    attempt = Attempt.objects.select_for_update().get(pk=attempt_id)
    if attempt.revision != expected_revision:
        raise ValidationError('Attempt revision conflict.')
    if attempt.status == 'VOID':
        return attempt
    attempt.status = 'VOID'
    attempt.void_reason = clean_reason
    attempt.revision += 1
    attempt.save(update_fields=['status', 'void_reason', 'revision'])
    AuditEvent.objects.create(actor=actor, action='attempt.void', target_type='attempt', target_id=attempt.id, reason=clean_reason)
    return attempt
