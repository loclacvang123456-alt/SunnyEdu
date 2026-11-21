"""Owner progress reporting, CSV export with formula safety, and ranking period CRUD/validation."""
import csv
import io
import json
import re
import secrets
from collections import Counter
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, OuterRef, Q, Subquery
from django.utils import timezone

from apps.accounts.models import AuditEvent
from apps.accounts.services import ALPHABET
from apps.assignments.models import (
    Assignment,
    AssignmentRecipient,
    Attempt,
    AttemptVisibilityEvent,
    RecipientEnglishClass,
    Response,
)
from apps.classes.models import EnglishClass, EnglishMembership, School, SchoolClass, SchoolMembership
from apps.classes.services import validate_school_year
from apps.content.models import Course, CourseExercise, Question
from apps.grading.models import GradeRelease

from .calculations import Evidence, SKILLS, skill_summary, skill_trend
from .models import RankingAssignment, RankingMember, RankingPeriod

QUESTION_TYPE_TOPIC_LABELS = {
    "STRESS_CHOICE": "Trọng âm",
    "WORD_ORDER": "Sắp xếp câu",
    "MATCH_IMAGE": "Từ vựng & Nối tranh",
    "SENTENCE_TRANSFORM": "Viết lại câu",
    "SINGLE_CHOICE": "Ngữ pháp & Từ vựng",
    "MULTIPLE_CHOICE": "Ngữ pháp & Từ vựng",
    "TEXT": "Viết tự luận",
    "AUDIO": "Phát âm & Nói",
}
QUESTION_FORMAT_LABELS = {
    "SINGLE_CHOICE": "Trắc nghiệm một đáp án",
    "MULTIPLE_CHOICE": "Trắc nghiệm nhiều đáp án",
    "WORD_ORDER": "Sắp xếp từ thành câu",
    "STRESS_CHOICE": "Chọn trọng âm",
    "MATCH_IMAGE": "Nối tranh với từ vựng",
    "SENTENCE_TRANSFORM": "Viết lại câu",
    "TEXT": "Viết tự luận",
    "AUDIO": "Thu âm phát âm / Nói",
}
LEVEL_TAG_CODES = {
    "PRIMARY_TAG",
    "SECONDARY_TAG",
    "HIGH_SCHOOL_TAG",
    "ENTRANCE_10_TAG",
    "THPT_QG_TAG",
    "IELTS_TAG",
    "TOEIC_TAG",
    "TESOL_TAG",
    "EXAM_PRACTICE",
}
WEAK_THRESHOLD_PERCENT = 75

GRAMMAR_KEYWORD_PATTERNS = (
    (
        "Quá khứ đơn & Động từ đuôi -ed / Bất quy tắc",
        "-ed, yesterday, last, ago, did, was/were, quá khứ",
        re.compile(
            r"(?i)(?:\b(?:quá khứ|past\s+simple|yesterday|ago|last\s+(?:week|month|year|night|weekend|summer|sunday|monday)|didn'?t|did\s+not|did|was|were)\b|-ed\b|\b(?!red\b|bed\b|fed\b|led\b|wed\b|shed\b|need\b|seed\b|speed\b|feed\b|bleed\b|breed\b|greed\b|weed\b|indeed\b|hundred\b|used\b|tired\b|excited\b|interested\b|bored\b)[a-z]{3,}ed\b)"
        ),
    ),
    (
        "Câu bị động (Passive Voice)",
        "bị động, passive, be + V3/ed, by...",
        re.compile(r"(?i)(?:bị\s*động|passive|\b(?:is|are|was|were|be|been|being)\s+[a-z]{3,}(?:ed|en|wn|pt|lt|nt|ght)\b)"),
    ),
    (
        "Hiện tại đơn & Thói quen (s/es, do/does)",
        "hiện tại đơn, usually, always, often, every day, do/does",
        re.compile(r"(?i)(?:hiện tại đơn|present\s+simple|\b(?:usually|always|often|sometimes|never|every\s+(?:day|week|morning)|do|does|don'?t|doesn'?t)\b)"),
    ),
    (
        "Động từ To Be & Đại từ (am/is/are)",
        "to be, đại từ, am, is, are, he/she/it/they",
        re.compile(r"(?i)(?:to\s+be|đại\s*từ|\b(?:am|is|are|i'm|he's|she's|it's|they're|we're)\b)"),
    ),
    (
        "Hiện tại tiếp diễn (am/is/are + V-ing)",
        "tiếp diễn, now, at the moment, look!, V-ing",
        re.compile(r"(?i)(?:tiếp\s*diễn|continuous|\b(?:now|at\s+the\s+moment|right\s+now|look!|listen!)\b|\b(?:am|is|are|was|were)\s+[a-z]{2,}ing\b)"),
    ),
    (
        "Hiện tại hoàn thành (have/has + V3/ed)",
        "hoàn thành, have/has, already, yet, since, for",
        re.compile(r"(?i)(?:hoàn\s*thành|present\s+perfect|\b(?:already|yet|just|since|ever|never)\b|\b(?:have|has|haven'?t|hasn'?t)\s+(?:been|done|seen|gone|made|taken|given|written|[a-z]{3,}ed)\b)"),
    ),
    (
        "Câu điều kiện (If / Unless)",
        "điều kiện, conditional, if, unless, would",
        re.compile(r"(?i)(?:câu\s*điều\s*kiện|conditional|\b(?:if|unless|would\s+have)\b)"),
    ),
    (
        "Câu tường thuật (Reported Speech)",
        "tường thuật, reported, said that, told, asked",
        re.compile(r"(?i)(?:tường\s*thuật|reported\s+speech|\b(?:said\s+that|told\s+(?:me|him|her|them)|asked\s+(?:if|whether))\b)"),
    ),
    (
        "Mệnh đề quan hệ (who/which/that/whose)",
        "mệnh đề quan hệ, relative, who, whom, which, whose",
        re.compile(r"(?i)(?:mệnh\s*đề\s*quan\s*hệ|relative\s+clause|\b(?:whom|whose|which)\b)"),
    ),
    (
        "So sánh hơn & So sánh nhất (-er/more, -est/most)",
        "so sánh, than, more, most, -er/-est, as...as",
        re.compile(r"(?i)(?:so\s*sánh|comparative|superlative|\b(?:than|the\s+most|the\s+best|the\s+worst|more\s+[a-z]+|as\s+[a-z]+\s+as)\b)"),
    ),
    (
        "Danh động từ & Động từ nguyên mẫu (To V / V-ing)",
        "danh động từ, nguyên mẫu, gerund, infinitive, enjoy/decide",
        re.compile(r"(?i)(?:danh\s*động\s*từ|nguyên\s*mẫu|gerund|infinitive|\b(?:enjoy|avoid|suggest|finish|mind|decide\s+to|want\s+to|hope\s+to|agree\s+to)\b)"),
    ),
    (
        "Đảo ngữ & Câu chẻ nhấn mạnh",
        "đảo ngữ, câu chẻ, inversion, cleft, not only, hardly",
        re.compile(r"(?i)(?:đảo\s*ngữ|câu\s*chẻ|inversion|cleft|\b(?:not\s+only|hardly|seldom|rarely|no\s+sooner|it\s+is\s+.+\s+that)\b)"),
    ),
    (
        "Cụm động từ & Giới từ (Phrasal Verbs / Prepositions)",
        "cụm động từ, giới từ, phrasal, look after, give up",
        re.compile(r"(?i)(?:cụm\s*động\s*từ|giới\s*từ|phrasal|preposition|\b(?:look\s+after|give\s+up|turn\s+on|turn\s+off|take\s+off|put\s+off|get\s+up)\b)"),
    ),
    (
        "Từ loại & Cấu tạo từ (Word Form)",
        "dạng từ, từ loại, word form, -tion/-ment/-ful/-ly",
        re.compile(r"(?i)(?:dạng\s*từ|từ\s*loại|word\s+form|\b[a-z]+(?:tion|ment|ness|ful|less)\b)"),
    ),
    (
        "Trọng âm & Ngữ âm (Stress & Pronunciation)",
        "trọng âm, ngữ âm, phát âm, stress, âm tiết",
        re.compile(r"(?i)(?:trọng\s*âm|ngữ\s*âm|phát\s*âm|stress|pronunciation|âm\s*tiết)"),
    ),
    (
        "Sắp xếp từ thành câu & Cấu trúc câu",
        "sắp xếp câu, word order, câu hỏi, câu trần thuật",
        re.compile(r"(?i)(?:sắp\s*xếp|word\s*order|câu\s*hỏi|câu\s*trần\s*thuật|trật\s*tự\s*từ)"),
    ),
    (
        "Giao tiếp & Chào hỏi tình huống",
        "giao tiếp, chào hỏi, hello, thank, pleasure, sorry",
        re.compile(r"(?i)(?:giao\s*tiếp|chào\s*hỏi|\b(?:hello|good\s+morning|thank\s+you|pleasure|sorry|excuse\s+me)\b)"),
    ),
    (
        "Từ vựng chủ đề (Màu sắc / Số đếm / Động vật / Đồ vật)",
        "từ vựng, màu sắc, số đếm, động vật, đồ vật, nghề nghiệp",
        re.compile(r"(?i)(?:từ\s*vựng|màu\s*sắc|số\s*đếm|động\s*vật|đồ\s*vật|nghề\s*nghiệp|thức\s*ăn|nối\s*tranh|\b(?:color|colour|red|blue|animal|cat|dog|book|pen|teacher|doctor)\b)"),
    ),
)


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


def _filter_recipients(school_id=None, grade=None, school_class_id=None, english_class_id=None, student=None, q=None):
    if grade and not school_id:
        raise ValidationError("Cần chọn trường khi lọc theo khối lớp.")
    qs = AssignmentRecipient.objects.filter(state="ASSIGNED").exclude(assignment__status="CANCELLED").select_related("student__student_profile", "assignment", "current_attempt")
    if student is not None:
        qs = qs.filter(student=student)
    if q:
        qs = qs.filter(
            Q(student__display_name__icontains=q)
            | Q(student__username__icontains=q)
            | Q(student__student_profile__student_ref__icontains=q)
        )
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


def _extract_exercise_topics(tags):
    topics = []
    for tag in tags:
        if tag.code not in LEVEL_TAG_CODES and tag.kind != "SKILL" and tag.name not in topics:
            topics.append(tag.name)
    return topics


