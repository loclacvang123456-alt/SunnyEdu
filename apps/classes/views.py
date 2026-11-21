"""Owner API views for schools, school classes, English classes, and memberships."""
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST

from apps.accounts.permissions import api_error, owner_api_required, read_json_body

from .models import EnglishClass, EnglishMembership, School, SchoolClass
from .services import (
    add_english_member,
    archive_english_class,
    archive_school,
    archive_school_class,
    create_english_class,
    create_school,
    create_school_class,
    leave_english_class,
    transfer_school,
)


def _parse_timestamp(value):
    if not value:
        return timezone.now()
    dt = parse_datetime(str(value))
    if not dt:
        raise ValidationError("Thời điểm không hợp lệ (cần RFC3339).")
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt)
    return dt


@never_cache
@require_http_methods(["GET", "POST"])
@owner_api_required
def schools(request):
    if request.method == "GET":
        rows = School.objects.filter(archived_at__isnull=True).order_by("name")[:100]
        return JsonResponse({"data": [{"id": str(s.id), "code": s.code, "name": s.name} for s in rows]})
    try:
        data = read_json_body(request)
        school = create_school(data.get("code"), data.get("name"), actor=request.user)
        return JsonResponse({"data": {"id": str(school.id), "code": school.code, "name": school.name}}, status=201)
    except ValidationError as exc:
        return api_error("INVALID_INPUT", "; ".join(exc.messages), 422)


@never_cache
@require_http_methods(["PATCH", "POST"])
@owner_api_required
def school_archive(request, school_id):
    get_object_or_404(School, pk=school_id)
    school = archive_school(school_id, actor=request.user)
    return JsonResponse({"data": {"id": str(school.id), "archived_at": school.archived_at.isoformat()}})


@never_cache
@require_http_methods(["GET", "POST"])
@owner_api_required
def school_classes(request):
    if request.method == "GET":
        qs = SchoolClass.objects.select_related("school").filter(archived_at__isnull=True).order_by("-school_year", "grade", "name")
        if sid := request.GET.get("school_id"):
            qs = qs.filter(school_id=sid)
        return JsonResponse({"data": [{"id": str(c.id), "school_id": str(c.school_id), "school_name": c.school.name, "school_year": c.school_year, "grade": c.grade, "name": c.name} for c in qs[:100]]})
    try:
        data = read_json_body(request)
        sc = create_school_class(data.get("school_id"), data.get("school_year"), data.get("grade"), data.get("name"), actor=request.user)
        return JsonResponse({"data": {"id": str(sc.id), "school_id": str(sc.school_id), "school_year": sc.school_year, "grade": sc.grade, "name": sc.name}}, status=201)
    except (ValidationError, School.DoesNotExist) as exc:
        msg = "; ".join(exc.messages) if isinstance(exc, ValidationError) else "Không tìm thấy trường."
        return api_error("INVALID_INPUT", msg, 422)


@never_cache
@require_http_methods(["PATCH", "POST"])
@owner_api_required
def school_class_archive(request, class_id):
    get_object_or_404(SchoolClass, pk=class_id)
    sc = archive_school_class(class_id, actor=request.user)
    return JsonResponse({"data": {"id": str(sc.id), "archived_at": sc.archived_at.isoformat()}})


@never_cache
@require_http_methods(["GET", "POST"])
@owner_api_required
def english_classes(request):
    if request.method == "GET":
        qs = EnglishClass.objects.filter(archived_at__isnull=True).order_by("-school_year", "name")[:100]
        return JsonResponse({"data": [{"id": str(c.id), "code": c.code, "name": c.name, "school_year": c.school_year} for c in qs]})
    try:
        data = read_json_body(request)
        ec = create_english_class(data.get("name"), data.get("school_year"), actor=request.user)
        return JsonResponse({"data": {"id": str(ec.id), "code": ec.code, "name": ec.name, "school_year": ec.school_year}}, status=201)
    except ValidationError as exc:
        return api_error("INVALID_INPUT", "; ".join(exc.messages), 422)


@never_cache
@require_http_methods(["PATCH", "POST"])
@owner_api_required
def english_class_archive(request, class_id):
    get_object_or_404(EnglishClass, pk=class_id)
    ec = archive_english_class(class_id, actor=request.user)
    return JsonResponse({"data": {"id": str(ec.id), "archived_at": ec.archived_at.isoformat()}})


@never_cache
@require_POST
@owner_api_required
def school_transfer(request, student_id):
    student = get_object_or_404(get_user_model(), pk=student_id, role="STUDENT")
    try:
        data = read_json_body(request)
        school_class = get_object_or_404(SchoolClass, pk=data.get("school_class_id"))
        membership = transfer_school(student, school_class, _parse_timestamp(data.get("effective_at")), actor=request.user)
        return JsonResponse({"data": {"id": str(membership.id), "school_class_id": str(membership.school_class_id), "start_at": membership.start_at.isoformat()}})
    except ValidationError as exc:
        return api_error("INVALID_INPUT", "; ".join(exc.messages), 422)


@never_cache
@require_POST
@owner_api_required
def english_members(request, class_id):
    ec = get_object_or_404(EnglishClass, pk=class_id)
    try:
        data = read_json_body(request)
        student = get_object_or_404(get_user_model(), pk=data.get("student_id"), role="STUDENT")
        membership = add_english_member(student, ec, _parse_timestamp(data.get("start_at")), actor=request.user)
        return JsonResponse({"data": {"id": str(membership.id), "student_id": str(membership.student_id), "start_at": membership.start_at.isoformat()}}, status=201)
    except ValidationError as exc:
        return api_error("INVALID_INPUT", "; ".join(exc.messages), 422)


@never_cache
@require_POST
@owner_api_required
def english_member_leave(request, class_id, student_id):
    ec = get_object_or_404(EnglishClass, pk=class_id)
    student = get_object_or_404(get_user_model(), pk=student_id, role="STUDENT")
    try:
        data = read_json_body(request)
        membership = leave_english_class(student, ec, _parse_timestamp(data.get("end_at")), actor=request.user)
        return JsonResponse({"data": {"id": str(membership.id), "end_at": membership.end_at.isoformat()}})
    except ValidationError as exc:
        return api_error("INVALID_INPUT", "; ".join(exc.messages), 422)
    except EnglishMembership.DoesNotExist:
        return api_error("NOT_FOUND", "Học sinh hiện không thuộc lớp này.", 404)
