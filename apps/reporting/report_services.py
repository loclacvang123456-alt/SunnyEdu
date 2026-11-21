"""Owner progress reporting, CSV export with formula safety, and ranking period CRUD/validation."""
import csv
import io
import secrets
from collections import Counter
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import OuterRef, Subquery
from django.utils import timezone

from apps.accounts.models import AuditEvent
from apps.accounts.services import ALPHABET
from apps.assignments.models import Assignment, AssignmentRecipient, Attempt, RecipientEnglishClass
from apps.classes.models import EnglishClass, School, SchoolClass
from apps.classes.services import validate_school_year
from apps.grading.models import GradeRelease

from .calculations import Evidence, SKILLS, skill_summary, skill_trend
from .models import RankingAssignment, RankingMember, RankingPeriod


def parse_date_window(from_str, to_str):
    """Parse YYYY-MM-DD bounds (default 28 days ending today local time, max 366 days)."""
    local_today = timezone.localdate()
    try:
        to_day = date.fromisoformat(to_str) if to_str else local_today
        from_day = date.fromisoformat(from_str) if from_str else (to_day - timedelta(days=27))
    except ValueError as exc:
        raise ValidationError("Ngày lọc phải theo định dạng YYYY-MM-DD.") from exc
    if from_day > to_day:
        raise ValidationError("Ngày bắt đầu không được sau ngày kết thúc.")
    if (to_day - from_day).days + 1 > 366:
        raise ValidationError("Khoảng thời gian báo cáo tối đa 366 ngày.")
    return from_day, to_day


def _day_range_utc(from_day, to_day):
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(from_day, time.min), tz)
    end = timezone.make_aware(datetime.combine(to_day + timedelta(days=1), time.min), tz)
    return start, end


def _latest_releases_for_recipients(recipients_qs):
    latest_sub = GradeRelease.objects.filter(attempt_id=OuterRef("current_attempt_id")).order_by("-number").values("id")[:1]
    rel_ids = list(
        recipients_qs.exclude(current_attempt_id__isnull=True)
        .exclude(current_attempt__status="VOID")
        .annotate(latest_release_id=Subquery(latest_sub))
        .exclude(latest_release_id__isnull=True)
        .values_list("latest_release_id", flat=True)
    )
    return list(GradeRelease.objects.select_related("attempt__recipient__student").filter(pk__in=rel_ids))


def _evidence_from_release(release):
    rows = []
    for item in (release.snapshot or {}).get("responses", []):
        topics = frozenset(t.get("name", "") for t in item.get("topics", []) if t.get("name"))
        rows.append(Evidence(
            attempt_id=str(release.attempt_id),
            skill=item["skill"],
            points=Decimal(str(item["points"])),
            maximum=Decimal(str(item["max_points"])),
            difficulty=item["difficulty"],
            topics=topics,
        ))
    return rows


def _filter_recipients(school_id=None, grade=None, school_class_id=None, english_class_id=None, student=None):
    if grade and not school_id:
        raise ValidationError("Cần chọn trường khi lọc theo khối lớp.")
    qs = AssignmentRecipient.objects.filter(state="ASSIGNED").exclude(assignment__status="CANCELLED").select_related("student__student_profile", "assignment", "current_attempt")
    if student is not None:
        qs = qs.filter(student=student)
    if school_id:
        qs = qs.filter(school_id=school_id)
    if grade:
        qs = qs.filter(grade=int(grade))
    if school_class_id:
        qs = qs.filter(school_class_id=school_class_id)
    if english_class_id:
        rec_ids = RecipientEnglishClass.objects.filter(english_class_id=english_class_id).values("recipient_id")
        qs = qs.filter(pk__in=rec_ids)
    return qs


def _serialize_summary(summary):
    return {
        "percent": str(summary["percent"]) if summary["percent"] is not None else None,
        "label": summary["label"],
        "questions": summary["questions"],
        "attempts": summary["attempts"],
    }


