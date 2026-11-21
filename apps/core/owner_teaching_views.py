"""Owner web UI views for exams, imports (T02), assignments, and grading (T03)."""
import json
from datetime import timedelta

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import F, Q, Count, Sum, Max
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache

from apps.accounts.models import User
from apps.accounts.permissions import owner_ui_required
from apps.assignments.models import Assignment, AssignmentClass, AssignmentRecipient, Attempt
from apps.assignments.pirate_assets import missing_game_assets
from apps.assignments.owner_services import (
    add_assignment_recipients,
    assign_targets_with_schedule,
    cancel_assignment,
    create_draft_assignment,
    exempt_recipient,
    extend_assignment,
    grant_retake,
    publish_assignment,
    release_answers,
    update_draft_assignment,
)
from apps.classes.models import EnglishClass, EnglishMembership, SchoolMembership
from apps.content.editor_services import archive_exam, clone_version, create_draft_version, update_exam_title
from apps.content.models import Asset, Course, CourseExercise, Exam, ExamVersion, Question, Tag
from apps.content.services import LEVELS, RUBRICS, publish_version
from apps.reporting.models import RankingAssignment, RankingPeriod

from .owner_views import owner_context, parse_local_dt, pending_grading_condition


def _version_publish_issues(version):
    issues = []
    questions = list(version.questions.prefetch_related("options", "answer_keys", "criteria", "question_tags__tag", "passage__audio_asset").order_by("position"))
    if not questions:
        issues.append("Đề chưa có câu hỏi nào.")
    for q in questions:
        if q.skill == "LISTENING" and (not q.passage or not q.passage.audio_asset or q.passage.audio_asset.status != Asset.Status.READY):
            issues.append(f"Câu {q.position} (Listening) chưa gắn tài liệu audio READY.")
        if not any(t.tag.kind == Tag.Kind.TOPIC and t.tag.skill == q.skill and not t.tag.archived_at for t in q.question_tags.all()):
            issues.append(f"Câu {q.position} chưa có TOPIC tag đúng kỹ năng.")
        if q.type in ("SINGLE_CHOICE", "MULTIPLE_CHOICE"):
            opts = q.options.count()
            ans = q.answer_keys.count()
            if not 2 <= opts <= 6 or (ans != 1 if q.type == "SINGLE_CHOICE" else ans < 2):
                issues.append(f"Câu {q.position} thiếu lựa chọn hoặc đáp án đúng.")
        elif q.type == "MATCH_IMAGE":
            if not 2 <= q.match_images.count() <= 6 or q.match_words.count() != q.match_images.count():
                issues.append(f"Câu {q.position} cần từ 2 đến 6 cặp tranh và từ.")
        elif q.type == "STRESS_CHOICE":
            if not 2 <= q.options.count() <= 10 or q.answer_keys.count() != 1:
                issues.append(f"Câu {q.position} cần 2 đến 10 âm tiết và một trọng âm đúng.")
        elif q.type == "WORD_ORDER":
            if not 2 <= q.options.count() <= 20:
                issues.append(f"Câu {q.position} cần 2 đến 20 ô từ.")
        elif q.type == "SENTENCE_TRANSFORM":
            if q.options.count() != 1 or not q.options.first().content.strip():
                issues.append(f"Câu {q.position} cần một câu trả lời chuẩn của giáo viên.")
        elif q.criteria.count() != 4:
            issues.append(f"Câu {q.position} cần đủ 4 tiêu chí chấm.")
    return issues


