"""Owner API views for progress reports, CSV export, and ranking period lifecycle."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.accounts.permissions import api_error, owner_api_required, read_json_body, verify_recent_mfa

from .models import RankingPeriod
from .report_services import check_ranking_eligibility, create_ranking_period, export_progress_csv, owner_progress_report
from .services import activate, finalize, invalidate, recompute_publish


def _dt(value):
    dt = parse_datetime(str(value or ""))
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


def _serialize_period(period, detail=False):
    data = {
        "id": str(period.id),
        "name": period.name,
        "school_year": period.school_year,
        "start_at": period.start_at.isoformat(),
        "end_at": period.end_at.isoformat(),
        "scope": period.scope,
        "scope_target": period.scope_target,
        "status": period.status,
        "show_peers": period.show_peers,
        "revision": period.revision,
        "invalid_reason": period.invalid_reason,
    }
    if detail:
        data["eligibility"] = check_ranking_eligibility(period) if period.status == "DRAFT" else None
        data["members"] = [
            {"id": str(m.id), "student_id": str(m.student_id), "display_name": m.student.display_name, "alias": m.alias}
            for m in period.members.select_related("student").order_by("student__display_name")
        ]
        data["assignments"] = [
            {"id": str(l.assignment_id), "code": l.assignment.code, "title": l.assignment.title}
            for l in period.assignment_links.select_related("assignment")
        ]
        if period.current_snapshot_id:
            snap = period.current_snapshot
            data["snapshot"] = {
                "id": str(snap.id),
                "number": snap.number,
                "published_at": snap.published_at.isoformat(),
                "entries": [
                    {
                        "student_id": str(e.member.student_id),
                        "display_name": e.member.student.display_name,
                        "alias": e.member.alias,
                        "status": e.status,
                        "score": str(e.score) if e.score is not None else None,
                        "rank": e.rank,
                    }
                    for e in snap.entries.select_related("member__student").order_by("rank", "member__student__display_name")
                ],
            }
    return data


@never_cache
@require_GET
@owner_api_required
def progress_report(request):
    try:
        data = owner_progress_report(
            request.user,
            from_str=request.GET.get("from"),
            to_str=request.GET.get("to"),
            school_id=request.GET.get("school_id") or None,
            grade=request.GET.get("grade") or None,
            school_class_id=request.GET.get("school_class_id") or None,
            english_class_id=request.GET.get("english_class_id") or None,
        )
        return JsonResponse({"data": data})
    except ValidationError as exc:
        return _fail(exc)


@never_cache
@require_GET
@owner_api_required
def progress_export_csv(request):
    if not verify_recent_mfa(request, request.GET.get("otp_token")):
        return api_error("MFA_REQUIRED", "Cần xác thực TOTP trong 10 phút gần nhất để xuất CSV.", 403)
    try:
        csv_text = export_progress_csv(
            request.user,
            from_str=request.GET.get("from"),
            to_str=request.GET.get("to"),
            school_id=request.GET.get("school_id") or None,
            grade=request.GET.get("grade") or None,
            school_class_id=request.GET.get("school_class_id") or None,
            english_class_id=request.GET.get("english_class_id") or None,
        )
    except ValidationError as exc:
        return _fail(exc)
    response = HttpResponse(csv_text, content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="eduweb-progress.csv"'
    response["Cache-Control"] = "no-store"
    return response


@never_cache
@require_http_methods(["GET", "POST"])
@owner_api_required
def ranking_periods(request):
    if request.method == "GET":
        rows = RankingPeriod.objects.order_by("-created_at")[:100]
        return JsonResponse({"data": [_serialize_period(p) for p in rows]})
    try:
        data = read_json_body(request)
        period = create_ranking_period(
            request.user,
            data.get("name"),
            data.get("school_year"),
            _dt(data.get("start_at")),
            _dt(data.get("end_at")),
            data.get("scope"),
            data.get("scope_target"),
            data.get("student_ids"),
            data.get("assignment_ids"),
            bool(data.get("show_peers", False)),
        )
        return JsonResponse({"data": _serialize_period(period, detail=True)}, status=201)
    except ValidationError as exc:
        return _fail(exc)


@never_cache
@require_http_methods(["GET", "DELETE"])
@owner_api_required
def ranking_period_detail(request, period_id):
    period = get_object_or_404(RankingPeriod, pk=period_id)
    if request.method == "GET":
        return JsonResponse({"data": _serialize_period(period, detail=True)})
    if period.status != "DRAFT":
        return api_error("INVALID_INPUT", "Chỉ xóa được kỳ xếp hạng DRAFT.", 422)
    period.members.all().delete()
    period.assignment_links.all().delete()
    period.delete()
    return HttpResponse(status=204)


def _ranking_action(request, period_id, fn, needs_reason=False):
    get_object_or_404(RankingPeriod, pk=period_id)
    try:
        data = read_json_body(request)
        if type(data.get("expected_revision")) is not int:
            raise ValidationError("Cần expected_revision.")
        if needs_reason:
            res = fn(period_id, request.user, data["expected_revision"], data.get("reason", ""))
            return JsonResponse({"data": {"id": str(res.id), "status": res.status, "revision": res.revision}})
        res = fn(period_id, request.user, data["expected_revision"])
        if hasattr(res, "number"):
            return JsonResponse({"data": {"snapshot_id": str(res.id), "number": res.number}})
        return JsonResponse({"data": {"id": str(res.id), "status": res.status, "revision": res.revision}})
    except PermissionDenied:
        return api_error("FORBIDDEN", "Không có quyền.", 403)
    except ValidationError as exc:
        return _fail(exc)


@never_cache
@require_POST
@owner_api_required
def ranking_activate(request, period_id):
    return _ranking_action(request, period_id, activate)


@never_cache
@require_POST
@owner_api_required
def ranking_finalize(request, period_id):
    return _ranking_action(request, period_id, finalize)


@never_cache
@require_POST
@owner_api_required
def ranking_recompute_publish(request, period_id):
    return _ranking_action(request, period_id, recompute_publish)


@never_cache
@require_POST
@owner_api_required
def ranking_invalidate(request, period_id):
    return _ranking_action(request, period_id, invalidate, needs_reason=True)
