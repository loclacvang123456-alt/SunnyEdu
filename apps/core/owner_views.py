"""Owner web UI views for dashboard, students/classes (T01), and settings."""
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import F, Q, Max
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.cache import never_cache

from apps.accounts.models import PrivacyRequest, User
from apps.accounts.permissions import owner_ui_required, recent_mfa_verified, verify_recent_mfa
from apps.accounts.services import (
    create_privacy_request,
    create_student,
    execute_privacy_request,
    generate_qr_svg,
    revoke_sessions,
    rotate_code,
    update_student,
)
from apps.assignments.models import Assignment, AssignmentRecipient, Attempt
from apps.classes.models import EnglishClass, EnglishMembership, School, SchoolClass, SchoolMembership
from apps.classes.services import (
    add_english_member,
    archive_english_class,
    archive_school,
    archive_school_class,
    create_english_class,
    create_school,
    create_school_class,
    generate_school_code,
    generate_student_import_template,
    leave_english_class,
    transfer_school,
)
from apps.content.editor_services import archive_tag, create_tag
from apps.content.models import Question, Tag
from apps.reporting.report_services import student_progress_summary
from .models import SiteAppearance
from .seasonal import THEME_CHOICES


def owner_context(active, **extra):
    """Build shared sidebar navigation URLs and merge view-specific context."""
    ctx = {
        "active": active,
        "owner_home_url": reverse("owner_dashboard"),
        "students_url": reverse("owner_students"),
        "exams_url": reverse("owner_exams"),
        "assignments_url": reverse("owner_assignments"),
        "grading_url": reverse("owner_grading_queue"),
        "reports_url": reverse("owner_reports"),
        "rankings_url": reverse("owner_rankings"),
        "settings_url": reverse("owner_settings"),
        "new_assignment_url": reverse("owner_assignment_new"),
        "logout_url": reverse("sign_out"),
    }
    ctx.update(extra)
    return ctx


def parse_local_dt(value):
    """Parse HTML datetime-local or RFC3339 input into timezone-aware UTC datetime."""
    if not value:
        return None
    dt = parse_datetime(str(value).strip())
    if not dt:
        raise ValidationError("Thời điểm không hợp lệ.")
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def pending_grading_condition():
    return Q(status="SUBMITTED") | Q(visibility_max_ms__gt=5000, visibility_reviewed_at__isnull=True)


@never_cache
@owner_ui_required
def dashboard(request):
    from .owner_teaching_views import _quick_assign_context
    now = timezone.now()
    pending_grading = Attempt.objects.filter(
        status__in=["SUBMITTED", "GRADED"],
        recipient__state="ASSIGNED",
        recipient__current_attempt_id=F("id"),
        recipient__assignment__version__exam__created_by=request.user,
    ).annotate(visibility_max_ms=Max("visibility_events__duration_ms")).filter(pending_grading_condition()).count()
    overdue_count = AssignmentRecipient.objects.filter(
        state="ASSIGNED",
        assignment__status="PUBLISHED",
        assignment__version__exam__created_by=request.user,
        assignment__due_at__lt=now,
    ).filter(Q(current_attempt__isnull=True) | Q(current_attempt__status="IN_PROGRESS")).count()
    open_assignments = Assignment.objects.filter(
        status="PUBLISHED",
        version__exam__created_by=request.user,
        opens_at__lte=now,
    ).filter(Q(late_until__isnull=True) | Q(late_until__gt=now)).count()
    qs = Assignment.objects.filter(version__exam__created_by=request.user).order_by("-created_at", "-pk")
    assignment_page = Paginator(qs, 10).get_page(request.GET.get("page"))
    status_map = {"DRAFT": "Nháp", "PUBLISHED": "Đã giao", "CANCELLED": "Đã hủy"}
    assignment_page.object_list = [
        {
            "title": a.title,
            "due_at": a.due_at,
            "status_label": status_map.get(a.status, a.status),
            "url": reverse("owner_assignment_detail", args=[a.id]),
        }
        for a in assignment_page.object_list
    ]
    return render(
        request,
        "owner/dashboard.html",
        owner_context(
            "dashboard",
            pending_grading=pending_grading,
            overdue_count=overdue_count,
            overdue_url=f"{reverse('owner_assignments')}?overdue=1",
            open_assignments=open_assignments,
            assignments=assignment_page,
            **_quick_assign_context(request.user),
        ),
    )