def _fallback_topic_label(skill, question_type):
    if skill == "LISTENING" and question_type in ("SINGLE_CHOICE", "MULTIPLE_CHOICE"):
        return "Nghe hiểu"
    if question_type in QUESTION_TYPE_TOPIC_LABELS:
        return QUESTION_TYPE_TOPIC_LABELS[question_type]
    return skill or ""


def _match_question_patterns(text_blob, fallback_labels=None):
    matched = []
    for name, hint, regex in GRAMMAR_KEYWORD_PATTERNS:
        if regex.search(text_blob):
            matched.append((name, hint))
    if not matched and fallback_labels:
        for lbl in fallback_labels:
            if lbl:
                matched.append((lbl, lbl.lower()))
    return matched


def _format_question_answers(q_obj, resp=None, is_wrong=False):
    if q_obj is None:
        return {
            "options_list": [],
            "student_answer": "Trả lời sai" if is_wrong else "Đúng (theo kết quả chấm)",
            "correct_answer": "—",
        }

    qtype = q_obj.type
    options = sorted(q_obj.options.all(), key=lambda o: o.position)
    options_list = []
    correct_answer = "—"
    student_answer = ""

    if qtype in ("SINGLE_CHOICE", "MULTIPLE_CHOICE", "STRESS_CHOICE"):
        options_list = [f"{o.key}. {o.content}" for o in options]
        correct_opts = sorted(
            [ak.option for ak in q_obj.answer_keys.all() if ak.option_id],
            key=lambda o: o.position,
        )
        if correct_opts:
            correct_answer = ", ".join(f"{o.key}. {o.content}" for o in correct_opts)
        elif q_obj.explanation:
            correct_answer = q_obj.explanation.strip()
        if resp is not None:
            sel_opts = sorted(resp.options.all(), key=lambda o: o.position)
            if sel_opts:
                student_answer = ", ".join(f"{o.key}. {o.content}" for o in sel_opts)
            elif resp.text_answer:
                student_answer = resp.text_answer.strip()
    elif qtype == "WORD_ORDER":
        options_list = [o.content for o in options]
        if options:
            correct_answer = " ".join(o.content for o in options)
        elif q_obj.explanation:
            correct_answer = q_obj.explanation.strip()
        if resp is not None:
            if resp.ordered_option_ids:
                by_id = {str(o.id): o.content for o in options}
                student_answer = " ".join(by_id.get(str(oid), str(oid)) for oid in resp.ordered_option_ids)
            elif resp.text_answer:
                student_answer = resp.text_answer.strip()
    elif qtype == "SENTENCE_TRANSFORM":
        if options:
            correct_answer = options[0].content
        elif q_obj.explanation:
            correct_answer = q_obj.explanation.strip()
        if resp is not None and resp.text_answer:
            student_answer = resp.text_answer.strip()
    elif qtype == "MATCH_IMAGE":
        imgs = sorted(q_obj.match_images.all(), key=lambda im: im.position)
        words = list(q_obj.match_words.all())
        word_by_id = {str(w.id): w.text for w in words}
        img_pos = {str(im.id): idx for idx, im in enumerate(imgs, 1)}
        correct_pairs = []
        for idx, im in enumerate(imgs, 1):
            ak = getattr(im, "answer_key", None)
            if ak and ak.word_id:
                wtxt = ak.word.text if getattr(ak, "word", None) else word_by_id.get(str(ak.word_id), "?")
                correct_pairs.append(f"Hình {idx} → {wtxt}")
        if correct_pairs:
            correct_answer = "; ".join(correct_pairs)
        elif q_obj.explanation:
            correct_answer = q_obj.explanation.strip()
        if resp is not None and resp.match_pairs:
            student_answer = "; ".join(
                f"Hình {img_pos.get(str(p.get('image_id')), '?')} → {word_by_id.get(str(p.get('word_id')), '?')}"
                for p in resp.match_pairs
            )
    elif qtype in ("TEXT", "AUDIO"):
        correct_answer = q_obj.explanation.strip() if q_obj.explanation else "Chấm theo tiêu chí (Rubric)"
        if resp is not None:
            if qtype == "AUDIO":
                student_answer = "Đã nộp bản ghi âm" if resp.audio_asset_id else "Chưa ghi âm"
            elif resp.text_answer:
                student_answer = resp.text_answer.strip()

    if not student_answer:
        if not is_wrong and correct_answer != "—":
            student_answer = correct_answer
        elif is_wrong:
            student_answer = "Chưa trả lời / Chưa ghi nhận đáp án"
        else:
            student_answer = "Đạt yêu cầu"

    return {
        "options_list": options_list,
        "student_answer": student_answer,
        "correct_answer": correct_answer,
    }


def _preferred_categories_by_student(student_uuid_list, all_recipients):
    cats_by_student = {}
    active_categories = {}
    assignment_ids = {r.assignment_id for r in all_recipients}
    if assignment_ids:
        ex_rows = CourseExercise.objects.filter(
            assignment_id__in=assignment_ids,
            course__is_published=True,
        ).values_list("assignment_id", "course__category").distinct()
        by_asg = {}
        for aid, cat in ex_rows:
            if cat:
                by_asg.setdefault(aid, set()).add(cat)
        for r in all_recipients:
            if r.assignment_id in by_asg:
                cats_by_student.setdefault(str(r.student_id), set()).update(by_asg[r.assignment_id])
    if student_uuid_list:
        mem_rows = Course.objects.filter(
            is_published=True,
            english_classes__archived_at__isnull=True,
            english_classes__memberships__student_id__in=student_uuid_list,
            english_classes__memberships__end_at__isnull=True,
        ).values_list("english_classes__memberships__student_id", "category").distinct()
        for sid, cat in mem_rows:
            if sid and cat:
                active_categories.setdefault(str(sid), set()).add(cat)
    cats_by_student.update(active_categories)
    return cats_by_student


def _build_topic_catalog_and_assignment_tags():
    published_assignments = list(
        Assignment.objects.filter(status="PUBLISHED")
        .select_related("version")
        .prefetch_related(
            "version__questions__options",
            "version__questions__question_tags__tag",
            "course_exercises__course__tags",
            "course_exercises__tags",
        )
        .order_by("title")
    )
    assignment_topics = {}
    catalog = {}
    format_catalog = {}
    pattern_catalog = {}
    seen_catalog = {}
    seen_formats = {}
    seen_patterns = {}
    for assignment in published_assignments:
        ex_topics = []
        course_name = ""
        is_ielts_assignment = False
        has_published_course = False
        categories = set()
        course_ids = set()
        difficulties = []
        for ce in assignment.course_exercises.all():
            if not ce.course or not ce.course.is_published:
                continue
            if ce.course and ce.course.is_published:
                if not course_name:
                    course_name = ce.course.name
                has_published_course = True
                if ce.course.category:
                    categories.add(ce.course.category)
                course_ids.add(str(ce.course_id))
                difficulties.append(ce.difficulty)
            if (
                (ce.course and ce.course.category == Course.Category.IELTS)
                or any(t.code == "IELTS_TAG" for t in ce.tags.all())
                or (ce.course and any(t.code == "IELTS_TAG" for t in ce.course.tags.all()))
            ):
                is_ielts_assignment = True
            for tname in _extract_exercise_topics(ce.tags.all()):
                if tname not in ex_topics:
                    ex_topics.append(tname)
        assignment_topics[assignment.id] = ex_topics

        q_topics = list(ex_topics)
        q_formats = []
        q_patterns = []
        pattern_formats = {}
        for q in assignment.version.questions.all():
            if q.type not in q_formats:
                q_formats.append(q.type)
            q_tag_names = []
            for qt in q.question_tags.all():
                if qt.tag.kind == "TOPIC":
                    q_tag_names.append(qt.tag.name)
                    if qt.tag.name not in q_topics:
                        q_topics.append(qt.tag.name)
            fb = _fallback_topic_label(q.skill, q.type)
            if fb and fb not in q_topics:
                q_topics.append(fb)
            blob = f"{q.prompt} {' '.join(q_tag_names)}"
            for pname, _hint in _match_question_patterns(blob):
                if pname not in q_patterns:
                    q_patterns.append(pname)
                pattern_formats.setdefault(pname, set()).add(q.type)

        entry = {
            "assignment_id": str(assignment.id),
            "title": assignment.title,
            "course_name": course_name,
            "is_ielts": is_ielts_assignment,
            "in_course": has_published_course,
            "categories": categories,
            "course_ids": course_ids,
            "min_difficulty": min(difficulties) if difficulties else 3,
            "formats": set(q_formats),
            "pattern_formats": pattern_formats,
        }
        for topic in q_topics:
            seen_ids = seen_catalog.setdefault(topic, set())
            if entry["assignment_id"] not in seen_ids:
                seen_ids.add(entry["assignment_id"])
                catalog.setdefault(topic, []).append(entry)
        for qtype in q_formats:
            seen_ids = seen_formats.setdefault(qtype, set())
            if entry["assignment_id"] not in seen_ids:
                seen_ids.add(entry["assignment_id"])
                format_catalog.setdefault(qtype, []).append(entry)
        for pname in q_patterns:
            seen_ids = seen_patterns.setdefault(pname, set())
            if entry["assignment_id"] not in seen_ids:
                seen_ids.add(entry["assignment_id"])
                pattern_catalog.setdefault(pname, []).append(entry)
    return assignment_topics, catalog, format_catalog, pattern_catalog


def _recommend_exercises(
    catalog,
    topic,
    completed_assignment_ids=None,
    prefer_non_ielts=True,
    preferred_categories=None,
    exclude_assignment_id=None,
    required_formats=None,
    match_pattern_format=False,
    preferred_course_ids=None,
    limit=3,
):
    pref_cats = set(preferred_categories or ())
    if not pref_cats:
        return []
    candidates = [c for c in catalog.get(topic, []) if c["categories"] & pref_cats]
    if required_formats:
        candidates = [
            c for c in candidates
            if set(required_formats) & (c["pattern_formats"].get(topic, set()) if match_pattern_format else c["formats"])
        ]
    if exclude_assignment_id:
        filtered = [c for c in candidates if c["assignment_id"] != str(exclude_assignment_id)]
        candidates = filtered
    if not candidates:
        return []
    completed = completed_assignment_ids or set()
    pool = [c for c in candidates if c["assignment_id"] not in completed]
    ordered = sorted(
        pool,
        key=lambda c: (
            0 if set(preferred_course_ids or ()) & c.get("course_ids", set()) else 1,
            0 if (pref_cats and (c["categories"] & pref_cats)) else (1 if pref_cats else 0),
            1 if (prefer_non_ielts and c["is_ielts"]) else 0,
            0 if c["in_course"] else 1,
            c["min_difficulty"],
            c["title"],
        ),
    )
    return [
        {"assignment_id": c["assignment_id"], "title": c["title"], "course_name": c["course_name"]}
        for c in ordered[:limit]
    ]


