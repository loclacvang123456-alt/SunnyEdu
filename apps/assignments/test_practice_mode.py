import json
from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from apps.accounts.models import User
from apps.accounts.services import rotate_code
from apps.assignments.models import Assignment, AssignmentRecipient
from apps.content.models import Exam, ExamVersion, Question


class PracticeModeTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='mode-owner', role='OWNER', display_name='Giáo viên')
        self.student = User.objects.create_user(username='mode-student', role='STUDENT', display_name='Học sinh')
        code = rotate_code(self.student, self.owner)
        login = self.client.post('/api/v1/auth/student-login/', data=json.dumps({'code': code}), content_type='application/json')
        self.assertEqual(login.status_code, 200)
        exam = Exam.objects.create(title='Mode test', created_by=self.owner)
        self.version = ExamVersion.objects.create(exam=exam, number=1, status='PUBLISHED')
        Question.objects.create(version=self.version, position=1, type='TEXT', skill='WRITING', difficulty='STANDARD', prompt='Write', max_points='1')

    def make_assignment(self, code, mode):
        now = timezone.now()
        a = Assignment.objects.create(version=self.version, title=code, code=code, status='PUBLISHED', mode=mode, opens_at=now-timedelta(hours=1), due_at=now+timedelta(hours=1), late_until=now+timedelta(days=1))
        AssignmentRecipient.objects.create(student=self.student, assignment=a)
        return a

    def test_practice_and_exam_are_preserved_per_assignment(self):
        for code, mode in [('HW-AAAAAA', 'PRACTICE'), ('HW-BBBBBB', 'EXAM')]:
            a = self.make_assignment(code, mode)
            response = self.client.post(f'/student/assignments/{a.id}/', follow=True)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, f'data-mode="{mode}"')
            self.assertContains(response, 'id="practice-navigation"')
            if mode == 'PRACTICE':
                self.assertContains(response, 'exercise-practice-page')
                self.assertContains(response, 'class="practice-heading"')
            else:
                self.assertNotContains(response, 'exercise-practice-page')
                self.assertContains(response, 'class="page-heading"')

    def test_writing_helper_only_available_in_practice(self):
        from unittest.mock import patch
        expected = {'offset_encoding': 'utf-16', 'matches': []}
        for code, mode, status in [('HW-CCCCCC', 'PRACTICE', 200), ('HW-DDDDDD', 'EXAM', 403)]:
            assignment = self.make_assignment(code, mode)
            self.client.post(f'/student/assignments/{assignment.id}/')
            recipient = AssignmentRecipient.objects.get(assignment=assignment, student=self.student)
            detail = self.client.get(f'/api/v1/attempts/{recipient.current_attempt_id}/').json()['data']
            response_id = detail['questions'][0]['response_id']
            with patch('apps.grading.writing_views.check_writing', return_value=expected) as service:
                res = self.client.post(f'/api/v1/writing/responses/{response_id}/check/', data=json.dumps({'text':'She go to school.'}), content_type='application/json')
            self.assertEqual(res.status_code, status)
            self.assertEqual(service.call_count, 1 if mode == 'PRACTICE' else 0)
