"""Owner assignment lifecycle services: create, publish, extend, cancel, recipients, retake, and answer release."""
import secrets
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import AuditEvent
from apps.accounts.services import ALPHABET
from apps.classes.models import EnglishClass, EnglishMembership, SchoolMembership
from apps.content.models import ExamVersion
from apps.reporting.models import RankingAssignment, RankingMember, RankingPeriod

from .models import Assignment, AssignmentClass, AssignmentRecipient, Attempt, RecipientEnglishClass, Response
from .pirate_assets import missing_game_assets


def _validate_game_assets(enabled):
    if enabled and missing_game_assets():
        raise ValidationError("Bộ ảnh game chưa đầy đủ. Hãy thêm ảnh còn thiếu trước khi bật game.")


def _generate_assignment_code():
    for _ in range(20):
        code = "HW-" + "".join(secrets.choice(ALPHABET) for _ in range(6))
        if not Assignment.objects.filter(code=code).exists():
            return code
    raise ValidationError("Không tạo được mã bài duy nhất.")


def _snapshot_membership(student, target_classes=None):
    """Capture current SchoolMembership and EnglishClass snapshots for a recipient."""
    school_m = SchoolMembership.objects.select_related("school_class__school").filter(student=student, end_at__isnull=True).first()
    school_data = {
        "school_class": school_m.school_class if school_m else None,
        "school": school_m.school_class.school if school_m else None,
        "grade": school_m.school_class.grade if school_m else None,
        "school_year": school_m.school_class.school_year if school_m else "",
        "school_name_snapshot": school_m.school_class.school.name if school_m else "",
        "school_class_name_snapshot": school_m.school_class.name if school_m else "",
    }
    qs = EnglishMembership.objects.select_related("english_class").filter(student=student, end_at__isnull=True)
    if target_classes is not None:
        qs = qs.filter(english_class_id__in=target_classes)
    english_classes = [m.english_class for m in qs]
    return school_data, english_classes


def _validate_schedule(opens_at, due_at, late_policy, late_until=None):
    if late_policy not in ("ALLOW", "BLOCK"):
        raise ValidationError("Chính sách nộp muộn phải là ALLOW hoặc BLOCK.")
    if late_policy == "BLOCK":
        effective_late = due_at
    else:
        effective_late = late_until
    if not (opens_at < due_at):
        raise ValidationError("Thời điểm mở bài phải trước hạn nộp.")
    if effective_late is not None and (effective_late < due_at or (late_policy == "ALLOW" and effective_late <= due_at)):
        raise ValidationError("Hạn đóng bài không hợp lệ so với hạn nộp.")
    return effective_late


@transaction.atomic
def create_draft_assignment(owner, version_id, title, class_ids, opens_at, due_at, late_policy="ALLOW", late_until=None, mode="PRACTICE", game_feedback_enabled=False, allow_individuals=False, instant_feedback=False):
    clean_title = (title or "").strip()
    if not 1 <= len(clean_title) <= 200:
        raise ValidationError("Tên bài giao phải từ 1..200 ký tự.")
    version = ExamVersion.objects.select_related("exam").filter(pk=version_id, exam__created_by=owner, status=ExamVersion.Status.PUBLISHED).first()
    if not version:
        raise ValidationError("Phiên bản đề phải ở trạng thái PUBLISHED.")
    classes = list(EnglishClass.objects.filter(pk__in=class_ids or [], archived_at__isnull=True))
    if not classes and not allow_individuals:
        raise ValidationError("Cần chọn ít nhất một lớp tiếng Anh đang hoạt động.")
    if mode not in ("PRACTICE", "EXAM"):
        raise ValidationError("Chế độ bài phải là luyện tập hoặc kiểm tra.")
    if type(game_feedback_enabled) is not bool or (game_feedback_enabled and mode != "PRACTICE"):
        raise ValidationError("Game phản hồi tức thời chỉ dùng được cho bài luyện tập.")
    _validate_game_assets(game_feedback_enabled)
    effective_late = _validate_schedule(opens_at, due_at, late_policy, late_until)
    assignment = Assignment.objects.create(
        version=version,
        title=clean_title,
        code=_generate_assignment_code(),
        status="DRAFT",
        opens_at=opens_at,
        due_at=due_at,
        late_until=effective_late,
        late_policy=late_policy,
        mode=mode,
        game_feedback_enabled=game_feedback_enabled,
        instant_feedback=bool(instant_feedback),
    )
    AssignmentClass.objects.bulk_create([AssignmentClass(assignment=assignment, english_class=c) for c in classes])
    from apps.content.auto_tagging import sync_version_and_exercise_auto_tags
    sync_version_and_exercise_auto_tags(version, title_context=clean_title)
    AuditEvent.objects.create(actor=owner, action="assignment.create", target_type="assignment", target_id=assignment.id)
    return assignment