def _ielts_courses_by_student(student_ids, all_recipients):
    ielts_map = {}
    assignment_ids = {r.assignment_id for r in all_recipients}
    if assignment_ids:
        ex_rows = (
            CourseExercise.objects.filter(assignment_id__in=assignment_ids)
            .filter(Q(course__category=Course.Category.IELTS) | Q(course__tags__code="IELTS_TAG") | Q(tags__code="IELTS_TAG"))
            .values_list("assignment_id", "course__name")
            .distinct()
        )
        by_assignment = {}
        for aid, cname in ex_rows:
            if cname:
                by_assignment.setdefault(aid, set()).add(cname)
        for r in all_recipients:
            if r.assignment_id in by_assignment:
                ielts_map.setdefault(str(r.student_id), set()).update(by_assignment[r.assignment_id])

    if student_ids:
        mem_rows = (
            Course.objects.filter(
                Q(category=Course.Category.IELTS) | Q(tags__code="IELTS_TAG"),
                english_classes__archived_at__isnull=True,
                english_classes__memberships__student_id__in=student_ids,
                english_classes__memberships__end_at__isnull=True,
            )
            .values_list("english_classes__memberships__student_id", "name")
            .distinct()
        )
        for sid, cname in mem_rows:
            if sid and cname:
                ielts_map.setdefault(str(sid), set()).add(cname)

    return {sid: sorted(names) for sid, names in ielts_map.items()}


def _latest_visibility_deductions(attempt_ids):
    if not attempt_ids:
        return {}
    deductions = {}
    events = AuditEvent.objects.filter(
        action="attempt.visibility_deduction",
        target_type="attempt",
        target_id__in=attempt_ids,
    ).order_by("target_id", "-created_at", "-id")
    for ev in events:
        if ev.target_id in deductions:
            continue
        try:
            pts = Decimal(str((ev.metadata or {}).get("points", "0")))
        except Exception:
            pts = Decimal("0")
        deductions[ev.target_id] = pts
    return deductions


def _filtered_active_students(school_id=None, grade=None, school_class_id=None, english_class_id=None, student=None, q=None):
    User = get_user_model()
    qs = User.objects.filter(role="STUDENT", status="ACTIVE").select_related("student_profile")
    if student is not None:
        qs = qs.filter(pk=student.id)
    if q:
        qs = qs.filter(
            Q(display_name__icontains=q)
            | Q(username__icontains=q)
            | Q(student_profile__student_ref__icontains=q)
        )
    if school_id:
        qs = qs.filter(school_memberships__end_at__isnull=True, school_memberships__school_class__school_id=school_id)
    if grade:
        qs = qs.filter(school_memberships__end_at__isnull=True, school_memberships__school_class__grade=int(grade))
    if school_class_id:
        qs = qs.filter(school_memberships__end_at__isnull=True, school_memberships__school_class_id=school_class_id)
    if english_class_id:
        qs = qs.filter(english_memberships__end_at__isnull=True, english_memberships__english_class_id=english_class_id)
    return list(qs.distinct().order_by("display_name"))


def _student_class_names_map(student_uuid_list):
    if not student_uuid_list:
        return {}
    names_by_student = {}
    for m in (
        EnglishMembership.objects.filter(
            student_id__in=student_uuid_list,
            end_at__isnull=True,
            english_class__archived_at__isnull=True,
        )
        .select_related("english_class")
        .order_by("english_class__name")
    ):
        names_by_student.setdefault(str(m.student_id), []).append(m.english_class.name)
    for m in (
        SchoolMembership.objects.filter(
            student_id__in=student_uuid_list,
            end_at__isnull=True,
            school_class__archived_at__isnull=True,
        )
        .select_related("school_class__school")
        .order_by("school_class__grade", "school_class__name")
    ):
        sc = m.school_class
        label = f"{sc.school.name} - {sc.name}" if sc.name != "Chung" else f"{sc.school.name} (Khối {sc.grade})"
        bucket = names_by_student.setdefault(str(m.student_id), [])
        if label not in bucket:
            bucket.append(label)
    return names_by_student


def _cheat_details_by_student(all_recipients):
    rec_ids = [r.id for r in all_recipients]
    if not rec_ids:
        return {}
    attempts = list(
        Attempt.objects.filter(recipient_id__in=rec_ids)
        .select_related("recipient__assignment")
        .order_by("-started_at", "attempt_no")
    )
    if not attempts:
        return {}
    attempt_ids = [a.id for a in attempts]
    vis_by_attempt = {}
    for ev in AttemptVisibilityEvent.objects.filter(attempt_id__in=attempt_ids, duration_ms__gt=5000).order_by("recorded_at"):
        entry = vis_by_attempt.setdefault(ev.attempt_id, {"count": 0, "max_ms": 0, "total_ms": 0})
        entry["count"] += 1
        entry["max_ms"] = max(entry["max_ms"], ev.duration_ms)
        entry["total_ms"] += ev.duration_ms

    deductions = _latest_visibility_deductions(attempt_ids)
    details_by_student = {}
    for a in attempts:
        reasons = []
        if a.status == "VOID":
            reasons.append(f"Hủy bài (VOID): {a.void_reason}" if a.void_reason else "Hủy bài (VOID)")
        if a.id in vis_by_attempt:
            v = vis_by_attempt[a.id]
            max_s = round(v["max_ms"] / 1000, 1)
            total_s = round(v["total_ms"] / 1000, 1)
            reasons.append(f"Rời trang {v['count']} lần > 5s (lâu nhất {max_s}s, tổng {total_s}s)")
        if deductions.get(a.id, Decimal("0")) > 0:
            reasons.append(f"Bị trừ {deductions[a.id]} điểm do rời trang")
        if reasons:
            sid = str(a.recipient.student_id)
            details_by_student.setdefault(sid, []).append({
                "attempt_id": str(a.id),
                "assignment_id": str(a.recipient.assignment_id),
                "title": a.recipient.assignment.title,
                "attempt_no": a.attempt_no,
                "reasons": reasons,
            })
    return details_by_student


def _evaluate_student_profile(st, avg_score, weak_areas, cheat_count, overdue_count):
    parts = []
    if avg_score is not None:
        parts.append(f"Điểm TB {avg_score}/10")
    if weak_areas:
        weak_list = ", ".join(f"{w['topic']} ({w['percent']}%)" for w in weak_areas[:3])
        parts.append(f"Cần bù đắp: {weak_list}")
    if st["missing_count"]:
        parts.append(f"Còn thiếu {st['missing_count']} bài chưa làm" + (f" ({overdue_count} quá hạn)" if overdue_count else ""))
    if st["late_count"]:
        parts.append(f"{st['late_count']} bài nộp trễ")
    if cheat_count:
        parts.append(f"{cheat_count} lần cảnh báo Cheat")

    if st["assigned"] == 0 and avg_score is None:
        return "neutral", "Chưa có bài giao", "Học sinh chưa được giao bài tập nào trong phạm vi lọc."

    if cheat_count > 0 and (avg_score is None or avg_score < 6.5 or st["missing_count"] >= 2):
        level, label = "danger", "Cần theo sát (Vi phạm & Kết quả)"
    elif cheat_count > 0:
        level, label = "warning", "Cần lưu ý tính trung thực"
    elif (avg_score is not None and avg_score < 5.0) or overdue_count >= 2 or (st["assigned"] >= 2 and st["submitted"] == 0 and overdue_count >= 1):
        level, label = "danger", "Cần hỗ trợ gấp"
    elif (avg_score is not None and avg_score < 7.5) or weak_areas or st["missing_count"] > 0 or st["late_count"] > 0:
        level, label = "warning", "Cần củng cố thêm"
    elif avg_score is not None and avg_score >= 8.5:
        level, label = "success", "Hoàn thành tốt"
    elif avg_score is not None:
        level, label = "success", "Đạt yêu cầu"
    else:
        level, label = "neutral", "Đang chờ chấm điểm"

    if not parts:
        parts.append("Đang theo kịp tiến độ bài học.")
    return level, label, " · ".join(parts) + "."


