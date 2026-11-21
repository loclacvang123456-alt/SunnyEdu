"""Owner API endpoints for student management, access codes, and privacy requests."""
import json

from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from django.utils import timezone
from apps.classes.models import EnglishClass, EnglishMembership, School, SchoolClass, SchoolMembership
from apps.classes.services import add_english_member, create_school, generate_school_code, generate_student_import_template

from .models import PrivacyRequest, User
from .permissions import api_error, owner_api_required, read_json_body, verify_recent_mfa
from .services import (
    create_privacy_request,
    create_student,
    execute_privacy_request,
    export_student_data,
    generate_qr_svg,
    revoke_sessions,
    rotate_code,
    update_student,
)


def _serialize_student(student):
    profile = getattr(student, "student_profile", None)
    school_m = SchoolMembership.objects.select_related("school_class__school").filter(student=student, end_at__isnull=True).first()
    english_ms = list(EnglishMembership.objects.select_related("english_class").filter(student=student, end_at__isnull=True))
    has_code = student.access_codes.filter(revoked_at__isnull=True).exists()
    return {
        "id": str(student.id),
        "student_ref": profile.student_ref if profile else "",
        "display_name": student.display_name,
        "status": student.status,
        "owner_note": profile.owner_note if profile else "",
        "has_active_code": has_code,
        "school_class": (
            {
                "id": str(school_m.school_class_id),
                "school_name": school_m.school_class.school.name,
                "school_year": school_m.school_class.school_year,
                "grade": school_m.school_class.grade,
                "name": school_m.school_class.name,
            }
            if school_m
            else None
        ),
        "english_classes": [
            {"id": str(m.english_class_id), "code": m.english_class.code, "name": m.english_class.name, "school_year": m.english_class.school_year}
            for m in english_ms
        ],
    }


@never_cache
@require_http_methods(["GET", "POST"])
@owner_api_required
def students(request):
    if request.method == "GET":
        qs = User.objects.filter(role=User.Role.STUDENT).select_related("student_profile").order_by("display_name", "created_at")
        q = request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(display_name__icontains=q) | Q(student_profile__student_ref__icontains=q))
        status = request.GET.get("status", "").strip()
        if status in User.Status.values:
            qs = qs.filter(status=status)
        if ec_id := request.GET.get("english_class_id", "").strip():
            qs = qs.filter(english_memberships__english_class_id=ec_id, english_memberships__end_at__isnull=True)
        if sc_id := request.GET.get("school_class_id", "").strip():
            qs = qs.filter(school_memberships__school_class_id=sc_id, school_memberships__end_at__isnull=True)
        qs = qs.distinct()
        page = max(1, int(request.GET.get("page", 1) or 1))
        page_size = min(100, max(1, int(request.GET.get("page_size", 25) or 25)))
        total = qs.count()
        items = [_serialize_student(s) for s in qs[(page - 1) * page_size : page * page_size]]
        return JsonResponse({"data": items, "page": page, "page_size": page_size, "total": total})
    try:
        data = read_json_body(request)
        display_name = data.get("display_name")
        student_ref = data.get("student_ref")
        owner_note = data.get("owner_note", "")
        school_id = data.get("school_id")
        new_school_name = (data.get("new_school_name") or "").strip()
        english_class_id = data.get("english_class_id")

        school = None
        if school_id == "__other__" and new_school_name:
            code = generate_school_code(new_school_name)
            school = create_school(code, new_school_name, actor=request.user)
        elif school_id and school_id != "__other__":
            school = School.objects.filter(pk=school_id, archived_at__isnull=True).first()

        student = create_student(display_name, student_ref, owner_note, actor=request.user)

        if school:
            now = timezone.now()
            year = f"{now.year}-{now.year + 1}"
            sc, _ = SchoolClass.objects.get_or_create(
                school=school,
                name="Chung",
                defaults={"school_year": year, "grade": 6},
            )
            SchoolMembership.objects.create(student=student, school_class=sc, start_at=now)

        if english_class_id:
            ec = EnglishClass.objects.filter(pk=english_class_id, archived_at__isnull=True).first()
            if ec:
                add_english_member(student, ec, timezone.now(), actor=request.user)

        return JsonResponse({"data": _serialize_student(student)}, status=201)
    except ValidationError as exc:
        return api_error("INVALID_INPUT", "; ".join(exc.messages), 422)