@transaction.atomic
def update_draft_assignment(owner, assignment_id, expected_revision, title=None, class_ids=None, opens_at=None, due_at=None, late_policy=None, late_until=None, mode=None, game_feedback_enabled=None, instant_feedback=None):
    assignment = Assignment.objects.select_for_update().select_related("version__exam").get(pk=assignment_id, version__exam__created_by=owner)
    if assignment.status != "DRAFT":
        raise ValidationError("Chỉ sửa trực tiếp được bài giao DRAFT.")
    if assignment.revision != expected_revision:
        raise ValidationError("Assignment revision conflict.")
    if mode is not None:
        if mode not in ("PRACTICE", "EXAM"):
            raise ValidationError("Chế độ bài phải là luyện tập hoặc kiểm tra.")
        assignment.mode = mode
    if game_feedback_enabled is not None:
        if type(game_feedback_enabled) is not bool:
            raise ValidationError("Cài đặt game không hợp lệ.")
        assignment.game_feedback_enabled = game_feedback_enabled
    if instant_feedback is not None:
        assignment.instant_feedback = bool(instant_feedback)
    if assignment.game_feedback_enabled and assignment.mode != "PRACTICE":
        raise ValidationError("Game phản hồi tức thời chỉ dùng được cho bài luyện tập.")
    _validate_game_assets(assignment.game_feedback_enabled)
    if title is not None:
        clean = title.strip()
        if not 1 <= len(clean) <= 200:
            raise ValidationError("Tên bài giao phải từ 1..200 ký tự.")
        assignment.title = clean
    new_opens = opens_at or assignment.opens_at
    new_due = due_at or assignment.due_at
    new_policy = late_policy or assignment.late_policy
    new_late = _validate_schedule(new_opens, new_due, new_policy, late_until if late_until is not None else assignment.late_until)
    assignment.opens_at, assignment.due_at, assignment.late_policy, assignment.late_until = new_opens, new_due, new_policy, new_late
    if class_ids is not None:
        classes = list(EnglishClass.objects.filter(pk__in=class_ids, archived_at__isnull=True))
        if not classes:
            raise ValidationError("Cần chọn ít nhất một lớp tiếng Anh.")
        AssignmentClass.objects.filter(assignment=assignment).delete()
        AssignmentClass.objects.bulk_create([AssignmentClass(assignment=assignment, english_class=c) for c in classes])
    assignment.revision += 1
    assignment.save()
    from apps.content.auto_tagging import sync_version_and_exercise_auto_tags
    sync_version_and_exercise_auto_tags(assignment.version, title_context=assignment.title)
    return assignment


@transaction.atomic
def delete_draft_assignment(owner, assignment_id):
    assignment = Assignment.objects.select_for_update().select_related("version__exam").get(pk=assignment_id, version__exam__created_by=owner)
    if assignment.status != "DRAFT" or assignment.recipients.exists():
        raise ValidationError("Chỉ xóa được bài giao DRAFT chưa phát hành.")
    AssignmentClass.objects.filter(assignment=assignment).delete()
    assignment.delete()