@never_cache
@owner_ui_required
def exams(request):
    if request.method == "POST":
        action = request.POST.get("action")
        try:
            if action == "create_exam":
                title = (request.POST.get("title") or "").strip()
                if not 1 <= len(title) <= 200:
                    raise ValidationError("Tên đề phải từ 1..200 ký tự.")
                exam = Exam.objects.create(title=title, created_by=request.user)
                version = ExamVersion.objects.create(exam=exam, number=1)
                messages.success(request, f"Đã tạo đề {exam.title}.")
                return redirect("owner_version_editor", exam_id=exam.id, version_id=version.id)
            if action == "clone_version":
                v = clone_version(request.user, request.POST.get("version_id"))
                messages.success(request, f"Đã tạo bản sửa nháp v{v.number}.")
                return redirect("owner_version_editor", exam_id=v.exam_id, version_id=v.id)
            if action == "new_version":
                v = create_draft_version(request.user, request.POST.get("exam_id"))
                return redirect("owner_version_editor", exam_id=v.exam_id, version_id=v.id)
            if action == "archive_exam":
                archive_exam(request.user, request.POST.get("exam_id"))
                messages.success(request, "Đã lưu trữ đề.")
                return redirect("owner_exams")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))

    q = request.GET.get("q", "").strip()
    exam_qs = Exam.objects.filter(created_by=request.user, archived_at__isnull=True).prefetch_related("versions__questions").order_by("-created_at")
    if q:
        exam_qs = exam_qs.filter(title__icontains=q)
    rows = []
    for exam in exam_qs[:100]:
        versions = []
        for v in exam.versions.order_by("-number"):
            qs = list(v.questions.all())
            skills = sorted({item.skill for item in qs})
            versions.append({"version": v, "question_count": len(qs), "skills": skills})
        rows.append({"exam": exam, "versions": versions})
    return render(request, "owner/exams.html", owner_context("exams", q=q, exam_rows=rows))


@never_cache
@owner_ui_required
def exam_import(request):
    existing_exams = Exam.objects.filter(created_by=request.user, archived_at__isnull=True).order_by("title")
    return render(request, "owner/exam_import.html", owner_context("exams", existing_exams=existing_exams))


@never_cache
@owner_ui_required
def version_editor(request, exam_id, version_id):
    version = get_object_or_404(ExamVersion.objects.select_related("exam"), pk=version_id, exam_id=exam_id, exam__created_by=request.user)
    if request.method == "POST":
        action = request.POST.get("action")
        try:
            if action == "rename_exam":
                update_exam_title(request.user, version.exam_id, request.POST.get("title"))
                messages.success(request, "Đã đổi tên đề.")
            elif action == "publish_version":
                publish_version(version.id, int(request.POST.get("expected_revision", version.revision)))
                messages.success(request, f"Đã phát hành phiên bản v{version.number}.")
            elif action == "clone_version":
                new_v = clone_version(request.user, version.id)
                messages.success(request, f"Đã tạo bản sửa nháp v{new_v.number}.")
                return redirect("owner_version_editor", exam_id=exam_id, version_id=new_v.id)
        except (ValidationError, ValueError) as exc:
            msg = "; ".join(exc.messages) if isinstance(exc, ValidationError) else "Dữ liệu không hợp lệ."
            messages.error(request, msg)
        return redirect("owner_version_editor", exam_id=exam_id, version_id=version_id)

    questions = list(version.questions.prefetch_related("options", "answer_keys", "criteria", "question_tags__tag", "passage").order_by("position"))
    total_points = sum((q.max_points for q in questions), 0)
    skills_present = sorted({q.skill for q in questions})
    passages = list(version.passages.select_related("audio_asset").order_by("ref"))
    assets = list(Asset.objects.filter(uploaded_by=request.user, purpose=Asset.Purpose.PROMPT_AUDIO, status=Asset.Status.READY).order_by("-created_at")[:200])
    topic_tags = list(Tag.objects.filter(kind=Tag.Kind.TOPIC, archived_at__isnull=True).order_by("skill", "name"))
    error_tags = list(Tag.objects.filter(kind=Tag.Kind.ERROR, archived_at__isnull=True).order_by("skill", "name"))
    course_id = request.GET.get("course_id")
    linked_course = Course.objects.filter(pk=course_id, created_by=request.user).first() if course_id else None
    if not linked_course:
        ce = CourseExercise.objects.select_related("course").filter(assignment__version=version, course__created_by=request.user).first()
        linked_course = ce.course if ce else None

    editor_payload = {
        "version_id": str(version.id),
        "status": version.status,
        "revision": version.revision,
        "passages": [
            {
                "id": str(p.id),
                "ref": p.ref,
                "text_body": p.text_body,
                "audio_asset_id": str(p.audio_asset_id) if p.audio_asset_id else "",
                "audio_asset_name": p.audio_asset.original_name if p.audio_asset else "",
                "transcript": p.transcript,
            }
            for p in passages
        ],
        "audio_assets": [
            {
                "id": str(a.id),
                "name": a.original_name,
                "mime": a.detected_mime,
            }
            for a in assets
        ],
        "questions": [
            {
                "id": str(q.id),
                "position": q.position,
                "type": q.type,
                "pirate_game": q.pirate_game,
                "skill": q.skill,
                "difficulty": q.difficulty,
                "prompt": q.prompt,
                "max_points": str(q.max_points),
                "passage_id": str(q.passage_id) if q.passage_id else "",
                "explanation": q.explanation,
                "options": [{"key": o.key, "content": o.content, "is_correct": o.id in {ak.option_id for ak in q.answer_keys.all()}} for o in q.options.all()],
                "match_pairs": [{"image_asset_id": str(image.image_asset_id), "word": image.answer_key.word.text} for image in q.match_images.select_related("answer_key__word").all()] if q.type == "MATCH_IMAGE" else [],
                "criteria": [{"key": c.key, "label": c.label, "level_descriptions": c.level_descriptions} for c in q.criteria.all()],
                "topic_tags": [qt.tag.name for qt in q.question_tags.all() if qt.tag.kind == Tag.Kind.TOPIC],
                "error_tags": [qt.tag.name for qt in q.question_tags.all() if qt.tag.kind == Tag.Kind.ERROR],
            }
            for q in questions
        ],
        "default_rubrics": RUBRICS,
        "default_levels": LEVELS,
    }
    return render(
        request,
        "owner/version_editor.html",
        owner_context(
            "exams",
            exam=version.exam,
            version=version,
            linked_course=linked_course,
            questions=questions,
            total_points=total_points,
            skills_present=skills_present,
            passages=passages,
            assets=assets,
            topic_tags=topic_tags,
            error_tags=error_tags,
            publish_issues=_version_publish_issues(version),
            editor_json=json.dumps(editor_payload, ensure_ascii=False),
        ),
    )


