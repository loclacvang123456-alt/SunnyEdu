from datetime import timedelta
from decimal import Decimal
import json
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from apps.assignments.models import Assignment, AssignmentRecipient, Attempt, Response
from apps.content.models import Exam, ExamVersion, Question, RubricCriterion
from apps.reporting.models import RankingAssignment, RankingMember, RankingPeriod
from apps.grading.models import GradeRelease
from apps.grading.services import grade_response, publish_result
from django.core.exceptions import ValidationError


@override_settings(ROOT_URLCONF='apps.grading.test_urls', ALLOWED_HOSTS=['testserver'], TEACHER_OTP_BYPASS=False)
class GradingIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create_user(username='owner', role='OWNER', display_name='Teacher', password='testpass')
        cls.student = User.objects.create_user(username='student', role='STUDENT', display_name='Student')
        now = timezone.now()
        exam = Exam.objects.create(title='Test', created_by=cls.owner)
        version = ExamVersion.objects.create(exam=exam, number=1, status='PUBLISHED')
        question = Question.objects.create(version=version, position=1, type='TEXT', skill='WRITING', difficulty='FOUNDATION', prompt='Write', max_points=Decimal('10'))
        cls.criteria = [RubricCriterion.objects.create(question=question, key='c'+str(i), position=i, label='Criterion '+str(i), level_descriptions={str(x): str(x) for x in range(5)}) for i in range(1, 5)]
        assignment = Assignment.objects.create(version=version, title='Test', code='HW-ABCDE1', status='PUBLISHED', opens_at=now-timedelta(days=3), due_at=now-timedelta(days=2), late_until=now-timedelta(days=1))
        recipient = AssignmentRecipient.objects.create(assignment=assignment, student=cls.student)
        cls.attempt = Attempt.objects.create(recipient=recipient, attempt_no=1, status='SUBMITTED', submitted_at=now-timedelta(days=1))
        recipient.current_attempt = cls.attempt
        recipient.save(update_fields=['current_attempt'])
        cls.response = Response.objects.create(attempt=cls.attempt, question=question, text_answer='Some text')
        cls.period = RankingPeriod.objects.create(name='Test ranking', school_year='2026-2027', start_at=now-timedelta(days=5), end_at=now-timedelta(hours=1), scope='SCHOOL', scope_target={}, status='FINAL')
        RankingAssignment.objects.create(period=cls.period, assignment=assignment)
        RankingMember.objects.create(period=cls.period, student=cls.student, alias='a', cohort_snapshot={})

    def levels(self):
        return {str(c.id): level for c, level in zip(self.criteria, [3, 2, 4, 3])}

    def test_grading_and_publication_marks_final_ranking_stale(self):
        grade = grade_response(self.response.id, self.owner, 0, 0, self.levels())
        self.assertEqual(grade.points, Decimal('7.50'))
        self.attempt.refresh_from_db()
        self.period.refresh_from_db()
        self.assertEqual(self.period.status, 'FINAL')
        release = publish_result(self.attempt.id, self.owner, self.attempt.revision)
        self.period.refresh_from_db()
        self.assertEqual(self.period.status, 'STALE')
        self.assertEqual(release.snapshot['responses'][0]['points'], '7.50')
        self.assertNotIn('answer_keys', str(release.snapshot))

    def test_stale_revision_and_replacement_are_rejected(self):
        grade_response(self.response.id, self.owner, 0, 0, self.levels())
        with self.assertRaises(ValidationError):
            publish_result(self.attempt.id, self.owner, 0)
        self.attempt.recipient.current_attempt = None
        self.attempt.recipient.save(update_fields=['current_attempt'])
        with self.assertRaises(ValidationError):
            publish_result(self.attempt.id, self.owner, 1)
        self.assertFalse(GradeRelease.objects.exists())

    def test_api_requires_verified_mfa_and_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        session = client.session
        now = timezone.now().isoformat()
        session.update({'issued_at': now, 'last_activity': now, 'auth_epoch': self.owner.auth_epoch})
        session.save()
        url = f'/api/v1/owner/attempts/{self.attempt.id}/grading/'
        self.assertEqual(client.get(url).status_code, 403)
        with patch('apps.grading.views.authorize', return_value=True):
            self.assertEqual(client.get(url).status_code, 200)
            grade_url = f'/api/v1/owner/responses/{self.response.id}/grade/'
            self.assertEqual(client.put(grade_url, data='{}', content_type='application/json').status_code, 403)

    def test_grade_and_publish_endpoints(self):
        client = Client()
        client.force_login(self.owner)
        session = client.session
        now = timezone.now().isoformat()
        session.update({'issued_at': now, 'last_activity': now, 'auth_epoch': self.owner.auth_epoch})
        session.save()
        grade_url = f'/api/v1/owner/responses/{self.response.id}/grade/'
        with patch('apps.grading.views.authorize', return_value=True):
            result = client.put(grade_url, data=json.dumps({'expected_revision': 0, 'grade_revision': 0, 'criterion_levels': self.levels()}), content_type='application/json')
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json()['data']['points'], '7.50')
            self.assertEqual(result.json()['data']['attempt_revision'], 1)
            result = client.post(f'/api/v1/owner/attempts/{self.attempt.id}/publish-result/', data=json.dumps({'expected_revision': 1}), content_type='application/json')
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json()['data']['total_points'], '7.50')
        self.period.refresh_from_db()
        self.assertEqual(self.period.status, 'STALE')
