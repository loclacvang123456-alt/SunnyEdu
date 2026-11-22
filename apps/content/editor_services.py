"""Owner exam/version/question/passage/tag editing and prompt audio asset services."""
import hashlib
import json
import os
import shutil
import subprocess
import uuid
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import AuditEvent

from .models import (
    AnswerKeyOption,
    Asset,
    Exam,
    ExamVersion,
    MatchImage,
    MatchWord,
    MatchKey,
    Passage,
    Question,
    QuestionOption,
    QuestionTag,
    RubricCriterion,
    Tag,
)
from .services import LEVELS, RUBRICS

ALLOWED_TYPE_SKILLS = {
    "SINGLE_CHOICE": {"READING", "LISTENING"},
    "MULTIPLE_CHOICE": {"READING", "LISTENING"},
    "WORD_ORDER": {"READING", "WRITING"},
    "STRESS_CHOICE": {"READING", "LISTENING"},
    "MATCH_IMAGE": {"READING", "LISTENING"},
    "SENTENCE_TRANSFORM": {"READING", "WRITING"},
    "TEXT": {"WRITING"},
    "AUDIO": {"SPEAKING"},
}
MAX_PROMPT_AUDIO_BYTES = 30 * 1024 * 1024
MAX_PROMPT_AUDIO_MS = 10 * 60 * 1000


def _lock_draft_version(owner, version_id, expected_revision, allow_published=False):
    version = ExamVersion.objects.select_for_update().select_related("exam").get(pk=version_id, exam__created_by=owner)
    if version.status != ExamVersion.Status.DRAFT and not (allow_published and version.status == ExamVersion.Status.PUBLISHED):
        raise ValidationError("Chỉ phiên bản DRAFT mới được sửa.")
    if version.revision != expected_revision:
        raise ValidationError("Version revision conflict.")
    return version


def _bump_version(version):
    version.revision += 1
    version.save(update_fields=["revision", "updated_at"])
    return version


@transaction.atomic
def update_exam_title(owner, exam_id, title):
    clean = (title or "").strip()
    if not 1 <= len(clean) <= 200:
        raise ValidationError("Tên đề phải có từ 1 đến 200 ký tự.")
    exam = Exam.objects.select_for_update().get(pk=exam_id, created_by=owner)
    exam.title = clean
    exam.save(update_fields=["title", "updated_at"])
    from .auto_tagging import sync_version_and_exercise_auto_tags
    for ver in exam.versions.all():
        sync_version_and_exercise_auto_tags(ver, title_context=clean)
    AuditEvent.objects.create(actor=owner, action="exam.rename", target_type="exam", target_id=exam.id)
    return exam


@transaction.atomic
def archive_exam(owner, exam_id):
    exam = Exam.objects.select_for_update().get(pk=exam_id, created_by=owner)
    if not exam.archived_at:
        exam.archived_at = timezone.now()
        exam.save(update_fields=["archived_at", "updated_at"])
        AuditEvent.objects.create(actor=owner, action="exam.archive", target_type="exam", target_id=exam.id)
    return exam


@transaction.atomic
def create_draft_version(owner, exam_id):
    exam = Exam.objects.select_for_update().get(pk=exam_id, created_by=owner, archived_at__isnull=True)
    latest = exam.versions.order_by("-number").first()
    version = ExamVersion.objects.create(exam=exam, number=latest.number + 1 if latest else 1)
    AuditEvent.objects.create(actor=owner, action="version.create", target_type="exam_version", target_id=version.id)
    return version


