from datetime import timedelta
from decimal import Decimal
import json
from uuid import uuid4

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.assignments.models import Assignment, AssignmentRecipient
from apps.assignments.sentence_transform_service import grade_sentence_transform, grade_word_form
from apps.assignments.services import save_response, start_attempt, submit_attempt
from apps.content.models import Exam, ExamVersion, Question, QuestionOption
from apps.grading.models import Grade


class SentenceTransformTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(username='teacher_trans', role='OWNER', display_name='Teacher')
        self.student = User.objects.create_user(username='student_trans', role='STUDENT', display_name='Student')

    def test_sentence_transform_grading_logic(self):
        # 1. Exact match
        res_exact = grade_sentence_transform(
            "He said that he was tired.",
            "He said that he was tired.",
            Decimal('2.00')
        )
        self.assertEqual(res_exact['points'], Decimal('2.00'))
        self.assertEqual(res_exact['status'], 'correct')
        self.assertEqual(res_exact['minor_errors'], 0)
        self.assertEqual(res_exact['major_errors'], 0)

        # 2. Minor typo error (-0.5 points)
        res_typo = grade_sentence_transform(
            "He said that he was tired", # missing period
            "He said that he was tired.",
            Decimal('2.00')
        )
        self.assertEqual(res_typo['points'], Decimal('1.50'))
        self.assertEqual(res_typo['minor_errors'], 1)
        self.assertEqual(res_typo['major_errors'], 0)

        # 3. Major error (different word -> 0 points)
        res_major = grade_sentence_transform(
            "He said that he was happy.",
            "He said that he was tired.",
            Decimal('2.00')
        )
        self.assertEqual(res_major['points'], Decimal('0.00'))
        self.assertGreater(res_major['major_errors'], 0)

        # 4. Check diff_tokens contains teacher_word and error hints
        has_error_token = any(t['is_error'] for t in res_major['diff_tokens'])
        self.assertTrue(has_error_token)

    def test_whitespace_and_punctuation_spacing_only_adds_guidance(self):
        for answer in ('Oke . oke', 'Oke .oke', '  Oke.   oke  ', 'Oke.oke'):
            with self.subTest(answer=answer):
                result = grade_sentence_transform(answer, 'Oke. oke', Decimal('2.00'))
                self.assertEqual(result['points'], Decimal('2.00'))
                self.assertEqual(result['status'], 'correct')
                self.assertIn('Gợi ý', result['feedback'])
        correct = grade_sentence_transform('Oke. oke', 'Oke. oke', Decimal('2.00'))
        self.assertNotIn('Gợi ý', correct['feedback'])
        missing = grade_sentence_transform('Oke oke', 'Oke. oke', Decimal('2.00'))
        self.assertLess(missing['points'], Decimal('2.00'))
        wrong = grade_sentence_transform('Oke. different', 'Oke. oke', Decimal('2.00'))
        self.assertLess(wrong['points'], Decimal('2.00'))

    def test_capitalization_is_advice_not_a_deduction(self):
        result = grade_sentence_transform('he SAID that he was tired.', 'He said that he was tired.', Decimal('2.00'))
        self.assertEqual(result['points'], Decimal('2.00'))
        self.assertEqual(result['minor_errors'], 0)
        self.assertIn('Gợi ý viết hoa', result['feedback'])
        self.assertIn("'he' → 'He'", result['feedback'])
        mixed = grade_sentence_transform('he said that he was tired', 'He said that he was tired.', Decimal('2.00'))
        self.assertEqual(mixed['points'], Decimal('1.50'))
        self.assertIn('Gợi ý viết hoa', mixed['feedback'])

    def test_sentence_transform_flow_and_result_view(self):
        exam = Exam.objects.create(title='Transform Test', created_by=self.teacher)
        version = ExamVersion.objects.create(exam=exam, number=1, status='PUBLISHED')
        q = Question.objects.create(
            version=version,
            position=1,
            type='SENTENCE_TRANSFORM',
            skill='WRITING',
            difficulty='FOUNDATION',
            prompt='Chuyển sang câu gián tiếp: "I am tired", he said.',
            max_points='2.00'
        )
        QuestionOption.objects.create(
            question=q,
            key='A',
            position=1,
            content='He said that he was tired.'
        )

        now = timezone.now()
        assignment = Assignment.objects.create(
            version=version,
            title='Bài tập biến đổi câu',
            code='HW-TR01',
            status='PUBLISHED',
            opens_at=now - timedelta(hours=1),
            due_at=now + timedelta(hours=2),
            late_until=now + timedelta(days=1),
        )
        recipient = AssignmentRecipient.objects.create(assignment=assignment, student=self.student)

        # Start attempt
        attempt, created = start_attempt(recipient.pk, self.student)
        self.assertTrue(created)

        # Student saves response with 1 minor typo (missing period)
        resp, attempt = save_response(
            attempt.id,
            q.id,
            self.student,
            0,
            text_answer='He said that he was tired'
        )
        self.assertEqual(resp.text_answer, 'He said that he was tired')

        # Submit attempt
        submit_res = submit_attempt(attempt.id, self.student, attempt.revision, uuid4())
        self.assertEqual(submit_res['status'], 'GRADED')

        # Verify Grade
        grade = Grade.objects.get(response=resp)
        self.assertEqual(grade.points, Decimal('1.50'))
        feedback = json.loads(grade.feedback)
        self.assertEqual(feedback['minor_errors'], 1)

        # Student logs in and accesses Result page
        from apps.accounts.services import rotate_code
        code = rotate_code(self.student, actor=self.teacher)
        login_res = self.client.post(
            '/api/v1/auth/student-login/',
            data=json.dumps({'code': code, 'remember_device': True}),
            content_type='application/json'
        )
        self.assertEqual(login_res.status_code, 200)

        result_url = reverse('student_assignment_result', args=[assignment.id])
        res = self.client.get(result_url)
        self.assertEqual(res.status_code, 200)
        content = res.content.decode('utf-8')
        self.assertIn('Kết quả: Bài tập biến đổi câu', content)
        self.assertIn('He said that he was tired.', content)
        self.assertIn('↑', content)
        self.assertIn('THANG 10', content)

        # Verify student dashboard contains link to result
        dash_res = self.client.get(reverse('student_dashboard'))
        self.assertEqual(dash_res.status_code, 200)
        dash_content = dash_res.content.decode('utf-8')
        self.assertIn('Xem kết quả', dash_content)
        self.assertIn(result_url, dash_content)


class WordFormTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(username='teacher_wf', role='OWNER', display_name='Teacher')
        self.student = User.objects.create_user(username='student_wf', role='STUDENT', display_name='Student')

    def test_word_form_grading_logic(self):
        # 1. Exact, case-insensitive, extra spaces
        for ans in ('friendly', 'FRIENDLY', '  Friendly  '):
            with self.subTest(ans=ans):
                res = grade_word_form(ans, 'friendly', Decimal('1.00'))
                self.assertEqual(res['points'], Decimal('1.00'))
                self.assertEqual(res['status'], 'correct')

        # 2. Multi-variant answers separated by /
        for ans in ('cleverer', 'PRETTIER', 'prettier'):
            with self.subTest(ans=ans):
                res = grade_word_form(ans, 'cleverer/prettier', Decimal('1.00'))
                self.assertEqual(res['points'], Decimal('1.00'))
                self.assertEqual(res['status'], 'correct')

        # 3. Wrong spelling -> 0 points
        res_wrong = grade_word_form('frendly', 'friendly', Decimal('1.00'))
        self.assertEqual(res_wrong['points'], Decimal('0.00'))
        self.assertEqual(res_wrong['status'], 'wrong')
        self.assertIn('friendly', res_wrong['feedback'])

        # 4. Blank -> 0 points
        res_blank = grade_word_form('   ', 'friendly', Decimal('1.00'))
        self.assertEqual(res_blank['points'], Decimal('0.00'))
        self.assertEqual(res_blank['status'], 'wrong')

    def test_word_form_flow_no_leak_and_result_view(self):
        exam = Exam.objects.create(title='Word Form Test', created_by=self.teacher)
        version = ExamVersion.objects.create(exam=exam, number=1, status='PUBLISHED')
        q = Question.objects.create(
            version=version,
            position=1,
            type='WORD_FORM',
            skill='WRITING',
            difficulty='STANDARD',
            prompt='Dùng dạng đúng của từ trong ngoặc\n\nHe said good morning in a most ......... way. (friend)',
            max_points='1.00',
        )
        QuestionOption.objects.create(question=q, key='A', position=1, content='friendly')

        now = timezone.now()
        assignment = Assignment.objects.create(
            version=version,
            title='Bài tập Word form',
            code='HW-WF01',
            status='PUBLISHED',
            opens_at=now - timedelta(hours=1),
            due_at=now + timedelta(hours=2),
            late_until=now + timedelta(days=1),
        )
        recipient = AssignmentRecipient.objects.create(assignment=assignment, student=self.student)
        attempt, _ = start_attempt(recipient.pk, self.student)

        # Log in student and verify attempt payload does NOT leak standard answer
        from apps.accounts.services import rotate_code
        code = rotate_code(self.student, actor=self.teacher)
        login_res = self.client.post(
            '/api/v1/auth/student-login/',
            data=json.dumps({'code': code, 'remember_device': True}),
            content_type='application/json',
        )
        self.assertEqual(login_res.status_code, 200)

        payload_res = self.client.get(f'/api/v1/attempts/{attempt.id}/')
        self.assertEqual(payload_res.status_code, 200)
        self.assertNotContains(payload_res, 'friendly')
        q_item = payload_res.json()['data']['questions'][0]
        self.assertEqual(q_item['type'], 'WORD_FORM')
        self.assertEqual(q_item['options'], [])

        # Save answer & submit
        resp, attempt = save_response(attempt.id, q.id, self.student, 0, text_answer='Friendly')
        submit_res = submit_attempt(attempt.id, self.student, attempt.revision, uuid4())
        self.assertEqual(submit_res['status'], 'GRADED')

        grade = Grade.objects.get(response=resp)
        self.assertEqual(grade.points, Decimal('1.00'))

        # Result view
        result_url = reverse('student_assignment_result', args=[assignment.id])
        res = self.client.get(result_url)
        self.assertEqual(res.status_code, 200)
        content = res.content.decode('utf-8')
        self.assertIn('Điền dạng đúng của từ', content)
        self.assertIn('Friendly', content)
        self.assertIn('friendly', content)