def owner_progress_report(actor, from_str=None, to_str=None, school_id=None, grade=None, school_class_id=None, english_class_id=None, student=None):
    """Compute skills, 28d vs previous 28d trend, pacing alerts, and top error tags."""
    from_day, to_day = parse_date_window(from_str, to_str)
    trend_cur_from = to_day - timedelta(days=27)
    trend_prev_from = trend_cur_from - timedelta(days=28)
    trend_prev_to = trend_cur_from - timedelta(days=1)

    overall_from = min(from_day, trend_prev_from)
    start_utc, end_utc = _day_range_utc(overall_from, to_day)
    sel_start, sel_end = _day_range_utc(from_day, to_day)
    tc_start, tc_end = _day_range_utc(trend_cur_from, to_day)
    tp_start, tp_end = _day_range_utc(trend_prev_from, trend_prev_to)

    recipients = _filter_recipients(school_id=school_id, grade=grade, school_class_id=school_class_id, english_class_id=english_class_id, student=student)
    releases = _latest_releases_for_recipients(recipients.filter(current_attempt__submitted_at__gte=start_utc, current_attempt__submitted_at__lt=end_utc))

    selected_ev, tc_ev, tp_ev = [], [], []
    by_student_ev = {}
    error_counts = Counter()

    for rel in releases:
        sub_at = rel.attempt.submitted_at
        if not sub_at:
            continue
        ev = _evidence_from_release(rel)
        sid = str(rel.attempt.recipient.student_id)
        if sel_start <= sub_at < sel_end:
            selected_ev.extend(ev)
            by_student_ev.setdefault(sid, []).extend(ev)
            for item in (rel.snapshot or {}).get("responses", []):
                for err in item.get("errors", []):
                    error_counts[(item.get("skill", ""), err.get("tag_name", ""))] += 1
        if tc_start <= sub_at < tc_end:
            tc_ev.extend(ev)
        elif tp_start <= sub_at < tp_end:
            tp_ev.extend(ev)

    skills = {}
    for skill in sorted(SKILLS):
        s_sum = skill_summary(selected_ev, skill)
        t_res = skill_trend(tc_ev, tp_ev, skill)
        skills[skill] = {
            **_serialize_summary(s_sum),
            "trend": t_res["trend"],
            "trend_current": _serialize_summary(t_res["current"]),
            "trend_previous": _serialize_summary(t_res["previous"]),
        }

    # Pacing & student breakdown (always checks 28d overdue ending at to_day)
    now = timezone.now()
    pacing_cutoff_end = min(now, tc_end)
    all_recipients = list(recipients.filter(assignment__status="PUBLISHED"))
    student_stats = {}
    for r in all_recipients:
        sid = str(r.student_id)
        if sid not in student_stats:
            profile = getattr(r.student, "student_profile", None)
            student_stats[sid] = {
                "student_id": sid,
                "student_ref": profile.student_ref if profile else "",
                "display_name": r.student.display_name,
                "assigned": 0,
                "submitted": 0,
                "overdue_28d": 0,
            }
        st = student_stats[sid]
        st["assigned"] += 1
        att = r.current_attempt
        if att and att.status in ("SUBMITTED", "GRADED"):
            st["submitted"] += 1
        elif tc_start <= r.assignment.due_at < pacing_cutoff_end:
            st["overdue_28d"] += 1

    student_rows = []
    for sid, st in sorted(student_stats.items(), key=lambda kv: kv[1]["display_name"]):
        evs = by_student_ev.get(sid, [])
        row_skills = {sk: _serialize_summary(skill_summary(evs, sk))["percent"] for sk in sorted(SKILLS)}
        student_rows.append({**st, "needs_pacing_support": st["overdue_28d"] >= 2, "skills": row_skills})

    top_errors = [
        {"skill": sk, "tag_name": name, "count": count}
        for (sk, name), count in error_counts.most_common(15)
    ]

    return {
        "from": from_day.isoformat(),
        "to": to_day.isoformat(),
        "trend_current_from": trend_cur_from.isoformat(),
        "trend_current_to": to_day.isoformat(),
        "trend_previous_from": trend_prev_from.isoformat(),
        "trend_previous_to": trend_prev_to.isoformat(),
        "skills": skills,
        "students": student_rows,
        "top_errors": top_errors,
    }