def _compute_student_ranks(student_uuid_list, sel_start, sel_end):
    """Compute per-student class rankings and course rankings against all active peers."""
    if not student_uuid_list:
        return {}, {}

    eng_class_names = {}
    eng_class_peers = {}
    student_eng_classes = {}
    target_eng_mems = list(
        EnglishMembership.objects.filter(
            student_id__in=student_uuid_list,
            end_at__isnull=True,
            english_class__archived_at__isnull=True,
        ).select_related("english_class")
    )
    for m in target_eng_mems:
        eng_class_names[m.english_class_id] = m.english_class.name
        student_eng_classes.setdefault(str(m.student_id), []).append(m.english_class_id)

    sch_class_names = {}
    sch_class_peers = {}
    student_sch_classes = {}
    target_sch_mems = list(
        SchoolMembership.objects.filter(
            student_id__in=student_uuid_list,
            end_at__isnull=True,
            school_class__archived_at__isnull=True,
        ).select_related("school_class__school")
    )
    for m in target_sch_mems:
        sc = m.school_class
        label = f"{sc.school.name} - {sc.name}" if sc.name != "Chung" else f"{sc.school.name} (Khối {sc.grade})"
        sch_class_names[sc.id] = label
        student_sch_classes.setdefault(str(m.student_id), []).append(sc.id)

    all_peer_ids = set(student_uuid_list)
    if eng_class_names:
        for sid_val, ec_id in EnglishMembership.objects.filter(
            english_class_id__in=eng_class_names.keys(),
            end_at__isnull=True,
            student__status="ACTIVE",
        ).values_list("student_id", "english_class_id"):
            all_peer_ids.add(sid_val)
            eng_class_peers.setdefault(ec_id, set()).add(str(sid_val))

    if sch_class_names:
        for sid_val, sc_id in SchoolMembership.objects.filter(
            school_class_id__in=sch_class_names.keys(),
            end_at__isnull=True,
            student__status="ACTIVE",
        ).values_list("student_id", "school_class_id"):
            all_peer_ids.add(sid_val)
            sch_class_peers.setdefault(sc_id, set()).add(str(sid_val))

    # Published courses where target students are enrolled (via EnglishClass) or assigned exercises
    course_names = {}
    course_aids = {}
    course_peers = {}
    student_courses = {}

    if eng_class_names:
        for cid, cname, ec_id in Course.objects.filter(
            is_published=True,
            english_classes__id__in=eng_class_names.keys(),
        ).values_list("id", "name", "english_classes__id").distinct():
            course_names[cid] = cname
            peers = eng_class_peers.get(ec_id, set())
            course_peers.setdefault(cid, set()).update(peers)
            for sid_str in peers:
                if sid_str in student_eng_classes and ec_id in student_eng_classes[sid_str]:
                    student_courses.setdefault(sid_str, set()).add(cid)

    assigned_course_rows = (
        CourseExercise.objects.filter(
            course__is_published=True,
            assignment__status="PUBLISHED",
            assignment__recipients__student_id__in=student_uuid_list,
            assignment__recipients__state="ASSIGNED",
        )
        .values_list("course_id", "course__name", "assignment__recipients__student_id")
        .distinct()
    )
    for cid, cname, sid_val in assigned_course_rows:
        course_names[cid] = cname
        sid_str = str(sid_val)
        student_courses.setdefault(sid_str, set()).add(cid)
        course_peers.setdefault(cid, set()).add(sid_str)

    if course_names:
        for cid, aid in CourseExercise.objects.filter(
            course_id__in=course_names.keys(),
            assignment__status="PUBLISHED",
        ).values_list("course_id", "assignment_id"):
            course_aids.setdefault(cid, set()).add(aid)

        # Include all active peers in those courses (either enrolled via EnglishClass or assigned)
        for cid, sid_val in Course.objects.filter(
            pk__in=course_names.keys(),
            english_classes__archived_at__isnull=True,
            english_classes__memberships__end_at__isnull=True,
            english_classes__memberships__student__status="ACTIVE",
        ).values_list("id", "english_classes__memberships__student_id").distinct():
            if sid_val:
                all_peer_ids.add(sid_val)
                course_peers.setdefault(cid, set()).add(str(sid_val))

        all_course_aids = {aid for aids in course_aids.values() for aid in aids}
        if all_course_aids:
            aid_to_courses = {}
            for cid, aids in course_aids.items():
                for aid in aids:
                    aid_to_courses.setdefault(aid, []).append(cid)
            for aid, sid_val in AssignmentRecipient.objects.filter(
                assignment_id__in=all_course_aids,
                state="ASSIGNED",
                student__status="ACTIVE",
            ).values_list("assignment_id", "student_id"):
                all_peer_ids.add(sid_val)
                for cid in aid_to_courses.get(aid, []):
                    course_peers.setdefault(cid, set()).add(str(sid_val))

    if not eng_class_names and not sch_class_names and not course_names:
        return {}, {}

    peer_recipients = list(
        AssignmentRecipient.objects.filter(
            student_id__in=all_peer_ids,
            state="ASSIGNED",
            assignment__status="PUBLISHED",
        ).select_related("current_attempt")
    )
    peer_attempt_ids = [
        r.current_attempt_id
        for r in peer_recipients
        if r.current_attempt_id
        and r.current_attempt.status != "VOID"
        and r.current_attempt.submitted_at
        and sel_start <= r.current_attempt.submitted_at < sel_end
    ]
    peer_rel_map = {}
    if peer_attempt_ids:
        for rel in GradeRelease.objects.filter(attempt_id__in=peer_attempt_ids).order_by("attempt_id", "-number"):
            if rel.attempt_id not in peer_rel_map:
                peer_rel_map[rel.attempt_id] = rel

    unreleased_peer_ids = [
        r.current_attempt_id
        for r in peer_recipients
        if r.current_attempt_id in set(peer_attempt_ids)
        and r.current_attempt_id not in peer_rel_map
        and r.current_attempt.status == "GRADED"
    ]
    peer_grade_totals = {}
    if unreleased_peer_ids:
        for aid_val, pts, max_pts in Response.objects.filter(
            attempt_id__in=unreleased_peer_ids,
            grade__isnull=False,
        ).values_list("attempt_id", "grade__points", "question__max_points"):
            b = peer_grade_totals.setdefault(aid_val, [Decimal("0"), Decimal("0")])
            b[0] += Decimal(str(pts))
            b[1] += Decimal(str(max_pts))
        peer_deductions = _latest_visibility_deductions(unreleased_peer_ids)
    else:
        peer_deductions = {}

    peer_all_scores = {}
    peer_submitted_count = {}
    peer_asg_score = {}
    peer_asg_submitted = {}

    for r in peer_recipients:
        sid_str = str(r.student_id)
        att = r.current_attempt
        if att and att.status in ("SUBMITTED", "GRADED"):
            peer_submitted_count[sid_str] = peer_submitted_count.get(sid_str, 0) + 1
            peer_asg_submitted.setdefault(sid_str, set()).add(r.assignment_id)
        if not att or att.id not in set(peer_attempt_ids):
            continue
        score_10 = None
        if att.id in peer_rel_map:
            rel = peer_rel_map[att.id]
            if Decimal(str(rel.max_points)) > 0:
                score_10 = float(Decimal(str(rel.total_points)) / Decimal(str(rel.max_points)) * Decimal("10"))
        elif att.id in peer_grade_totals:
            earned_sum, max_sum = peer_grade_totals[att.id]
            if max_sum > 0:
                net_earned = max(Decimal("0"), earned_sum - peer_deductions.get(att.id, Decimal("0")))
                score_10 = float(net_earned / max_sum * Decimal("10"))
        if score_10 is not None:
            peer_all_scores.setdefault(sid_str, []).append(score_10)
            peer_asg_score[(sid_str, r.assignment_id)] = score_10

    peer_avg_map = {
        sid_str: round(sum(vals) / len(vals), 1)
        for sid_str, vals in peer_all_scores.items()
        if vals
    }

    def _rank_for_peers(sid_str, peer_set, score_fn, count_fn):
        my_score = score_fn(sid_str)
        my_cnt = count_fn(sid_str)
        ranked_entries = []
        for p_sid in peer_set:
            p_score = score_fn(p_sid)
            if p_score is not None:
                ranked_entries.append((p_score, count_fn(p_sid)))
        group_avg = round(sum(s for s, _ in ranked_entries) / len(ranked_entries), 1) if ranked_entries else None
        if my_score is None:
            return None, len(peer_set), group_avg
        ahead = sum(1 for p_score, p_cnt in ranked_entries if (p_score, p_cnt) > (my_score, my_cnt))
        return ahead + 1, len(peer_set), group_avg

    class_ranks_by_student = {}
    for sid_val in student_uuid_list:
        sid_str = str(sid_val)
        ranks = []
        for ec_id in student_eng_classes.get(sid_str, []):
            peers = eng_class_peers.get(ec_id, {sid_str})
            rk, total, grp_avg = _rank_for_peers(
                sid_str,
                peers,
                lambda s: peer_avg_map.get(s),
                lambda s: peer_submitted_count.get(s, 0),
            )
            ranks.append({
                "class_name": eng_class_names[ec_id],
                "kind": "Lớp tiếng Anh",
                "rank": rk,
                "total_students": total,
                "avg_score": peer_avg_map.get(sid_str),
                "class_avg_score": grp_avg,
            })
        for sc_id in student_sch_classes.get(sid_str, []):
            peers = sch_class_peers.get(sc_id, {sid_str})
            rk, total, grp_avg = _rank_for_peers(
                sid_str,
                peers,
                lambda s: peer_avg_map.get(s),
                lambda s: peer_submitted_count.get(s, 0),
            )
            ranks.append({
                "class_name": sch_class_names[sc_id],
                "kind": "Lớp trường",
                "rank": rk,
                "total_students": total,
                "avg_score": peer_avg_map.get(sid_str),
                "class_avg_score": grp_avg,
            })
        class_ranks_by_student[sid_str] = ranks

    course_ranks_by_student = {}
    for sid_val in student_uuid_list:
        sid_str = str(sid_val)
        c_ranks = []
        for cid in sorted(student_courses.get(sid_str, ()), key=lambda c: course_names[c]):
            aids = course_aids.get(cid, set())
            peers = course_peers.get(cid, {sid_str})

            def _c_score(s, aids=aids):
                vals = [peer_asg_score[(s, aid)] for aid in aids if (s, aid) in peer_asg_score]
                return round(sum(vals) / len(vals), 1) if vals else None

            def _c_sub(s, aids=aids):
                return len(peer_asg_submitted.get(s, set()) & aids)

            rk, total, grp_avg = _rank_for_peers(sid_str, peers, _c_score, _c_sub)
            c_ranks.append({
                "course_id": str(cid),
                "course_name": course_names[cid],
                "rank": rk,
                "total_students": total,
                "course_avg_score": _c_score(sid_str),
                "group_avg_score": grp_avg,
                "submitted_in_course": _c_sub(sid_str),
                "total_in_course": len(aids),
            })
        course_ranks_by_student[sid_str] = c_ranks

    return class_ranks_by_student, course_ranks_by_student


def _build_skill_dict(selected_ev, tc_ev, tp_ev):
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
    return skills