@never_cache
@owner_ui_required
def version_preview(request, exam_id, version_id):
    version = get_object_or_404(ExamVersion.objects.select_related("exam"), pk=version_id, exam_id=exam_id, exam__created_by=request.user)
    questions = version.questions.select_related("passage__audio_asset").prefetch_related("options").order_by("position")
    return render(request, "owner/version_preview.html", owner_context("exams", exam=version.exam, version=version, questions=questions))


@never_cache
@owner_ui_required
def assignments(request):
    status_filter = request.GET.get("status", "")
    overdue = request.GET.get("overdue") == "1"
    now = timezone.now()
    qs = Assignment.objects.filter(version__exam__created_by=request.user).select_related("version__exam").order_by("-created_at")
    if status_filter in ("DRAFT", "PUBLISHED", "CANCELLED"):
        qs = qs.filter(status=status_filter)
    if overdue:
        overdue_ids = AssignmentRecipient.objects.filter(
            state="ASSIGNED", assignment__status="PUBLISHED", assignment__due_at__lt=now
        ).filter(Q(current_attempt__isnull=True) | Q(current_attempt__status="IN_PROGRESS")).values("assignment_id")
        qs = qs.filter(pk__in=overdue_ids)
    rows = []
    for a in qs[:100]:
        rows.append({
            "assignment": a,
            "recipient_count": a.recipients.count(),
            "submitted_count": a.recipients.filter(current_attempt__status__in=("SUBMITTED", "GRADED")).count(),
        })
    return render(request, "owner/assignments.html", owner_context("assignments", rows=rows, status_filter=status_filter, overdue=overdue))