@transaction.atomic
def publish_assignment(owner, assignment_id, expected_revision):
    """Freeze active students from selected English classes into deduplicated AssignmentRecipient rows."""
    assignment = Assignment.objects.select_for_update().select_related("version__exam").get(pk=assignment_id, version__exam__created_by=owner)
    if assignment.status != "DRAFT":
        raise ValidationError("Bài giao không còn ở trạng thái DRAFT.")
    if assignment.revision != expected_revision:
        raise ValidationError("Assignment revision conflict.")
    if assignment.version.status != ExamVersion.Status.PUBLISHED:
        raise ValidationError("Phiên bản đề phải PUBLISHED trước khi giao.")
    class_ids = list(AssignmentClass.objects.filter(assignment=assignment).values_list("english_class_id", flat=True))
    if not class_ids:
        raise ValidationError("Bài giao cần ít nhất một lớp nhận.")

    student_ids = list(
        EnglishMembership.objects.filter(
            english_class_id__in=class_ids,
            end_at__isnull=True,
            student__role="STUDENT",
            student__status="ACTIVE",
        ).values_list("student_id", flat=True).distinct()
    )
    if not student_ids:
        raise ValidationError("Các lớp đã chọn chưa có học sinh ACTIVE nào.")

    User = get_user_model()
    students = list(User.objects.filter(pk__in=student_ids).order_by("id"))
    for student in students:
        school_data, english_classes = _snapshot_membership(student, target_classes=class_ids)
        recipient = AssignmentRecipient.objects.create(assignment=assignment, student=student, **school_data)
        RecipientEnglishClass.objects.bulk_create([
            RecipientEnglishClass(
                recipient=recipient,
                english_class=ec,
                class_name_snapshot=ec.name,
                school_year_snapshot=ec.school_year,
            )
            for ec in english_classes
        ])

    assignment.status = "PUBLISHED"
    assignment.published_at = timezone.now()
    assignment.revision += 1
    assignment.save(update_fields=["status", "published_at", "revision", "updated_at"])
    AuditEvent.objects.create(actor=owner, action="assignment.publish", target_type="assignment", target_id=assignment.id, metadata={"recipients": len(students)})
    return assignment


def _lock_linked_periods(assignment_id, student_id=None):
    period_ids = RankingAssignment.objects.filter(assignment_id=assignment_id).values("period_id")
    qs = RankingPeriod.objects.select_for_update().filter(pk__in=period_ids)
    if student_id:
        member_ids = RankingMember.objects.filter(student_id=student_id).values("period_id")
        qs = qs.filter(pk__in=member_ids)
    return list(qs.order_by("pk"))


@transaction.atomic
def extend_assignment(owner, assignment_id, expected_revision, due_at, late_until, reason):
    periods = _lock_linked_periods(assignment_id)
    assignment = Assignment.objects.select_for_update().select_related("version__exam").get(pk=assignment_id, version__exam__created_by=owner)
    clean_reason = (reason or "").strip()
    if assignment.status != "PUBLISHED" or assignment.answers_released_at:
        raise ValidationError("Không thể gia hạn bài đã hủy hoặc đã công bố đáp án.")
    if assignment.revision != expected_revision:
        raise ValidationError("Assignment revision conflict.")
    if not clean_reason:
        raise ValidationError("Cần lý do khi gia hạn bài.")
    if due_at < assignment.due_at or (assignment.late_until is not None and late_until < assignment.late_until):
        raise ValidationError("Không được rút ngắn hạn nộp hoặc hạn đóng.")
    if late_until < due_at or (assignment.late_policy == "ALLOW" and late_until <= due_at):
        raise ValidationError("Hạn đóng phải sau hoặc bằng hạn nộp phù hợp chính sách.")
    for p in periods:
        if p.status in ("FINAL", "STALE"):
            raise ValidationError("Bài thuộc kỳ xếp hạng FINAL/STALE; cần INVALID kỳ xếp hạng trước.")
        if p.status == "ACTIVE" and late_until > p.end_at:
            raise ValidationError("Không được gia hạn quá ngày kết thúc của kỳ xếp hạng ACTIVE.")

    assignment.due_at = due_at
    assignment.late_until = late_until
    assignment.revision += 1
    assignment.save(update_fields=["due_at", "late_until", "revision", "updated_at"])
    AuditEvent.objects.create(actor=owner, action="assignment.extend", target_type="assignment", target_id=assignment.id, reason=clean_reason)
    return assignment


@transaction.atomic
def cancel_assignment(owner, assignment_id, expected_revision, reason):
    periods = _lock_linked_periods(assignment_id)
    assignment = Assignment.objects.select_for_update().select_related("version__exam").get(pk=assignment_id, version__exam__created_by=owner)
    clean_reason = (reason or "").strip()
    if assignment.status != "PUBLISHED":
        raise ValidationError("Chỉ hủy được bài đã phát hành.")
    if assignment.revision != expected_revision:
        raise ValidationError("Assignment revision conflict.")
    if not clean_reason:
        raise ValidationError("Cần lý do khi hủy bài.")
    for p in periods:
        if p.status in ("ACTIVE", "FINAL", "STALE"):
            p.status = "INVALID"
            p.invalid_reason = f"Bài {assignment.code} bị hủy: {clean_reason}"
            p.revision += 1
            p.save(update_fields=["status", "invalid_reason", "revision"])
    assignment.status = "CANCELLED"
    assignment.cancel_reason = clean_reason
    assignment.revision += 1
    assignment.save(update_fields=["status", "cancel_reason", "revision", "updated_at"])
    AuditEvent.objects.create(actor=owner, action="assignment.cancel", target_type="assignment", target_id=assignment.id, reason=clean_reason)
    return assignment


