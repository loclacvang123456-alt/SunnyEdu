"""Owner image upload and student-only private image delivery."""
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import FileResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.permissions import api_error, owner_api_required
from apps.assignments.models import Attempt, Response
from .image_assets import MAX_INPUT_BYTES, store_prompt_image


@never_cache
@require_POST
@owner_api_required
def upload_image(request):
    upload = request.FILES.get('file')
    if not upload:
        return api_error('INVALID_INPUT', 'Hãy chọn một tệp ảnh.', 422)
    if upload.size and upload.size > MAX_INPUT_BYTES:
        return api_error('FILE_TOO_LARGE', 'Ảnh vượt quá 5 MiB.', 413)
    try:
        asset = store_prompt_image(request.user, upload)
    except ValidationError as exc:
        return api_error('INVALID_INPUT', '; '.join(exc.messages), 422)
    return JsonResponse({'data': {'id': str(asset.id), 'detected_mime': asset.detected_mime,
                                  'bytes': asset.bytes, 'status': asset.status}}, status=201)


def private_png_response(asset):
    root = Path(settings.PRIVATE_MEDIA_ROOT).resolve()
    path = (root / asset.object_key).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        return api_error('NOT_FOUND', 'Không tìm thấy ảnh.', 404)
    try:
        response = FileResponse(path.open('rb'), content_type='image/png')
    except OSError:
        return api_error('NOT_FOUND', 'Không tìm thấy ảnh.', 404)
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


@never_cache
@require_GET
@owner_api_required
def owner_image(request, asset_id):
    from .models import Asset
    asset = Asset.objects.filter(pk=asset_id, uploaded_by=request.user, purpose='PROMPT_IMAGE',
                                 status='READY', detected_mime='image/png').first()
    if not asset:
        return api_error('NOT_FOUND', 'Không tìm thấy ảnh.', 404)
    return private_png_response(asset)


def match_image_model():
    try:
        return apps.get_model('content', 'MatchImage')
    except LookupError:
        return None


@never_cache
@require_GET
def student_image(request, attempt_id, image_id):
    from apps.assignments.services import course_access_allowed
    user = request.user
    if not user.is_authenticated or user.role != 'STUDENT' or user.status != 'ACTIVE':
        return api_error('NOT_FOUND', 'Không tìm thấy ảnh.', 404)
    attempt = Attempt.objects.select_related('recipient__assignment').filter(
        pk=attempt_id, recipient__student=user,
    ).first()
    if not attempt:
        return api_error('NOT_FOUND', 'Không tìm thấy ảnh.', 404)
    recipient, now = attempt.recipient, timezone.now()
    assignment = recipient.assignment
    if (recipient.state != 'ASSIGNED' or recipient.current_attempt_id != attempt.id
            or assignment.status != 'PUBLISHED' or now < assignment.opens_at
            or attempt.status not in ('IN_PROGRESS', 'SUBMITTED', 'GRADED')
            or (attempt.status == 'IN_PROGRESS' and now >= assignment.late_until)
            or not course_access_allowed(assignment.id, user)):
        return api_error('NOT_FOUND', 'Không tìm thấy ảnh.', 404)
    model = match_image_model()
    if model is None:
        return api_error('NOT_FOUND', 'Không tìm thấy ảnh.', 404)
    item = model.objects.select_related('question', 'image_asset').filter(
        pk=image_id, question__version_id=assignment.version_id,
        question__type='MATCH_IMAGE', image_asset__purpose='PROMPT_IMAGE',
        image_asset__status='READY', image_asset__detected_mime='image/png',
    ).first()
    if not item or not Response.objects.filter(attempt=attempt, question=item.question).exists():
        return api_error('NOT_FOUND', 'Không tìm thấy ảnh.', 404)
    return private_png_response(item.image_asset)

