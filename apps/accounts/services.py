import hashlib
import hmac
import io
import secrets
import uuid
from datetime import timedelta

import qrcode
import qrcode.image.svg
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import AccessCode, AuditEvent, PrivacyRequest, StudentProfile, User

ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def normalize_code(code):
    value = code.upper().replace("-", "").replace(" ", "")
    if len(value) != 20 or any(c not in ALPHABET for c in value):
        raise ValidationError("Invalid code")
    return value


def digest_code(code, key):
    return hmac.new(key.encode(), code.encode(), hashlib.sha256).hexdigest()


def access_keys():
    return {int(version): key for version, key in settings.ACCESS_CODE_HMAC_KEYS.items()}


@transaction.atomic
def rotate_code(student, actor=None):
    student = User.objects.select_for_update().get(pk=student.pk)
    if student.role != User.Role.STUDENT or student.status != User.Status.ACTIVE:
        raise ValidationError("Học sinh không ở trạng thái hoạt động.")
    now = timezone.now()
    student.access_codes.filter(revoked_at__isnull=True).update(revoked_at=now)
    keys = access_keys()
    version = max(keys)
    raw = "".join(secrets.choice(ALPHABET) for _ in range(20))
    AccessCode.objects.create(student=student, key_version=version, code_digest=digest_code(raw, keys[version]))
    student.auth_epoch += 1
    student.save(update_fields=["auth_epoch", "updated_at"])
    AuditEvent.objects.create(actor=actor, action="student.code.rotate", target_type="user", target_id=student.pk)
    return "-".join(raw[i:i + 5] for i in range(0, 20, 5))


def generate_qr_svg(login_url):
    """Generate a self-contained SVG QR code for private teacher printing."""
    img = qrcode.make(login_url, image_factory=qrcode.image.svg.SvgPathImage, box_size=8, border=2)
    buf = io.BytesIO()
    img.save(buf)
    return buf.getvalue().decode("utf-8")


def find_student(raw):
    try:
        normalized = normalize_code(raw)
    except (ValidationError, AttributeError):
        return None
    for version, key in access_keys().items():
        code = AccessCode.objects.select_related("student").filter(
            code_digest=digest_code(normalized, key),
            key_version=version,
            revoked_at__isnull=True,
            student__role=User.Role.STUDENT,
            student__status=User.Status.ACTIVE,
        ).first()
        if code:
            return code.student
    return None


@transaction.atomic
def revoke_sessions(student, actor=None):
    student = User.objects.select_for_update().get(pk=student.pk)
    student.auth_epoch += 1
    student.save(update_fields=["auth_epoch", "updated_at"])
    AuditEvent.objects.create(actor=actor, action="student.sessions.revoke", target_type="user", target_id=student.pk)


def initialize_session(request, user, remember_device=False):
    """Initialize session validity metadata according to user role."""
    now = timezone.now()
    is_student = user.role == User.Role.STUDENT
    remember = bool(remember_device and is_student)
    request.session["auth_epoch"] = user.auth_epoch
    request.session["issued_at"] = now.isoformat()
    request.session["last_activity"] = now.isoformat()
    request.session["remember_device"] = remember
    request.session.set_expiry(30 * 86400 if remember else (7200 if is_student else 8 * 3600))


def generate_student_ref():
    """Tự động tạo mã học sinh duy nhất dạng HS2026-0001."""
    year = timezone.now().year
    prefix = f"HS{year}-"
    count = StudentProfile.objects.filter(student_ref__startswith=prefix).count()
    for num in range(count + 1, count + 10000):
        candidate = f"{prefix}{num:04d}"
        if not StudentProfile.objects.filter(student_ref=candidate).exists():
            return candidate
    for _ in range(50):
        candidate = f"{prefix}{''.join(secrets.choice(ALPHABET) for _ in range(4))}"
        if not StudentProfile.objects.filter(student_ref=candidate).exists():
            return candidate
    raise ValidationError("Không thể tự động tạo mã học sinh duy nhất.")


@transaction.atomic
def create_student(display_name, student_ref=None, owner_note="", actor=None):
    """Create a STUDENT account and StudentProfile without public signup."""
    name = (display_name or "").strip()
    ref = (student_ref or "").strip()
    if not ref:
        ref = generate_student_ref()
    if not 1 <= len(name) <= 120:
        raise ValidationError("Tên học sinh phải có từ 1 đến 120 ký tự.")
    if not 1 <= len(ref) <= 32:
        raise ValidationError("Mã học sinh (student_ref) phải có từ 1 đến 32 ký tự.")
    try:
        user = User(username=f"stu-{uuid.uuid4().hex[:16]}", role=User.Role.STUDENT, display_name=name, status=User.Status.ACTIVE)
        user.set_unusable_password()
        user.save()
        StudentProfile.objects.create(user=user, student_ref=ref, owner_note=(owner_note or "").strip())
    except IntegrityError as exc:
        raise ValidationError("Mã học sinh (student_ref) đã tồn tại.") from exc
    AuditEvent.objects.create(actor=actor, action="student.create", target_type="user", target_id=user.pk)
    return user