@transaction.atomic
def clone_version(owner, version_id):
    """Clone any ExamVersion into a new DRAFT version copying passages, questions, options, keys, rubrics, and tags."""
    source = ExamVersion.objects.select_related("exam").get(pk=version_id, exam__created_by=owner)
    exam = Exam.objects.select_for_update().get(pk=source.exam_id)
    latest = exam.versions.order_by("-number").first()
    target = ExamVersion.objects.create(exam=exam, number=latest.number + 1)

    passage_map = {}
    for p in source.passages.all():
        passage_map[p.id] = Passage.objects.create(
            version=target,
            ref=p.ref,
            text_body=p.text_body,
            audio_asset=p.audio_asset,
            transcript=p.transcript,
        )

    for q in source.questions.prefetch_related("options", "answer_keys", "criteria", "question_tags__tag").order_by("position"):
        new_q = Question.objects.create(
            version=target,
            position=q.position,
            type=q.type,
            skill=q.skill,
            difficulty=q.difficulty,
            prompt=q.prompt,
            max_points=q.max_points,
            passage=passage_map.get(q.passage_id),
            explanation=q.explanation,
            pirate_game=q.pirate_game,
        )
        opt_map = {}
        for opt in q.options.all():
            opt_map[opt.id] = QuestionOption.objects.create(question=new_q, key=opt.key, position=opt.position, content=opt.content)
        for ak in q.answer_keys.all():
            AnswerKeyOption.objects.create(question=new_q, option=opt_map[ak.option_id])
        for image in q.match_images.select_related("answer_key__word").all():
            new_image = MatchImage.objects.create(question=new_q, image_asset=image.image_asset, position=image.position)
            word = image.answer_key.word
            new_word = MatchWord.objects.create(question=new_q, text=word.text, position=word.position)
            MatchKey.objects.create(image=new_image, word=new_word)
        for crit in q.criteria.all():
            RubricCriterion.objects.create(
                question=new_q,
                key=crit.key,
                position=crit.position,
                label=crit.label,
                level_descriptions=crit.level_descriptions,
            )
        for qt in q.question_tags.all():
            if not qt.tag.archived_at:
                QuestionTag.objects.create(question=new_q, tag=qt.tag)

    AuditEvent.objects.create(actor=owner, action="version.clone", target_type="exam_version", target_id=target.id, metadata={"source_version_id": str(source.id)})
    return target


@transaction.atomic
def archive_version(owner, version_id):
    version = ExamVersion.objects.select_for_update().get(pk=version_id, exam__created_by=owner)
    version.status = ExamVersion.Status.ARCHIVED
    version.revision += 1
    version.save(update_fields=["status", "revision", "updated_at"])
    AuditEvent.objects.create(actor=owner, action="version.archive", target_type="exam_version", target_id=version.id)
    return version


@transaction.atomic
def delete_draft_version(owner, version_id):
    version = ExamVersion.objects.select_for_update().get(pk=version_id, exam__created_by=owner)
    if version.status != ExamVersion.Status.DRAFT or version.assignment_set.exists():
        raise ValidationError("Chỉ xóa được phiên bản DRAFT chưa được giao bài.")
    version.delete()


@transaction.atomic
def upsert_passage(owner, version_id, expected_revision, data, passage_id=None, allow_published=False):
    version = _lock_draft_version(owner, version_id, expected_revision, allow_published=allow_published)
    ref = (data.get("ref") or "").strip()
    text_body = (data.get("text_body") or "").strip()
    transcript = (data.get("transcript") or "").strip()
    audio_id = data.get("audio_asset_id") or None
    if not 1 <= len(ref) <= 40:
        raise ValidationError("Mã tài liệu (ref) phải có 1..40 ký tự.")
    if len(text_body) > 20000:
        raise ValidationError("Đoạn văn tối đa 20.000 ký tự.")
    audio = None
    if audio_id:
        audio = Asset.objects.select_for_update().filter(pk=audio_id, uploaded_by=owner, purpose=Asset.Purpose.PROMPT_AUDIO, status=Asset.Status.READY).first()
        if not audio:
            raise ValidationError("Tệp nghe không tồn tại hoặc chưa READY.")
    if not text_body and not audio:
        raise ValidationError("Tài liệu cần nội dung văn bản hoặc tệp nghe.")
    try:
        if passage_id:
            passage = Passage.objects.select_for_update().get(pk=passage_id, version=version)
            passage.ref, passage.text_body, passage.audio_asset, passage.transcript = ref, text_body, audio, transcript
            passage.save(update_fields=["ref", "text_body", "audio_asset", "transcript", "updated_at"])
        else:
            passage = Passage.objects.create(version=version, ref=ref, text_body=text_body, audio_asset=audio, transcript=transcript)
    except IntegrityError as exc:
        raise ValidationError("Mã tài liệu (ref) bị trùng trong phiên bản.") from exc
    _bump_version(version)
    return passage, version


