"""Automatic classification and database tagging for questions and course exercises."""
import re
from django.db import transaction

from .models import CourseExercise, CourseTag, Question, QuestionTag, Tag

GENERIC_TOPIC_PLACEHOLDERS = {"ôn tập chung", "general", "khác"}
IGNORED_DB_SCAN_CODES = {
    "PRIMARY_TAG",
    "SECONDARY_TAG",
    "HIGH_SCHOOL_TAG",
    "ENTRANCE_10_TAG",
    "THPT_QG_TAG",
    "IELTS_TAG",
    "TOEIC_TAG",
    "TESOL_TAG",
    "EXAM_PRACTICE",
    "READING",
    "LISTENING",
    "WRITING",
    "SPEAKING",
}
IGNORED_DB_SCAN_NAMES = {"ôn tập chung", "bài mẫu", "đề mẫu", "đọc", "nghe", "nói", "viết"}

# (compiled regex, question_topic_names, course_tag_specs[(code, name, kind)])
AUTO_TAG_RULES = (
    (
        re.compile(
            r"(?i)(?:quá\s*khứ\s*đơn|quá\s*khứ|past\s+simple|\b(?:yesterday|ago|last\s+(?:week|month|year|night|weekend|summer|sunday|monday|tuesday|wednesday|thursday|friday|saturday)|didn'?t|did\s+not|did|was|were|went|saw|ate|bought|took|made|had|wrote|came|gave)\b)"
        ),
        ("Bài chia thì", "Quá khứ đơn"),
        (("TENSES", "Các thì", CourseTag.Kind.GRAMMAR), ("PAST_SIMPLE", "Quá khứ đơn", CourseTag.Kind.GRAMMAR)),
    ),
    (
        re.compile(
            r"(?i)(?!.*(?:phát\s*âm|gạch\s*chân|/ɪd/|/d/|/t/))\b(?!red\b|bed\b|fed\b|led\b|wed\b|shed\b|need\b|seed\b|speed\b|feed\b|bleed\b|breed\b|greed\b|weed\b|indeed\b|hundred\b|used\b|tired\b|excited\b|interested\b|bored\b)[a-z]{3,}ed\b"
        ),
        ("Bài chia thì", "Quá khứ đơn"),
        (("TENSES", "Các thì", CourseTag.Kind.GRAMMAR), ("PAST_SIMPLE", "Quá khứ đơn", CourseTag.Kind.GRAMMAR)),
    ),
    (
        re.compile(
            r"(?i)(?:hiện\s*tại\s*đơn|present\s+simple|\b(?:usually|always|often|sometimes|seldom|every\s+(?:day|week|morning|evening|year)|don'?t|doesn'?t|goes|watches|plays|studies|does)\b)"
        ),
        ("Bài chia thì", "Hiện tại đơn"),
        (("TENSES", "Các thì", CourseTag.Kind.GRAMMAR), ("PRESENT_SIMPLE", "Hiện tại đơn", CourseTag.Kind.GRAMMAR)),
    ),
    (
        re.compile(
            r"(?i)(?:hiện\s*tại\s*tiếp\s*diễn|tiếp\s*diễn|present\s+continuous|\b(?:at\s+the\s+moment|right\s+now|look!|listen!)\b|\b(?:am|is|are|was|were)\s+[a-z]{2,}ing\b)"
        ),
        ("Bài chia thì", "Hiện tại tiếp diễn"),
        (("TENSES", "Các thì", CourseTag.Kind.GRAMMAR), ("PRESENT_CONTINUOUS", "Hiện tại tiếp diễn", CourseTag.Kind.GRAMMAR)),
    ),
    (
        re.compile(
            r"(?i)(?:hiện\s*tại\s*hoàn\s*thành|present\s+perfect|\b(?:already|yet|since)\b|\b(?:have|has|haven'?t|hasn'?t)\s+(?:just|ever|already|never|been|done|seen|gone|made|taken|given|written|[a-z]{3,}ed)\b)"
        ),
        ("Bài chia thì", "Hiện tại hoàn thành"),
        (("TENSES", "Các thì", CourseTag.Kind.GRAMMAR), ("PRESENT_PERFECT", "Hiện tại hoàn thành", CourseTag.Kind.GRAMMAR)),
    ),
    (
        re.compile(
            r"(?i)(?:thì\s*tương\s*lai|tương\s*lai\s*đơn|future\s+simple|\b(?:tomorrow|next\s+(?:week|month|year|summer)|won'?t|going\s+to)\b)"
        ),
        ("Bài chia thì", "Thì tương lai"),
        (("TENSES", "Các thì", CourseTag.Kind.GRAMMAR), ("FUTURE_SIMPLE", "Thì tương lai", CourseTag.Kind.GRAMMAR)),
    ),
    (
        re.compile(r"(?i)(?:chia\s*thì|chia\s*động\s*từ|dạng\s*đúng\s*của\s*động\s*từ|các\s*thì|correct\s+tense|verb\s+tense)"),
        ("Bài chia thì",),
        (("TENSES", "Các thì", CourseTag.Kind.GRAMMAR),),
    ),
    (
        re.compile(r"(?i)(?:\bto\s+be\b|đại\s*từ|\bwhose\b)"),
        ("Động từ To Be & Đại từ",),
        (("TENSES", "Các thì", CourseTag.Kind.GRAMMAR),),
    ),
    (
        re.compile(
            r"(?i)(?:bị\s*động|passive|\b(?:is|are|was|were|be|been|being)\s+(?:[a-z]{3,}ed|written|built|made|spoken|given|taken|sold|seen|eaten|known)\b)"
        ),
        ("Câu bị động",),
        (("PASSIVE", "Câu bị động", CourseTag.Kind.GRAMMAR),),
    ),
    (
        re.compile(r"(?i)(?:câu\s*điều\s*kiện|điều\s*kiện\s*loại|conditional|\bunless\b|\bwould\s+have\b)"),
        ("Câu điều kiện",),
        (("CONDITIONALS", "Câu điều kiện", CourseTag.Kind.GRAMMAR),),
    ),
    (
        re.compile(r"(?i)(?:tường\s*thuật|câu\s*gián\s*tiếp|reported\s+speech|\b(?:said\s+that|told\s+(?:me|him|her|them)\s+that|asked\s+(?:if|whether))\b)"),
        ("Câu tường thuật",),
        (("REPORTED_SPEECH", "Câu tường thuật", CourseTag.Kind.GRAMMAR),),
    ),
    (
        re.compile(r"(?i)(?:mệnh\s*đề\s*quan\s*hệ|relative\s+clause|\bwhom\b)"),
        ("Mệnh đề quan hệ",),
        (("RELATIVE_CLAUSES", "Mệnh đề quan hệ", CourseTag.Kind.GRAMMAR),),
    ),
    (
        re.compile(r"(?i)(?:so\s*sánh|comparative|superlative|\b(?:more\s+[a-z]+\s+than|the\s+most\s+[a-z]+|the\s+best|the\s+worst|as\s+[a-z]+\s+as)\b)"),
        ("So sánh hơn & nhất",),
        (),
    ),
    (
        re.compile(r"(?i)(?:danh\s*động\s*từ|động\s*từ\s*nguyên\s*mẫu|gerund|infinitive|\bwould\s+like\s+to\b|\b(?:enjoy|avoid|suggest)\s+[a-z]+ing\b)"),
        ("Danh động từ & Động từ nguyên mẫu",),
        (("GERUND_INFINITIVE", "Danh động từ & Động từ nguyên mẫu", CourseTag.Kind.GRAMMAR),),
    ),
    (
        re.compile(r"(?i)(?:đảo\s*ngữ|inversion|\b(?:not\s+only|no\s+sooner)\b)"),
        ("Đảo ngữ",),
        (("INVERSION", "Đảo ngữ", CourseTag.Kind.GRAMMAR),),
    ),
    (
        re.compile(r"(?i)(?:câu\s*chẻ|cleft\s+sentence)"),
        ("Câu chẻ nhấn mạnh",),
        (("CLEFT_SENTENCE", "Câu chẻ nhấn mạnh", CourseTag.Kind.GRAMMAR),),
    ),
    (
        re.compile(r"(?i)(?:cụm\s*động\s*từ|phrasal\s+verb|\b(?:look\s+after|give\s+up|turn\s+on|turn\s+off|take\s+off|put\s+off)\b)"),
        ("Cụm động từ",),
        (("PHRASAL_VERBS", "Cụm động từ", CourseTag.Kind.VOCAB),),
    ),
    (
        re.compile(r"(?i)(?:collocation|cụm\s*từ\s*cố\s*định)"),
        ("Collocations",),
        (("COLLOCATIONS", "Cụm từ cố định", CourseTag.Kind.VOCAB),),
    ),
    (
        re.compile(r"(?i)(?:từ\s*đồng\s*nghĩa|từ\s*trái\s*nghĩa|synonym|antonym)"),
        ("Đồng nghĩa & Trái nghĩa",),
        (("SYNONYMS_ANTONYMS", "Đồng nghĩa & Trái nghĩa", CourseTag.Kind.VOCAB),),
    ),
    (
        re.compile(r"(?i)(?:dạng\s*từ|từ\s*loại|cấu\s*tạo\s*từ|word\s+form)"),
        ("Dạng từ",),
        (("WORD_FORM", "Dạng từ", CourseTag.Kind.VOCAB),),
    ),
    (
        re.compile(r"(?i)(?:phát\s*âm\s*đuôi\s*-?ed|đuôi\s*-?ed)"),
        ("Phát âm đuôi -ed", "Ngữ âm"),
        (("PRONUNCIATION", "Ngữ âm", CourseTag.Kind.EXAM),),
    ),
    (
        re.compile(r"(?i)(?:phát\s*âm\s*đuôi\s*-?s/-?es|đuôi\s*-?s/-?es)"),
        ("Phát âm đuôi -s/-es", "Ngữ âm"),
        (("PRONUNCIATION", "Ngữ âm", CourseTag.Kind.EXAM),),
    ),
    (
        re.compile(r"(?i)(?:trọng\s*âm|stress|âm\s*tiết)"),
        ("Trọng âm", "Ngữ âm"),
        (("STRESS", "Trọng âm", CourseTag.Kind.EXAM), ("PRONUNCIATION", "Ngữ âm", CourseTag.Kind.EXAM)),
    ),
    (
        re.compile(r"(?i)(?:ngữ\s*âm|phát\s*âm|pronunciation)"),
        ("Ngữ âm",),
        (("PRONUNCIATION", "Ngữ âm", CourseTag.Kind.EXAM),),
    ),
    (
        re.compile(r"(?i)(?:sắp\s*xếp|word\s*order|trật\s*tự\s*từ)"),
        ("Sắp xếp câu",),
        (("WORD_ORDER", "Sắp xếp câu", CourseTag.Kind.EXAM),),
    ),
    (
        re.compile(r"(?i)(?:viết\s*lại\s*câu|đổi\s*câu|sentence\s+transform|rewrite)"),
        ("Viết lại câu",),
        (("SENTENCE_TRANSFORM", "Viết lại câu", CourseTag.Kind.EXAM),),
    ),
    (
        re.compile(r"(?i)(?:nối\s*tranh|hình\s*ảnh|từ\s*vựng\s*hình\s*ảnh)"),
        ("Từ vựng & Nối tranh", "Từ vựng"),
        (("MATCHING", "Nối tranh & từ", CourseTag.Kind.EXAM), ("VOCABULARY", "Từ vựng", CourseTag.Kind.VOCAB)),
    ),
    (
        re.compile(
            r"(?i)(?:từ\s*vựng|màu\s*sắc|số\s*đếm|động\s*vật|đồ\s*vật|nghề\s*nghiệp|\b(?:color|colour|animal|sky|ship|boat|bird|fish|cat|dog)\b)"
        ),
        ("Từ vựng",),
        (("VOCABULARY", "Từ vựng", CourseTag.Kind.VOCAB),),
    ),
    (
        re.compile(r"(?i)(?:giao\s*tiếp|chào\s*hỏi|\b(?:hello|good\s+morning|how\s+are\s+you|thank\s+you)\b)"),
        ("Giao tiếp",),
        (("VOCABULARY", "Từ vựng", CourseTag.Kind.VOCAB),),
    ),
)