def owner_progress_report(actor, from_str=None, to_str=None, school_id=None, grade=None, school_class_id=None, english_class_id=None, student=None, student_id=None, q=None):
    """Compute comprehensive per-student evaluation, pacing/cheat alerts, auto-diagnosed weak topics, and IELTS skills."""
    q = (q or "").strip() or None
    if student is None and student_id:
        User = get_user_model()
        try:
            student = User.objects.select_related("student_profile").filter(pk=student_id, role="STUDENT").first()
        except (ValidationError, ValueError):
            raise ValidationError("Mã học sinh không hợp lệ.")
        if student is None:
            raise ValidationError("Không tìm thấy học sinh.")

    from_day, to_day = parse_date_window(from_str, to_str)
    trend_cur_from = to_day - timedelta(days=27)
    trend_prev_from = trend_cur_from - timedelta(days=28)
    trend_prev_to = trend_cur_from - timedelta(days=1)

    overall_from = min(from_day, trend_prev_from)
    start_utc, end_utc = _day_range_utc(overall_from, to_day)
    sel_start, sel_end = _day_range_utc(from_day, to_day)
    tc_start, tc_end = _day_range_utc(trend_cur_from, to_day)
    tp_start, tp_end = _day_range_utc(trend_prev_from, trend_prev_to)

    recipients = _filter_recipients(school_id=school_id, grade=grade, school_class_id=school_class_id, english_class_id=english_class_id, student=student, q=q)
    releases = _latest_releases_for_recipients(recipients.filter(current_attempt__submitted_at__gte=start_utc, current_attempt__submitted_at__lt=end_utc))

    selected_ev, tc_ev, tp_ev = [], [], []
    by_student_ev = {}
    by_student_tc_ev = {}
    by_student_tp_ev = {}
    error_counts = Counter()
    sel_release_by_attempt = {}
    snapshot_q_ids = set()

    for rel in releases:
        sub_at = rel.attempt.submitted_at
        if not sub_at:
            continue
        ev = _evidence_from_release(rel)
        sid = str(rel.attempt.recipient.student_id)
        if sel_start <= sub_at < sel_end:
            selected_ev.extend(ev)
            by_student_ev.setdefault(sid, []).extend(ev)
            sel_release_by_attempt[rel.attempt_id] = rel
            for item in (rel.snapshot or {}).get("responses", []):
                if item.get("question_id"):
                    snapshot_q_ids.add(item["question_id"])
                for err in item.get("errors", []):
                    error_counts[(item.get("skill", ""), err.get("tag_name", ""))] += 1
        if tc_start <= sub_at < tc_end:
            tc_ev.extend(ev)
            by_student_tc_ev.setdefault(sid, []).extend(ev)
        elif tp_start <= sub_at < tp_end:
            tp_ev.extend(ev)
            by_student_tp_ev.setdefault(sid, []).extend(ev)

    skills = _build_skill_dict(selected_ev, tc_ev, tp_ev)

    now = timezone.now()
    pacing_cutoff_end = min(now, tc_end)
    all_recipients = list(recipients.filter(assignment__status="PUBLISHED").order_by("assignment__due_at", "assignment__title"))
    active_students = _filtered_active_students(
        school_id=school_id,
        grade=grade,
        school_class_id=school_class_id,
        english_class_id=english_class_id,
        student=student,
        q=q,
    )

    student_stats = {}
    student_uuid_map = {}

    def _ensure_student(user_obj):
        sid = str(user_obj.id)
        if sid not in student_stats:
            profile = getattr(user_obj, "student_profile", None)
            student_stats[sid] = {
                "student_id": sid,
                "student_ref": profile.student_ref if profile else "",
                "display_name": user_obj.display_name,
                "assigned": 0,
                "submitted": 0,
                "late_count": 0,
                "missing_count": 0,
                "overdue_count": 0,
                "overdue_28d": 0,
            }
            student_uuid_map[sid] = user_obj.id
        return student_stats[sid]

    for stu in active_students:
        _ensure_student(stu)

    submitted_assignment_ids_by_student = {}
    graded_without_snap_attempt_ids = []
    missing_assignments_by_student = {}
    late_assignments_by_student = {}
    completed_assignments_by_student = {}

    for r in all_recipients:
        sid = str(r.student_id)
        st = _ensure_student(r.student)
        st["assigned"] += 1
        att = r.current_attempt
        eff_due = r.due_at_override or r.assignment.due_at
        if att and att.status in ("SUBMITTED", "GRADED"):
            st["submitted"] += 1
            submitted_assignment_ids_by_student.setdefault(sid, set()).add(str(r.assignment_id))
        else:
            st["missing_count"] += 1
            is_overdue = eff_due < now
            if is_overdue:
                st["overdue_count"] += 1
            if tc_start <= r.assignment.due_at < pacing_cutoff_end:
                st["overdue_28d"] += 1
            if att and att.status == "IN_PROGRESS":
                status_label = "Đang làm dở"
            elif att and att.status == "VOID":
                status_label = "Đã hủy lượt làm (VOID)"
            else:
                status_label = "Chưa bắt đầu"
            missing_assignments_by_student.setdefault(sid, []).append({
                "assignment_id": str(r.assignment_id),
                "title": r.assignment.title,
                "due_at": eff_due,
                "is_overdue": is_overdue,
                "status_label": status_label,
            })
        if att and att.status != "VOID" and att.is_late:
            st["late_count"] += 1
        if (
            att
            and att.status == "GRADED"
            and att.submitted_at
            and sel_start <= att.submitted_at < sel_end
            and (att.id not in sel_release_by_attempt or not (sel_release_by_attempt[att.id].snapshot or {}).get("responses"))
        ):
            graded_without_snap_attempt_ids.append(att.id)

    student_uuid_list = list(student_uuid_map.values())
    ielts_courses_map = _ielts_courses_by_student(student_uuid_list, all_recipients)
    preferred_cats_map = _preferred_categories_by_student(student_uuid_list, all_recipients)
    class_names_map = _student_class_names_map(student_uuid_list)
    cheat_details_map = _cheat_details_by_student(all_recipients)
    assignment_topics, topic_catalog, format_catalog, pattern_catalog = _build_topic_catalog_and_assignment_tags()
    assignment_categories = {item["assignment_id"]: item["categories"] for entries in format_catalog.values() for item in entries}
    assignment_courses = {item["assignment_id"]: item["course_ids"] for entries in format_catalog.values() for item in entries}
    class_ranks_map, course_ranks_map = _compute_student_ranks(student_uuid_list, sel_start, sel_end)

    snap_q_map = {}
    if snapshot_q_ids:
        for q_obj in Question.objects.filter(id__in=snapshot_q_ids).prefetch_related(
            "options",
            "answer_keys__option",
            "question_tags__tag",
            "match_images__answer_key__word",
            "match_words",
        ):
            snap_q_map[str(q_obj.id)] = {
                "q_obj": q_obj,
                "type": q_obj.type,
                "prompt": q_obj.prompt,
                "explanation": q_obj.explanation,
                "options_text": " ".join(o.content for o in q_obj.options.all()),
                "topics": [qt.tag.name for qt in q_obj.question_tags.all() if qt.tag.kind == "TOPIC" and not qt.tag.archived_at],
            }

    all_sel_attempt_ids = list(set(sel_release_by_attempt.keys()) | set(graded_without_snap_attempt_ids))
    responses_by_attempt = {}
    resp_by_attempt_q = {}
    resp_by_id = {}
    unreleased_deductions = {}
    if all_sel_attempt_ids:
        for resp in (
            Response.objects.filter(attempt_id__in=all_sel_attempt_ids)
            .select_related("grade", "question")
            .prefetch_related(
                "options",
                "question__options",
                "question__answer_keys__option",
                "question__question_tags__tag",
                "question__match_images__answer_key__word",
                "question__match_words",
            )
        ):
            responses_by_attempt.setdefault(resp.attempt_id, []).append(resp)
            resp_by_attempt_q[(resp.attempt_id, str(resp.question_id))] = resp
            resp_by_id[str(resp.id)] = resp
    if graded_without_snap_attempt_ids:
        unreleased_attempt_ids = [aid for aid in graded_without_snap_attempt_ids if aid not in sel_release_by_attempt]
        unreleased_deductions = _latest_visibility_deductions(unreleased_attempt_ids)

    attempt_scores_by_student = {}
    student_topic_totals = {}
    student_qtype_totals = {}
    student_pattern_totals = {}
    student_question_totals = {}
    student_asg_stats = {}
    student_question_logs = {}
    attempt_score_map = {}

    for r in all_recipients:
        att = r.current_attempt
        if not att or att.status == "VOID":
            continue
        sid = str(r.student_id)
        eff_due = r.due_at_override or r.assignment.due_at
        in_sel_window = bool(att.submitted_at and sel_start <= att.submitted_at < sel_end)
        rel = sel_release_by_attempt.get(att.id) if in_sel_window else None
        attempt_score_10 = None

        if rel is not None and Decimal(str(rel.max_points)) > 0:
            attempt_score_10 = round(float(Decimal(str(rel.total_points)) / Decimal(str(rel.max_points)) * Decimal("10")), 1)
        elif in_sel_window and att.status == "GRADED":
            resps = responses_by_attempt.get(att.id, [])
            earned_sum = Decimal("0")
            max_sum = Decimal("0")
            for resp in resps:
                grade = getattr(resp, "grade", None)
                if grade is None:
                    continue
                earned_sum += Decimal(str(grade.points))
                max_sum += Decimal(str(resp.question.max_points))
            if max_sum > 0:
                net_earned = max(Decimal("0"), earned_sum - unreleased_deductions.get(att.id, Decimal("0")))
                attempt_score_10 = round(float(net_earned / max_sum * Decimal("10")), 1)

        if attempt_score_10 is not None:
            attempt_score_map[att.id] = attempt_score_10
        if in_sel_window and attempt_score_10 is not None:
            attempt_scores_by_student.setdefault(sid, []).append(attempt_score_10)

        if att.status in ("SUBMITTED", "GRADED"):
            completed_assignments_by_student.setdefault(sid, []).append({
                "assignment_id": str(r.assignment_id),
                "title": r.assignment.title,
                "submitted_at": att.submitted_at,
                "is_late": bool(att.is_late),
                "score_10": attempt_score_10,
                "status": att.status,
            })
            if att.is_late:
                late_assignments_by_student.setdefault(sid, []).append({
                    "assignment_id": str(r.assignment_id),
                    "title": r.assignment.title,
                    "due_at": eff_due,
                    "submitted_at": att.submitted_at,
                    "score_10": attempt_score_10,
                })

        if not in_sel_window:
            continue

        raw_rows = []
        if rel is not None and (rel.snapshot or {}).get("responses"):
            for item in rel.snapshot.get("responses", []):
                qid = str(item.get("question_id") or "")
                qinfo = snap_q_map.get(qid, {})
                resp = resp_by_id.get(str(item.get("response_id") or "")) or resp_by_attempt_q.get((att.id, qid))
                q_obj = qinfo.get("q_obj") or (resp.question if resp is not None else None)
                snap_topics = [t.get("name", "") for t in item.get("topics", []) if t.get("name")]
                db_topics = qinfo.get("topics") or (
                    [qt.tag.name for qt in q_obj.question_tags.all() if qt.tag.kind == "TOPIC" and not qt.tag.archived_at]
                    if q_obj is not None
                    else []
                )
                merged_topics = list(dict.fromkeys([*snap_topics, *db_topics]))
                if len(merged_topics) > 1:
                    merged_topics = [t for t in merged_topics if t.casefold() != "ôn tập chung"]
                raw_rows.append({
                    "question_id": qid,
                    "q_obj": q_obj,
                    "resp": resp,
                    "skill": item.get("skill", ""),
                    "question_type": qinfo.get("type") or (q_obj.type if q_obj is not None else None),
                    "prompt": qinfo.get("prompt") or (q_obj.prompt if q_obj is not None else ""),
                    "options_text": qinfo.get("options_text") or (" ".join(o.content for o in q_obj.options.all()) if q_obj is not None else ""),
                    "explanation": qinfo.get("explanation") or (q_obj.explanation if q_obj is not None else ""),
                    "points": Decimal(str(item.get("points", "0"))),
                    "max_points": Decimal(str(item.get("max_points", "0"))),
                    "topics": merged_topics,
                })
        elif att.status == "GRADED":
            for resp in responses_by_attempt.get(att.id, []):
                grade = getattr(resp, "grade", None)
                if grade is None:
                    continue
                q_topics = [qt.tag.name for qt in resp.question.question_tags.all() if qt.tag.kind == "TOPIC" and not qt.tag.archived_at]
                if len(q_topics) > 1:
                    q_topics = [t for t in q_topics if t.casefold() != "ôn tập chung"]
                raw_rows.append({
                    "question_id": str(resp.question_id),
                    "q_obj": resp.question,
                    "resp": resp,
                    "skill": resp.question.skill,
                    "question_type": resp.question.type,
                    "prompt": resp.question.prompt,
                    "options_text": " ".join(o.content for o in resp.question.options.all()),
                    "explanation": resp.question.explanation,
                    "points": Decimal(str(grade.points)),
                    "max_points": Decimal(str(resp.question.max_points)),
                    "topics": q_topics,
                })

        ex_topics = assignment_topics.get(r.assignment_id, [])
        q_totals = student_question_totals.setdefault(sid, {"correct": 0, "total": 0})
        asg_id_str = str(r.assignment_id)
        asg_stat = student_asg_stats.setdefault(
            (sid, asg_id_str),
            {
                "assignment_id": asg_id_str,
                "title": r.assignment.title,
                "total": 0,
                "correct": 0,
                "wrong": 0,
                "score_10": attempt_score_10,
                "is_late": bool(att.is_late),
                "topics": set(ex_topics),
                "q_types": set(),
            },
        )
        for row in raw_rows:
            if row["max_points"] <= 0:
                continue
            is_wrong = 1 if row["points"] < row["max_points"] else 0
            q_totals["total"] += 1
            asg_stat["total"] += 1
            if is_wrong:
                asg_stat["wrong"] += 1
            else:
                q_totals["correct"] += 1
                asg_stat["correct"] += 1
            qtype = row.get("question_type")
            if qtype:
                asg_stat["q_types"].add(qtype)
                q_bucket = student_qtype_totals.setdefault(sid, {}).setdefault(
                    qtype, {"earned": Decimal("0"), "max": Decimal("0"), "wrong": 0, "total": 0, "wrong_categories": set(), "wrong_courses": set()}
                )
                q_bucket["earned"] += row["points"]
                q_bucket["max"] += row["max_points"]
                q_bucket["wrong"] += is_wrong
                q_bucket["total"] += 1
                if is_wrong:
                    q_bucket["wrong_categories"].update(assignment_categories.get(asg_id_str, set()))
                    q_bucket["wrong_courses"].update(assignment_courses.get(asg_id_str, set()))
            resolved_topics = list(dict.fromkeys([t for t in row["topics"] if t] + ex_topics))
            if not resolved_topics:
                fb = _fallback_topic_label(row["skill"], qtype)
                if fb:
                    resolved_topics = [fb]
            asg_stat["topics"].update(resolved_topics)
            per_student = student_topic_totals.setdefault(sid, {})
            for topic in resolved_topics:
                bucket = per_student.setdefault(topic, {"earned": Decimal("0"), "max": Decimal("0"), "wrong": 0, "total": 0, "wrong_categories": set(), "wrong_courses": set()})
                bucket["earned"] += row["points"]
                bucket["max"] += row["max_points"]
                bucket["wrong"] += is_wrong
                bucket["total"] += 1
                if is_wrong:
                    bucket["wrong_categories"].update(assignment_categories.get(asg_id_str, set()))
                    bucket["wrong_courses"].update(assignment_courses.get(asg_id_str, set()))

            text_blob = f"{row['prompt']} {' '.join(row['topics'])}"
            matched_patterns = _match_question_patterns(text_blob, fallback_labels=row["topics"])
            pat_names = []
            for pname, hint in matched_patterns:
                pat_names.append(pname)
                pbucket = student_pattern_totals.setdefault(sid, {}).setdefault(
                    pname,
                    {"hint": hint, "earned": Decimal("0"), "max": Decimal("0"), "wrong": 0, "total": 0, "samples": [], "wrong_formats": set(), "wrong_categories": set(), "wrong_courses": set()},
                )
                pbucket["earned"] += row["points"]
                pbucket["max"] += row["max_points"]
                pbucket["wrong"] += is_wrong
                pbucket["total"] += 1
                if is_wrong and qtype:
                    pbucket["wrong_formats"].add(qtype)
                    pbucket["wrong_categories"].update(assignment_categories.get(asg_id_str, set()))
                    pbucket["wrong_courses"].update(assignment_courses.get(asg_id_str, set()))
                if is_wrong and row["prompt"] and len(pbucket["samples"]) < 3:
                    sample = row["prompt"].strip()[:110]
                    if sample not in pbucket["samples"]:
                        pbucket["samples"].append(sample)

            ans_info = _format_question_answers(row.get("q_obj"), resp=row.get("resp"), is_wrong=bool(is_wrong))
            student_question_logs.setdefault(sid, []).append({
                "assignment_id": asg_id_str,
                "assignment_title": r.assignment.title,
                "question_type": qtype or "",
                "question_type_label": QUESTION_FORMAT_LABELS.get(qtype, qtype or row["skill"] or "Câu hỏi"),
                "prompt": row["prompt"] or "",
                "options_list": ans_info["options_list"],
                "options_text": row["options_text"],
                "student_answer": ans_info["student_answer"],
                "correct_answer": ans_info["correct_answer"],
                "explanation": row["explanation"],
                "topics": resolved_topics,
                "patterns": pat_names,
                "is_wrong": bool(is_wrong),
                "points": float(row["points"]),
                "max_points": float(row["max_points"]),
            })

    student_assignments_by_student = {}
    for r in all_recipients:
        sid = str(r.student_id)
        aid = str(r.assignment_id)
        att = r.current_attempt
        eff_due = r.due_at_override or r.assignment.due_at
        if att and att.status in ("SUBMITTED", "GRADED"):
            status_code = "late" if att.is_late else "on_time"
            status_label = "Nộp trễ" if att.is_late else "Đã nộp đúng hạn"
            submitted_at = att.submitted_at
            score_10 = attempt_score_map.get(att.id)
        else:
            is_overdue = eff_due < now
            if is_overdue:
                status_code = "missing_overdue"
                status_label = "Chưa làm (Quá hạn)"
            elif att and att.status == "IN_PROGRESS":
                status_code = "missing"
                status_label = "Đang làm dở"
            else:
                status_code = "missing"
                status_label = "Chưa làm"
            submitted_at = None
            score_10 = None
        cheat_reasons = [
            f"Lượt #{ch['attempt_no']}: {'; '.join(ch['reasons'])}"
            for ch in cheat_details_map.get(sid, [])
            if ch["assignment_id"] == aid
        ]
        student_assignments_by_student.setdefault(sid, []).append({
            "assignment_id": aid,
            "title": r.assignment.title,
            "due_at": eff_due,
            "submitted_at": submitted_at,
            "score_10": score_10,
            "status_code": status_code,
            "status_label": status_label,
            "cheat_reasons": cheat_reasons,
        })

    global_topic_stats = {}
    ielts_topic_stats = {}
    student_rows = []
    ielts_students = []
    ielts_sel_ev, ielts_tc_ev, ielts_tp_ev = [], [], []

    for sid, st in sorted(student_stats.items(), key=lambda kv: kv[1]["display_name"]):
        evs = by_student_ev.get(sid, [])
        skill_details = {sk: _serialize_summary(skill_summary(evs, sk)) for sk in sorted(SKILLS)}
        row_skills = {sk: skill_details[sk]["percent"] for sk in sorted(SKILLS)}
        scores = attempt_scores_by_student.get(sid, [])
        avg_score = round(sum(scores) / len(scores), 1) if scores else None
        ielts_courses = ielts_courses_map.get(sid, [])
        is_ielts = bool(ielts_courses)
        preferred_cats = preferred_cats_map.get(sid, set())
        completed_aids = submitted_assignment_ids_by_student.get(sid, set())

        topic_breakdown = []
        for topic, tstat in student_topic_totals.get(sid, {}).items():
            if tstat["max"] <= 0:
                continue
            pct = round(float(tstat["earned"] / tstat["max"] * Decimal("100")), 1)
            wrong_pct = round(100.0 - pct, 1)
            is_weak = pct < WEAK_THRESHOLD_PERCENT
            gstat = global_topic_stats.setdefault(topic, {"earned": Decimal("0"), "max": Decimal("0"), "wrong": 0, "total": 0, "weak_students": set()})
            gstat["earned"] += tstat["earned"]
            gstat["max"] += tstat["max"]
            gstat["wrong"] += tstat["wrong"]
            gstat["total"] += tstat["total"]
            if is_ielts:
                istat = ielts_topic_stats.setdefault(topic, {"earned": Decimal("0"), "max": Decimal("0"), "wrong": 0, "total": 0, "weak_students": set()})
                istat["earned"] += tstat["earned"]
                istat["max"] += tstat["max"]
                istat["wrong"] += tstat["wrong"]
                istat["total"] += tstat["total"]

            recs = []
            if is_weak:
                gstat["weak_students"].add(sid)
                if is_ielts:
                    ielts_topic_stats[topic]["weak_students"].add(sid)
                recs = _recommend_exercises(
                    topic_catalog,
                    topic,
                    completed_assignment_ids=completed_aids,
                    prefer_non_ielts=not is_ielts,
                    preferred_categories=preferred_cats & tstat["wrong_categories"],
                    preferred_course_ids=tstat["wrong_courses"],
                )

            topic_breakdown.append({
                "topic": topic,
                "percent": pct,
                "wrong_percent": wrong_pct,
                "correct_count": tstat["total"] - tstat["wrong"],
                "wrong_count": tstat["wrong"],
                "total_count": tstat["total"],
                "is_weak": is_weak,
                "recommended_exercises": recs,
                "recommendation": ", ".join(ex["title"] for ex in recs) if recs else ("Chưa có bài phù hợp" if is_weak else ""),
            })

        topic_breakdown.sort(key=lambda w: (w["percent"], -w["wrong_count"], w["topic"]))
        weak_areas = [t for t in topic_breakdown if t["is_weak"]]
        strong_areas = sorted(
            [t for t in topic_breakdown if not t["is_weak"]],
            key=lambda s: (-s["percent"], -s["total_count"], s["topic"]),
        )

        question_type_breakdown = []
        for qtype, qstat in student_qtype_totals.get(sid, {}).items():
            if qstat["max"] <= 0:
                continue
            pct = round(float(qstat["earned"] / qstat["max"] * Decimal("100")), 1)
            wrong_pct = round(100.0 - pct, 1)
            is_weak = pct < WEAK_THRESHOLD_PERCENT
            label = QUESTION_FORMAT_LABELS.get(qtype, qtype)
            recs = (
                _recommend_exercises(
                    format_catalog,
                    qtype,
                    completed_assignment_ids=completed_aids,
                    prefer_non_ielts=not is_ielts,
                    preferred_categories=preferred_cats & qstat["wrong_categories"],
                    preferred_course_ids=qstat["wrong_courses"],
                )
                if is_weak
                else []
            )
            question_type_breakdown.append({
                "type": qtype,
                "label": label,
                "percent": pct,
                "wrong_percent": wrong_pct,
                "correct_count": qstat["total"] - qstat["wrong"],
                "wrong_count": qstat["wrong"],
                "total_count": qstat["total"],
                "is_weak": is_weak,
                "recommended_exercises": recs,
            })
        good_question_types = sorted(
            [q for q in question_type_breakdown if not q["is_weak"]],
            key=lambda q: (-q["percent"], -q["total_count"], q["label"]),
        )
        weak_question_types = sorted(
            [q for q in question_type_breakdown if q["is_weak"]],
            key=lambda q: (q["percent"], -q["wrong_count"], q["label"]),
        )
        question_type_breakdown.sort(key=lambda q: (q["percent"], -q["wrong_count"], q["label"]))

        pattern_breakdown = []
        for pname, pstat in student_pattern_totals.get(sid, {}).items():
            if pstat["total"] <= 0:
                continue
            wrong_pct = round(pstat["wrong"] / pstat["total"] * 100, 1)
            correct_pct = round(100.0 - wrong_pct, 1)
            recs = _recommend_exercises(
                pattern_catalog,
                pname,
                completed_assignment_ids=completed_aids,
                prefer_non_ielts=not is_ielts,
                preferred_categories=preferred_cats & pstat["wrong_categories"],
                preferred_course_ids=pstat["wrong_courses"],
                required_formats=pstat["wrong_formats"],
                match_pattern_format=True,
            )
            if not recs:
                recs = _recommend_exercises(
                    topic_catalog,
                    pname,
                    completed_assignment_ids=completed_aids,
                    prefer_non_ielts=not is_ielts,
                    preferred_categories=preferred_cats & pstat["wrong_categories"],
                    preferred_course_ids=pstat["wrong_courses"],
                    required_formats=pstat["wrong_formats"],
                )
            pattern_breakdown.append({
                "pattern": pname,
                "keywords_hint": pstat["hint"],
                "total_count": pstat["total"],
                "correct_count": pstat["total"] - pstat["wrong"],
                "wrong_count": pstat["wrong"],
                "wrong_percent": wrong_pct,
                "correct_percent": correct_pct,
                "sample_wrong_prompts": pstat["samples"],
                "recommended_exercises": recs,
            })
        pattern_breakdown.sort(key=lambda p: (-p["wrong_percent"], -p["wrong_count"], -p["total_count"], p["pattern"]))

        def _similar_for_assignment(aid_str, topics_set, q_types_set):
            seen_ids = set()
            sim = []
            for topic_name in sorted(topics_set):
                for ex in _recommend_exercises(
                    topic_catalog,
                    topic_name,
                    completed_assignment_ids=completed_aids,
                    prefer_non_ielts=not is_ielts,
                    preferred_categories=preferred_cats & assignment_categories.get(aid_str, set()),
                    preferred_course_ids=assignment_courses.get(aid_str, set()),
                    exclude_assignment_id=aid_str,
                    required_formats=q_types_set,
                    limit=2,
                ):
                    if ex["assignment_id"] not in seen_ids:
                        seen_ids.add(ex["assignment_id"])
                        sim.append(ex)
            return sim[:3]

        most_wrong_assignments = []
        enriched_student_assignments = []
        for item in student_assignments_by_student.get(sid, []):
            ast = student_asg_stats.get((sid, item["assignment_id"]))
            total_q = ast["total"] if ast else 0
            wrong_q = ast["wrong"] if ast else 0
            correct_q = ast["correct"] if ast else 0
            wrong_q_pct = round(wrong_q / total_q * 100, 1) if total_q > 0 else None
            sim_exs = _similar_for_assignment(item["assignment_id"], ast["topics"], ast["q_types"]) if ast and wrong_q > 0 else []
            enriched_item = {
                **item,
                "total_questions": total_q,
                "correct_questions": correct_q,
                "wrong_questions": wrong_q,
                "wrong_percent": wrong_q_pct,
                "similar_exercises": sim_exs,
            }
            enriched_student_assignments.append(enriched_item)
            if wrong_q > 0:
                most_wrong_assignments.append({
                    "assignment_id": item["assignment_id"],
                    "title": item["title"],
                    "total_questions": total_q,
                    "correct_questions": correct_q,
                    "wrong_questions": wrong_q,
                    "wrong_percent": wrong_q_pct,
                    "score_10": item["score_10"],
                    "is_late": item["status_code"] == "late",
                    "similar_exercises": sim_exs,
                })
        most_wrong_assignments.sort(
            key=lambda a: (-a["wrong_questions"], -(a["wrong_percent"] or 0), a["score_10"] if a["score_10"] is not None else 99, a["title"])
        )

        weak_summary = "; ".join(f"{w['topic']} ({w['percent']}%)" for w in weak_areas[:3])
        rec_titles = []
        for w in weak_areas[:3]:
            for ex in w["recommended_exercises"]:
                if ex["title"] not in rec_titles:
                    rec_titles.append(ex["title"])
        recommendation_summary = ", ".join(rec_titles[:3])

        cheat_details = cheat_details_map.get(sid, [])
        cheat_count = len(cheat_details)
        on_time_count = max(0, st["submitted"] - st["late_count"])
        completion_percent = round(st["submitted"] / st["assigned"] * 100) if st["assigned"] > 0 else None
        q_totals = student_question_totals.get(sid, {"correct": 0, "total": 0})
        eval_level, eval_label, eval_note = _evaluate_student_profile(
            st, avg_score, weak_areas, cheat_count, st["overdue_count"],
        )
        completed_list = sorted(
            completed_assignments_by_student.get(sid, []),
            key=lambda item: item["submitted_at"] or now,
            reverse=True,
        )
        question_log = student_question_logs.get(sid, [])

        row = {
            **st,
            "class_names": class_names_map.get(sid, []),
            "class_ranks": class_ranks_map.get(sid, []),
            "course_ranks": course_ranks_map.get(sid, []),
            "avg_score": avg_score,
            "on_time_count": on_time_count,
            "completion_percent": completion_percent,
            "total_correct_questions": q_totals["correct"],
            "total_graded_questions": q_totals["total"],
            "cheat_count": cheat_count,
            "cheat_details": cheat_details,
            "missing_assignments": missing_assignments_by_student.get(sid, []),
            "late_assignments": late_assignments_by_student.get(sid, []),
            "completed_assignments": completed_list,
            "student_assignments": enriched_student_assignments,
            "most_wrong_assignments": most_wrong_assignments,
            "needs_pacing_support": st["overdue_28d"] >= 2,
            "evaluation_level": eval_level,
            "evaluation_label": eval_label,
            "evaluation_note": eval_note,
            "skills": row_skills,
            "skill_details": skill_details,
            "topic_breakdown": topic_breakdown,
            "weak_areas": weak_areas,
            "strong_areas": strong_areas,
            "question_type_breakdown": question_type_breakdown,
            "good_question_types": good_question_types,
            "weak_question_types": weak_question_types,
            "pattern_breakdown": pattern_breakdown,
            "question_log": question_log,
            "question_log_json": json.dumps(question_log, ensure_ascii=False),
            "weak_summary": weak_summary,
            "recommendation_summary": recommendation_summary,
            "is_ielts": is_ielts,
            "ielts_courses": ielts_courses,
        }
        student_rows.append(row)
        if is_ielts:
            ielts_students.append(row)
            ielts_sel_ev.extend(evs)
            ielts_tc_ev.extend(by_student_tc_ev.get(sid, []))
            ielts_tp_ev.extend(by_student_tp_ev.get(sid, []))

    def _build_auto_weaknesses(topic_map, prefer_non_ielts=True):
        items = []
        for topic, gstat in topic_map.items():
            if gstat["max"] <= 0:
                continue
            avg_pct = round(float(gstat["earned"] / gstat["max"] * Decimal("100")), 1)
            weak_count = len(gstat["weak_students"])
            if weak_count == 0 and avg_pct >= WEAK_THRESHOLD_PERCENT:
                continue
            category_sets = [preferred_cats_map.get(sid, set()) for sid in gstat["weak_students"]]
            common_categories = set.intersection(*(set(cats) for cats in category_sets)) if category_sets else set()
            recs = _recommend_exercises(topic_catalog, topic, prefer_non_ielts=prefer_non_ielts, preferred_categories=common_categories)
            items.append({
                "topic": topic,
                "avg_percent": avg_pct,
                "weak_student_count": weak_count,
                "wrong_count": gstat["wrong"],
                "total_count": gstat["total"],
                "recommended_exercises": recs,
            })
        items.sort(key=lambda x: (-x["weak_student_count"], x["avg_percent"], x["topic"]))
        return items

    auto_weaknesses = _build_auto_weaknesses(global_topic_stats, prefer_non_ielts=True)
    auto_weaknesses_ielts = _build_auto_weaknesses(ielts_topic_stats, prefer_non_ielts=False)
    ielts_skills = _build_skill_dict(ielts_sel_ev, ielts_tc_ev, ielts_tp_ev)

    all_avg_scores = [row["avg_score"] for row in student_rows if row["avg_score"] is not None]
    overview = {
        "avg_score": round(sum(all_avg_scores) / len(all_avg_scores), 1) if all_avg_scores else None,
        "total_assigned": sum(row["assigned"] for row in student_rows),
        "total_submitted": sum(row["submitted"] for row in student_rows),
        "total_late": sum(row["late_count"] for row in student_rows),
        "total_missing": sum(row["missing_count"] for row in student_rows),
        "total_cheat_count": sum(row["cheat_count"] for row in student_rows),
        "ielts_student_count": len(ielts_students),
    }

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
        "overview": overview,
        "skills": skills,
        "ielts_skills": ielts_skills,
        "students": student_rows,
        "ielts_students": ielts_students,
        "auto_weaknesses": auto_weaknesses,
        "auto_weaknesses_ielts": auto_weaknesses_ielts,
        "top_errors": top_errors,
    }