@never_cache
@owner_ui_required
def assignment_new(request):
    if request.method == "POST":
        try:
            opens_at = parse_local_dt(request.POST.get("opens_at"))
            due_at = parse_local_dt(request.POST.get("due_at"))
            late_policy = request.POST.get("late_policy", "ALLOW")
            late_until = parse_local_dt(request.POST.get("late_until")) if late_policy == "ALLOW" else due_at
            a = create_draft_assignment(
                request.user,
                request.POST.get("version_id"),
                request.POST.get("title"),
                request.POST.getlist("class_ids"),
                opens_at,
                due_at,
                late_policy,
                late_until,
                mode=request.POST.get("mode", "PRACTICE"),
                game_feedback_enabled=request.POST.get("game_feedback_enabled") == "on",
            )
            messages.success(request, f"Đã tạo bài giao nháp {a.title} ({a.code}).")
            return redirect("owner_assignment_detail", assignment_id=a.id)
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))

    versions = ExamVersion.objects.select_related("exam").filter(exam__created_by=request.user, status=ExamVersion.Status.PUBLISHED).order_by("exam__title", "-number")
    classes = list(EnglishClass.objects.filter(archived_at__isnull=True).order_by("-school_year", "name"))
    school_member_ids = set(SchoolMembership.objects.filter(end_at__isnull=True).values_list("student_id", flat=True))
    class_members = {}
    for m in EnglishMembership.objects.filter(english_class__in=classes, end_at__isnull=True, student__status="ACTIVE"):
        class_members.setdefault(str(m.english_class_id), []).append({"id": str(m.student_id), "no_school": m.student_id not in school_member_ids})
    now_local = timezone.localtime(timezone.now()).replace(second=0, microsecond=0)
    return render(
        request,
        "owner/assignment_new.html",
        owner_context(
            "assignments",
            versions=versions,
            classes=classes,
            class_members_json=json.dumps(class_members),
            default_opens=now_local,
            default_due=now_local + timedelta(days=3),
            default_late=now_local + timedelta(days=10),
            missing_pirate_assets=missing_game_assets(),
        ),
    )


def build_assign_target_rows(assignment=None, course=None):
    """Build sortable class_rows and student_rows for assignment/course target modals."""
    classes = list(EnglishClass.objects.filter(archived_at__isnull=True).order_by("-school_year", "name"))
    active_memberships = list(
        EnglishMembership.objects.filter(
            english_class__in=classes,
            end_at__isnull=True,
            student__role=User.Role.STUDENT,
            student__status=User.Status.ACTIVE,
        ).select_related("english_class")
    )
    count_by_class = {}
    classes_by_student = {}
    for m in active_memberships:
        count_by_class[m.english_class_id] = count_by_class.get(m.english_class_id, 0) + 1
        classes_by_student.setdefault(m.student_id, []).append(m.english_class.name)

    ac_by_class = (
        {ac.english_class_id: ac for ac in AssignmentClass.objects.filter(assignment=assignment)}
        if assignment else {}
    )
    course_class_ids = set(course.english_classes.values_list("id", flat=True)) if course else set()

    class_rows = []
    for c in classes:
        ac = ac_by_class.get(c.id)
        eff_due = (ac.due_at or assignment.due_at) if (ac and assignment) else None
        class_rows.append({
            "classroom": c,
            "member_count": count_by_class.get(c.id, 0),
            "is_assigned": ac is not None,
            "is_unlocked": c.id in course_class_ids,
            "due_at": eff_due,
            "due_ts": int(eff_due.timestamp()) if eff_due else 0,
            "max_attempts": ac.max_attempts if ac else None,
        })

    students = list(User.objects.filter(role=User.Role.STUDENT, status="ACTIVE").select_related("student_profile").order_by("display_name")[:500])
    rec_by_student = (
        {r.student_id: r for r in assignment.recipients.select_related("current_attempt").all()}
        if assignment else {}
    )
    student_rows = []
    for s in students:
        r = rec_by_student.get(s.id)
        try:
            ref = s.student_profile.student_ref
        except Exception:
            ref = ""
        eff_due = (r.due_at_override or assignment.due_at) if (r and assignment) else None
        attempts_used = r.current_attempt.attempt_no if (r and r.current_attempt_id) else 0
        student_rows.append({
            "student": s,
            "student_ref": ref,
            "class_names": ", ".join(sorted(classes_by_student.get(s.id, []))),
            "recipient": r,
            "is_assigned": r is not None,
            "due_at": eff_due,
            "due_ts": int(eff_due.timestamp()) if eff_due else 0,
            "attempts_used": attempts_used,
            "max_attempts": r.max_attempts if r else None,
        })

    now_local = timezone.localtime(timezone.now()).replace(second=0, microsecond=0)
    return {
        "class_rows": class_rows,
        "student_rows": student_rows,
        "default_due": now_local + timedelta(days=7),
    }


