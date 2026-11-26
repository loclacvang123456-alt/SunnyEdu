"""Owner API views for exams, versions, passages, questions, tags, imports, and prompt audio assets."""
import os
import re
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import FileResponse, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.accounts.permissions import api_error, owner_api_required, read_json_body
from apps.classes.services import commit_student_import, preview_student_import

from .editor_services import (
    archive_exam,
    archive_tag,
    archive_version,
    clone_version,
    create_draft_version,
    create_tag,
    delete_draft_version,
    delete_passage,
    delete_question,
    store_prompt_audio,
    update_exam_title,
    upsert_passage,
    upsert_question,
)
from .models import Asset, Exam, ExamVersion, ImportBatch, Passage, Question, Tag
from .services import commit_question_import, preview_question_import, publish_version


def _fail(exc):
    msg = "; ".join(exc.messages)
    if "revision conflict" in msg or "đã thay đổi" in msg:
        return api_error("CONFLICT", msg, 409)
    return api_error("INVALID_INPUT", msg, 422)


def _serialize_version(version, include_children=False):
    data = {
        "id": str(version.id),
        "exam_id": str(version.exam_id),
        "exam_title": version.exam.title,
        "number": version.number,
        "status": version.status,
        "revision": version.revision,
        "published_at": version.published_at.isoformat() if version.published_at else None,
        "question_count": version.questions.count(),
    }
    if not include_children:
        return data
    data["passages"] = [
        {
            "id": str(p.id),
            "ref": p.ref,
            "text_body": p.text_body,
            "audio_asset_id": str(p.audio_asset_id) if p.audio_asset_id else None,
            "transcript": p.transcript,
        }
        for p in version.passages.order_by("ref")
    ]
    questions = []
    for q in version.questions.prefetch_related("options", "answer_keys", "criteria", "question_tags__tag").order_by("position"):
        answer_ids = {ak.option_id for ak in q.answer_keys.all()}
        questions.append({
            "id": str(q.id),
            "position": q.position,
            "type": q.type,
                "pirate_game": q.pirate_game,
            "skill": q.skill,
            "difficulty": q.difficulty,
            "prompt": q.prompt,
            "max_points": str(q.max_points),
            "passage_id": str(q.passage_id) if q.passage_id else None,
            "explanation": q.explanation,
            "options": [{"id": str(o.id), "key": o.key, "content": o.content, "is_correct": o.id in answer_ids} for o in q.options.all()],
            "criteria": [{"id": str(c.id), "key": c.key, "label": c.label, "level_descriptions": c.level_descriptions} for c in q.criteria.all()],
            "topic_tags": [qt.tag.name for qt in q.question_tags.all() if qt.tag.kind == Tag.Kind.TOPIC],
            "error_tags": [qt.tag.name for qt in q.question_tags.all() if qt.tag.kind == Tag.Kind.ERROR],
        })
    data["questions"] = questions
    return data


@never_cache
@require_http_methods(["GET", "POST"])
@owner_api_required
def exams(request):
    if request.method == "GET":
        items = Exam.objects.filter(created_by=request.user, archived_at__isnull=True).prefetch_related("versions").order_by("-created_at")[:100]
        return JsonResponse({
            "data": [
                {
                    "id": str(e.id),
                    "title": e.title,
                    "versions": [{"id": str(v.id), "number": v.number, "status": v.status, "revision": v.revision} for v in e.versions.order_by("-number")],
                }
                for e in items
            ]
        })
    try:
        payload = read_json_body(request)
        title = (payload.get("title") or "").strip()
        if not 1 <= len(title) <= 200:
            raise ValidationError("Tên đề phải có từ 1 đến 200 ký tự.")
        exam = Exam.objects.create(title=title, created_by=request.user)
        version = ExamVersion.objects.create(exam=exam, number=1)
        return JsonResponse({"data": {"id": str(exam.id), "title": exam.title, "version_id": str(version.id)}}, status=201)
    except ValidationError as exc:
        return _fail(exc)


