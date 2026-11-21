"""Owner API views for assignments, recipients, exemptions, retakes, and answer release."""
from django.core.exceptions import ValidationError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST

from apps.accounts.permissions import api_error, owner_api_required, read_json_body
from apps.reporting.models import RankingAssignment, RankingPeriod

from .models import Assignment, AssignmentRecipient
from .owner_services import (
    add_assignment_recipients,
    cancel_assignment,
    create_draft_assignment,
    delete_draft_assignment,
    exempt_recipient,
    extend_assignment,
    grant_retake,
    publish_assignment,
    release_answers,
    update_draft_assignment,
)


def _dt(value, required=True):
    if not value:
        if required:
            raise ValidationError("Thiếu mốc thời gian RFC3339.")
        return None
    dt = parse_datetime(str(value))
    if not dt:
        raise ValidationError("Mốc thời gian không hợp lệ.")
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt)
    return dt


def _fail(exc):
    msg = "; ".join(exc.messages)
    if "revision conflict" in msg:
        return api_error("CONFLICT", msg, 409)
    return api_error("INVALID_INPUT", msg, 422)


def _ranking_warnings(assignment_id):
    pids = RankingAssignment.objects.filter(assignment_id=assignment_id).values_list("period_id", flat=True)
    return [
        {"id": str(p.id), "name": p.name, "status": p.status}
        for p in RankingPeriod.objects.filter(pk__in=pids, status__in=("ACTIVE", "FINAL", "STALE"))
    ]


def _serialize_assignment(a, detail=False):
    data = {
        "id": str(a.id),
        "code": a.code,
        "title": a.title,
        "status": a.status,
        "revision": a.revision,
        "version_id": str(a.version_id),
        "exam_title": a.version.exam.title,
        "version_number": a.version.number,
        "opens_at": a.opens_at.isoformat(),
        "due_at": a.due_at.isoformat(),
        "late_until": a.late_until.isoformat(),
        "late_policy": a.late_policy,
        "mode": a.mode,
        "game_feedback_enabled": a.game_feedback_enabled,
        "published_at": a.published_at.isoformat() if a.published_at else None,
        "answers_released_at": a.answers_released_at.isoformat() if a.answers_released_at else None,
        "recipient_count": a.recipients.count(),
    }
    if detail:
        data["ranking_warnings"] = _ranking_warnings(a.id)
        data["classes"] = [{"id": str(c.id), "code": c.code, "name": c.name} for c in a.classes.all()]
        data["recipients"] = [
            {
                "id": str(r.id),
                "student_id": str(r.student_id),
                "student_name": r.student.display_name,
                "state": r.state,
                "school_class_name": r.school_class_name_snapshot,
                "current_attempt_id": str(r.current_attempt_id) if r.current_attempt_id else None,
                "attempt_status": r.current_attempt.status if r.current_attempt_id else None,
                "attempt_no": r.current_attempt.attempt_no if r.current_attempt_id else 0,
                "is_late": r.current_attempt.is_late if r.current_attempt_id else False,
            }
            for r in a.recipients.select_related("student", "current_attempt").order_by("student__display_name")
        ]
    return data


@never_cache
@require_http_methods(["GET", "POST"])
@owner_api_required
def assignments(request):
    if request.method == "GET":
        qs = Assignment.objects.filter(version__exam__created_by=request.user).select_related("version__exam").order_by("-created_at")
        if status := request.GET.get("status"):
            qs = qs.filter(status=status)
        return JsonResponse({"data": [_serialize_assignment(a) for a in qs[:100]]})
    try:
        data = read_json_body(request)
        a = create_draft_assignment(
            request.user,
            data.get("version_id"),
            data.get("title"),
            data.get("class_ids"),
            _dt(data.get("opens_at")),
            _dt(data.get("due_at")),
            data.get("late_policy", "ALLOW"),
            _dt(data.get("late_until"), required=False),
            mode=data.get("mode", "PRACTICE"),
            game_feedback_enabled=data.get("game_feedback_enabled", False),
        )
        return JsonResponse({"data": _serialize_assignment(a, detail=True)}, status=201)
    except ValidationError as exc:
        return _fail(exc)


