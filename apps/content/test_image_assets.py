import io
import tempfile
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.middleware.csrf import CsrfViewMiddleware
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.utils import timezone
from PIL import Image

from .image_assets import encode_safe_png, store_prompt_image
from .image_upload_views import student_image, upload_image


def upload_png(size=(8, 8)):
    data = io.BytesIO()
    image = Image.new('RGB', size, '#2468aa')
    exif = Image.Exif()
    exif[270] = 'student name to remove'
    image.save(data, format='JPEG', exif=exif)
    return SimpleUploadedFile('example.jpg', data.getvalue(), content_type='image/jpeg')


class ImageAssetTests(SimpleTestCase):
    def test_reencode_strips_exif_and_untrusted_types(self):
        result = encode_safe_png(upload_png())
        with Image.open(io.BytesIO(result)) as img:
            self.assertEqual(img.format, 'PNG')
            self.assertEqual(img.size, (8, 8))
            self.assertFalse(img.getexif())
            self.assertNotIn('student name', str(img.info))
        for content in [b'<svg onload="alert(1)"></svg>', b'', b'not an image']:
            with self.assertRaises(ValidationError):
                encode_safe_png(SimpleUploadedFile('image.png', content, content_type='image/png'))

    def test_oversized_dimensions_and_bytes_rejected(self):
        with self.assertRaises(ValidationError):
            encode_safe_png(upload_png((2001, 2000)))
        large = SimpleUploadedFile('large.png', b'x' * (5 * 1024 * 1024 + 1))
        with self.assertRaises(ValidationError):
            encode_safe_png(large)

    @patch('apps.content.image_assets.Asset.objects.create')
    def test_storage_uses_random_private_key_and_cleanup_on_failure(self, create):
        with tempfile.TemporaryDirectory() as directory, override_settings(PRIVATE_MEDIA_ROOT=Path(directory)):
            def stored(**kwargs):
                return SimpleNamespace(**kwargs)
            create.side_effect = stored
            asset = store_prompt_image(object(), upload_png())
            self.assertTrue(asset.object_key.startswith('prompt_image/'))
            self.assertEqual(asset.detected_mime, 'image/png')
            self.assertTrue((Path(directory) / asset.object_key).is_file())
            before = set((Path(directory) / 'prompt_image').iterdir())
            create.side_effect = RuntimeError('db down')
            with self.assertRaises(RuntimeError):
                store_prompt_image(object(), upload_png())
            self.assertEqual(before, set((Path(directory) / 'prompt_image').iterdir()))


    @patch('apps.content.image_assets.uuid.uuid4')
    def test_existing_file_is_not_deleted_on_key_collision(self, make_uuid):
        fixed = uuid4()
        make_uuid.return_value = fixed
        with tempfile.TemporaryDirectory() as directory, override_settings(PRIVATE_MEDIA_ROOT=Path(directory)):
            folder = Path(directory) / 'prompt_image'
            folder.mkdir()
            existing = folder / str(fixed)
            existing.write_bytes(b'original')
            with self.assertRaises(FileExistsError):
                store_prompt_image(object(), upload_png())
            self.assertEqual(existing.read_bytes(), b'original')


class ImageViewTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.student = SimpleNamespace(is_authenticated=True, role='STUDENT', status='ACTIVE')
        self.owner = SimpleNamespace(is_authenticated=True, role='OWNER', status='ACTIVE', is_verified=lambda: True)
        self.attempt_id, self.image_id, self.version_id = uuid4(), uuid4(), uuid4()
        now = timezone.now()
        assignment = SimpleNamespace(id=uuid4(), status='PUBLISHED', opens_at=now-timedelta(hours=1), late_until=now+timedelta(hours=1), version_id=self.version_id)
        course_access = patch('apps.assignments.services.course_access_allowed', return_value=True)
        self.course_access = course_access.start()
        self.addCleanup(course_access.stop)
        self.recipient = SimpleNamespace(state='ASSIGNED', current_attempt_id=self.attempt_id, assignment=assignment)
        self.attempt = SimpleNamespace(id=self.attempt_id, status='IN_PROGRESS', recipient=self.recipient)

    def request(self):
        request = self.factory.get('/image/')
        request.user = self.student
        return request

    @patch('apps.content.image_upload_views.Response')
    @patch('apps.content.image_upload_views.match_image_model')
    @patch('apps.content.image_upload_views.Attempt')
    def test_student_receives_only_authorized_private_asset(self, attempt_model, get_model, response_model):
        with tempfile.TemporaryDirectory() as directory, override_settings(PRIVATE_MEDIA_ROOT=Path(directory)):
            file = Path(directory) / 'test.png'
            file.write_bytes(b'example')
            asset = SimpleNamespace(object_key='test.png')
            item = SimpleNamespace(question=SimpleNamespace(), image_asset=asset)
            attempt_model.objects.select_related.return_value.filter.return_value.first.return_value = self.attempt
            match_model = get_model.return_value
            match_model.objects.select_related.return_value.filter.return_value.first.return_value = item
            response_model.objects.filter.return_value.exists.return_value = True
            result = student_image(self.request(), self.attempt_id, self.image_id)
            self.assertEqual(result.status_code, 200)
            self.assertIn('no-store', result['Cache-Control'])
            self.assertEqual(result['X-Content-Type-Options'], 'nosniff')
            self.assertEqual(b''.join(result.streaming_content), b'example')
            result.close()
            kwargs = match_model.objects.select_related.return_value.filter.call_args.kwargs
            self.assertEqual(kwargs['question__version_id'], self.version_id)
            self.assertEqual(kwargs['image_asset__status'], 'READY')
            self.assertEqual(kwargs['question__type'], 'MATCH_IMAGE')
            self.course_access.return_value = False
            self.assertEqual(student_image(self.request(), self.attempt_id, self.image_id).status_code, 404)
            self.course_access.return_value = True
            self.recipient.current_attempt_id = uuid4()
            self.assertEqual(student_image(self.request(), self.attempt_id, self.image_id).status_code, 404)
            self.recipient.current_attempt_id = self.attempt_id
            response_model.objects.filter.return_value.exists.return_value = False
            self.assertEqual(student_image(self.request(), self.attempt_id, self.image_id).status_code, 404)
            asset.object_key = '../outside.png'
            response_model.objects.filter.return_value.exists.return_value = True
            self.assertEqual(student_image(self.request(), self.attempt_id, self.image_id).status_code, 404)

    def test_upload_requires_owner_otp_and_csrf(self):
        request = self.factory.post('/owner/image-assets/', {'file': upload_png()})
        request.user = self.student
        self.assertEqual(upload_image(request).status_code, 403)
        request = self.factory.post('/owner/image-assets/', {'file': upload_png()})
        request.user = self.owner
        middleware = CsrfViewMiddleware(lambda req: None)
        middleware.process_request(request)
        self.assertEqual(middleware.process_view(request, upload_image, (), {}).status_code, 403)

    @patch('apps.content.image_upload_views.store_prompt_image')
    def test_authorized_upload_returns_no_private_path(self, store):
        asset = SimpleNamespace(id=uuid4(), detected_mime='image/png', bytes=123, status='READY')
        store.return_value = asset
        request = self.factory.post('/owner/image-assets/', {'file': upload_png()})
        request.user = self.owner
        result = upload_image(request)
        self.assertEqual(result.status_code, 201)
        self.assertNotIn(b'object_key', result.content)
        store.assert_called_once()

    @patch('apps.content.models.Asset.objects.filter')
    def test_owner_preview_requires_otp_and_same_owner(self, lookup):
        from .image_upload_views import owner_image
        with tempfile.TemporaryDirectory() as directory, override_settings(PRIVATE_MEDIA_ROOT=Path(directory)):
            file = Path(directory) / 'preview.png'
            file.write_bytes(b'png')
            lookup.return_value.first.return_value = SimpleNamespace(object_key='preview.png')
            req = self.factory.get('/preview/')
            req.user = self.owner
            result = owner_image(req, self.image_id)
            self.assertEqual(result.status_code, 200)
            self.assertIn('no-store', result['Cache-Control'])
            self.assertEqual(b''.join(result.streaming_content), b'png')
            result.close()
            self.assertEqual(lookup.call_args.kwargs['uploaded_by'], self.owner)
            self.assertEqual(lookup.call_args.kwargs['purpose'], 'PROMPT_IMAGE')
            req.user = SimpleNamespace(is_authenticated=True, role='OWNER', status='ACTIVE', is_verified=lambda: False)
            self.assertEqual(owner_image(req, self.image_id).status_code, 403)
            req.user = self.student
            self.assertEqual(owner_image(req, self.image_id).status_code, 403)
            req.user = self.owner
            lookup.return_value.first.return_value = None
            self.assertEqual(owner_image(req, self.image_id).status_code, 404)

