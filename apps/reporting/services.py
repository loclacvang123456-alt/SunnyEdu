"""Ranking lifecycle. Call only from authenticated OWNER requests."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from apps.accounts.models import AuditEvent
from apps.assignments.models import Assignment, AssignmentRecipient, Attempt, RecipientEnglishClass
from apps.grading.models import GradeRelease
from .calculations import rank_results
from .models import RankingAssignment, RankingEntry, RankingMember, RankingPeriod, RankingSnapshot


def owner_required(actor):
    if not actor or not actor.is_authenticated or actor.role != 'OWNER' or actor.status != 'ACTIVE':
        raise PermissionDenied


def _period(period_id, actor, expected_revision):
    owner_required(actor)
    period = RankingPeriod.objects.select_for_update().get(pk=period_id)
    if period.revision != expected_revision:
        raise ValidationError('Ranking revision conflict.')
    return period


def _audit(actor, period, action, reason=''):
    AuditEvent.objects.create(actor=actor, action=action, target_type='ranking_period', target_id=period.id, reason=reason)


def _scope_matches(period, recipient):
    target = period.scope_target
    if not isinstance(target, dict):
        return False
    if period.scope == 'ENGLISH_CLASS':
        return bool(target.get('class_id')) and RecipientEnglishClass.objects.filter(recipient=recipient, english_class_id=target['class_id'], school_year_snapshot=period.school_year).exists()
    if recipient.school_year != period.school_year:
        return False
    if period.scope == 'SCHOOL_CLASS':
        return str(recipient.school_class_id) == str(target.get('school_class_id')) and recipient.school_class_id is not None
    if period.scope == 'SCHOOL_GRADE':
        return recipient.school_id is not None and str(recipient.school_id) == str(target.get('school_id')) and recipient.grade == target.get('grade')
    if period.scope == 'SCHOOL':
        return recipient.school_id is not None and str(recipient.school_id) == str(target.get('school_id'))
    return False


def _locked_cohort(period):
    members = list(RankingMember.objects.filter(period=period).order_by('id'))
    ids = list(RankingAssignment.objects.filter(period=period).values_list('assignment_id', flat=True))
    assignments = list(Assignment.objects.select_for_update().filter(id__in=ids).order_by('id'))
    if not members or not assignments:
        raise ValidationError('Ranking requires at least one member and assignment.')
    recipients = list(AssignmentRecipient.objects.select_for_update().filter(assignment_id__in=ids, student_id__in=[m.student_id for m in members]).order_by('id'))
    by_pair = {(r.student_id, r.assignment_id): r for r in recipients}
    if any(a.status != 'PUBLISHED' for a in assignments):
        raise ValidationError('All assignments must remain published.')
    if any(a.game_feedback_enabled for a in assignments):
        raise ValidationError('Bài luyện có phản hồi game tức thời không thể dùng để xếp hạng.')
    for member in members:
        for assignment in assignments:
            recipient = by_pair.get((member.student_id, assignment.id))
            if recipient is None or recipient.state != 'ASSIGNED' or not _scope_matches(period, recipient):
                raise ValidationError('Every member must be an eligible recipient of every shared assignment.')
    return members, assignments, by_pair


@transaction.atomic
def activate(period_id, actor, expected_revision):
    period = _period(period_id, actor, expected_revision)
    if period.status != 'DRAFT':
        raise ValidationError('Only a draft may be activated.')
    members, assignments, recipients = _locked_cohort(period)
    now = timezone.now()
    if period.end_at <= period.start_at or any(a.opens_at < period.start_at or (a.late_until is None or a.late_until > period.end_at) or a.opens_at <= now for a in assignments):
        raise ValidationError('Ranking must be activated before all assignments open and cover their availability.')
    if Attempt.objects.filter(recipient_id__in=[r.id for r in recipients.values()], submitted_at__isnull=False).exists():
        raise ValidationError('A cohort member already submitted an attempt.')
    period.status = 'ACTIVE'
    period.revision += 1
    period.save(update_fields=['status', 'revision'])
    _audit(actor, period, 'ranking.activate')
    return period


def _publish(period, actor, required_status):
    if period.status != required_status:
        raise ValidationError('Ranking is not in the required status.')
    members, assignments, recipients = _locked_cohort(period)
    now = timezone.now()
    if now < period.end_at or any((a.late_until is None or now < a.late_until) for a in assignments):
        raise ValidationError('Ranking and assignments must be closed.')
    attempt_ids = [r.current_attempt_id for r in recipients.values() if r.current_attempt_id]
    attempts = {a.id: a for a in Attempt.objects.select_for_update().filter(id__in=attempt_ids).order_by('id')}
    member_scores, releases = {}, {}
    for member in members:
        scores, sources = [], []
        for assignment in assignments:
            recipient = recipients[(member.student_id, assignment.id)]
            attempt = attempts.get(recipient.current_attempt_id)
            if attempt is None or attempt.status in ('IN_PROGRESS', 'VOID'):
                scores.append(None)
                continue
            if attempt.recipient_id != recipient.id:
                raise ValidationError('Current attempt does not belong to the recipient.')
            if attempt.status != 'GRADED':
                raise ValidationError('A submitted attempt still needs grading.')
            release = GradeRelease.objects.filter(attempt=attempt).order_by('-number').first()
            if release is None:
                raise ValidationError('A graded attempt has no published result.')
            scores.append((release.total_points, release.max_points))
            sources.append(str(release.id))
        member_scores[member.id], releases[member.id] = scores, sources
    result = rank_results(member_scores, len(assignments))
    last = RankingSnapshot.objects.filter(period=period).order_by('-number').first()
    snapshot = RankingSnapshot.objects.create(period=period, number=last.number + 1 if last else 1, published_at=now, published_by=actor)
    RankingEntry.objects.bulk_create([RankingEntry(snapshot=snapshot, member=member, source_release_ids=releases[member.id], **result[member.id]) for member in members])
    period.status, period.current_snapshot, period.revision = 'FINAL', snapshot, period.revision + 1
    period.save(update_fields=['status','current_snapshot','revision'])
    _audit(actor, period, 'ranking.publish')
    return snapshot


@transaction.atomic
def finalize(period_id, actor, expected_revision):
    return _publish(_period(period_id, actor, expected_revision), actor, 'ACTIVE')


@transaction.atomic
def recompute_publish(period_id, actor, expected_revision):
    return _publish(_period(period_id, actor, expected_revision), actor, 'STALE')


@transaction.atomic
def invalidate(period_id, actor, expected_revision, reason):
    period = _period(period_id, actor, expected_revision)
    if period.status not in ('ACTIVE', 'FINAL', 'STALE') or not reason.strip():
        raise ValidationError('Invalidation requires an active ranking and a reason.')
    period.status, period.invalid_reason, period.revision = 'INVALID', reason.strip(), period.revision + 1
    period.save(update_fields=['status','invalid_reason','revision'])
    _audit(actor, period, 'ranking.invalidate', reason.strip())
    return period