@transaction.atomic
def update_student(student_id, actor, display_name=None, status=None, owner_note=None, reason=""):
    """Update student name/note or transition ACTIVE/SUSPENDED/ARCHIVED status with session revocation."""
    student = User.objects.select_for_update().get(pk=student_id, role=User.Role.STUDENT)
    fields = ["updated_at"]
    if display_name is not None:
        name = display_name.strip()
        if not 1 <= len(name) <= 120:
            raise ValidationError("Tên học sinh phải có từ 1 đến 120 ký tự.")
        student.display_name = name
        fields.append("display_name")
    if owner_note is not None and hasattr(student, "student_profile"):
        student.student_profile.owner_note = owner_note.strip()
        student.student_profile.save(update_fields=["owner_note", "updated_at"])
    if status is not None and status != student.status:
        if status not in User.Status.values:
            raise ValidationError("Trạng thái học sinh không hợp lệ.")
        old_status = student.status
        if old_status == User.Status.ARCHIVED and status == User.Status.ACTIVE and not (reason or "").strip():
            raise ValidationError("Cần ghi rõ lý do khi khôi phục tài khoản đã lưu trữ.")
        student.status = status
        fields.append("status")
        if status in (User.Status.SUSPENDED, User.Status.ARCHIVED):
            student.auth_epoch += 1
            fields.append("auth_epoch")
            if status == User.Status.ARCHIVED:
                student.archived_at = timezone.now()
                fields.append("archived_at")
            AuditEvent.objects.create(actor=actor, action=f"student.status.{status.lower()}", target_type="user", target_id=student.pk, reason=(reason or "").strip())
        else:
            student.archived_at = None
            fields.append("archived_at")
            AuditEvent.objects.create(actor=actor, action="student.restore", target_type="user", target_id=student.pk, reason=(reason or "").strip())
    student.save(update_fields=fields)
    return student


def create_privacy_request(student_id, kind, actor, reason):
    """Register an EXPORT or ERASE privacy request with required reason."""
    if kind not in PrivacyRequest.Kind.values:
        raise ValidationError("Loại yêu cầu không hợp lệ.")
    clean_reason = (reason or "").strip()
    if not clean_reason:
        raise ValidationError("Cần ghi lý do cho yêu cầu dữ liệu.")
    student = User.objects.get(pk=student_id, role=User.Role.STUDENT)
    req = PrivacyRequest.objects.create(student=student, kind=kind, requested_by=actor, reason=clean_reason)
    AuditEvent.objects.create(actor=actor, action=f"privacy.{kind.lower()}.request", target_type="privacy_request", target_id=req.id, reason=clean_reason)
    return req


def export_student_data(student_id, actor):
    """Build a JSON-serializable export of one student's allowed records without secrets."""
    from apps.assignments.models import AssignmentRecipient
    from apps.classes.models import EnglishMembership, SchoolMembership
    from apps.grading.models import ErrorOccurrence, GradeRelease

    student = User.objects.select_related("student_profile").get(pk=student_id, role=User.Role.STUDENT)
    profile = getattr(student, "student_profile", None)
    school_memberships = [
        {"school": m.school_class.school.name, "school_year": m.school_class.school_year, "grade": m.school_class.grade, "class_name": m.school_class.name, "start_at": m.start_at.isoformat(), "end_at": m.end_at.isoformat() if m.end_at else None}
        for m in SchoolMembership.objects.select_related("school_class__school").filter(student=student)
    ]
    english_memberships = [
        {"class_code": m.english_class.code, "class_name": m.english_class.name, "school_year": m.english_class.school_year, "start_at": m.start_at.isoformat(), "end_at": m.end_at.isoformat() if m.end_at else None}
        for m in EnglishMembership.objects.select_related("english_class").filter(student=student)
    ]
    recipients = []
    for r in AssignmentRecipient.objects.select_related("assignment").prefetch_related("attempts__responses__question", "attempts__grade_releases").filter(student=student):
        attempts = []
        for a in r.attempts.all().order_by("attempt_no"):
            releases = [{"number": rel.number, "published_at": rel.published_at.isoformat(), "total_points": str(rel.total_points), "max_points": str(rel.max_points), "snapshot": rel.snapshot} for rel in a.grade_releases.all().order_by("number")]
            responses = [{"question_id": str(resp.question_id), "position": resp.question.position, "text_answer": resp.text_answer, "audio_asset_id": str(resp.audio_asset_id) if resp.audio_asset_id else None, "selected_option_ids": [str(option.id) for option in resp.options.all()], "ordered_option_ids": resp.ordered_option_ids, "match_pairs": resp.match_pairs} for resp in a.responses.all()]
            attempts.append({"attempt_no": a.attempt_no, "status": a.status, "submitted_at": a.submitted_at.isoformat() if a.submitted_at else None, "is_late": a.is_late, "responses": responses, "releases": releases})
        recipients.append({"assignment_code": r.assignment.code, "assignment_title": r.assignment.title, "state": r.state, "attempts": attempts})
    errors = [
        {"id": str(e.id), "tag": e.tag.name, "skill": e.tag.skill, "source": e.source, "confidence": e.confidence, "note": e.note, "withdrawn_at": e.withdrawn_at.isoformat() if e.withdrawn_at else None}
        for e in ErrorOccurrence.objects.select_related("tag").filter(response__attempt__recipient__student=student)
    ]
    AuditEvent.objects.create(actor=actor, action="privacy.export", target_type="user", target_id=student.id)
    return {
        "student": {"id": str(student.id), "student_ref": profile.student_ref if profile else "", "display_name": student.display_name, "status": student.status},
        "school_memberships": school_memberships,
        "english_memberships": english_memberships,
        "assignments": recipients,
        "errors": errors,
    }