@transaction.atomic
def delete_passage(owner, passage_id, expected_revision, allow_published=False):
    passage = Passage.objects.select_related("version").get(pk=passage_id, version__exam__created_by=owner)
    version = _lock_draft_version(owner, passage.version_id, expected_revision, allow_published=allow_published)
    if passage.questions.exists():
        raise ValidationError("Không thể xóa tài liệu đang được câu hỏi tham chiếu.")
    passage.delete()
    return _bump_version(version)


def _validate_question_payload(version, data):
    q_type = data.get("type")
    skill = data.get("skill")
    difficulty = data.get("difficulty")
    prompt = (data.get("prompt") or "").strip()
    explanation = (data.get("explanation") or "").strip()
    if skill not in ALLOWED_TYPE_SKILLS.get(q_type, set()):
        raise ValidationError("Loại câu và kỹ năng không khớp ma trận BR-03.")
    if difficulty not in Question.Difficulty.values:
        raise ValidationError("Độ khó không hợp lệ.")
    if not 1 <= len(prompt) <= 10000:
        raise ValidationError("Nội dung câu hỏi phải từ 1..10.000 ký tự.")
    try:
        max_points = Decimal(str(data.get("max_points")))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError("Điểm tối đa không hợp lệ.") from exc
    if not max_points.is_finite() or not Decimal("0.01") <= max_points <= Decimal("100.00") or max_points.as_tuple().exponent < -2:
        raise ValidationError("Điểm câu phải từ 0.01 đến 100.00.")

    passage = None
    if data.get("passage_id"):
        passage = Passage.objects.filter(pk=data["passage_id"], version=version).first()
        if not passage:
            raise ValidationError("Tài liệu không thuộc phiên bản này.")
    if skill == "LISTENING" and (not passage or not passage.audio_asset or passage.audio_asset.status != Asset.Status.READY):
        raise ValidationError("Câu Listening cần tài liệu có tệp audio READY.")

    options = []
    answers = []
    match_pairs = []
    if q_type == "MATCH_IMAGE":
        raw_pairs = data.get("match_pairs")
        if not isinstance(raw_pairs, list) or not 2 <= len(raw_pairs) <= 6:
            raise ValidationError("Cần từ 2 đến 6 cặp tranh và từ.")
        seen_assets, seen_words = set(), set()
        for pair in raw_pairs:
            if not isinstance(pair, dict) or not isinstance(pair.get("word"), str):
                raise ValidationError("Cặp tranh và từ không hợp lệ.")
            word = pair["word"].strip()
            try:
                asset_id = str(uuid.UUID(str(pair.get("image_asset_id", ""))))
            except (ValueError, TypeError, AttributeError) as exc:
                raise ValidationError("Mã ảnh không hợp lệ.") from exc
            if not 1 <= len(word) <= 200 or word.casefold() in seen_words or asset_id in seen_assets:
                raise ValidationError("Mỗi cặp cần ảnh và từ khác nhau, từ tối đa 200 ký tự.")
            seen_assets.add(asset_id)
            seen_words.add(word.casefold())
            match_pairs.append((asset_id, word))
        assets = {str(a.id): a for a in Asset.objects.select_for_update().filter(id__in=sorted(seen_assets), uploaded_by=version.exam.created_by, purpose=Asset.Purpose.PROMPT_IMAGE, status=Asset.Status.READY).order_by('id')}
        if len(assets) != len(seen_assets):
            raise ValidationError("Ảnh không tồn tại, không thuộc giáo viên hoặc chưa sẵn sàng.")
        match_pairs = [(assets[asset_id], word) for asset_id, word in match_pairs]
    if q_type == "STRESS_CHOICE":
        syllables = data.get("stress_syllables")
        index = data.get("correct_syllable_index")
        if not isinstance(syllables, list) or not 2 <= len(syllables) <= 10:
            raise ValidationError("Nhập từ 2 đến 10 âm tiết theo thứ tự của từ.")
        if type(index) is not int or not 1 <= index <= len(syllables):
            raise ValidationError("Chọn vị trí âm tiết mang trọng âm hợp lệ.")
        for idx, syllable in enumerate(syllables):
            if not isinstance(syllable, str) or not syllable.strip() or len(syllable.strip()) > 80 or any(c.isspace() for c in syllable.strip()):
                raise ValidationError("Mỗi âm tiết phải có từ 1 đến 80 ký tự và không chứa khoảng trắng.")
            options.append((chr(ord("A") + idx), idx + 1, syllable.strip()))
        answers = [chr(ord("A") + index - 1)]
    if q_type == "WORD_ORDER":
        tokens = data.get("word_tokens")
        if not isinstance(tokens, list) or not 2 <= len(tokens) <= 20:
            raise ValidationError("Nhập từ 2 đến 20 ô từ theo thứ tự đúng.")
        for idx, token in enumerate(tokens):
            if not isinstance(token, str) or not token.strip() or len(token.strip()) > 80:
                raise ValidationError("Mỗi ô từ phải có từ 1 đến 80 ký tự.")
            options.append((chr(ord("A") + idx), idx + 1, token.strip()))
    if q_type == "SENTENCE_TRANSFORM":
        std_ans = (data.get("standard_answer") or (data.get("options") and data["options"][0].get("content")) or "").strip()
        if not std_ans or len(std_ans) > 2000:
            raise ValidationError("Giáo viên cần nhập câu trả lời chuẩn (tối đa 2.000 ký tự).")
        options.append(("A", 1, std_ans))
        answers = ["A"]
    if q_type in ("SINGLE_CHOICE", "MULTIPLE_CHOICE"):
        raw_opts = data.get("options") or []
        if not isinstance(raw_opts, list) or not 2 <= len(raw_opts) <= 6:
            raise ValidationError("Câu trắc nghiệm cần từ 2 đến 6 lựa chọn.")
        for idx, item in enumerate(raw_opts):
            key = "ABCDEF"[idx]
            content = (item.get("content") if isinstance(item, dict) else str(item)).strip()
            if not 1 <= len(content) <= 2000:
                raise ValidationError(f"Lựa chọn {key} phải có 1..2.000 ký tự.")
            options.append((key, idx + 1, content))
        answers = list(dict.fromkeys(data.get("correct_options") or []))
        valid_keys = {k for k, _, _ in options}
        if not set(answers) <= valid_keys or (len(answers) != 1 if q_type == "SINGLE_CHOICE" else len(answers) < 2):
            raise ValidationError("Đáp án đúng không hợp lệ.")

    criteria = []
    if q_type in ("TEXT", "AUDIO"):
        raw_crit = data.get("criteria")
        if raw_crit:
            if not isinstance(raw_crit, list) or len(raw_crit) != 4:
                raise ValidationError("Cần đúng 4 tiêu chí chấm cho Writing/Speaking.")
            for idx, item in enumerate(raw_crit, 1):
                label = (item.get("label") or "").strip()
                descs = item.get("level_descriptions") or {}
                if not 1 <= len(label) <= 120 or set(descs) != {"0", "1", "2", "3", "4"} or any(not str(descs[k]).strip() for k in descs):
                    raise ValidationError("Mỗi tiêu chí cần tên và đủ mô tả mức 0..4.")
                criteria.append((item.get("key") or f"c{idx}", idx, label, {k: str(descs[k]).strip() for k in ("0", "1", "2", "3", "4")}))
        else:
            for idx, (key, label) in enumerate(RUBRICS[q_type], 1):
                criteria.append((key, idx, label, dict(LEVELS)))

    pirate_game = data.get("pirate_game")
    if pirate_game is not None and type(pirate_game) is not bool:
        raise ValidationError("Chế độ bắn tàu không hợp lệ.")
    if pirate_game is True and (q_type != "SINGLE_CHOICE" or passage):
        raise ValidationError("Bắn tàu chỉ hỗ trợ câu trắc nghiệm một đáp án độc lập.")

    topic_names = [x.strip() for x in (data.get("topic_tags") or []) if isinstance(x, str) and x.strip()]
    error_names = [x.strip() for x in (data.get("error_tags") or []) if isinstance(x, str) and x.strip()]
    if any(len(n) > 100 for n in topic_names + error_names):
        raise ValidationError("Tên tag tối đa 100 ký tự.")

    from apps.assignments.models import Assignment
    from .auto_tagging import GENERIC_TOPIC_PLACEHOLDERS, infer_question_error_names, infer_question_topic_names

    if q_type in ("SINGLE_CHOICE", "MULTIPLE_CHOICE", "STRESS_CHOICE") and answers:
        opts_text = " ".join(c for k, _, c in options if k in answers)
    else:
        opts_text = " ".join([*(c for _, _, c in options), *(w for _, w in match_pairs)])
    asg_titles = " ".join(Assignment.objects.filter(version=version).values_list("title", flat=True))
    title_ctx = " ".join(x for x in (version.exam.title, asg_titles) if x)
    inferred_topics = infer_question_topic_names(
        q_type,
        skill,
        prompt=prompt,
        options_text=opts_text,
        explanation=explanation,
        title_context=title_ctx,
        manual_topics=topic_names,
    )
    manual_non_generic = [n for n in topic_names if n.casefold() not in GENERIC_TOPIC_PLACEHOLDERS]
    manual_set = {n.casefold() for n in manual_non_generic}
    auto_extra_topics = [n for n in inferred_topics if n.casefold() not in manual_set]
    auto_errors = [] if error_names else infer_question_error_names(
        q_type,
        skill,
        prompt=prompt,
        options_text=opts_text,
        explanation=explanation,
        has_passage=bool(passage),
    )

    return {
        "type": q_type,
        "pirate_game": pirate_game,
        "skill": skill,
        "difficulty": difficulty,
        "prompt": prompt,
        "max_points": max_points,
        "passage": passage,
        "explanation": explanation,
        "options": options,
        "match_pairs": match_pairs,
        "answers": set(answers),
        "criteria": criteria,
        "topic_names": list(dict.fromkeys(manual_non_generic)),
        "auto_topic_names": auto_extra_topics,
        "error_names": list(dict.fromkeys(error_names)),
        "auto_error_names": auto_errors,
    }