QUESTION_TYPE_DEFAULTS = {
    "STRESS_CHOICE": (("Trọng âm", "Ngữ âm"), (("STRESS", "Trọng âm", CourseTag.Kind.EXAM), ("PRONUNCIATION", "Ngữ âm", CourseTag.Kind.EXAM))),
    "WORD_ORDER": (("Sắp xếp câu",), (("WORD_ORDER", "Sắp xếp câu", CourseTag.Kind.EXAM),)),
    "MATCH_IMAGE": (("Từ vựng & Nối tranh", "Từ vựng"), (("MATCHING", "Nối tranh & từ", CourseTag.Kind.EXAM), ("VOCABULARY", "Từ vựng", CourseTag.Kind.VOCAB))),
    "SENTENCE_TRANSFORM": (("Viết lại câu",), (("SENTENCE_TRANSFORM", "Viết lại câu", CourseTag.Kind.EXAM),)),
    "TEXT": (("Viết tự luận",), ()),
    "AUDIO": (("Phát âm & Nói",), ()),
}


def _dedupe_ci(items):
    seen = set()
    result = []
    for item in items:
        clean = (item or "").strip()
        if not clean or len(clean) > 100:
            continue
        key = clean.casefold()
        if key not in seen:
            seen.add(key)
            result.append(clean)
    return result