@never_cache
@owner_ui_required
def students(request):
    tab = request.GET.get("tab", "students")
    if request.method == "POST":
        action = request.POST.get("action")
        try:
            if action == "create_student":
                display_name = request.POST.get("display_name", "").strip()
                student_ref = request.POST.get("student_ref", "").strip() or None
                owner_note = request.POST.get("owner_note", "").strip()

                school_id = request.POST.get("school_id", "").strip()
                new_school_name = request.POST.get("new_school_name", "").strip()
                school = None
                if school_id == "__other__" and new_school_name:
                    code = generate_school_code(new_school_name)
                    school = create_school(code, new_school_name, actor=request.user)
                elif school_id and school_id != "__other__":
                    school = School.objects.filter(pk=school_id, archived_at__isnull=True).first()

                s = create_student(display_name, student_ref=student_ref, owner_note=owner_note, actor=request.user)

                if school:
                    now = timezone.now()
                    year = f"{now.year}-{now.year + 1}"
                    sc, _ = SchoolClass.objects.get_or_create(
                        school=school,
                        name="Chung",
                        defaults={"school_year": year, "grade": 6},
                    )
                    SchoolMembership.objects.create(student=s, school_class=sc, start_at=now)

                english_class_id = request.POST.get("english_class_id", "").strip()
                if english_class_id:
                    ec = EnglishClass.objects.filter(pk=english_class_id, archived_at__isnull=True).first()
                    if ec:
                        add_english_member(s, ec, timezone.now(), actor=request.user)

                messages.success(request, f"Đã tạo hồ sơ học sinh {s.display_name} (Mã: {s.student_profile.student_ref}).")
                return redirect("owner_student_detail", student_id=s.id)
            if action == "create_english_class":
                ec = create_english_class(request.POST.get("name"), request.POST.get("school_year"), actor=request.user)
                messages.success(request, f"Đã tạo lớp {ec.name} ({ec.code}).")
                return redirect(f"{reverse('owner_students')}?tab=english")
            if action == "archive_english_class":
                archive_english_class(request.POST.get("class_id"), actor=request.user)
                messages.success(request, "Đã lưu trữ lớp tiếng Anh.")
                return redirect(f"{reverse('owner_students')}?tab=english")
            if action == "create_school":
                sc = create_school(request.POST.get("code"), request.POST.get("name"), actor=request.user)
                messages.success(request, f"Đã tạo trường {sc.name}.")
                return redirect(f"{reverse('owner_students')}?tab=school")
            if action == "archive_school":
                archive_school(request.POST.get("school_id"), actor=request.user)
                messages.success(request, "Đã lưu trữ trường.")
                return redirect(f"{reverse('owner_students')}?tab=school")
            if action == "create_school_class":
                sc = create_school_class(request.POST.get("school_id"), request.POST.get("school_year"), request.POST.get("grade"), request.POST.get("name"), actor=request.user)
                messages.success(request, f"Đã tạo lớp trường {sc.name}.")
                return redirect(f"{reverse('owner_students')}?tab=school")
            if action == "archive_school_class":
                archive_school_class(request.POST.get("class_id"), actor=request.user)
                messages.success(request, "Đã lưu trữ lớp trường.")
                return redirect(f"{reverse('owner_students')}?tab=school")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))

    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "ACTIVE")
    ec_filter = request.GET.get("english_class_id", "").strip()
    student_qs = User.objects.filter(role=User.Role.STUDENT).select_related("student_profile").order_by("display_name", "id")
    if q:
        student_qs = student_qs.filter(Q(display_name__icontains=q) | Q(student_profile__student_ref__icontains=q))
    if status in User.Status.values:
        student_qs = student_qs.filter(status=status)
    if ec_filter:
        student_qs = student_qs.filter(english_memberships__english_class_id=ec_filter, english_memberships__end_at__isnull=True)
    student_page = Paginator(student_qs.distinct(), 10).get_page(request.GET.get("page"))
    student_rows = []
    for s in student_page:
        sm = SchoolMembership.objects.select_related("school_class__school").filter(student=s, end_at__isnull=True).first()
        ems = list(EnglishMembership.objects.select_related("english_class").filter(student=s, end_at__isnull=True))
        if sm:
            school_label = sm.school_class.school.name if sm.school_class.name == "Chung" else f"{sm.school_class.school.name} - {sm.school_class.name}"
        else:
            school_label = "Chưa gắn trường"
        student_rows.append({
            "user": s,
            "student_ref": s.student_profile.student_ref if hasattr(s, "student_profile") else "",
            "school_label": school_label,
            "english_labels": [f"{m.english_class.name} ({m.english_class.code})" for m in ems],
            "has_code": s.access_codes.filter(revoked_at__isnull=True).exists(),
        })

    english_classes = list(EnglishClass.objects.filter(archived_at__isnull=True).order_by("-school_year", "name"))
    schools = list(School.objects.filter(archived_at__isnull=True).order_by("name"))
    school_classes = list(SchoolClass.objects.select_related("school").filter(archived_at__isnull=True).order_by("school__name", "-school_year", "grade", "name"))
    return render(
        request,
        "owner/students.html",
        owner_context(
            "students",
            tab=tab,
            q=q,
            status_filter=status,
            ec_filter=ec_filter,
            student_rows=student_rows,
            student_page=student_page,
            english_classes=english_classes,
            schools=schools,
            school_classes=school_classes,
        ),
    )