@transaction.atomic
def upsert_question(owner, version_id, expected_revision, data, question_id=None, allow_published=False):
    version = _lock_draft_version(owner, version_id, expected_revision, allow_published=allow_published)
    if question_id and "pirate_game" not in data:
        data = {**data, "pirate_game": Question.objects.get(pk=question_id, version=version).pirate_game}
    parsed = _validate_question_payload(version, data)
    if question_id:
        question = Question.objects.select_for_update().get(pk=question_id, version=version)
        for field in ("type", "skill", "difficulty", "prompt", "max_points", "passage", "explanation", "pirate_game"):
            setattr(question, field, parsed[field])
        question.save()
        question.answer_keys.all().delete()
        question.options.all().delete()
        question.criteria.all().delete()
        question.question_tags.all().delete()
        question.match_images.all().delete()
        question.match_words.all().delete()
    else:
        count = version.questions.count()
        if count >= 100:
            raise ValidationError("Mỗi phiên bản tối đa 100 câu hỏi.")
        question = Question.objects.create(
            version=version,
            position=count + 1,
            type=parsed["type"],
            skill=parsed["skill"],
            difficulty=parsed["difficulty"],
            prompt=parsed["prompt"],
            max_points=parsed["max_points"],
            passage=parsed["passage"],
            explanation=parsed["explanation"],
            pirate_game=parsed["pirate_game"],
        )

    for key, pos, content in parsed["options"]:
        opt = QuestionOption.objects.create(question=question, key=key, position=pos, content=content)
        if key in parsed["answers"]:
            AnswerKeyOption.objects.create(question=question, option=opt)
    for pos, (asset, word_text) in enumerate(parsed["match_pairs"], 1):
        image = MatchImage.objects.create(question=question, image_asset=asset, position=pos)
        word = MatchWord.objects.create(question=question, text=word_text, position=pos)
        MatchKey.objects.create(image=image, word=word)
    for key, pos, label, descs in parsed["criteria"]:
        RubricCriterion.objects.create(question=question, key=key, position=pos, label=label, level_descriptions=descs)
    from .auto_tagging import get_or_create_error_tag, get_or_create_topic_tag, sync_course_exercise_auto_tags
    for kind, names in (("TOPIC", parsed["topic_names"]), ("ERROR", parsed["error_names"])):
        for name in names:
            if kind == "TOPIC":
                tag, _ = get_or_create_topic_tag(parsed["skill"], name)
            else:
                tag, _ = Tag.objects.get_or_create(kind=kind, skill=parsed["skill"], name=name)
            if tag.archived_at:
                raise ValidationError(f"Tag '{name}' đã lưu trữ, hãy chọn tag khác.")
            QuestionTag.objects.get_or_create(question=question, tag=tag)
    for name in parsed["auto_topic_names"]:
        tag, _ = get_or_create_topic_tag(parsed["skill"], name)
        if not tag.archived_at:
            QuestionTag.objects.get_or_create(question=question, tag=tag)
    for ename in parsed["auto_error_names"]:
        etag, _ = get_or_create_error_tag(parsed["skill"], ename)
        if not etag.archived_at:
            QuestionTag.objects.get_or_create(question=question, tag=etag)

    from .models import CourseExercise
    for ce in CourseExercise.objects.filter(assignment__version=version).select_related("assignment__version__exam"):
        sync_course_exercise_auto_tags(ce)

    if allow_published and version.status == ExamVersion.Status.DRAFT:
        version.status = ExamVersion.Status.PUBLISHED
        version.published_at = version.published_at or timezone.now()
        version.revision += 1
        version.save(update_fields=["status", "published_at", "revision", "updated_at"])
        from apps.assignments.models import Assignment
        from .course_services import _sync_assignment_to_classes
        for asn in Assignment.objects.filter(version=version, status="DRAFT", course_exercises__isnull=False).distinct().prefetch_related("course_exercises__course__english_classes"):
            course_classes = []
            for ce in asn.course_exercises.all():
                course_classes.extend(ce.course.english_classes.filter(archived_at__isnull=True))
            asn.status = "PUBLISHED"
            asn.published_at = timezone.now()
            asn.save(update_fields=["status", "published_at", "updated_at"])
            if course_classes:
                _sync_assignment_to_classes(asn, course_classes)
    else:
        _bump_version(version)
    return question, version