def _match_existing_db_tag_names(blob):
    lower_blob = blob.casefold()
    matched_topics = []
    matched_course_tags = []

    for name in (
        Tag.objects.filter(kind=Tag.Kind.TOPIC, archived_at__isnull=True)
        .values_list("name", flat=True)
        .distinct()
    ):
        clean = (name or "").strip()
        if len(clean) < 3 or clean.casefold() in IGNORED_DB_SCAN_NAMES:
            continue
        if re.search(rf"(?<!\w){re.escape(clean.casefold())}(?!\w)", lower_blob):
            matched_topics.append(clean)

    for ctag in CourseTag.objects.exclude(code__in=IGNORED_DB_SCAN_CODES):
        clean = (ctag.name or "").strip()
        if len(clean) < 3 or clean.casefold() in IGNORED_DB_SCAN_NAMES:
            continue
        if re.search(rf"(?<!\w){re.escape(clean.casefold())}(?!\w)", lower_blob):
            matched_course_tags.append((ctag.code, ctag.name, ctag.kind))

    return matched_topics, matched_course_tags


def _question_correct_text(question):
    if question.type in ("SINGLE_CHOICE", "MULTIPLE_CHOICE", "STRESS_CHOICE"):
        correct_opts = [ak.option.content for ak in question.answer_keys.all() if ak.option_id]
        if correct_opts:
            return " ".join(correct_opts)
    if question.type == "MATCH_IMAGE":
        return " ".join(w.text for w in question.match_words.all())
    return " ".join(o.content for o in question.options.all())


