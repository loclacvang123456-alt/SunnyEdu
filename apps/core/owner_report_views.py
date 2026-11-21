"""Owner web UI views for progress reports and ranking periods (T04)."""
import json
import uuid
from datetime import timedelta

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import F
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache

from apps.accounts.models import User
from apps.accounts.permissions import owner_ui_required, recent_mfa_verified
from apps.assignments.models import Assignment
from apps.classes.models import EnglishClass, School, SchoolClass
from apps.content.models import Course
from apps.reporting.models import RankingPeriod
from apps.reporting.report_services import check_ranking_eligibility, create_ranking_period, owner_progress_report
from apps.reporting.services import activate, finalize, invalidate, recompute_publish

from .owner_views import owner_context, parse_local_dt


@never_cache
@owner_ui_required
def reports(request):
    view_mode = "ielts" if request.GET.get("view") == "ielts" else "general"
    school_id = request.GET.get("school_id") or None
    grade = request.GET.get("grade") or None
    school_class_id = request.GET.get("school_class_id") or None
    english_class_id = request.GET.get("english_class_id") or None
    student_id = request.GET.get("student_id") or None
    if student_id:
        try:
            parsed_sid = uuid.UUID(str(student_id))
            return redirect("owner_student_detail", student_id=parsed_sid)
        except ValueError:
            pass
    q = (request.GET.get("q") or "").strip() or None
    from_str = request.GET.get("from") or None
    to_str = request.GET.get("to") or None

    # Clear incompatible child filters if parent school changed.
    if school_class_id and school_id:
        if not SchoolClass.objects.filter(pk=school_class_id, school_id=school_id).exists():
            school_class_id = None
    if grade and not school_id:
        grade = None

    report_data = None
    error_msg = None
    try:
        report_data = owner_progress_report(
            request.user,
            from_str=from_str,
            to_str=to_str,
            school_id=school_id,
            grade=grade,
            school_class_id=school_class_id,
            english_class_id=english_class_id,
            student_id=student_id,
            q=q,
        )
    except ValidationError as exc:
        error_msg = "; ".join(exc.messages)

    schools = list(School.objects.filter(archived_at__isnull=True).order_by("name"))
    school_classes = list(SchoolClass.objects.select_related("school").filter(archived_at__isnull=True).order_by("-school_year", "grade", "name"))
    english_classes = list(EnglishClass.objects.filter(archived_at__isnull=True).order_by("-school_year", "name"))
    export_assignments = list(Assignment.objects.filter(version__exam__created_by=request.user, status="PUBLISHED").prefetch_related("classes", "course_exercises").order_by(F("published_at").desc(nulls_last=True), "-created_at"))
    export_courses = list(Course.objects.filter(created_by=request.user).prefetch_related("english_classes").order_by("name"))
    export_data = {
        "assignments": [{"id": str(a.id), "title": a.title, "classes": [str(c.id) for c in a.classes.all()], "courses": [str(e.course_id) for e in a.course_exercises.all()]} for a in export_assignments],
        "classes": [{"id": str(c.id), "name": c.name} for c in english_classes],
        "courses": [{"id": str(c.id), "name": c.name, "classes": [str(cl.id) for cl in c.english_classes.all()]} for c in export_courses],
    }
    if school_id:
        school_classes_filtered = [c for c in school_classes if str(c.school_id) == str(school_id)]
    else:
        school_classes_filtered = school_classes

    selected_student = None
    if student_id and report_data and report_data.get("students"):
        selected_student = next((s for s in report_data["students"] if s["student_id"] == str(student_id)), None)

    return render(
        request,
        "owner/reports.html",
        owner_context(
            "reports",
            report=report_data,
            selected_student=selected_student,
            view_mode=view_mode,
            error_msg=error_msg,
            schools=schools,
            school_classes=school_classes_filtered,
            all_school_classes_json=json.dumps([{"id": str(c.id), "school_id": str(c.school_id), "grade": c.grade, "label": f"{c.school_year} - Khối {c.grade} - {c.name}"} for c in school_classes]),
            english_classes=english_classes,
            export_data=export_data,
            filters={"view": view_mode, "school_id": school_id or "", "grade": grade or "", "school_class_id": school_class_id or "", "english_class_id": english_class_id or "", "student_id": student_id or "", "q": q or "", "from": report_data["from"] if report_data else (from_str or ""), "to": report_data["to"] if report_data else (to_str or "")},
            recent_mfa=recent_mfa_verified(request),
            grades=list(range(1, 13)),
        ),
    )


