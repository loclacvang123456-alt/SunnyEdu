from datetime import timedelta
import json
from uuid import uuid4

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from apps.accounts.models import User
from apps.accounts.services import rotate_code
from apps.assignments.models import Assignment, AssignmentRecipient, AttemptVisibilityEvent
from apps.assignments.services import start_attempt, submit_attempt
from apps.content.models import Exam, ExamVersion, Question, QuestionOption, AnswerKeyOption


@override_settings(TEACHER_OTP_BYPASS=True)
class VisibilityTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(username='visibility-teacher', role='OWNER')
        self.student = User.objects.create_user(username='visibility-student', role='STUDENT')
        exam = Exam.objects.create(title='Test', created_by=self.teacher)
        version = ExamVersion.objects.create(exam=exam, number=1, status='PUBLISHED')
        question = Question.objects.create(version=version, position=1, type='SINGLE_CHOICE', skill='READING', difficulty='FOUNDATION', prompt='Q', max_points='1.00')
        option = QuestionOption.objects.create(question=question, key='A', position=1, content='A')
        AnswerKeyOption.objects.create(question=question, option=option)
        now = timezone.now()
        self.assignment = Assignment.objects.create(version=version, title='Test', code='HW-VIS001', status='PUBLISHED', opens_at=now-timedelta(hours=1), due_at=now+timedelta(hours=1), late_until=now+timedelta(days=1))
        self.recipient = AssignmentRecipient.objects.create(assignment=self.assignment, student=self.student)
        self.attempt, _ = start_attempt(self.recipient.id, self.student)
        code = rotate_code(self.student, actor=self.teacher)
        self.client.post('/api/v1/auth/student-login/', json.dumps({'code': code}), content_type='application/json')

    def test_record_deduplicate_and_review_auto_graded_attempt(self):
        url = f'/api/v1/attempts/{self.attempt.id}/visibility/'
        event = {'id': str(uuid4()), 'duration_ms': 7200}
        for _ in range(2):
            self.assertEqual(self.client.post(url, json.dumps(event), content_type='application/json').status_code, 200)
        self.assertEqual(AttemptVisibilityEvent.objects.count(), 1)
        submit_attempt(self.attempt.id, self.student, 0, uuid4())
        self.client.force_login(self.teacher)
        session = self.client.session
        now = timezone.now().isoformat()
        session['auth_epoch'] = self.teacher.auth_epoch
        session['issued_at'] = now
        session['last_activity'] = now
        session.save()
        queue = reverse('owner_grading_queue')
        self.assertEqual(self.client.get(reverse('owner_dashboard')).context['pending_grading'], 1)
        self.assertContains(self.client.get(queue), 'Cần xem: rời trang trên 5 giây')
        detail = reverse('owner_grading_detail', args=[self.attempt.id])
        self.assertContains(self.client.get(detail), '7,2')
        self.client.post(detail, {'action': 'review_visibility'})
        self.assertEqual(self.client.get(reverse('owner_dashboard')).context['pending_grading'], 0)
        self.assertNotContains(self.client.get(queue), 'Cần xem: rời trang trên 5 giây')

    def test_five_seconds_does_not_flag_auto_graded_attempt(self):
        url = f'/api/v1/attempts/{self.attempt.id}/visibility/'
        self.client.post(url, json.dumps({'id': str(uuid4()), 'duration_ms': 5000}), content_type='application/json')
        submit_attempt(self.attempt.id, self.student, 0, uuid4())
        self.client.force_login(self.teacher)
        session = self.client.session
        session['auth_epoch'] = self.teacher.auth_epoch
        session['issued_at'] = session['last_activity'] = timezone.now().isoformat()
        session.save()
        self.assertNotContains(self.client.get(reverse('owner_grading_queue')), 'Cần xem: rời trang trên 5 giây')

    def test_deduction_cannot_exceed_score_and_updates_published_result(self):
        from decimal import Decimal
        from apps.assignments.services import save_response
        from apps.grading.models import GradeRelease
        from apps.grading.services import publish_result, set_visibility_deduction
        from django.core.exceptions import ValidationError
        question = self.attempt.responses.first().question
        option = question.options.first()
        _, attempt = save_response(self.attempt.id, question.id, self.student, 0, option_ids=[str(option.id)])
        AttemptVisibilityEvent.objects.create(attempt=attempt, duration_ms=6000)
        submit_attempt(attempt.id, self.student, attempt.revision, uuid4())
        attempt.refresh_from_db()
        publish_result(attempt.id, self.teacher, attempt.revision)
        with self.assertRaises(ValidationError):
            set_visibility_deduction(attempt.id, self.teacher, '1.01')
        with self.assertRaises(ValidationError):
            set_visibility_deduction(attempt.id, self.teacher, '-0.5')
        set_visibility_deduction(attempt.id, self.teacher, '0.25')
        release = GradeRelease.objects.filter(attempt=attempt).order_by('-number').first()
        self.assertEqual(release.total_points, Decimal('0.75'))
        self.assertEqual(release.snapshot['visibility_deduction'], '0.25')
        result = self.client.get(reverse('student_assignment_result', args=[self.assignment.id]))
        self.assertEqual(result.context['total_earned'], Decimal('0.75'))
        set_visibility_deduction(attempt.id, self.teacher, '0')
        self.assertEqual(GradeRelease.objects.filter(attempt=attempt).order_by('-number').first().total_points, Decimal('1.00'))

    def test_reject_invalid_or_other_student_event(self):
        url = f'/api/v1/attempts/{self.attempt.id}/visibility/'
        self.assertEqual(self.client.post(url, json.dumps({'id': str(uuid4()), 'duration_ms': -1}), content_type='application/json').status_code, 422)
        other = User.objects.create_user(username='visibility-other', role='STUDENT')
        code = rotate_code(other, actor=self.teacher)
        self.client.post('/api/v1/auth/student-login/', json.dumps({'code': code}), content_type='application/json')
        self.assertEqual(self.client.post(url, json.dumps({'id': str(uuid4()), 'duration_ms': 6000}), content_type='application/json').status_code, 403)