def infer_question_topic_names(
    q_type,
    skill,
    prompt="",
    options_text="",
    explanation="",
    title_context="",
    manual_topics=None,
):
    """Return ordered list of TOPIC tag names combining manual input, grammar/type rules, and existing DB tags."""
    manual_clean = _dedupe_ci(manual_topics or [])
    non_generic_manual = [t for t in manual_clean if t.casefold() not in GENERIC_TOPIC_PLACEHOLDERS]

    question_blob = " ".join(x for x in (prompt, options_text, explanation, " ".join(non_generic_manual)) if x)
    full_blob = " ".join(x for x in (title_context, question_blob) if x)
    inferred = []

    if q_type in QUESTION_TYPE_DEFAULTS:
        inferred.extend(QUESTION_TYPE_DEFAULTS[q_type][0])

    for regex, topic_names, _ctags in AUTO_TAG_RULES:
        if regex.search(full_blob):
            inferred.extend(topic_names)

    db_topics, _db_ctags = _match_existing_db_tag_names(question_blob)
    inferred.extend(db_topics)

    combined = _dedupe_ci([*non_generic_manual, *inferred])
    if combined:
        return combined
    if skill == "LISTENING" and q_type in ("SINGLE_CHOICE", "MULTIPLE_CHOICE"):
        return ["Nghe hiểu"]
    if q_type in ("SINGLE_CHOICE", "MULTIPLE_CHOICE"):
        return ["Ngữ pháp & Từ vựng"]
    return manual_clean or ["Ôn tập chung"]