@never_cache
@require_http_methods(["GET", "PATCH"])
@owner_api_required
def exam_detail(request, exam_id):
    exam = get_object_or_404(Exam, pk=exam_id, created_by=request.user)
    if request.method == "GET":
        return JsonResponse({
            "data": {
                "id": str(exam.id),
                "title": exam.title,
                "archived_at": exam.archived_at.isoformat() if exam.archived_at else None,
                "versions": [_serialize_version(v) for v in exam.versions.order_by("-number")],
            }
        })
    try:
        data = read_json_body(request)
        exam = update_exam_title(request.user, exam.id, data.get("title"))
        return JsonResponse({"data": {"id": str(exam.id), "title": exam.title}})
    except ValidationError as exc:
        return _fail(exc)


@never_cache
@require_POST
@owner_api_required
def exam_archive(request, exam_id):
    get_object_or_404(Exam, pk=exam_id, created_by=request.user)
    exam = archive_exam(request.user, exam_id)
    return JsonResponse({"data": {"id": str(exam.id), "archived_at": exam.archived_at.isoformat()}})


@never_cache
@require_http_methods(["GET", "POST"])
@owner_api_required
def exam_versions(request, exam_id):
    exam = get_object_or_404(Exam, pk=exam_id, created_by=request.user)
    if request.method == "GET":
        return JsonResponse({"data": [_serialize_version(v) for v in exam.versions.order_by("-number")]})
    try:
        version = create_draft_version(request.user, exam.id)
        return JsonResponse({"data": _serialize_version(version)}, status=201)
    except ValidationError as exc:
        return _fail(exc)


@never_cache
@require_http_methods(["GET", "PATCH", "DELETE"])
@owner_api_required
def version_detail(request, version_id):
    version = get_object_or_404(ExamVersion.objects.select_related("exam"), pk=version_id, exam__created_by=request.user)
    if request.method == "GET":
        return JsonResponse({"data": _serialize_version(version, include_children=True)})
    if request.method == "DELETE":
        try:
            delete_draft_version(request.user, version.id)
            return HttpResponse(status=204)
        except ValidationError as exc:
            return _fail(exc)
    try:
        data = read_json_body(request)
        if type(data.get("expected_revision")) is not int:
            raise ValidationError("Cần expected_revision.")
        if data["expected_revision"] != version.revision:
            return api_error("CONFLICT", "Phiên bản đề đã thay đổi.", 409)
        return JsonResponse({"data": _serialize_version(version)})
    except ValidationError as exc:
        return _fail(exc)


@never_cache
@require_POST
@owner_api_required
def version_clone(request, version_id):
    get_object_or_404(ExamVersion, pk=version_id, exam__created_by=request.user)
    version = clone_version(request.user, version_id)
    return JsonResponse({"data": _serialize_version(version)}, status=201)


@never_cache
@require_POST
@owner_api_required
def version_archive(request, version_id):
    get_object_or_404(ExamVersion, pk=version_id, exam__created_by=request.user)
    version = archive_version(request.user, version_id)
    return JsonResponse({"data": _serialize_version(version)})


@never_cache
@require_POST
@owner_api_required
def version_publish(request, version_id):
    version = get_object_or_404(ExamVersion, pk=version_id, exam__created_by=request.user)
    try:
        data = read_json_body(request)
        if type(data.get("expected_revision")) is not int:
            raise ValidationError("Cần expected_revision.")
        version = publish_version(version.id, data["expected_revision"])
        return JsonResponse({"data": {"id": str(version.id), "status": version.status, "revision": version.revision}})
    except ValidationError as exc:
        return _fail(exc)


@never_cache
@require_http_methods(["GET", "POST"])
@owner_api_required
def version_passages(request, version_id):
    version = get_object_or_404(ExamVersion, pk=version_id, exam__created_by=request.user)
    if request.method == "GET":
        return JsonResponse({"data": [{"id": str(p.id), "ref": p.ref, "text_body": p.text_body, "audio_asset_id": str(p.audio_asset_id) if p.audio_asset_id else None, "transcript": p.transcript} for p in version.passages.order_by("ref")]})
    try:
        data = read_json_body(request)
        if type(data.get("expected_revision")) is not int:
            raise ValidationError("Cần expected_revision.")
        allow_published = bool(data.get("ui_direct_edit"))
        passage, updated_v = upsert_passage(request.user, version.id, data["expected_revision"], data, allow_published=allow_published)
        return JsonResponse({"data": {"id": str(passage.id), "ref": passage.ref, "version_revision": updated_v.revision}}, status=201)
    except ValidationError as exc:
        return _fail(exc)