@transaction.atomic
def delete_question(owner, question_id, expected_revision, allow_published=False):
    question = Question.objects.select_related("version").get(pk=question_id, version__exam__created_by=owner)
    version = _lock_draft_version(owner, question.version_id, expected_revision, allow_published=allow_published)
    question.delete()
    remaining = list(version.questions.order_by("position"))
    # Shift positions cleanly in two passes to respect unique(version, position).
    for idx, q in enumerate(remaining, 1001):
        if q.position != idx:
            q.position = idx
            q.save(update_fields=["position"])
    for idx, q in enumerate(remaining, 1):
        q.position = idx
        q.save(update_fields=["position"])
    return _bump_version(version)


def create_tag(kind, skill, name, actor=None):
    if kind not in Tag.Kind.values or skill not in Question.Skill.values:
        raise ValidationError("Loại hoặc kỹ năng tag không hợp lệ.")
    clean = (name or "").strip()
    if not 1 <= len(clean) <= 100:
        raise ValidationError("Tên tag phải từ 1..100 ký tự.")
    tag, created = Tag.objects.get_or_create(kind=kind, skill=skill, name=clean)
    if tag.archived_at:
        raise ValidationError("Tag này đã bị lưu trữ trước đó.")
    if created:
        AuditEvent.objects.create(actor=actor, action="tag.create", target_type="tag", target_id=tag.id)
    return tag