def infer_question_error_names(
    q_type,
    skill,
    prompt="",
    options_text="",
    explanation="",
    manual_errors=None,
    has_passage=False,
):
    """Suggest a question's topic only when its type or prompt identifies it clearly."""
    manual_clean = _dedupe_ci(manual_errors or [])
    if manual_clean:
        return manual_clean

    blob = " ".join(x for x in (prompt, explanation) if x)
    if q_type == "STRESS_CHOICE":
        return ["Phát âm: trọng âm của từ"]
    if q_type == "WORD_ORDER":
        return ["Sắp xếp câu: trật tự từ"]
    if q_type == "SENTENCE_TRANSFORM":
        if re.search(r"(?i)(?:tường\s*thuật|gián\s*tiếp|reported\s+speech)", blob):
            return ["Ngữ pháp: câu tường thuật"]
        return ["Viết lại câu"]
    if q_type == "MATCH_IMAGE":
        return ["Từ vựng: nối tranh và từ"]
    if q_type == "TEXT":
        return ["Viết: diễn đạt nội dung"]
    if q_type == "AUDIO":
        return ["Nói: diễn đạt và phát âm"]
    if re.search(r"(?i)(?:closest\s+(?:in\s+meaning|to)|synonym|đồng\s*nghĩa|từ\s+gần\s+nghĩa)", blob):
        return ["Từ vựng: từ đồng nghĩa"]
    if re.search(r"(?i)(?:opposite\s+(?:in\s+meaning|to)|antonym|trái\s*nghĩa)", blob):
        return ["Từ vựng: từ trái nghĩa"]
    if re.search(r"(?i)(?:danh\s*từ\s*số\s*nhiều|plural\s+nouns?)", blob):
        return ["Ngữ pháp: danh từ số nhiều"]
    if re.search(r"(?i)(?:hiện\s*tại\s*đơn|present\s+simple)", blob):
        return ["Ngữ pháp: thì hiện tại đơn"]
    if re.search(r"(?i)(?:quá\s*khứ\s*đơn|past\s+simple)", blob):
        return ["Ngữ pháp: thì quá khứ đơn"]
    if re.search(r"(?i)(?:bị\s*động|passive\s+voice)", blob):
        return ["Ngữ pháp: câu bị động"]
    if re.search(r"(?i)(?:trọng\s*âm|word\s+stress)", blob):
        return ["Phát âm: trọng âm của từ"]
    if re.search(r"(?i)(?:pronounced\s+differently|phát\s*âm)", blob):
        return ["Phát âm: phân biệt âm"]
    if re.search(r"(?i)(?:từ\s+tiếng\s+anh\s+có\s+nghĩa|từ\s+vựng|vocabulary)", blob):
        return ["Từ vựng: nghĩa của từ"]
    if has_passage and skill in ("READING", "LISTENING"):
        return ["Đọc hiểu: thông tin trong bài" if skill == "READING" else "Nghe hiểu: thông tin trong bài"]
    return []


def infer_course_tag_specs_from_text(text, question_types=None):
    """Infer CourseTag tuples (code, name, kind) from title/question text and question types."""
    specs = []
    for qtype in question_types or ():
        if qtype in QUESTION_TYPE_DEFAULTS:
            specs.extend(QUESTION_TYPE_DEFAULTS[qtype][1])

    if text:
        for regex, _tnames, ctag_specs in AUTO_TAG_RULES:
            if regex.search(text):
                specs.extend(ctag_specs)
        _db_topics, db_ctags = _match_existing_db_tag_names(text)
        specs.extend(db_ctags)

    seen_codes = set()
    seen_kind_names = set()
    unique = []
    for code, name, kind in specs:
        kn = (kind, name.casefold())
        if code in seen_codes or kn in seen_kind_names:
            continue
        seen_codes.add(code)
        seen_kind_names.add(kn)
        unique.append((code, name, kind))
    return unique


def get_or_create_topic_tag(skill, name):
    clean = (name or "").strip()[:100]
    existing = Tag.objects.filter(kind=Tag.Kind.TOPIC, skill=skill, name__iexact=clean).first()
    if existing:
        return existing, False
    canonical = Tag.objects.filter(kind=Tag.Kind.TOPIC, name__iexact=clean).values_list("name", flat=True).first()
    tag, created = Tag.objects.get_or_create(kind=Tag.Kind.TOPIC, skill=skill, name=canonical or clean)
    return tag, created


def get_or_create_error_tag(skill, name):
    clean = (name or "").strip()[:100]
    existing = Tag.objects.filter(kind=Tag.Kind.ERROR, skill=skill, name__iexact=clean).first()
    if existing:
        return existing, False
    canonical = Tag.objects.filter(kind=Tag.Kind.ERROR, name__iexact=clean).values_list("name", flat=True).first()
    tag, created = Tag.objects.get_or_create(kind=Tag.Kind.ERROR, skill=skill, name=canonical or clean)
    return tag, created


def get_or_create_course_tag(code, name, kind):
    clean_name = (name or "").strip()[:100]
    tag = CourseTag.objects.filter(kind=kind, name__iexact=clean_name).first()
    if tag:
        return tag
    tag = CourseTag.objects.filter(code=code[:48]).first()
    if tag:
        return tag
    return CourseTag.objects.create(code=code[:48], name=clean_name, kind=kind)