@never_cache
@require_http_methods(["PATCH", "DELETE"])
@owner_api_required
def passage_detail(request, passage_id):
    passage = get_object_or_404(Passage.objects.select_related("version"), pk=passage_id, version__exam__created_by=request.user)
    try:
        data = read_json_body(request)
        if type(data.get("expected_revision")) is not int:
            raise ValidationError("Cần expected_revision.")
        allow_published = bool(data.get("ui_direct_edit"))
        if request.method == "DELETE":
            updated_v = delete_passage(request.user, passage.id, data["expected_revision"], allow_published=allow_published)
            return JsonResponse({"data": {"deleted": True, "version_revision": updated_v.revision}})
        passage, updated_v = upsert_passage(request.user, passage.version_id, data["expected_revision"], data, passage_id=passage.id, allow_published=allow_published)
        return JsonResponse({"data": {"id": str(passage.id), "ref": passage.ref, "version_revision": updated_v.revision}})
    except ValidationError as exc:
        return _fail(exc)


@never_cache
@require_http_methods(["GET", "POST"])
@owner_api_required
def version_questions(request, version_id):
    version = get_object_or_404(ExamVersion.objects.select_related("exam"), pk=version_id, exam__created_by=request.user)
    if request.method == "GET":
        return JsonResponse({"data": _serialize_version(version, include_children=True)["questions"]})
    try:
        data = read_json_body(request)
        if type(data.get("expected_revision")) is not int:
            raise ValidationError("Cần expected_revision.")
        allow_published = bool(data.get("ui_direct_edit"))
        question, updated_v = upsert_question(request.user, version.id, data["expected_revision"], data, allow_published=allow_published)
        return JsonResponse({"data": {"id": str(question.id), "position": question.position, "version_revision": updated_v.revision}}, status=201)
    except ValidationError as exc:
        return _fail(exc)


@never_cache
@require_http_methods(["PATCH", "DELETE"])
@owner_api_required
def question_detail(request, question_id):
    question = get_object_or_404(Question.objects.select_related("version"), pk=question_id, version__exam__created_by=request.user)
    try:
        data = read_json_body(request)
        if type(data.get("expected_revision")) is not int:
            raise ValidationError("Cần expected_revision.")
        allow_published = bool(data.get("ui_direct_edit"))
        if request.method == "DELETE":
            updated_v = delete_question(request.user, question.id, data["expected_revision"], allow_published=allow_published)
            return JsonResponse({"data": {"deleted": True, "version_revision": updated_v.revision}})
        question, updated_v = upsert_question(request.user, question.version_id, data["expected_revision"], data, question_id=question.id, allow_published=allow_published)
        return JsonResponse({"data": {"id": str(question.id), "position": question.position, "version_revision": updated_v.revision}})
    except ValidationError as exc:
        return _fail(exc)


@never_cache
@require_http_methods(["GET", "POST"])
@owner_api_required
def tags(request):
    if request.method == "GET":
        qs = Tag.objects.filter(archived_at__isnull=True).order_by("kind", "skill", "name")
        if kind := request.GET.get("kind"):
            qs = qs.filter(kind=kind)
        if skill := request.GET.get("skill"):
            qs = qs.filter(skill=skill)
        return JsonResponse({"data": [{"id": str(t.id), "kind": t.kind, "skill": t.skill, "name": t.name} for t in qs[:200]]})
    try:
        data = read_json_body(request)
        tag = create_tag(data.get("kind"), data.get("skill"), data.get("name"), actor=request.user)
        return JsonResponse({"data": {"id": str(tag.id), "kind": tag.kind, "skill": tag.skill, "name": tag.name}}, status=201)
    except ValidationError as exc:
        return _fail(exc)


@never_cache
@require_POST
@owner_api_required
def tag_archive(request, tag_id):
    get_object_or_404(Tag, pk=tag_id)
    tag = archive_tag(tag_id, actor=request.user)
    return JsonResponse({"data": {"id": str(tag.id), "archived_at": tag.archived_at.isoformat()}})