@transaction.atomic
def execute_privacy_request(request_id, actor):
    """Approve and execute an EXPORT or ERASE privacy request idempotently."""
    from apps.assignments.models import PracticeShot, Response, ResponseOption
    from apps.content.models import Asset
    from apps.grading.models import CriterionScore, ErrorOccurrence, ErrorReview, Grade, GradeHistory, GradeRelease
    from apps.reporting.models import RankingMember, RankingPeriod

    req = PrivacyRequest.objects.select_for_update().get(pk=request_id)
    if req.status == PrivacyRequest.Status.COMPLETED:
        return req
    now = timezone.now()
    req.approved_at = req.approved_at or now
    req.status = PrivacyRequest.Status.APPROVED
    if req.kind == PrivacyRequest.Kind.EXPORT:
        data = export_student_data(req.student_id, actor)
        req.report = {"assignments_count": len(data["assignments"]), "errors_count": len(data["errors"])}
        req.completed_at = now
        req.status = PrivacyRequest.Status.COMPLETED
        req.save(update_fields=["approved_at", "status", "report", "completed_at", "updated_at"])
        return req

    student = User.objects.select_for_update().get(pk=req.student_id)
    period_ids = list(RankingMember.objects.filter(student=student).values_list("period_id", flat=True))
    periods = list(RankingPeriod.objects.select_for_update().filter(pk__in=period_ids).order_by("pk"))
    for period in periods:
        if period.status in ("ACTIVE", "FINAL", "STALE"):
            period.status = "INVALID"
            period.invalid_reason = "Yêu cầu xóa dữ liệu học sinh"
            period.revision += 1
            period.save(update_fields=["status", "invalid_reason", "revision"])

    student.access_codes.filter(revoked_at__isnull=True).update(revoked_at=now)
    student.display_name = "Đã xóa"
    student.status = User.Status.ARCHIVED
    student.archived_at = student.archived_at or now
    student.auth_epoch += 1
    student.save(update_fields=["display_name", "status", "archived_at", "auth_epoch", "updated_at"])
    StudentProfile.objects.filter(user=student).update(student_ref=f"ERASED-{str(student.id)[:18]}", owner_note="")

    responses = Response.objects.select_for_update().filter(attempt__recipient__student=student)
    audio_ids = list(responses.exclude(audio_asset_id__isnull=True).values_list("audio_asset_id", flat=True))
    PracticeShot.objects.filter(response__in=responses).delete()
    ResponseOption.objects.filter(response__in=responses).delete()
    resp_count = responses.update(text_answer="", audio_asset=None, ordered_option_ids=[], match_pairs=[])
    if audio_ids:
        Asset.objects.filter(pk__in=audio_ids, purpose=Asset.Purpose.RESPONSE_AUDIO).exclude(
            status__in=[Asset.Status.DELETING, Asset.Status.DELETED]
        ).update(status=Asset.Status.DELETING)

    grades = Grade.objects.filter(response__attempt__recipient__student=student)
    grades.update(feedback="")
    CriterionScore.objects.filter(grade__in=grades).update(note="")
    GradeHistory.objects.filter(grade__in=grades).update(previous={}, next={}, reason="")
    ErrorOccurrence.objects.filter(response__attempt__recipient__student=student).update(note="")
    ErrorReview.objects.filter(occurrence__response__attempt__recipient__student=student).update(teacher_note="")
    releases = GradeRelease.objects.filter(attempt__recipient__student=student)
    rel_count = 0
    for rel in releases.select_for_update():
        rel.snapshot = {"schema_version": 1, "erased": True, "responses": []}
        rel.save(update_fields=["snapshot"])
        rel_count += 1
    RankingMember.objects.filter(student=student).update(cohort_snapshot={"erased": True})

    req.report = {"responses_scrubbed": resp_count, "releases_scrubbed": rel_count, "audio_marked_deleting": len(audio_ids), "rankings_invalidated": len(periods)}
    req.status = PrivacyRequest.Status.COMPLETED
    req.completed_at = now
    req.save(update_fields=["approved_at", "status", "report", "completed_at", "updated_at"])
    AuditEvent.objects.create(actor=actor, action="privacy.erase.complete", target_type="user", target_id=student.id, reason=req.reason, metadata=req.report)
    return req