@transaction.atomic
def add_assignment_recipients(owner, assignment_id, student_ids, reason):
    assignment = Assignment.objects.select_for_update().select_related("version__exam").get(pk=assignment_id, version__exam__created_by=owner)
    clean_reason = (reason or "").strip()
    if assignment.status != "PUBLISHED" or not clean_reason:
        raise ValidationError("Bài phải đang PUBLISHED và cần lý do thêm người nhận.")
    User = get_user_model()
    students = list(User.objects.filter(pk__in=student_ids or [], role="STUDENT", status="ACTIVE").order_by("id"))
    added = []
    for student in students:
        if AssignmentRecipient.objects.filter(assignment=assignment, student=student).exists():
            continue
        school_data, english_classes = _snapshot_membership(student)
        rec = AssignmentRecipient.objects.create(assignment=assignment, student=student, **school_data)
        RecipientEnglishClass.objects.bulk_create([
            RecipientEnglishClass(recipient=rec, english_class=ec, class_name_snapshot=ec.name, school_year_snapshot=ec.school_year)
            for ec in english_classes
        ])
        added.append(rec)
    if added:
        assignment.revision += 1
        assignment.save(update_fields=["revision", "updated_at"])
        AuditEvent.objects.create(actor=owner, action="assignment.recipients.add", target_type="assignment", target_id=assignment.id, reason=clean_reason, metadata={"added": len(added)})
    return added


@transaction.atomic
def exempt_recipient(owner, recipient_id, reason):
    target = AssignmentRecipient.objects.select_related("assignment__version__exam").get(pk=recipient_id, assignment__version__exam__created_by=owner)
    periods = _lock_linked_periods(target.assignment_id, student_id=target.student_id)
    Assignment.objects.select_for_update().get(pk=target.assignment_id)
    recipient = AssignmentRecipient.objects.select_for_update().get(pk=recipient_id)
    clean_reason = (reason or "").strip()
    if target.assignment.status != "PUBLISHED" or not clean_reason:
        raise ValidationError("Chỉ miễn bài đã phát hành và cần ghi lý do.")
    if recipient.state != "EXEMPT":
        recipient.state = "EXEMPT"
        recipient.exempt_reason = clean_reason
        recipient.save(update_fields=["state", "exempt_reason"])
        for p in periods:
            if p.status in ("ACTIVE", "FINAL", "STALE"):
                p.status = "INVALID"
                p.invalid_reason = f"Miễn bài cho thành viên cohort: {clean_reason}"
                p.revision += 1
                p.save(update_fields=["status", "invalid_reason", "revision"])
        AuditEvent.objects.create(actor=owner, action="recipient.exempt", target_type="assignment_recipient", target_id=recipient.id, reason=clean_reason)
    return recipient