@never_cache
@require_http_methods(["GET", "POST"])
@owner_api_required
def assets(request):
    if request.method == "GET":
        rows = Asset.objects.filter(uploaded_by=request.user, purpose=Asset.Purpose.PROMPT_AUDIO, status=Asset.Status.READY).order_by("-created_at")[:100]
        return JsonResponse({"data": [{"id": str(a.id), "original_name": a.original_name, "detected_mime": a.detected_mime, "bytes": a.bytes, "duration_ms": a.duration_ms} for a in rows]})
    upload = request.FILES.get("file")
    purpose = request.POST.get("purpose", Asset.Purpose.PROMPT_AUDIO)
    if not upload or purpose != Asset.Purpose.PROMPT_AUDIO:
        return api_error("INVALID_INPUT", "Cần chọn tệp audio với purpose=PROMPT_AUDIO.", 422)
    if upload.size and upload.size > 30 * 1024 * 1024:
        return api_error("FILE_TOO_LARGE", "Tệp nghe vượt quá 30 MiB.", 413)
    try:
        asset = store_prompt_audio(request.user, upload)
        return JsonResponse({"data": {"id": str(asset.id), "original_name": asset.original_name, "detected_mime": asset.detected_mime, "bytes": asset.bytes, "duration_ms": asset.duration_ms, "status": asset.status}}, status=201)
    except ValidationError as exc:
        return _fail(exc)


@never_cache
@require_GET
@owner_api_required
def asset_content(request, asset_id):
    asset = get_object_or_404(Asset, pk=asset_id, status=Asset.Status.READY)
    path = Path(settings.PRIVATE_MEDIA_ROOT) / asset.object_key
    if not path.exists():
        return api_error("NOT_FOUND", "Không tìm thấy tệp.", 404)
    size = os.path.getsize(path)
    range_header = request.headers.get("Range", "")
    if range_header.startswith("bytes="):
        parts = range_header[6:].split("-", 1)
        try:
            start = int(parts[0]) if parts[0] else 0
            end = int(parts[1]) if len(parts) > 1 and parts[1] else size - 1
            if start < 0 or end >= size or start > end:
                raise ValueError
        except ValueError:
            return HttpResponse(status=416)
        length = end - start + 1
        with open(path, "rb") as f:
            f.seek(start)
            chunk = f.read(length)
        resp = HttpResponse(chunk, status=206, content_type=asset.detected_mime or "application/octet-stream")
        resp["Content-Range"] = f"bytes {start}-{end}/{size}"
        resp["Content-Length"] = str(length)
    else:
        resp = FileResponse(open(path, "rb"), content_type=asset.detected_mime or "application/octet-stream")
        resp["Content-Length"] = str(size)
    resp["Accept-Ranges"] = "bytes"
    resp["X-Content-Type-Options"] = "nosniff"
    resp["Cache-Control"] = "no-store"
    return resp


def _clean_default_title(filename):
    if not filename:
        return "Đề thi mới"
    name = Path(filename).stem
    clean = re.sub(r'[-_]+', ' ', name).strip('. ')
    clean = re.sub(r'\s+', ' ', clean).strip()
    if not clean or clean.lower() in ('csv', 'xlsx'):
        return "Đề thi mới"
    return clean[:200]


@never_cache
@require_POST
@owner_api_required
def import_preview(request):
    upload = request.FILES.get("file") or (request.FILES.getlist("files")[0] if request.FILES.getlist("files") else None)
    kind = request.POST.get("kind", "")
    if not upload or kind not in ("QUESTIONS", "STUDENTS"):
        return api_error("INVALID_INPUT", "Cần chọn tệp và loại QUESTIONS hoặc STUDENTS.", 422)
    if upload.size > 2 * 1024 * 1024:
        return api_error("FILE_TOO_LARGE", "Tệp vượt quá 2 MiB.", 413)
    try:
        raw = upload.read()
        batch = preview_question_import(request.user, raw, upload.name) if kind == "QUESTIONS" else preview_student_import(request.user, raw, upload.name)
        default_title = _clean_default_title(upload.name)
        return JsonResponse({"data": {"id": str(batch.id), "kind": batch.kind, "source_digest": batch.source_digest, "expires_at": batch.expires_at.isoformat(), "rows": batch.payload_json, "default_title": default_title, "filename": upload.name}}, status=201)
    except ValidationError as exc:
        return _fail(exc)