def student_progress_summary(student, from_str=None, to_str=None):
    report = owner_progress_report(student, from_str=from_str, to_str=to_str, student=student)
    if report["students"]:
        summary = report["students"][0]
    else:
        ielts_courses = _ielts_courses_by_student([student.id], []).get(str(student.id), [])
        c_ranks, cr_ranks = _compute_student_ranks([student.id], *(_day_range_utc(*parse_date_window(from_str, to_str))))
        sid_str = str(student.id)
        summary = {
            "student_id": sid_str,
            "student_ref": getattr(getattr(student, "student_profile", None), "student_ref", ""),
            "display_name": student.display_name,
            "class_names": _student_class_names_map([student.id]).get(sid_str, []),
            "class_ranks": c_ranks.get(sid_str, []),
            "course_ranks": cr_ranks.get(sid_str, []),
            "avg_score": None,
            "assigned": 0,
            "submitted": 0,
            "on_time_count": 0,
            "completion_percent": None,
            "late_count": 0,
            "missing_count": 0,
            "overdue_count": 0,
            "overdue_28d": 0,
            "total_correct_questions": 0,
            "total_graded_questions": 0,
            "cheat_count": 0,
            "cheat_details": [],
            "missing_assignments": [],
            "late_assignments": [],
            "completed_assignments": [],
            "student_assignments": [],
            "most_wrong_assignments": [],
            "needs_pacing_support": False,
            "evaluation_level": "neutral",
            "evaluation_label": "Chưa có bài giao",
            "evaluation_note": "Học sinh chưa được giao bài tập nào trong phạm vi lọc.",
            "skills": {sk: None for sk in sorted(SKILLS)},
            "skill_details": {sk: {"percent": None, "label": None, "questions": 0, "attempts": 0} for sk in sorted(SKILLS)},
            "topic_breakdown": [],
            "weak_areas": [],
            "strong_areas": [],
            "question_type_breakdown": [],
            "good_question_types": [],
            "weak_question_types": [],
            "pattern_breakdown": [],
            "question_log": [],
            "question_log_json": "[]",
            "weak_summary": "",
            "recommendation_summary": "",
            "is_ielts": bool(ielts_courses),
            "ielts_courses": ielts_courses,
        }
    report["student_summary"] = summary
    report["is_ielts_student"] = summary["is_ielts"]
    report["ielts_courses"] = summary["ielts_courses"]
    return report


