import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4
from django.middleware.csrf import CsrfViewMiddleware
from django.test import RequestFactory, SimpleTestCase
from django.utils import timezone
from .writing_assistance import AssistanceUnavailable, check_writing, local_endpoint
from .writing_views import check


class WritingAssistanceTests(SimpleTestCase):
    def test_only_loopback_url_is_allowed(self):
        self.assertEqual(local_endpoint('http://localhost:8081/v2/check'), 'http://127.0.0.1:8081/v2/check')
        for value in ['', 'https://api.languagetool.org/v2/check', 'http://127.0.0.2:8081/v2/check',
                      'http://127.0.0.1:8081/v2/check?url=evil', 'http://x@localhost:8081/v2/check',
                      'http://localhost:8081/other', 'http://localhost/v2/check']:
            with self.subTest(value=value), self.assertRaises(AssistanceUnavailable):
                local_endpoint(value)

    @patch('apps.grading.writing_assistance.build_opener')
    def test_offsets_are_utf16_and_result_is_sanitized(self, build):
        payload = {'matches': [
            {'offset': 3, 'length': 2, 'message': 'Check', 'replacements': [{'value': 'is'}], 'rule': {'category': {'name': 'Grammar'}}},
            {'offset': 900, 'length': 2, 'message': 'Invalid', 'replacements': []},
        ]}
        response = MagicMock()
        response.read.return_value = json.dumps(payload).encode()
        build.return_value.open.return_value.__enter__.return_value = response
        result = check_writing('😀 iz good', 'http://localhost:8081/v2/check')
        self.assertEqual(result['offset_encoding'], 'utf-16')
        self.assertEqual(result['matches'], [{'offset': 3, 'length': 2, 'message': 'Check', 'suggestions': ['is'], 'category': 'Grammar'}])
        self.assertEqual(build.return_value.open.call_args.kwargs['timeout'], 10)
        self.assertEqual(build.return_value.open.call_args.args[0].full_url, 'http://127.0.0.1:8081/v2/check')

    @patch('apps.grading.writing_assistance.build_opener')
    def test_unavailable_or_oversized_response_does_not_fallback(self, build):
        build.return_value.open.side_effect = OSError('down')
        with self.assertRaises(AssistanceUnavailable):
            check_writing('hello', 'http://localhost:8081/v2/check')
        self.assertEqual(build.call_count, 1)
        with self.assertRaises(AssistanceUnavailable):
            check_writing('hello', '')
        self.assertEqual(build.call_count, 1)
        with self.assertRaises(ValueError):
            check_writing('x' * 10001, 'http://localhost:8081/v2/check')
        with self.assertRaises(ValueError):
            check_writing('\ud800', 'http://localhost:8081/v2/check')


class WritingViewTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.uid = uuid4()
        self.other = uuid4()
        now = timezone.now()
        self.assignment = SimpleNamespace(id=self.uid, mode='PRACTICE', status='PUBLISHED', version_id=self.uid, opens_at=now-timedelta(hours=1), late_until=now+timedelta(hours=1))
        course_access = patch('apps.grading.writing_views.course_access_allowed', return_value=True)
        self.course_access = course_access.start()
        self.addCleanup(course_access.stop)
        self.recipient = SimpleNamespace(assignment=self.assignment, state='ASSIGNED', current_attempt_id=self.uid)
        self.attempt = SimpleNamespace(id=self.uid, recipient=self.recipient, status='IN_PROGRESS')
        self.response = SimpleNamespace(attempt=self.attempt, question=SimpleNamespace(type='TEXT', version_id=self.uid))
        self.user = SimpleNamespace(pk=self.uid, is_authenticated=True, role='STUDENT', status='ACTIVE')

    def request(self):
        request = self.factory.post('/writing/check/', data=json.dumps({'text': 'I is happy'}), content_type='application/json')
        request.user = self.user
        return request

    @patch('apps.grading.writing_views.consume', return_value=0)
    @patch('apps.grading.writing_views.check_writing')
    @patch('apps.grading.writing_views.Response')
    def test_only_current_practice_response(self, response_model, service, limiter):
        response_model.objects.select_related.return_value.filter.return_value.first.return_value = self.response
        service.return_value = {'offset_encoding': 'utf-16', 'matches': []}
        self.assertEqual(check(self.request(), self.uid).status_code, 200)
        for field, value in [('mode', 'EXAM'), ('status', 'CANCELLED')]:
            original = getattr(self.assignment, field)
            setattr(self.assignment, field, value)
            self.assertEqual(check(self.request(), self.uid).status_code, 403)
            setattr(self.assignment, field, original)
        self.recipient.current_attempt_id = self.other
        self.assertEqual(check(self.request(), self.uid).status_code, 403)
        self.recipient.current_attempt_id = self.uid
        self.attempt.status = 'SUBMITTED'
        self.assertEqual(check(self.request(), self.uid).status_code, 403)
        self.assertEqual(service.call_count, 1)
        self.attempt.status = 'IN_PROGRESS'
        self.course_access.return_value = False
        self.assertEqual(check(self.request(), self.uid).status_code, 403)

    @patch('apps.grading.writing_views.consume', return_value=0)
    @patch('apps.grading.writing_views.check_writing')
    @patch('apps.grading.writing_views.Response')
    def test_invalid_owner_and_missing_service(self, response_model, service, limiter):
        response_model.objects.select_related.return_value.filter.return_value.first.return_value = None
        self.assertEqual(check(self.request(), self.uid).status_code, 404)
        response_model.objects.select_related.return_value.filter.return_value.first.return_value = self.response
        service.side_effect = AssistanceUnavailable
        self.assertEqual(check(self.request(), self.uid).status_code, 503)
        user = self.user
        user.role = 'OWNER'
        self.assertEqual(check(self.request(), self.uid).status_code, 401)

    @patch('apps.grading.writing_views.consume', return_value=21)
    @patch('apps.grading.writing_views.check_writing')
    @patch('apps.grading.writing_views.Response')
    def test_rate_limit_does_not_call_languagetool(self, response_model, service, limiter):
        response_model.objects.select_related.return_value.filter.return_value.first.return_value = self.response
        response = check(self.request(), self.uid)
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response['Retry-After'], '21')
        service.assert_not_called()

    def test_csrf_middleware_blocks_unsafe_request_without_token(self):
        request = self.request()
        middleware = CsrfViewMiddleware(lambda req: None)
        middleware.process_request(request)
        self.assertEqual(middleware.process_view(request, check, (), {'response_id': self.uid}).status_code, 403)