from django.test import TestCase
from apps.accounts.models import User
from apps.assignments.models import Assignment, AssignmentRecipient, Attempt, Response
from .models import Exam, ExamVersion, MatchImage, Question


class PrivateImageDatabaseTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.overrides = override_settings(PRIVATE_MEDIA_ROOT=Path(self.tmp.name))
        self.overrides.enable()
        self.addCleanup(self.overrides.disable)
        self.factory = RequestFactory()
        self.owner = User.objects.create_user(username='image_owner', role='OWNER', display_name='Owner')
        self.student = User.objects.create_user(username='image_student', role='STUDENT', display_name='Student')
        self.other = User.objects.create_user(username='image_other', role='STUDENT', display_name='Other')
        exam = Exam.objects.create(title='Match', created_by=self.owner)
        self.version = ExamVersion.objects.create(exam=exam, number=1, status='PUBLISHED')
        self.question = Question.objects.create(version=self.version, position=1, type='MATCH_IMAGE', skill='READING', difficulty='FOUNDATION', prompt='Match', max_points='1.00')
        self.other_question = Question.objects.create(version=self.version, position=2, type='MATCH_IMAGE', skill='READING', difficulty='FOUNDATION', prompt='Other', max_points='1.00')
        self.asset = store_prompt_image(self.owner, upload_png())
        self.image = MatchImage.objects.create(question=self.question, image_asset=self.asset, position=1)
        self.other_image = MatchImage.objects.create(question=self.other_question, image_asset=self.asset, position=1)
        now = timezone.now()
        self.assignment = Assignment.objects.create(version=self.version, title='Test', code='HW-IMG001', status='PUBLISHED', opens_at=now-timedelta(hours=1), due_at=now+timedelta(hours=1), late_until=now+timedelta(days=1))
        self.recipient = AssignmentRecipient.objects.create(assignment=self.assignment, student=self.student)
        self.attempt = Attempt.objects.create(recipient=self.recipient, attempt_no=1)
        self.recipient.current_attempt = self.attempt
        self.recipient.save(update_fields=['current_attempt'])
        Response.objects.create(attempt=self.attempt, question=self.question)

    def req(self, user):
        request = self.factory.get('/private-image/')
        request.user = user
        return request

    def test_owner_matching_version_and_specific_response(self):
        result = student_image(self.req(self.student), self.attempt.id, self.image.id)
        self.assertEqual(result.status_code, 200)
        self.assertTrue(b''.join(result.streaming_content).startswith(b'\x89PNG'))
        self.assertEqual(student_image(self.req(self.other), self.attempt.id, self.image.id).status_code, 404)
        self.assertEqual(student_image(self.req(self.student), self.attempt.id, self.other_image.id).status_code, 404)
        self.recipient.state = 'EXEMPT'
        self.recipient.save(update_fields=['state'])
        self.assertEqual(student_image(self.req(self.student), self.attempt.id, self.image.id).status_code, 404)
        result.close()