@never_cache
@require_http_methods(["GET", "PATCH", "DELETE"])
@owner_api_required
def assignment_detail(request, assignment_id):
    assignment = get_object_or_404(Assignment.objects.select_related("version__exam"), pk=assignment_id, version__exam__created_by=request.user)
    if request.method == "GET":
        return JsonResponse({"data": _serialize_assignment(assignment, detail=True)})
    if request.method == "DELETE":
        try:
            delete_draft_assignment(request.user, assignment.id)
            return HttpResponse(status=204)
        except ValidationError as exc:
            return _fail(exc)
    try:
        data = read_json_body(request)
        if type(data.get("expected_revision")) is not int:
            raise ValidationError("Cần expected_revision.")
        updated = update_draft_assignment(
            request.user,
            assignment.id,
            data["expected_revision"],
            title=data.get("title"),
            class_ids=data.get("class_ids"),
            opens_at=_dt(data.get("opens_at"), required=False),
            due_at=_dt(data.get("due_at"), required=False),
            late_policy=data.get("late_policy"),
            late_until=_dt(data.get("late_until"), required=False),
            mode=data.get("mode"),
            game_feedback_enabled=data.get("game_feedback_enabled"),
        )
        return JsonResponse({"data": _serialize_assignment(updated, detail=True)})
    except ValidationError as exc:
        return _fail(exc)


@never_cache
@require_POST
@owner_api_required
def assignment_publish(request, assignment_id):
    get_object_or_404(Assignment, pk=assignment_id, version__exam__created_by=request.user)
    try:
        data = read_json_body(request)
        if type(data.get("expected_revision")) is not int:
            raise ValidationError("Cần expected_revision.")
        a = publish_assignment(request.user, assignment_id, data["expected_revision"])
        return JsonResponse({"data": _serialize_assignment(a, detail=True)})
    except ValidationError as exc:
        return _fail(exc)


@never_cache
@require_POST
@owner_api_required
def assignment_extend(request, assignment_id):
    get_object_or_404(Assignment, pk=assignment_id, version__exam__created_by=request.user)
    try:
        data = read_json_body(request)
        if type(data.get("expected_revision")) is not int:
            raise ValidationError("Cần expected_revision.")
        a = extend_assignment(request.user, assignment_id, data["expected_revision"], _dt(data.get("due_at")), _dt(data.get("late_until")), data.get("reason", ""))
        return JsonResponse({"data": _serialize_assignment(a, detail=True)})
    except ValidationError as exc:
        return _fail(exc)


@never_cache
@require_POST
@owner_api_required
def assignment_cancel(request, assignment_id):
    get_object_or_404(Assignment, pk=assignment_id, version__exam__created_by=request.user)
    try:
        data = read_json_body(request)
        if type(data.get("expected_revision")) is not int:
            raise ValidationError("Cần expected_revision.")
        a = cancel_assignment(request.user, assignment_id, data["expected_revision"], data.get("reason", ""))
        return JsonResponse({"data": _serialize_assignment(a, detail=True)})
    except ValidationError as exc:
        return _fail(exc)


@never_cache
@require_POST
@owner_api_required
def assignment_recipients(request, assignment_id):
    get_object_or_404(Assignment, pk=assignment_id, version__exam__created_by=request.user)
    try:
        data = read_json_body(request)
        added = add_assignment_recipients(request.user, assignment_id, data.get("student_ids"), data.get("reason", ""))
        return JsonResponse({"data": {"added": len(added), "warnings": _ranking_warnings(assignment_id)}}, status=201)
    except ValidationError as exc:
        return _fail(exc)


@never_cache
@require_POST
@owner_api_required
def recipient_exempt(request, recipient_id):
    get_object_or_404(AssignmentRecipient, pk=recipient_id, assignment__version__exam__created_by=request.user)
    try:
        data = read_json_body(request)
        rec = exempt_recipient(request.user, recipient_id, data.get("reason", ""))
        return JsonResponse({"data": {"id": str(rec.id), "state": rec.state, "warnings": _ranking_warnings(rec.assignment_id)}})
    except ValidationError as exc:
        return _fail(exc)


@never_cache
@require_POST
@owner_api_required
def recipient_retake(request, recipient_id):
    get_object_or_404(AssignmentRecipient, pk=recipient_id, assignment__version__exam__created_by=request.user)
    try:
        data = read_json_body(request)
        attempt = grant_retake(request.user, recipient_id, data.get("reason", ""))
        return JsonResponse({"data": {"attempt_id": str(attempt.id), "attempt_no": attempt.attempt_no, "warnings": _ranking_warnings(attempt.recipient.assignment_id)}}, status=201)
    except ValidationError as exc:
        return _fail(exc)


@never_cache
@require_POST
@owner_api_required
def assignment_release_answers(request, assignment_id):
    get_object_or_404(Assignment, pk=assignment_id, version__exam__created_by=request.user)
    try:
        data = read_json_body(request)
        if type(data.get("expected_revision")) is not int:
            raise ValidationError("Cần expected_revision.")
        a = release_answers(request.user, assignment_id, data["expected_revision"])
        return JsonResponse({"data": {"id": str(a.id), "answers_released_at": a.answers_released_at.isoformat()}})
    except ValidationError as exc:
        return _fail(exc)