@transaction.atomic
def grant_retake(owner, recipient_id, reason):
    """Issue a replacement Attempt (up to 5) while preserving old history and ranking invariants."""
    target = AssignmentRecipient.objects.select_related("assignment__version__exam").get(pk=recipient_id, assignment__version__exam__created_by=owner)
    periods = _lock_linked_periods(target.assignment_id, student_id=target.student_id)
    assignment = Assignment.objects.select_for_update().get(pk=target.assignment_id)
    recipient = AssignmentRecipient.objects.select_for_update().get(pk=recipient_id)
    clean_reason = (reason or "").strip()
    now = timezone.now()

    if assignment.status != "PUBLISHED" or assignment.answers_released_at or (assignment.late_until is not None and now >= assignment.late_until):
        raise ValidationError("Không thể cấp làm lại khi bài đã đóng hoặc đã công bố đáp án.")
    if recipient.state != "ASSIGNED" or not clean_reason:
        raise ValidationError("Người nhận không hợp lệ hoặc thiếu lý do cấp làm lại.")
    if any(p.status in ("FINAL", "STALE") for p in periods):
        raise ValidationError("Không được cấp làm lại khi kỳ xếp hạng liên quan đang FINAL/STALE.")
    if not recipient.current_attempt_id:
        raise ValidationError("Học sinh chưa có lần làm nào để cấp làm lại.")

    current = Attempt.objects.select_for_update().get(pk=recipient.current_attempt_id)
    if current.status not in ("SUBMITTED", "GRADED", "VOID"):
        raise ValidationError("Lần làm hiện tại chưa nộp nên không cần cấp làm lại.")
    if current.attempt_no >= 5:
        raise ValidationError("Đã đạt tối đa 5 lần làm cho bài này.")

    if any(p.status == "ACTIVE" for p in periods) and current.status != "VOID":
        current.status = "VOID"
        current.void_reason = clean_reason
        current.revision += 1
        current.save(update_fields=["status", "void_reason", "revision"])

    new_attempt = Attempt.objects.create(recipient=recipient, attempt_no=current.attempt_no + 1, replacement_reason=clean_reason)
    Response.objects.bulk_create([Response(attempt=new_attempt, question=q) for q in assignment.version.questions.all()])
    recipient.current_attempt = new_attempt
    recipient.save(update_fields=["current_attempt"])
    AuditEvent.objects.create(actor=owner, action="recipient.retake", target_type="attempt", target_id=new_attempt.id, reason=clean_reason)
    return new_attempt


@transaction.atomic
def release_answers(owner, assignment_id, expected_revision):
    assignment = Assignment.objects.select_for_update().select_related("version__exam").get(pk=assignment_id, version__exam__created_by=owner)
    if assignment.status != "PUBLISHED":
        raise ValidationError("Bài chưa phát hành.")
    if assignment.revision != expected_revision:
        raise ValidationError("Assignment revision conflict.")
    if assignment.late_until is None or timezone.now() < assignment.late_until:
        raise ValidationError("Chỉ công bố đáp án sau khi hết hạn đóng bài (late_until).")
    if AssignmentRecipient.objects.filter(assignment=assignment, state="ASSIGNED", current_attempt__status="SUBMITTED").exists():
        raise ValidationError("Vẫn còn bài đã nộp đang chờ chấm.")
    if not assignment.answers_released_at:
        assignment.answers_released_at = timezone.now()
        assignment.revision += 1
        assignment.save(update_fields=["answers_released_at", "revision", "updated_at"])
        AuditEvent.objects.create(actor=owner, action="assignment.release_answers", target_type="assignment", target_id=assignment.id)
    return assignment