def _safe_csv_cell(value):
    text = "" if value is None else str(value)
    if text and text[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text
    return text


def export_scores_csv(actor, scope, assignment_id=None, class_id=None, course_id=None):
    import uuid
    from django.db.models import Prefetch

    if scope not in ("assignment", "class", "course"):
        raise ValidationError("Phạm vi xuất không hợp lệ.")
    try:
        assignment_id = uuid.UUID(assignment_id) if assignment_id else None
        class_id = uuid.UUID(class_id) if class_id else None
        course_id = uuid.UUID(course_id) if course_id else None
    except (ValueError, TypeError, AttributeError):
        raise ValidationError("Lựa chọn không hợp lệ.")
    if (scope == "assignment" and not assignment_id) or (scope == "class" and not class_id) or (scope == "course" and not course_id):
        raise ValidationError("Hãy chọn bài tập, lớp hoặc khóa học cần xuất.")
    assignments = Assignment.objects.filter(version__exam__created_by=actor, status="PUBLISHED")
    if assignment_id:
        assignments = assignments.filter(id=assignment_id)
    if course_id:
        if not Course.objects.filter(id=course_id, created_by=actor).exists():
            raise ValidationError("Khóa học không tồn tại.")
        assignments = assignments.filter(course_exercises__course_id=course_id, course_exercises__course__created_by=actor)
    if class_id and not EnglishClass.objects.filter(id=class_id).exists():
        raise ValidationError("Lớp học không tồn tại.")
    if course_id and class_id and not Course.objects.filter(id=course_id, english_classes__id=class_id).exists():
        raise ValidationError("Lớp không thuộc khóa học đã chọn.")

    recipients = AssignmentRecipient.objects.filter(assignment__in=assignments, state="ASSIGNED")
    if class_id:
        recipients = recipients.filter(recipientenglishclass__english_class_id=class_id)
    elif course_id:
        recipients = recipients.filter(recipientenglishclass__english_class__courses__id=course_id)
    recipients = recipients.select_related("student__student_profile", "assignment", "current_attempt").prefetch_related(
        "recipientenglishclass_set", Prefetch("current_attempt__grade_releases", queryset=GradeRelease.objects.order_by("-number")),
        "current_attempt__responses__grade", "current_attempt__responses__question",
    ).distinct().order_by(F("assignment__published_at").desc(nulls_last=True), "-assignment__created_at", "student__display_name", "student_id")
    rows = list(recipients[:10001])
    if len(rows) > 10000:
        raise ValidationError("Tối đa 10.000 dòng mỗi lần xuất, hãy thu hẹp phạm vi.")
    attempt_ids = [r.current_attempt_id for r in rows if r.current_attempt_id and r.current_attempt.status == "GRADED"]
    deductions = _latest_visibility_deductions(attempt_ids)
    buf = io.StringIO()
    buf.write("\ufeff")
    writer = csv.writer(buf)
    writer.writerow(["Mã học sinh", "Học sinh", "Lớp", "Bài tập", "Điểm / 10", "Trạng thái", "Hạn nộp", "Thời gian nộp"])
    for recipient in rows:
        attempt = recipient.current_attempt
        score = ""
        status = "Chưa nộp"
        if attempt and attempt.status in ("SUBMITTED", "GRADED"):
            status = "Nộp muộn" if attempt.is_late else "Đã nộp"
            releases = list(attempt.grade_releases.all())
            if releases and releases[0].max_points > 0:
                score = round(releases[0].total_points / releases[0].max_points * 10, 1)
            elif attempt.status == "GRADED":
                graded = [r for r in attempt.responses.all() if hasattr(r, "grade")]
                maximum = sum((r.question.max_points for r in graded), Decimal("0"))
                if maximum:
                    earned = max(Decimal("0"), sum((r.grade.points for r in graded), Decimal("0")) - deductions.get(attempt.id, Decimal("0")))
                    score = round(earned / maximum * 10, 1)
        names = sorted({c.class_name_snapshot for c in recipient.recipientenglishclass_set.all() if not class_id or c.english_class_id == class_id})
        profile = getattr(recipient.student, "student_profile", None)
        writer.writerow([_safe_csv_cell(getattr(profile, "student_ref", "")), _safe_csv_cell(recipient.student.display_name), _safe_csv_cell(", ".join(names)), _safe_csv_cell(recipient.assignment.title), score, status, timezone.localtime(recipient.due_at_override or recipient.assignment.due_at).strftime("%d/%m/%Y %H:%M"), timezone.localtime(attempt.submitted_at).strftime("%d/%m/%Y %H:%M") if attempt and attempt.submitted_at else ""])
    AuditEvent.objects.create(actor=actor, action="reports.export_csv", target_type="report", metadata={"rows": len(rows), "scope": scope})
    return buf.getvalue()


def export_progress_csv(actor, from_str=None, to_str=None, school_id=None, grade=None, school_class_id=None, english_class_id=None, student_id=None, q=None):
    """Export filtered progress table to UTF-8 BOM CSV with formula-injection protection (max 1,000 students)."""
    report = owner_progress_report(actor, from_str=from_str, to_str=to_str, school_id=school_id, grade=grade, school_class_id=school_class_id, english_class_id=english_class_id, student_id=student_id, q=q)
    if len(report["students"]) > 1000:
        raise ValidationError("Tối đa xuất 1.000 học sinh mỗi lần, hãy thu hẹp bộ lọc.")
    buf = io.StringIO()
    buf.write("\ufeff")
    writer = csv.writer(buf)
    writer.writerow([
        "student_ref",
        "display_name",
        "avg_score",
        "assigned",
        "submitted",
        "late_count",
        "missing_count",
        "cheat_count",
        "overdue_28d",
        "needs_pacing_support",
        "weak_areas",
        "recommendations",
        "is_ielts",
        "reading_pct",
        "listening_pct",
        "writing_pct",
        "speaking_pct",
    ])
    for row in report["students"]:
        writer.writerow([
            _safe_csv_cell(row["student_ref"]),
            _safe_csv_cell(row["display_name"]),
            row["avg_score"] if row["avg_score"] is not None else "",
            row["assigned"],
            row["submitted"],
            row["late_count"],
            row["missing_count"],
            row["cheat_count"],
            row["overdue_28d"],
            "YES" if row["needs_pacing_support"] else "NO",
            _safe_csv_cell(row["weak_summary"]),
            _safe_csv_cell(row["recommendation_summary"]),
            "YES" if row["is_ielts"] else "NO",
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
        if a.opens_at < period.start_at or (a.late_until is None or a.late_until > period.end_at):
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