@never_cache
@owner_ui_required
def student_import_template(request):
    fmt = request.GET.get("format", "csv").lower()
    content, content_type, filename = generate_student_import_template(fmt)
    response = HttpResponse(content, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@never_cache
@owner_ui_required
def student_detail(request, student_id):
    student = get_object_or_404(User.objects.select_related("student_profile"), pk=student_id, role=User.Role.STUDENT)
    issued_code = None
    if request.method == "POST":
        action = request.POST.get("action")
        try:
            if action == "update_profile":
                update_student(student.id, request.user, display_name=request.POST.get("display_name"), owner_note=request.POST.get("owner_note"), parent_phone=request.POST.get("parent_phone"))
                messages.success(request, "Đã cập nhật hồ sơ học sinh.")
                return redirect("owner_student_detail", student_id=student.id)
            if action == "change_status":
                update_student(student.id, request.user, status=request.POST.get("status"), reason=request.POST.get("reason", ""))
                messages.success(request, "Đã cập nhật trạng thái tài khoản.")
                return redirect("owner_student_detail", student_id=student.id)
            if action == "rotate_code":
                # ponytail: tạm tắt yêu cầu verify_recent_mfa khi cấp lại mã HS; bật lại bằng check verify_recent_mfa(request, request.POST.get("otp_token"))
                raw = rotate_code(student, actor=request.user)
                login_url = request.build_absolute_uri(f"/login/#code={raw}")
                issued_code = {"code": raw, "login_url": login_url, "qr_svg": generate_qr_svg(login_url)}
            if action == "revoke_sessions":
                revoke_sessions(student, actor=request.user)
                messages.success(request, "Đã thu hồi toàn bộ phiên đăng nhập của học sinh.")
                return redirect("owner_student_detail", student_id=student.id)
            if action == "school_transfer":
                sc = get_object_or_404(SchoolClass, pk=request.POST.get("school_class_id"))
                dt = parse_local_dt(request.POST.get("effective_at")) or timezone.now()
                transfer_school(student, sc, dt, actor=request.user)
                messages.success(request, "Đã chuyển lớp trường.")
                return redirect("owner_student_detail", student_id=student.id)
            if action == "join_english":
                ec = get_object_or_404(EnglishClass, pk=request.POST.get("english_class_id"))
                dt = parse_local_dt(request.POST.get("start_at")) or timezone.now()
                add_english_member(student, ec, dt, actor=request.user)
                messages.success(request, f"Đã thêm vào lớp {ec.name}.")
                return redirect("owner_student_detail", student_id=student.id)
            if action == "leave_english":
                ec = get_object_or_404(EnglishClass, pk=request.POST.get("english_class_id"))
                dt = parse_local_dt(request.POST.get("end_at")) or timezone.now()
                leave_english_class(student, ec, dt, actor=request.user)
                messages.success(request, f"Đã rời lớp {ec.name}.")
                return redirect("owner_student_detail", student_id=student.id)
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))

    progress = student_progress_summary(student, request.GET.get("from"), request.GET.get("to"))
    school_memberships = SchoolMembership.objects.select_related("school_class__school").filter(student=student).order_by("-start_at")
    current_sm = school_memberships.filter(end_at__isnull=True).first()
    current_school = current_sm.school_class.school if current_sm else None
    english_memberships = EnglishMembership.objects.select_related("english_class").filter(student=student).order_by("-start_at")
    available_school_classes = SchoolClass.objects.select_related("school").filter(archived_at__isnull=True).order_by("school__name", "-school_year", "grade", "name")
    available_english_classes = EnglishClass.objects.filter(archived_at__isnull=True).order_by("-school_year", "name")
    recipient_rows = AssignmentRecipient.objects.select_related("assignment", "current_attempt").filter(student=student).order_by("-assigned_at", "-pk")
    recipient_page = Paginator(recipient_rows, 10).get_page(request.GET.get("bai_tap"))

    return render(
        request,
        "owner/student_detail.html",
        owner_context(
            "students",
            student=student,
            profile=getattr(student, "student_profile", None),
            current_school=current_school,
            issued_code=issued_code,
            theme_choices=THEME_CHOICES,
            theme_selection=(SiteAppearance.objects.filter(pk=1).values_list("theme", flat=True).first() or "auto"),
            recent_mfa=recent_mfa_verified(request),
            progress=progress,
            school_memberships=school_memberships,
            english_memberships=english_memberships,
            available_school_classes=available_school_classes,
            available_english_classes=available_english_classes,
            recipient_page=recipient_page,
            now_local=timezone.localtime(timezone.now()),
        ),
    )