def apply_auto_tags_to_question(question, title_context="", manual_topics=None, manual_errors=None):
    """Infer and attach TOPIC and ERROR Tag rows in DB for the given Question."""
    options_text = _question_correct_text(question)
    existing_topics = [qt.tag.name for qt in question.question_tags.select_related("tag").filter(tag__kind=Tag.Kind.TOPIC)]
    all_manual = list(manual_topics) if manual_topics is not None else existing_topics

    names = infer_question_topic_names(
        question.type,
        question.skill,
        prompt=question.prompt,
        options_text=options_text,
        explanation=question.explanation,
        title_context=title_context,
        manual_topics=all_manual,
    )
    attached = []
    for name in names:
        tag, _ = get_or_create_topic_tag(question.skill, name)
        if tag.archived_at:
            continue
        QuestionTag.objects.get_or_create(question=question, tag=tag)
        attached.append(tag)

    existing_active_errors = [
        qt.tag
        for qt in question.question_tags.select_related("tag").all()
        if qt.tag.kind == Tag.Kind.ERROR and qt.tag.skill == question.skill and not qt.tag.archived_at
    ]
    if not existing_active_errors or manual_errors:
        err_names = infer_question_error_names(
            question.type,
            question.skill,
            prompt=question.prompt,
            options_text=options_text,
            explanation=question.explanation,
            manual_errors=manual_errors,
            has_passage=bool(question.passage_id),
        )
        for ename in err_names:
            etag, _ = get_or_create_error_tag(question.skill, ename)
            if etag.archived_at:
                continue
            QuestionTag.objects.get_or_create(question=question, tag=etag)
            attached.append(etag)
    return attached


def sync_course_exercise_auto_tags(exercise, extra_text=""):
    """Infer and attach matching CourseTag rows to a CourseExercise from its assignment & questions."""
    assignment = exercise.assignment
    version = assignment.version
    questions = list(version.questions.prefetch_related("options", "answer_keys__option", "match_words"))
    parts = [assignment.title, version.exam.title, extra_text]
    q_types = []
    for q in questions:
        q_types.append(q.type)
        parts.extend((q.prompt, q.explanation, _question_correct_text(q)))
    blob = " ".join(p for p in parts if p)
    specs = infer_course_tag_specs_from_text(blob, question_types=q_types)
    if not specs:
        return []
    added = []
    existing_ids = set(exercise.tags.values_list("id", flat=True))
    for code, name, kind in specs:
        ctag = get_or_create_course_tag(code, name, kind)
        if ctag.id not in existing_ids:
            exercise.tags.add(ctag)
            existing_ids.add(ctag.id)
            added.append(ctag)
    return added


def sync_version_and_exercise_auto_tags(version, title_context="", auto_attach_course_tags=True):
    """Ensure every Question on ExamVersion and every linked CourseExercise has auto-inferred DB tags."""
    from apps.assignments.models import Assignment

    assignments = list(Assignment.objects.filter(version=version))
    asg_titles = " ".join(a.title for a in assignments)
    combined_title = " ".join(t for t in (version.exam.title, asg_titles, title_context) if t)

    questions = list(
        version.questions.prefetch_related("options", "answer_keys__option", "match_words", "question_tags__tag").all()
    )
    for q in questions:
        apply_auto_tags_to_question(q, title_context=combined_title)

    if auto_attach_course_tags:
        for ce in CourseExercise.objects.filter(assignment__version=version).select_related("assignment__version__exam"):
            sync_course_exercise_auto_tags(ce, extra_text=title_context)


@transaction.atomic
def backfill_all_auto_tags():
    """Backfill QuestionTag and CourseTag associations across all existing questions and course exercises."""
    from apps.assignments.models import Assignment

    titles_by_version = {}
    for vid, title in Assignment.objects.values_list("version_id", "title"):
        titles_by_version.setdefault(vid, []).append(title)

    q_count = 0
    for q in Question.objects.select_related("version__exam").prefetch_related("options", "answer_keys__option", "match_words", "question_tags__tag"):
        ctx = " ".join([q.version.exam.title, *titles_by_version.get(q.version_id, [])])
        apply_auto_tags_to_question(q, title_context=ctx)
        q_count += 1

    ex_count = 0
    for ce in CourseExercise.objects.select_related("assignment__version__exam").prefetch_related("tags"):
        sync_course_exercise_auto_tags(ce)
        ex_count += 1

    return {"questions_processed": q_count, "exercises_processed": ex_count}