@never_cache
@require_POST
@owner_api_required
def batch_import_preview(request):
    files = request.FILES.getlist("files") or request.FILES.getlist("file")
    if not files:
        return api_error("INVALID_INPUT", "Cần chọn ít nhất một tệp CSV hoặc XLSX.", 422)
    results = []
    total_questions = 0
    errors = []
    for upload in files:
        if upload.size > 2 * 1024 * 1024:
            errors.append(f"Tệp {upload.name} vượt quá 2 MiB.")
            continue
        try:
            raw = upload.read()
            batch = preview_question_import(request.user, raw, upload.name)
            q_count = len(batch.payload_json)
            total_questions += q_count
            results.append({
                "batch_id": str(batch.id),
                "filename": upload.name,
                "default_title": _clean_default_title(upload.name),
                "question_count": q_count,
                "expected_digest": batch.source_digest,
            })
        except ValidationError as exc:
            msg = "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
            errors.append(f"Tệp {upload.name}: {msg}")
    if errors:
        return api_error("IMPORT_VALIDATION_ERROR", "\n".join(errors), 422)
    return JsonResponse({
        "data": {
            "total_files": len(results),
            "total_questions": total_questions,
            "batches": results,
        }
    }, status=201)


@never_cache
@require_GET
@owner_api_required
def import_detail(request, batch_id):
    batch = get_object_or_404(ImportBatch, pk=batch_id, owner=request.user)
    return JsonResponse({"data": {"id": str(batch.id), "kind": batch.kind, "status": batch.status, "source_digest": batch.source_digest, "expires_at": batch.expires_at.isoformat(), "rows": batch.payload_json}})


@never_cache
@require_POST
@owner_api_required
def import_commit(request, batch_id):
    batch = get_object_or_404(ImportBatch, pk=batch_id, owner=request.user)
    try:
        data = read_json_body(request)
        if batch.kind == "STUDENTS":
            result = commit_student_import(request.user, batch.id, data.get("expected_digest"), data.get("class_id"))
            return JsonResponse({"data": result}, status=200)
        exam = get_object_or_404(Exam, pk=data["target_exam_id"], created_by=request.user) if data.get("target_exam_id") else None
        title = (data.get("title") or data.get("default_title") or "").strip()
        if not title:
            title = f"Đề thi mới ({timezone.now().strftime('%d/%m/%Y %H:%M')})"
        version = commit_question_import(request.user, batch.id, data.get("expected_digest"), title, exam)
        return JsonResponse({"data": {"exam_id": str(version.exam_id), "version_id": str(version.id), "number": version.number, "status": version.status}}, status=200)
    except ValidationError as exc:
        return _fail(exc)


@never_cache
@require_POST
@owner_api_required
def batch_import_commit(request):
    data = read_json_body(request)
    items = data.get("items", [])
    if not items or not isinstance(items, list):
        return api_error("INVALID_INPUT", "Danh sách tệp xác nhận không hợp lệ.", 422)
    created = []
    try:
        with transaction.atomic():
            for item in items:
                batch_id = item.get("batch_id")
                expected_digest = item.get("expected_digest")
                title = (item.get("title") or item.get("default_title") or "").strip()
                if not title:
                    title = f"Đề thi mới ({timezone.now().strftime('%d/%m/%Y %H:%M')})"
                batch = get_object_or_404(ImportBatch, pk=batch_id, owner=request.user)
                version = commit_question_import(request.user, batch.id, expected_digest, title)
                created.append({
                    "exam_id": str(version.exam_id),
                    "version_id": str(version.id),
                    "title": version.exam.title,
                    "number": version.number,
                })
        return JsonResponse({"data": {"created_count": len(created), "exams": created}}, status=200)
    except ValidationError as exc:
        return _fail(exc)