def archive_tag(tag_id, actor=None):
    tag = Tag.objects.get(pk=tag_id)
    if not tag.archived_at:
        tag.archived_at = timezone.now()
        tag.save(update_fields=["archived_at", "updated_at"])
        AuditEvent.objects.create(actor=actor, action="tag.archive", target_type="tag", target_id=tag.id)
    return tag


def _sniff_audio_mime(header):
    """Detect real audio container signature from file header bytes; reject HTML/SVG/ZIP/executables."""
    head_l = header.lstrip()[:32].lower()
    if head_l.startswith((b"<html", b"<!doctype", b"<svg", b"<?xml", b"<script", b"pk\x03\x04", b"mz", b"\x7felf")):
        return None
    if header.startswith(b"ID3") or (len(header) >= 2 and header[0] == 0xFF and (header[1] & 0xE0) == 0xE0):
        return "audio/mpeg"
    if len(header) >= 12 and header[4:8] == b"ftyp":
        return "audio/mp4"
    if header.startswith(b"OggS"):
        return "audio/ogg"
    if header.startswith(b"\x1a\x45\xdf\xa3"):
        return "audio/webm"
    return None


def _probe_audio_ms(path):
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        if not settings.DEBUG:
            raise ValidationError("Thiếu công cụ ffprobe kiểm tra audio trên môi trường vận hành.")
        # ponytail: local Windows dev without ffprobe binary falls back to signature-only duration placeholder; install ffmpeg in prod.
        return 1000
    try:
        proc = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "stream=codec_type:format=duration", "-of", "json", str(path)],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        info = json.loads(proc.stdout or "{}")
        streams = [s.get("codec_type") for s in info.get("streams", [])]
        if "video" in streams or "audio" not in streams:
            raise ValidationError("Chỉ chấp nhận tệp audio, không chứa video.")
        duration_ms = int(float(info.get("format", {}).get("duration", 0)) * 1000)
        if duration_ms <= 0 or duration_ms > MAX_PROMPT_AUDIO_MS:
            raise ValidationError("Thời lượng tệp nghe tối đa 10 phút.")
        return duration_ms
    except (subprocess.SubprocessError, ValueError, json.JSONDecodeError) as exc:
        raise ValidationError("Không đọc được thông số tệp audio.") from exc


