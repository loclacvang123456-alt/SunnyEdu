from datetime import timedelta
import json
from uuid import uuid4
from django.test import TestCase
from django.utils import timezone
from apps.accounts.models import User
from apps.content.models import Exam, ExamVersion, Question, QuestionOption, AnswerKeyOption, QuestionTag, Tag
from apps.grading.models import Grade
from .models import Assignment, AssignmentRecipient
from .services import ConflictError, start_attempt, save_response, submit_attempt


class AttemptFlowTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(username='teacher', role='OWNER', display_name='Teacher')
        self.student = User.objects.create_user(username='student', role='STUDENT', display_name='Student')
        self.other = User.objects.create_user(username='other', role='STUDENT', display_name='Other')
        exam = Exam.objects.create(title='Demo', created_by=self.teacher)
        version = ExamVersion.objects.create(exam=exam, number=1, status='PUBLISHED')
        self.question = Question.objects.create(version=version, position=1, type='SINGLE_CHOICE', skill='READING', difficulty='FOUNDATION', prompt='Choose', max_points='2.00')
        self.correct = QuestionOption.objects.create(question=self.question, key='A', position=1, content='A')
        QuestionOption.objects.create(question=self.question, key='B', position=2, content='B')
        AnswerKeyOption.objects.create(question=self.question, option=self.correct)
        now = timezone.now()
        self.assignment = Assignment.objects.create(version=version, title='Demo', code='HW-ABC123', status='PUBLISHED', opens_at=now-timedelta(hours=1), due_at=now+timedelta(hours=1), late_until=now+timedelta(days=1))
        self.recipient = AssignmentRecipient.objects.create(assignment=self.assignment, student=self.student)

    def test_save_conflict_and_submit_idempotent(self):
        attempt, created = start_attempt(self.recipient.pk, self.student)
        self.assertTrue(created)
        response, attempt = save_response(attempt.id, self.question.id, self.student, 0, option_ids=[str(self.correct.id)])
        with self.assertRaises(ConflictError):
            save_response(attempt.id, self.question.id, self.student, 0, option_ids=[])
        key = uuid4()
        result = submit_attempt(attempt.id, self.student, attempt.revision, key)
        self.assertEqual(result, submit_attempt(attempt.id, self.student, attempt.revision, key))
        self.assertEqual(Grade.objects.get(response=response).points, 2)
        with self.assertRaises(ConflictError):
            submit_attempt(attempt.id, self.student, 99, key)

    def test_wrong_automatic_answer_saves_suggestion_without_teacher(self):
        tag = Tag.objects.create(kind='ERROR', skill='READING', name='Từ vựng: nghĩa của từ')
        QuestionTag.objects.create(question=self.question, tag=tag)
        wrong = self.question.options.exclude(pk=self.correct.pk).get()
        attempt, _ = start_attempt(self.recipient.pk, self.student)
        response, attempt = save_response(attempt.id, self.question.id, self.student, 0, option_ids=[str(wrong.id)])
        submit_attempt(attempt.id, self.student, attempt.revision, uuid4())
        occurrence = response.errors.get(tag=tag)
        self.assertEqual((occurrence.source, occurrence.confidence), ('RULE', 'SIGNAL'))
        self.assertIsNone(occurrence.withdrawn_at)

    def test_sentence_transform_answer_is_not_sent_to_student(self):
        from apps.accounts.services import rotate_code
        question = Question.objects.create(version=self.assignment.version, position=2, type='SENTENCE_TRANSFORM', skill='WRITING', difficulty='FOUNDATION', prompt='Rewrite', max_points='2.00')
        QuestionOption.objects.create(question=question, key='A', position=1, content='Secret model answer')
        code = rotate_code(self.student, actor=self.teacher)
        self.client.post('/api/v1/auth/student-login/', data=json.dumps({'code': code}), content_type='application/json')
        attempt, _ = start_attempt(self.recipient.pk, self.student)
        response = self.client.get(f'/api/v1/attempts/{attempt.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Secret model answer')
        self.assertEqual(response.json()['data']['questions'][1]['options'], [])

    def test_exam_result_hides_answer_until_release(self):
        from apps.accounts.services import rotate_code
        self.assignment.mode = 'EXAM'
        self.assignment.save(update_fields=['mode'])
        code = rotate_code(self.student, actor=self.teacher)
        self.client.post('/api/v1/auth/student-login/', data=json.dumps({'code': code}), content_type='application/json')
        attempt, _ = start_attempt(self.recipient.pk, self.student)
        submit_attempt(attempt.id, self.student, attempt.revision, uuid4())
        from django.urls import reverse
        url = reverse('student_assignment_result', args=[self.assignment.id])
        self.assertNotContains(self.client.get(url), 'Đáp án đúng')
        self.assignment.answers_released_at = timezone.now()
        self.assignment.save(update_fields=['answers_released_at'])
        self.assertContains(self.client.get(url), 'Đáp án đúng')

    def test_cross_student_denied(self):
        attempt, _ = start_attempt(self.recipient.pk, self.student)
        with self.assertRaises(type(attempt).DoesNotExist):
            save_response(attempt.id, self.question.id, self.other, 0, option_ids=[])

    def test_http_login_and_private_attempt_flow(self):
        import json
        from apps.accounts.services import rotate_code
        code = rotate_code(self.student, actor=self.teacher)
        client = self.client_class(enforce_csrf_checks=True)
        client.get('/api/v1/auth/csrf/')
        csrf = client.cookies['csrftoken'].value
        login = client.post('/api/v1/auth/student-login/', data=json.dumps({'code': code, 'remember_device': False}), content_type='application/json', HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(login.status_code, 200)
        csrf = client.cookies['csrftoken'].value
        start = client.post(f'/api/v1/assignments/{self.assignment.id}/start/', HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(start.status_code, 201)
        attempt_id = start.json()['data']['attempt_id']
        detail = client.get(f'/api/v1/attempts/{attempt_id}/')
        self.assertEqual(detail.status_code, 200)
        self.assertNotIn('answer_keys', detail.content.decode())
        self.assertNotIn('explanation', detail.content.decode())
        payload = json.dumps({'expected_revision': 0, 'option_ids': [str(self.correct.id)]})
        url = f'/api/v1/attempts/{attempt_id}/responses/{self.question.id}/'
        self.assertEqual(client.put(url, data=payload, content_type='application/json').status_code, 403)
        saved = client.put(url, data=payload, content_type='application/json', HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(saved.status_code, 200)
        submitted = client.post(f'/api/v1/attempts/{attempt_id}/submit/', data=json.dumps({'expected_attempt_revision': saved.json()['data']['attempt_revision']}), content_type='application/json', HTTP_X_CSRFTOKEN=csrf, HTTP_IDEMPOTENCY_KEY=str(uuid4()))
        self.assertEqual(submitted.status_code, 200)
        self.assertNotIn('points', submitted.content.decode())
