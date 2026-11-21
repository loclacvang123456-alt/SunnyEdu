import json
from datetime import timedelta
from uuid import uuid4

from django.test import TestCase
from django.utils import timezone
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.models import User
from apps.accounts.tests_owner import _login_verified_owner
from apps.assignments.models import Assignment, AssignmentClass, AssignmentRecipient
from apps.assignments.services import save_response, start_attempt, submit_attempt
from apps.classes.models import EnglishClass, EnglishMembership
from apps.content.models import AnswerKeyOption, Course, CourseTag, Exam, ExamVersion, Question, QuestionOption


class CourseTeacherUITests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='course-owner', password='StrongPassword!2026', role='OWNER', display_name='Giáo viên', is_staff=True)
        self.device = TOTPDevice.objects.create(user=self.owner, name='default', confirmed=True)
        self.classroom = EnglishClass.objects.create(code='ENG-COURSE', name='Lớp mẫu', school_year='2026-2027')
        exam = Exam.objects.create(title='Đề mẫu', created_by=self.owner)
        version = ExamVersion.objects.create(exam=exam, number=1, status='PUBLISHED')
        now = timezone.now()
        self.assignment = Assignment.objects.create(version=version, title='Bài mẫu', code='HW-CRS001', opens_at=now, due_at=now+timedelta(days=1), late_until=now+timedelta(days=2))

    def test_course_pages_require_verified_teacher(self):
        self.assertEqual(self.client.get('/teacher/courses/').status_code, 302)
        self.client.force_login(self.owner)
        session = self.client.session
        now = timezone.now().isoformat()
        session.update({'auth_epoch': self.owner.auth_epoch, 'issued_at': now, 'last_activity': now})
        session.save()
        self.assertEqual(self.client.get('/teacher/courses/').status_code, 302)

    def test_teacher_can_create_course_assign_class_and_edit_exercise(self):
        _login_verified_owner(self.client, self.owner, 'StrongPassword!2026', self.device)
        result = self.client.post('/teacher/courses/', {'name': 'IELTS cơ bản', 'description': 'Luyện tập', 'category': 'IELTS', 'difficulty': '2', 'is_published': 'on'})
        self.assertEqual(result.status_code, 302)
        course = Course.objects.get(name='IELTS cơ bản')
        url = f'/teacher/courses/{course.id}/'
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.post(url, {'action': 'classes', 'class_ids': [str(self.classroom.id)]})
        self.assertTrue(course.english_classes.filter(pk=self.classroom.id).exists())
        self.client.post(url, {'action': 'create_tag', 'tag_name': 'Đọc hiểu', 'tag_kind': 'SKILL'})
        tag = CourseTag.objects.get(name='Đọc hiểu')
        self.client.post(url, {'action': 'course_tags', 'tag_ids': [str(tag.id)]})
        self.assertTrue(course.tags.filter(pk=tag.id).exists())
        self.client.post(url, {'action': 'add_exercise', 'assignment_id': str(self.assignment.id), 'difficulty': '3', 'tag_ids': [str(tag.id)]})
        exercise = course.exercises.get(assignment=self.assignment)
        self.assertEqual(exercise.difficulty, 3)
        self.assertTrue(exercise.tags.filter(pk=tag.id).exists())
        self.assertContains(self.client.get(url), 'Chỉnh bài')
        self.client.post(url, {'action': 'add_exercise', 'assignment_id': str(self.assignment.id), 'difficulty': '4'})
        exercise.refresh_from_db()
        self.assertEqual(exercise.difficulty, 4)
        self.assertFalse(exercise.tags.exists())
        self.client.post(url, {'action': 'remove_exercise', 'exercise_id': str(exercise.id)})
        self.assertFalse(course.exercises.exists())

    def test_create_exercise_from_course_and_direct_question_editing(self):
        student = User.objects.create_user(username='course-ui-stu', role='STUDENT', display_name='Lan')
        EnglishMembership.objects.create(student=student, english_class=self.classroom, start_at=timezone.now() - timedelta(days=1))
        course = Course.objects.create(name='Ôn thi lớp 11', category='HIGH_SCHOOL', difficulty=3, is_published=True, created_by=self.owner)
        _login_verified_owner(self.client, self.owner, 'StrongPassword!2026', self.device)

        url = f'/teacher/courses/{course.id}/'
        self.client.post(url, {'action': 'classes', 'class_ids': [str(self.classroom.id)]})
        resp = self.client.post(url, {'action': 'create_new_exercise', 'title': 'Đề ôn tập HK1', 'difficulty': '3'})
        self.assertEqual(resp.status_code, 302)
        created_ex = course.exercises.get(assignment__title='Đề ôn tập HK1')
        version = created_ex.assignment.version
        expected_editor = f'/teacher/exams/{version.exam_id}/versions/{version.id}/'
        self.assertTrue(resp['Location'].startswith(expected_editor))
        self.assertIn(f'course_id={course.id}', resp['Location'])
        self.assertTrue(created_ex.assignment.classes.filter(pk=self.classroom.id).exists())

        # Course detail links directly to question editor and displays question count
        detail_resp = self.client.get(url)
        self.assertContains(detail_resp, expected_editor)
        self.assertContains(detail_resp, '0 câu')

        # Direct UI edit works on DRAFT/PUBLISHED version without manual topic_tags and auto-publishes/syncs recipients
        q_resp = self.client.post(
            f'/api/v1/owner/versions/{version.id}/questions',
            data=json.dumps({
                'expected_revision': version.revision,
                'ui_direct_edit': True,
                'type': 'SINGLE_CHOICE',
                'skill': 'READING',
                'difficulty': 'STANDARD',
                'max_points': '1.00',
                'prompt': 'She ___ to school every day.',
                'options': [{'content': 'goes'}, {'content': 'go'}],
                'correct_options': ['A'],
            }),
            content_type='application/json',
        )
        self.assertEqual(q_resp.status_code, 201)
        self.assertEqual(version.questions.count(), 1)
        created_ex.assignment.refresh_from_db()
        self.assertEqual(created_ex.assignment.status, 'PUBLISHED')
        self.assertTrue(AssignmentRecipient.objects.filter(assignment=created_ex.assignment, student=student).exists())
        self.assertContains(self.client.get(url), '1 câu')

    def test_bulk_assign_from_course_and_per_target_schedule_with_retries(self):
        class2 = EnglishClass.objects.create(code='ENG-B2', name='Lớp B2', school_year='2026-2027')
        stu1 = User.objects.create_user(username='assign-stu1', role='STUDENT', display_name='An')
        stu2 = User.objects.create_user(username='assign-stu2', role='STUDENT', display_name='Bình')
        now = timezone.now()
        EnglishMembership.objects.create(student=stu1, english_class=self.classroom, start_at=now - timedelta(days=1))
        EnglishMembership.objects.create(student=stu2, english_class=class2, start_at=now - timedelta(days=1))

        course = Course.objects.create(name='Khóa Giao Bài', category='HIGH_SCHOOL', difficulty=3, is_published=True, created_by=self.owner)
        _login_verified_owner(self.client, self.owner, 'StrongPassword!2026', self.device)
        course_url = f'/teacher/courses/{course.id}/'

        # Create 2 exercises inside the course
        self.client.post(course_url, {'action': 'create_new_exercise', 'title': 'Bài tập 1', 'difficulty': '2'})
        self.client.post(course_url, {'action': 'create_new_exercise', 'title': 'Bài tập 2', 'difficulty': '4'})
        ex1 = course.exercises.get(assignment__title='Bài tập 1')
        ex2 = course.exercises.get(assignment__title='Bài tập 2')

        # Add 1 auto-graded question to ex1 so submit_attempt can run
        q1 = Question.objects.create(
            version=ex1.assignment.version, position=1, type='SINGLE_CHOICE', skill='READING',
            difficulty='STANDARD', prompt='1+1=?', max_points='1.00',
        )
        opt_a = QuestionOption.objects.create(question=q1, key='A', position=1, content='2')
        QuestionOption.objects.create(question=q1, key='B', position=2, content='3')
        AnswerKeyOption.objects.create(question=q1, option=opt_a)

        # Course page shows tabs/multiselect modals and hides old unlock-only button
        course_resp = self.client.get(course_url)
        self.assertEqual(course_resp.status_code, 200)
        self.assertNotContains(course_resp, 'modal-course-classes')
        self.assertContains(course_resp, 'modal-course-assign')
        self.assertContains(course_resp, 'modal-course-assign-schedule')

        # Bulk assign both exercises to self.classroom with max_attempts=3
        due_class_str = timezone.localtime(now + timedelta(days=5)).strftime('%Y-%m-%dT%H:%M')
        resp = self.client.post(course_url, {
            'action': 'assign_exercises',
            'assignment_ids': [str(ex1.assignment_id), str(ex2.assignment_id)],
            'class_ids': [str(self.classroom.id)],
            'due_at': due_class_str,
            'max_attempts': '3',
            'mode': 'PRACTICE',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(course.english_classes.filter(pk=self.classroom.id).exists())
        ac1 = AssignmentClass.objects.get(assignment=ex1.assignment, english_class=self.classroom)
        self.assertEqual(ac1.max_attempts, 3)
        rec1 = AssignmentRecipient.objects.get(assignment=ex1.assignment, student=stu1)
        self.assertEqual(rec1.max_attempts, 3)
        self.assertIsNotNone(rec1.due_at_override)
        self.assertFalse(AssignmentRecipient.objects.filter(assignment=ex1.assignment, student=stu2).exists())
        self.assertTrue(AssignmentRecipient.objects.filter(assignment=ex2.assignment, student=stu1).exists())

        # Assignment detail removes general schedule box and has class/student tabs
        assign_url = f'/teacher/assignments/{ex1.assignment_id}/'
        assign_resp = self.client.get(assign_url)
        self.assertEqual(assign_resp.status_code, 200)
        self.assertNotContains(assign_resp, 'Lịch &amp; Thiết lập bài giao')
        self.assertContains(assign_resp, 'Danh sách Lớp học')
        self.assertContains(assign_resp, 'Cá nhân Học sinh')

        # Assign ex1 individually to stu2 with max_attempts=2
        due_stu_str = timezone.localtime(now + timedelta(days=10)).strftime('%Y-%m-%dT%H:%M')
        resp2 = self.client.post(assign_url, {
            'action': 'assign_targets',
            'student_ids': [str(stu2.id)],
            'due_at': due_stu_str,
            'max_attempts': '2',
            'mode': 'EXAM',
        })
        self.assertEqual(resp2.status_code, 302)
        rec2 = AssignmentRecipient.objects.get(assignment=ex1.assignment, student=stu2)
        self.assertEqual(rec2.max_attempts, 2)
        self.assertTrue(course.english_classes.filter(pk=class2.id).exists())

        # Verify stu1 can start and submit up to max_attempts=3 tries, not 4
        for expected_no in (1, 2, 3):
            att, created = start_attempt(rec1.id, stu1)
            self.assertTrue(created)
            self.assertEqual(att.attempt_no, expected_no)
            _, att = save_response(att.id, q1.id, stu1, 0, option_ids=[str(opt_a.id)])
            submit_attempt(att.id, stu1, att.revision, uuid4())
        att_extra, created_extra = start_attempt(rec1.id, stu1)
        self.assertFalse(created_extra)
        self.assertEqual(att_extra.attempt_no, 3)