@never_cache
@owner_ui_required
def assignment_detail(request, assignment_id):
    assignment = get_object_or_404(Assignment.objects.select_related("version__exam"), pk=assignment_id, version__exam__created_by=request.user)
    if request.method == "POST":
        action = request.POST.get("action")
        try:
            if action == "assign_targets":
                due_at = parse_local_dt(request.POST.get("due_at"))
                max_attempts = request.POST.get("max_attempts", "1")
                mode = request.POST.get("mode") or None
                assign_targets_with_schedule(
                    request.user,
                    [assignment.id],
                    request.POST.getlist("class_ids"),
                    request.POST.getlist("student_ids"),
                    due_at,
                    max_attempts=max_attempts,
                    mode=mode,
                )
                messages.success(request, "Đã giao bài theo thời hạn và số lần làm đã thiết lập.")
            elif action == "publish":
                publish_assignment(request.user, assignment.id, int(request.POST.get("expected_revision", assignment.revision)))
                messages.success(request, "Đã phát hành bài giao và chốt danh sách học sinh.")
            elif action == "update_mode":
                update_draft_assignment(request.user, assignment.id, int(request.POST.get("expected_revision", assignment.revision)), mode=request.POST.get("mode"), game_feedback_enabled=request.POST.get("game_feedback_enabled") == "on")
                messages.success(request, "Đã cập nhật chế độ bài giao.")
            elif action == "extend":
                extend_assignment(
                    request.user,
                    assignment.id,
                    int(request.POST.get("expected_revision", assignment.revision)),
                    parse_local_dt(request.POST.get("due_at")),
                    parse_local_dt(request.POST.get("late_until")),
                    request.POST.get("reason", ""),
                )
                messages.success(request, "Đã gia hạn bài giao.")
            elif action == "cancel":
                cancel_assignment(request.user, assignment.id, int(request.POST.get("expected_revision", assignment.revision)), request.POST.get("reason", ""))
                messages.success(request, "Đã hủy bài giao.")
            elif action == "add_recipients":
                added = add_assignment_recipients(request.user, assignment.id, request.POST.getlist("student_ids"), request.POST.get("reason", ""))
                messages.success(request, f"Đã thêm {len(added)} học sinh vào bài giao.")
            elif action == "exempt":
                exempt_recipient(request.user, request.POST.get("recipient_id"), request.POST.get("reason", ""))
                messages.success(request, "Đã miễn bài cho học sinh.")
            elif action == "retake":
                grant_retake(request.user, request.POST.get("recipient_id"), request.POST.get("reason", ""))
                messages.success(request, "Đã cấp lượt làm lại.")
            elif action == "release_answers":
                release_answers(request.user, assignment.id, int(request.POST.get("expected_revision", assignment.revision)))
                messages.success(request, "Đã công bố đáp án chuẩn và giải thích.")
        except (ValidationError, ValueError) as exc:
            msg = "; ".join(exc.messages) if isinstance(exc, ValidationError) else "Dữ liệu không hợp lệ."
            messages.error(request, msg)
        return redirect("owner_assignment_detail", assignment_id=assignment.id)

    recipients = list(assignment.recipients.select_related("student__student_profile", "current_attempt").order_by("student__display_name"))
    ranking_warnings = list(RankingPeriod.objects.filter(pk__in=RankingAssignment.objects.filter(assignment=assignment).values("period_id"), status__in=("ACTIVE", "FINAL", "STALE")))
    now = timezone.now()
    can_release_answers = (
        assignment.status == "PUBLISHED"
        and not assignment.answers_released_at
        and now >= assignment.late_until
        and not any(r.state == "ASSIGNED" and r.current_attempt and r.current_attempt.status == "SUBMITTED" for r in recipients)
    )
    target_data = build_assign_target_rows(assignment=assignment)
    return render(
        request,
        "owner/assignment_detail.html",
        owner_context(
            "assignments",
            assignment=assignment,
            question_count=assignment.version.questions.count(),
            course_exercises=assignment.course_exercises.select_related('course').filter(course__created_by=request.user),
            recipients=recipients,
            class_rows=target_data["class_rows"],
            student_rows=target_data["student_rows"],
            default_due=target_data["default_due"],
            ranking_warnings=ranking_warnings,
            can_release_answers=can_release_answers,
            now=now,
        ),
    )