@never_cache
@owner_ui_required
def rankings(request):
    periods = RankingPeriod.objects.order_by("-created_at")
    return render(request, "owner/rankings.html", owner_context("rankings", periods=periods))


@never_cache
@owner_ui_required
def ranking_new(request):
    if request.method == "POST":
        try:
            scope = request.POST.get("scope")
            target = {}
            if scope == "ENGLISH_CLASS":
                target = {"class_id": request.POST.get("english_class_id")}
            elif scope == "SCHOOL_CLASS":
                target = {"school_class_id": request.POST.get("school_class_id")}
            elif scope == "SCHOOL_GRADE":
                target = {"school_id": request.POST.get("school_id"), "grade": int(request.POST.get("grade", 0))}
            elif scope == "SCHOOL":
                target = {"school_id": request.POST.get("school_id")}

            period = create_ranking_period(
                request.user,
                request.POST.get("name"),
                request.POST.get("school_year"),
                parse_local_dt(request.POST.get("start_at")),
                parse_local_dt(request.POST.get("end_at")),
                scope,
                target,
                request.POST.getlist("student_ids"),
                request.POST.getlist("assignment_ids"),
                show_peers=bool(request.POST.get("show_peers")),
            )
            messages.success(request, f"Đã tạo kỳ xếp hạng nháp {period.name}.")
            return redirect("owner_ranking_detail", period_id=period.id)
        except (ValidationError, ValueError) as exc:
            msg = "; ".join(exc.messages) if isinstance(exc, ValidationError) else "Dữ liệu kỳ xếp hạng không hợp lệ."
            messages.error(request, msg)

    english_classes = EnglishClass.objects.filter(archived_at__isnull=True).order_by("-school_year", "name")
    schools = School.objects.filter(archived_at__isnull=True).order_by("name")
    school_classes = SchoolClass.objects.select_related("school").filter(archived_at__isnull=True).order_by("school__name", "-school_year", "grade", "name")
    students = User.objects.filter(role=User.Role.STUDENT, status="ACTIVE").select_related("student_profile").order_by("display_name")[:200]
    assignments = Assignment.objects.filter(status="PUBLISHED", version__exam__created_by=request.user).order_by("-opens_at")[:100]
    now_local = timezone.localtime(timezone.now()).replace(second=0, microsecond=0)
    return render(
        request,
        "owner/ranking_new.html",
        owner_context(
            "rankings",
            english_classes=english_classes,
            schools=schools,
            school_classes=school_classes,
            students=students,
            assignments=assignments,
            default_start=now_local,
            default_end=now_local + timedelta(days=14),
            grades=list(range(1, 13)),
        ),
    )


@never_cache
@owner_ui_required
def ranking_detail(request, period_id):
    period = get_object_or_404(RankingPeriod, pk=period_id)
    if request.method == "POST":
        action = request.POST.get("action")
        try:
            rev = int(request.POST.get("expected_revision", period.revision))
            if action == "activate":
                activate(period.id, request.user, rev)
                messages.success(request, "Đã kích hoạt kỳ xếp hạng.")
            elif action == "finalize":
                finalize(period.id, request.user, rev)
                messages.success(request, "Đã chốt và công bố bảng xếp hạng.")
            elif action == "recompute":
                recompute_publish(period.id, request.user, rev)
                messages.success(request, "Đã tính lại và công bố phiên bản mới.")
            elif action == "invalidate":
                invalidate(period.id, request.user, rev, request.POST.get("reason", ""))
                messages.success(request, "Đã hủy hiệu lực kỳ xếp hạng.")
        except (ValidationError, ValueError) as exc:
            msg = "; ".join(exc.messages) if isinstance(exc, ValidationError) else "Dữ liệu không hợp lệ."
            messages.error(request, msg)
        return redirect("owner_ranking_detail", period_id=period.id)

    eligibility = check_ranking_eligibility(period) if period.status == "DRAFT" else None
    members = period.members.select_related("student").order_by("student__display_name")
    assignments = [l.assignment for l in period.assignment_links.select_related("assignment")]
    entries = []
    if period.current_snapshot_id:
        for e in period.current_snapshot.entries.select_related("member__student").order_by("rank", "member__student__display_name"):
            late_any = any(
                r.current_attempt and r.current_attempt.is_late
                for r in e.member.student.assignmentrecipient_set.filter(assignment__in=assignments)
            )
            entries.append({"entry": e, "late_any": late_any})

    return render(
        request,
        "owner/ranking_detail.html",
        owner_context(
            "rankings",
            period=period,
            eligibility=eligibility,
            members=members,
            assignments=assignments,
            entries=entries,
        ),
    )