@never_cache
@owner_ui_required
def settings_view(request):
    if request.method == "POST":
        action = request.POST.get("action")
        try:
            if action == "save_theme":
                theme = request.POST.get("theme", "")
                if theme not in dict(THEME_CHOICES):
                    raise ValidationError("Chủ đề không hợp lệ.")
                SiteAppearance.objects.update_or_create(pk=1, defaults={"theme": theme})
                messages.success(request, "Đã lưu chủ đề cho website.")
                return redirect("owner_settings")
            if action == "verify_mfa":
                if verify_recent_mfa(request, request.POST.get("otp_token")):
                    messages.success(request, "Đã gia hạn xác thực TOTP thêm 10 phút.")
                else:
                    messages.error(request, "Mã TOTP chưa đúng.")
                return redirect("owner_settings")
            if action == "create_tag":
                create_tag(request.POST.get("kind"), request.POST.get("skill"), request.POST.get("name"), actor=request.user)
                messages.success(request, "Đã tạo tag mới.")
                return redirect("owner_settings")
            if action == "archive_tag":
                archive_tag(request.POST.get("tag_id"), actor=request.user)
                messages.success(request, "Đã lưu trữ tag.")
                return redirect("owner_settings")
            if action == "create_privacy":
                if not verify_recent_mfa(request, request.POST.get("otp_token")):
                    messages.error(request, "Cần xác thực TOTP trong 10 phút gần nhất cho yêu cầu dữ liệu.")
                else:
                    create_privacy_request(request.POST.get("student_id"), request.POST.get("kind"), request.user, request.POST.get("reason", ""))
                    messages.success(request, "Đã tạo yêu cầu dữ liệu.")
                    return redirect("owner_settings")
            if action == "execute_privacy":
                if not verify_recent_mfa(request, request.POST.get("otp_token")):
                    messages.error(request, "Cần xác thực TOTP trong 10 phút gần nhất để phê duyệt thực thi.")
                else:
                    execute_privacy_request(request.POST.get("request_id"), request.user)
                    messages.success(request, "Đã thực thi yêu cầu dữ liệu.")
                    return redirect("owner_settings")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))

    tags = Tag.objects.filter(archived_at__isnull=True).order_by("kind", "skill", "name")
    privacy_requests = PrivacyRequest.objects.select_related("student").order_by("-created_at")
    students_list = User.objects.filter(role=User.Role.STUDENT).select_related("student_profile").order_by("display_name")[:200]
    return render(
        request,
        "owner/settings.html",
        owner_context(
            "settings",
            theme_choices=THEME_CHOICES,
            theme_selection=(SiteAppearance.objects.filter(pk=1).values_list("theme", flat=True).first() or "auto"),
            recent_mfa=recent_mfa_verified(request),
            tags=tags,
            skills=Question.Skill.choices,
            privacy_requests=privacy_requests,
            students_list=students_list,
        ),
    )
