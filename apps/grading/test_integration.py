from datetime import timedelta
from decimal import Decimal
import json
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from apps.assignments.models import Assignment, AssignmentRecipient, Attempt, Response
from apps.content.models import AnswerKeyOption, Exam, ExamVersion, Question, QuestionOption, QuestionTag, RubricCriterion, Tag
from apps.reporting.models import RankingAssignment, RankingMember, RankingPeriod
from apps.grading.models import ErrorOccurrence, GradeRelease
from apps.grading.services import ensure_suggested_error, grade_response, publish_result, set_single_error
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

    def test_pending_essay_includes_multiple_choice_answers(self):
        question = Question.objects.create(version=self.response.question.version, position=2, type='MULTIPLE_CHOICE', skill='READING', difficulty='FOUNDATION', prompt='Choose', max_points=Decimal('1'))
        choices = [QuestionOption.objects.create(question=question, key=key, position=i, content=f'Option {key}') for i, key in enumerate(('A', 'B', 'C'), 1)]
        AnswerKeyOption.objects.create(question=question, option=choices[0])
        AnswerKeyOption.objects.create(question=question, option=choices[1])
        response = Response.objects.create(attempt=self.attempt, question=question)
        response.options.add(choices[0], choices[2])
        client = Client()
        client.force_login(self.owner)
        with patch('apps.grading.views.authorize', return_value=True):
            result = client.get(f'/api/v1/owner/attempts/{self.attempt.id}/grading/')
        self.assertEqual(result.status_code, 200)
        item = next(row for row in result.json()['data']['responses'] if row['question_id'] == str(question.id))
        self.assertEqual(set(item['selected_options']), {str(choices[0].id), str(choices[2].id)})
        self.assertEqual(set(item['correct_options']), {str(choices[0].id), str(choices[1].id)})
        self.assertEqual([option['content'] for option in item['options']], ['Option A', 'Option B', 'Option C'])

    def test_select_error_replaces_and_clears_without_duplicates(self):
        first = Tag.objects.create(kind='ERROR', skill='WRITING', name='Grammar')
        second = Tag.objects.create(kind='ERROR', skill='WRITING', name='Spelling')
        old = ErrorOccurrence.objects.create(response=self.response, tag=first, source='RULE', confidence='SIGNAL')
        client = Client()
        client.force_login(self.owner)
        url = f'/api/v1/owner/responses/{self.response.id}/errors/'
        with patch('apps.grading.views.authorize', return_value=True):
            result = client.post(url, data=json.dumps({'expected_revision': 0, 'tag_id': str(second.id), 'replace_selection': True}), content_type='application/json')
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json()['data']['attempt_revision'], 1)
            old.refresh_from_db()
            self.assertIsNotNone(old.withdrawn_at)
            self.assertEqual(list(ErrorOccurrence.objects.filter(response=self.response, withdrawn_at__isnull=True).values_list('tag_id', flat=True)), [second.id])
            stale = client.post(url, data=json.dumps({'expected_revision': 0, 'tag_id': str(first.id), 'replace_selection': True}), content_type='application/json')
            self.assertEqual(stale.status_code, 409)
            result = client.post(url, data=json.dumps({'expected_revision': 1, 'tag_id': str(first.id), 'replace_selection': True}), content_type='application/json')
            self.assertEqual(result.status_code, 200)
            self.assertEqual(ErrorOccurrence.objects.filter(response=self.response, tag=first).count(), 1)
            result = client.post(url, data=json.dumps({'expected_revision': 2, 'tag_id': '', 'replace_selection': True}), content_type='application/json')
            self.assertEqual(result.status_code, 200)
        self.assertFalse(ErrorOccurrence.objects.filter(response=self.response, withdrawn_at__isnull=True).exists())

    def test_grading_detail_suggests_question_tag_without_creating_error(self):
        from apps.content.models import QuestionTag

        err_tag = Tag.objects.create(kind='ERROR', skill='WRITING', name='Thiếu liên kết câu')
        QuestionTag.objects.create(question=self.response.question, tag=err_tag)
        client = Client()
        client.force_login(self.owner)
        with patch('apps.grading.views.authorize', return_value=True):
            result = client.get(f'/api/v1/owner/attempts/{self.attempt.id}/grading/')
        self.assertEqual(result.status_code, 200)
        row = result.json()['data']['responses'][0]
        self.assertEqual(row['default_error_tag_id'], str(err_tag.id))
        self.assertEqual(row['default_error_tag_name'], 'Thiếu liên kết câu')
        self.assertEqual(row['errors'], [])
        self.assertFalse(ErrorOccurrence.objects.filter(response=self.response).exists())

    def test_suggestion_is_recorded_after_grading_and_published(self):
        tag = Tag.objects.create(kind='ERROR', skill='WRITING', name='Viết: diễn đạt nội dung')
        QuestionTag.objects.create(question=self.response.question, tag=tag)
        grade = grade_response(self.response.id, self.owner, 0, 0, self.levels())
        occurrence = ErrorOccurrence.objects.get(response=self.response, tag=tag)
        self.assertEqual((occurrence.source, occurrence.confidence), ('RULE', 'SIGNAL'))
        self.attempt.refresh_from_db()
        release = publish_result(self.attempt.id, self.owner, self.attempt.revision)
        self.assertEqual(release.snapshot['responses'][0]['errors'][0]['tag_id'], str(tag.id))
        self.assertEqual(grade.points, Decimal('7.50'))

    def test_clear_suggestion_is_not_recreated_and_correct_answer_is_not_tagged(self):
        tag = Tag.objects.create(kind='ERROR', skill='WRITING', name='Viết: diễn đạt nội dung')
        QuestionTag.objects.create(question=self.response.question, tag=tag)
        attempt = set_single_error(self.response.id, self.owner, 0, '')
        self.assertTrue(ErrorOccurrence.objects.filter(response=self.response, tag=tag, withdrawn_at__isnull=False).exists())
        grade_response(self.response.id, self.owner, attempt.revision, 0, self.levels())
        self.attempt.refresh_from_db()
        release = publish_result(self.attempt.id, self.owner, self.attempt.revision)
        self.assertEqual(release.snapshot['responses'][0]['errors'], [])
        self.assertFalse(ErrorOccurrence.objects.filter(response=self.response, withdrawn_at__isnull=True).exists())

        second = Response.objects.create(attempt=self.attempt, question=Question.objects.create(version=self.response.question.version, position=2, type='TEXT', skill='WRITING', difficulty='FOUNDATION', prompt='Write more', max_points=Decimal('10')), text_answer='Correct answer')
        QuestionTag.objects.create(question=second.question, tag=tag)
        ensure_suggested_error(second, Decimal('10'))
        self.assertFalse(second.errors.exists())