def student_progress_summary(student, from_str=None, to_str=None):
    return owner_progress_report(student, from_str=from_str, to_str=to_str, student=student)


def _safe_csv_cell(value):
    text = "" if value is None else str(value)
    if text and text[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text
    return text


def export_progress_csv(actor, from_str=None, to_str=None, school_id=None, grade=None, school_class_id=None, english_class_id=None):
    """Export filtered progress table to UTF-8 BOM CSV with formula-injection protection (max 1,000 students)."""
    report = owner_progress_report(actor, from_str=from_str, to_str=to_str, school_id=school_id, grade=grade, school_class_id=school_class_id, english_class_id=english_class_id)
    if len(report["students"]) > 1000:
        raise ValidationError("Tối đa xuất 1.000 học sinh mỗi lần, hãy thu hẹp bộ lọc.")
    buf = io.StringIO()
    buf.write("\ufeff")
    writer = csv.writer(buf)
    writer.writerow(["student_ref", "display_name", "assigned", "submitted", "overdue_28d", "needs_pacing_support", "reading_pct", "listening_pct", "writing_pct", "speaking_pct"])
    for row in report["students"]:
        writer.writerow([
            _safe_csv_cell(row["student_ref"]),
            _safe_csv_cell(row["display_name"]),
            row["assigned"],
            row["submitted"],
            row["overdue_28d"],
            "YES" if row["needs_pacing_support"] else "NO",
            row["skills"]["READING"] or "",
            row["skills"]["LISTENING"] or "",
            row["skills"]["WRITING"] or "",
            row["skills"]["SPEAKING"] or "",
        ])
    AuditEvent.objects.create(actor=actor, action="reports.export_csv", target_type="report", metadata={"students": len(report["students"])})
    return buf.getvalue()


def _validate_scope_target(scope, scope_target, school_year):
    if not isinstance(scope_target, dict):
        raise ValidationError("scope_target không hợp lệ.")
    if scope == "ENGLISH_CLASS":
        ec = EnglishClass.objects.filter(pk=scope_target.get("class_id"), school_year=school_year, archived_at__isnull=True).first()
        if not ec:
            raise ValidationError("Lớp tiếng Anh không tồn tại hoặc khác năm học.")
        return {"class_id": str(ec.id)}
    if scope == "SCHOOL_CLASS":
        sc = SchoolClass.objects.filter(pk=scope_target.get("school_class_id"), school_year=school_year, archived_at__isnull=True).first()
        if not sc:
            raise ValidationError("Lớp trường không tồn tại hoặc khác năm học.")
        return {"school_class_id": str(sc.id)}
    if scope == "SCHOOL_GRADE":
        school = School.objects.filter(pk=scope_target.get("school_id"), archived_at__isnull=True).first()
        try:
            grade = int(scope_target.get("grade"))
        except (TypeError, ValueError) as exc:
            raise ValidationError("Khối lớp không hợp lệ.") from exc
        if not school or not 1 <= grade <= 12:
            raise ValidationError("Trường hoặc khối không hợp lệ.")
        return {"school_id": str(school.id), "grade": grade}
    if scope == "SCHOOL":
        school = School.objects.filter(pk=scope_target.get("school_id"), archived_at__isnull=True).first()
        if not school:
            raise ValidationError("Trường không tồn tại.")
        return {"school_id": str(school.id)}
    raise ValidationError("Phạm vi xếp hạng không hợp lệ.")


def _unique_aliases(count):
    aliases = []
    seen = set()
    while len(aliases) < count:
        alias = "HS-" + "".join(secrets.choice(ALPHABET) for _ in range(5))
        if alias not in seen:
            seen.add(alias)
            aliases.append(alias)
    return aliases


@transaction.atomic
def create_ranking_period(actor, name, school_year, start_at, end_at, scope, scope_target, student_ids, assignment_ids, show_peers=False):
    clean_name = (name or "").strip()
    if not 1 <= len(clean_name) <= 160:
        raise ValidationError("Tên kỳ xếp hạng phải từ 1..160 ký tự.")
    year = validate_school_year(school_year)
    if end_at <= start_at:
        raise ValidationError("Ngày kết thúc phải sau ngày bắt đầu.")
    if show_peers and scope != "ENGLISH_CLASS":
        raise ValidationError("Chỉ bật danh sách bí danh trong phạm vi lớp tiếng Anh.")
    clean_target = _validate_scope_target(scope, scope_target, year)
    User = get_user_model()
    students = list(User.objects.filter(pk__in=student_ids or [], role="STUDENT", status="ACTIVE").order_by("id"))
    assignments = list(Assignment.objects.filter(pk__in=assignment_ids or [], status="PUBLISHED", version__exam__created_by=actor).order_by("id"))
    if not students or not assignments:
        raise ValidationError("Cần ít nhất một học sinh và một bài giao đã phát hành.")
    if any(a.game_feedback_enabled for a in assignments):
        raise ValidationError("Bài luyện có phản hồi game tức thời không thể dùng để xếp hạng.")

    period = RankingPeriod.objects.create(
        name=clean_name,
        school_year=year,
        start_at=start_at,
        end_at=end_at,
        scope=scope,
        scope_target=clean_target,
        show_peers=bool(show_peers),
    )
    RankingAssignment.objects.bulk_create([RankingAssignment(period=period, assignment=a) for a in assignments])
    aliases = _unique_aliases(len(students))
    RankingMember.objects.bulk_create([
        RankingMember(period=period, student=s, alias=alias, cohort_snapshot={"display_name": s.display_name, "scope": scope, "school_year": year})
        for s, alias in zip(students, aliases)
    ])
    AuditEvent.objects.create(actor=actor, action="ranking.create", target_type="ranking_period", target_id=period.id)
    return period


def check_ranking_eligibility(period):
    """Return specific eligibility errors without silently dropping any cohort member."""
    from .services import _scope_matches
    errors = []
    members = list(period.members.select_related("student").order_by("student__display_name"))
    assignments = [link.assignment for link in period.assignment_links.select_related("assignment").all()]
    now = timezone.now()
    for a in assignments:
        if a.status != "PUBLISHED":
            errors.append(f"Bài {a.title} không còn PUBLISHED.")
        if a.opens_at < period.start_at or a.late_until > period.end_at:
            errors.append(f"Bài {a.title} có khoảng mở/đóng nằm ngoài thời gian kỳ xếp hạng.")
        if a.opens_at <= now:
            errors.append(f"Bài {a.title} đã mở trước khi kích hoạt kỳ.")
    rec_map = {
        (r.student_id, r.assignment_id): r
        for r in AssignmentRecipient.objects.filter(assignment__in=assignments, student_id__in=[m.student_id for m in members])
    }
    for m in members:
        for a in assignments:
            rec = rec_map.get((m.student_id, a.id))
            if not rec or rec.state != "ASSIGNED":
                errors.append(f"{m.student.display_name} chưa được giao (hoặc đã miễn) bài {a.title}.")
            elif not _scope_matches(period, rec):
                errors.append(f"{m.student.display_name} không khớp nhãn trường/lớp snapshot của kỳ ở bài {a.title}.")
    return {"eligible": len(errors) == 0, "errors": errors}