def store_prompt_audio(owner, uploaded_file):
    """Stream, verify signature/size/duration, and store a PROMPT_AUDIO asset privately."""
    if uploaded_file.size and uploaded_file.size > MAX_PROMPT_AUDIO_BYTES:
        raise ValidationError("Tệp nghe vượt quá 30 MiB.")
    media_root = Path(settings.PRIVATE_MEDIA_ROOT)
    media_root.mkdir(parents=True, exist_ok=True)
    asset_id = uuid.uuid4()
    object_key = f"prompt_audio/{asset_id}"
    dest = media_root / object_key
    dest.parent.mkdir(parents=True, exist_ok=True)

    hasher = hashlib.sha256()
    total = 0
    first_chunk = b""
    try:
        with open(dest, "wb") as out:
            for chunk in uploaded_file.chunks():
                if not first_chunk:
                    first_chunk = chunk[:64]
                total += len(chunk)
                if total > MAX_PROMPT_AUDIO_BYTES:
                    raise ValidationError("Tệp nghe vượt quá 30 MiB.")
                hasher.update(chunk)
                out.write(chunk)
        mime = _sniff_audio_mime(first_chunk)
        if not mime or total == 0:
            raise ValidationError("Định dạng tệp không hợp lệ. Chỉ nhận MP3, M4A/MP4 audio, Ogg hoặc WebM audio.")
        duration_ms = _probe_audio_ms(dest)
    except Exception:
        if dest.exists():
            os.remove(dest)
        raise

    return Asset.objects.create(
        id=asset_id,
        uploaded_by=owner,
        purpose=Asset.Purpose.PROMPT_AUDIO,
        object_key=object_key,
        original_name=(uploaded_file.name or "")[:255],
        detected_mime=mime,
        bytes=total,
        duration_ms=duration_ms,
        sha256=hasher.hexdigest(),
        status=Asset.Status.READY,
    )