@transaction.atomic
def assign_targets_with_schedule(owner, assignment_ids, class_ids, student_ids, due_at, max_attempts=1, mode=None):
    """Assign one or more assignments to selected classes and/or individual students with custom due_at & max_attempts."""
    from apps.content.models import CourseExercise

    clean_assignment_ids = [aid for aid in (assignment_ids or []) if aid]
    clean_class_ids = [cid for cid in (class_ids or []) if cid]
    clean_student_ids = [sid for sid in (student_ids or []) if sid]
    if not clean_assignment_ids:
        raise ValidationError("Cần chọn ít nhất một bài tập để giao.")
    if not clean_class_ids and not clean_student_ids:
        raise ValidationError("Cần chọn ít nhất một lớp học hoặc học sinh.")
    if due_at is None:
        raise ValidationError("Cần nhập thời hạn nộp bài.")
    now = timezone.now()
    if due_at <= now:
        raise ValidationError("Hạn nộp bài phải sau thời điểm hiện tại.")
    try:
        if isinstance(max_attempts, bool):
            raise ValueError
        max_attempts_int = int(max_attempts)
    except (TypeError, ValueError) as exc:
        raise ValidationError("Số lần được làm thử (try) phải là số nguyên từ 1 đến 5.") from exc
    if not 1 <= max_attempts_int <= 5:
        raise ValidationError("Số lần được làm thử (try) phải từ 1 đến 5.")
    if mode is not None and mode != "":
        if mode not in ("PRACTICE", "EXAM"):
            raise ValidationError("Chế độ làm bài phải là luyện tập hoặc kiểm tra.")

    unique_assignment_ids = list(dict.fromkeys(str(x) for x in clean_assignment_ids))
    unique_class_ids = list(dict.fromkeys(str(x) for x in clean_class_ids))
    unique_student_ids = list(dict.fromkeys(str(x) for x in clean_student_ids))

    assignments = list(
        Assignment.objects.select_for_update()
        .select_related("version__exam")
        .filter(pk__in=unique_assignment_ids, version__exam__created_by=owner)
        .exclude(status="CANCELLED")
    )
    if len(assignments) != len(unique_assignment_ids):
        raise ValidationError("Có bài tập không tồn tại hoặc đã bị hủy.")

    classes = list(EnglishClass.objects.filter(pk__in=unique_class_ids, archived_at__isnull=True)) if unique_class_ids else []
    if len(classes) != len(unique_class_ids):
        raise ValidationError("Có lớp học không tồn tại hoặc đã lưu trữ.")

    User = get_user_model()
    explicit_students = list(User.objects.filter(pk__in=unique_student_ids, role="STUDENT", status="ACTIVE")) if unique_student_ids else []
    if len(explicit_students) != len(unique_student_ids):
        raise ValidationError("Có học sinh không tồn tại hoặc đã ngừng hoạt động.")

    class_student_ids = list(
        EnglishMembership.objects.filter(
            english_class__in=classes,
            end_at__isnull=True,
            student__role="STUDENT",
            student__status="ACTIVE",
        ).values_list("student_id", flat=True).distinct()
    ) if classes else []
    all_student_ids = list(dict.fromkeys([*class_student_ids, *(s.id for s in explicit_students)]))
    all_students = list(User.objects.filter(pk__in=all_student_ids).order_by("id")) if all_student_ids else []

    student_classes = list(
        EnglishClass.objects.filter(
            archived_at__isnull=True,
            memberships__student_id__in=[s.id for s in explicit_students],
            memberships__end_at__isnull=True,
        ).distinct()
    ) if explicit_students else []
    classes_to_link = list({c.id: c for c in [*classes, *student_classes]}.values())

    for assignment in assignments:
        version = ExamVersion.objects.select_for_update().get(pk=assignment.version_id)
        if version.status == ExamVersion.Status.DRAFT:
            version.status = ExamVersion.Status.PUBLISHED
            version.published_at = version.published_at or now
            version.save(update_fields=["status", "published_at"])

        assignment.status = "PUBLISHED"
        assignment.published_at = assignment.published_at or now
        assignment.opens_at = min(assignment.opens_at, now)
        if assignment.opens_at >= due_at:
            assignment.opens_at = due_at - timedelta(minutes=1)
        assignment.due_at = due_at
        if assignment.late_policy == "BLOCK":
            assignment.late_until = due_at
        elif assignment.late_until is not None:
            assignment.late_until = max(assignment.late_until, due_at + timedelta(days=7))
        if mode in ("PRACTICE", "EXAM"):
            assignment.mode = mode
            if mode == "EXAM" and assignment.game_feedback_enabled:
                assignment.game_feedback_enabled = False
        assignment.revision += 1
        assignment.save(update_fields=["status", "published_at", "opens_at", "due_at", "late_until", "mode", "game_feedback_enabled", "revision", "updated_at"])

        if classes_to_link:
            for ce in CourseExercise.objects.filter(assignment=assignment).select_related("course"):
                ce.course.english_classes.add(*classes_to_link)

        for ec in classes:
            AssignmentClass.objects.update_or_create(
                assignment=assignment,
                english_class=ec,
                defaults={"due_at": due_at, "max_attempts": max_attempts_int, "assigned_at": now},
            )

        for student in all_students:
            school_data, english_classes = _snapshot_membership(student)
            recipient, created = AssignmentRecipient.objects.get_or_create(
                assignment=assignment,
                student=student,
                defaults={
                    **school_data,
                    "state": "ASSIGNED",
                    "due_at_override": due_at,
                    "max_attempts": max_attempts_int,
                },
            )
            if not created:
                recipient.state = "ASSIGNED"
                recipient.due_at_override = due_at
                recipient.max_attempts = max_attempts_int
                recipient.save(update_fields=["state", "due_at_override", "max_attempts"])
            for ec in english_classes:
                RecipientEnglishClass.objects.get_or_create(
                    recipient=recipient,
                    english_class=ec,
                    defaults={"class_name_snapshot": ec.name, "school_year_snapshot": ec.school_year},
                )

        AuditEvent.objects.create(
            actor=owner,
            action="assignment.assign_targets",
            target_type="assignment",
            target_id=assignment.id,
            metadata={"classes": len(classes), "students": len(all_students), "max_attempts": max_attempts_int},
        )
    return assignments