@never_cache
@owner_ui_required
def grading_queue(request):
    # Ensure any attempt without manual grading questions (all auto-gradable) is marked as GRADED
    Attempt.objects.filter(
        status="SUBMITTED",
        recipient__state="ASSIGNED",
        recipient__current_attempt_id=F("id"),
        recipient__assignment__version__exam__created_by=request.user,
    ).exclude(
        recipient__assignment__version__questions__type__in=['TEXT', 'AUDIO']
    ).update(status="GRADED")

    status_filter = request.GET.get("status", "SUBMITTED")
    if status_filter not in ("SUBMITTED", "GRADED", "ALL"):
        status_filter = "SUBMITTED"
    base = Attempt.objects.filter(
        status__in=["SUBMITTED", "GRADED"],
        recipient__state="ASSIGNED", recipient__current_attempt_id=F("id"),
        recipient__assignment__version__exam__created_by=request.user,
    ).annotate(
        visibility_count=Count('visibility_events'),
        visibility_total_ms=Sum('visibility_events__duration_ms'),
        visibility_max_ms=Max('visibility_events__duration_ms'),
    )
    if status_filter == "SUBMITTED":
        rows = base.filter(pending_grading_condition())
    elif status_filter == "GRADED":
        rows = base.filter(status="GRADED")
    else:
        rows = base
    rows = rows.select_related("recipient__student", "recipient__assignment__version").prefetch_related("grade_releases").order_by("submitted_at")[:100]
    items = []
    for attempt in rows:
        has_manual = attempt.recipient.assignment.version.questions.filter(type__in=['TEXT', 'AUDIO']).exists()
        items.append({
            "attempt": attempt,
            "released": attempt.grade_releases.exists(),
            "has_manual": has_manual,
            "needs_visibility_review": (attempt.visibility_max_ms or 0) > 5000 and not attempt.visibility_reviewed_at,
        })
    pending_count = base.filter(pending_grading_condition()).count()
    graded_count = base.filter(status="GRADED").count()

    return render(
        request,
        "owner/grading_queue.html",
        owner_context(
            "grading",
            items=items,
            status_filter=status_filter,
            pending_count=pending_count,
            graded_count=graded_count,
        ),
    )


@never_cache
@owner_ui_required
def grading_detail(request, attempt_id):
    attempt = get_object_or_404(
        Attempt.objects.select_related("recipient__student", "recipient__assignment__version__exam"),
        pk=attempt_id,
        recipient__assignment__version__exam__created_by=request.user,
    )
    from apps.grading.services import set_visibility_deduction, visibility_deduction
    from apps.grading.models import Grade
    from decimal import Decimal
    from django.db.models import Sum
    if request.method == "POST" and request.POST.get("action") == "visibility_deduction":
        try:
            set_visibility_deduction(attempt.id, request.user, request.POST.get("deduction", ""))
            messages.success(request, "Đã lưu điểm trừ và đánh dấu đã xem xét.")
            return redirect("owner_grading_detail", attempt_id=attempt.id)
        except ValidationError as exc:
            messages.error(request, '; '.join(exc.messages))
    if request.method == "POST" and request.POST.get("action") == "review_visibility":
        attempt.visibility_reviewed_at = timezone.now()
        attempt.save(update_fields=["visibility_reviewed_at"])
        return redirect("owner_grading_detail", attempt_id=attempt.id)
    visibility_events = list(attempt.visibility_events.order_by("recorded_at"))
    visibility_total_seconds = round(sum(event.duration_ms for event in visibility_events) / 1000, 1)
    visibility_flagged = any(event.duration_ms > 5000 for event in visibility_events)
    return render(
        request,
        "owner/grading_detail.html",
        owner_context(
            "grading",
            attempt=attempt,
            student=attempt.recipient.student,
            assignment=attempt.recipient.assignment,
            is_current=attempt.recipient.current_attempt_id == attempt.id,
            visibility_events=visibility_events,
            visibility_total_seconds=visibility_total_seconds,
            visibility_flagged=visibility_flagged,
            visibility_deduction=visibility_deduction(attempt),
            total_grade=Grade.objects.filter(response__attempt=attempt).aggregate(total=Sum('points'))['total'] or Decimal('0'),
        ),
    )