@never_cache
@require_GET
@owner_api_required
def student_import_template(request):
    fmt = request.GET.get("format", "csv").lower()
    content, content_type, filename = generate_student_import_template(fmt)
    response = HttpResponse(content, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@never_cache
@require_http_methods(["GET", "PATCH"])
@owner_api_required
def student_detail(request, student_id):
    student = get_object_or_404(User.objects.select_related("student_profile"), pk=student_id, role=User.Role.STUDENT)
    if request.method == "GET":
        return JsonResponse({"data": _serialize_student(student)})
    try:
        data = read_json_body(request)
        updated = update_student(
            student.id,
            request.user,
            display_name=data.get("display_name") if "display_name" in data else None,
            status=data.get("status") if "status" in data else None,
            owner_note=data.get("owner_note") if "owner_note" in data else None,
            reason=data.get("reason", ""),
        )
        return JsonResponse({"data": _serialize_student(updated)})
    except ValidationError as exc:
        return api_error("INVALID_INPUT", "; ".join(exc.messages), 422)


@never_cache
@require_POST
@owner_api_required
def student_rotate_code(request, student_id):
    try:
        data = read_json_body(request)
    except ValidationError as exc:
        return api_error("INVALID_INPUT", "; ".join(exc.messages), 422)
    if not verify_recent_mfa(request, data.get("otp_token")):
        return api_error("MFA_REQUIRED", "Cần xác thực TOTP trong 10 phút gần nhất để cấp mã.", 403)
    student = get_object_or_404(User, pk=student_id, role=User.Role.STUDENT)
    try:
        raw_code = rotate_code(student, actor=request.user)
        login_url = request.build_absolute_uri(f"/login/#code={raw_code}")
        return JsonResponse({"data": {"code": raw_code, "login_url": login_url, "qr_svg": generate_qr_svg(login_url), "warning": "Mã cá nhân là bí mật. Chỉ gửi riêng cho học sinh, không gửi vào nhóm chung."}})
    except ValidationError as exc:
        return api_error("INVALID_INPUT", "; ".join(exc.messages), 422)


@never_cache
@require_POST
@owner_api_required
def student_revoke_sessions(request, student_id):
    student = get_object_or_404(User, pk=student_id, role=User.Role.STUDENT)
    revoke_sessions(student, actor=request.user)
    return JsonResponse({"data": {"revoked": True}})


@never_cache
@require_GET
@owner_api_required
def student_progress(request, student_id):
    from apps.reporting.services import student_progress_summary
    student = get_object_or_404(User, pk=student_id, role=User.Role.STUDENT)
    try:
        data = student_progress_summary(student, request.GET.get("from"), request.GET.get("to"))
        return JsonResponse({"data": data})
    except ValidationError as exc:
        return api_error("INVALID_INPUT", "; ".join(exc.messages), 422)


@never_cache
@require_http_methods(["GET", "POST"])
@owner_api_required
def privacy_requests(request):
    if request.method == "GET":
        rows = PrivacyRequest.objects.select_related("student").order_by("-created_at")[:100]
        return JsonResponse({"data": [{"id": str(r.id), "student_id": str(r.student_id), "student_name": r.student.display_name, "kind": r.kind, "status": r.status, "reason": r.reason, "report": r.report, "created_at": r.created_at.isoformat()} for r in rows]})
    try:
        data = read_json_body(request)
        if not verify_recent_mfa(request, data.get("otp_token")):
            return api_error("MFA_REQUIRED", "Cần xác thực TOTP trong 10 phút gần nhất cho yêu cầu dữ liệu.", 403)
        req = create_privacy_request(data.get("student_id"), data.get("kind"), request.user, data.get("reason", ""))
        return JsonResponse({"data": {"id": str(req.id), "status": req.status, "kind": req.kind}}, status=201)
    except (ValidationError, User.DoesNotExist) as exc:
        msg = "; ".join(exc.messages) if isinstance(exc, ValidationError) else "Không tìm thấy học sinh."
        return api_error("INVALID_INPUT", msg, 422)


@never_cache
@require_GET
@owner_api_required
def privacy_request_detail(request, request_id):
    req = get_object_or_404(PrivacyRequest.objects.select_related("student"), pk=request_id)
    return JsonResponse({"data": {"id": str(req.id), "student_id": str(req.student_id), "student_name": req.student.display_name, "kind": req.kind, "status": req.status, "reason": req.reason, "report": req.report, "approved_at": req.approved_at.isoformat() if req.approved_at else None, "completed_at": req.completed_at.isoformat() if req.completed_at else None}})


@never_cache
@require_POST
@owner_api_required
def privacy_request_approve(request, request_id):
    try:
        data = read_json_body(request)
    except ValidationError as exc:
        return api_error("INVALID_INPUT", "; ".join(exc.messages), 422)
    if not verify_recent_mfa(request, data.get("otp_token")):
        return api_error("MFA_REQUIRED", "Cần xác thực TOTP trong 10 phút gần nhất để phê duyệt xuất/xóa dữ liệu.", 403)
    req = get_object_or_404(PrivacyRequest, pk=request_id)
    req = execute_privacy_request(req.id, request.user)
    return JsonResponse({"data": {"id": str(req.id), "status": req.status, "report": req.report}})


@never_cache
@require_GET
@owner_api_required
def privacy_request_export(request, request_id):
    if not verify_recent_mfa(request, request.GET.get("otp_token")):
        return api_error("MFA_REQUIRED", "Cần xác thực TOTP trong 10 phút gần nhất để tải dữ liệu học sinh.", 403)
    req = get_object_or_404(PrivacyRequest, pk=request_id, kind=PrivacyRequest.Kind.EXPORT)
    payload = export_student_data(req.student_id, request.user)
    response = HttpResponse(json.dumps(payload, ensure_ascii=False, indent=2), content_type="application/json; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="student-export-{req.student_id}.json"'
    response["Cache-Control"] = "no-store"
    return response
