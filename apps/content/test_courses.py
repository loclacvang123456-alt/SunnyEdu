from datetime import timedelta
from io import StringIO
import json
from uuid import uuid4

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.services import rotate_code
from apps.assignments.models import Assignment, AssignmentRecipient
from apps.assignments.services import course_access_allowed, start_attempt
from apps.classes.models import EnglishClass, EnglishMembership
from .course_services import (add_course_exercise, create_and_attach_course_exercise, create_course, create_course_tag,
                              set_course_classes, set_course_tags, update_course)
from .models import Course, CourseExercise, CourseTag, Exam, ExamVersion, Question, QuestionOption, AnswerKeyOption


class CourseServiceTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='owner-courses', role='OWNER', display_name='Giáo viên')
        self.student = User.objects.create_user(username='student-courses', role='STUDENT', display_name='Học sinh')
        self.course = create_course(self.owner, 'IELTS', 'Bốn kỹ năng', 'IELTS', 2, True)
        self.english_class = EnglishClass.objects.create(code='ENG-TEST01', name='Lớp A', school_year='2026-2027')
        self.tag = create_course_tag(self.owner, 'Thì hiện tại', 'GRAMMAR')
        exam = Exam.objects.create(title='Đề mẫu', created_by=self.owner)
        version = ExamVersion.objects.create(exam=exam, number=1, status='PUBLISHED')
        now = timezone.now()
        self.assignment = Assignment.objects.create(version=version, title='Bài mẫu', code='HW-TEST01',
            status='PUBLISHED', opens_at=now, due_at=now+timedelta(days=1), late_until=now+timedelta(days=2))

    def test_new_course_exercise_is_editable_draft(self):
        set_course_classes(self.owner, self.course.id, [str(self.english_class.id)])
        exercise, exam, version = create_and_attach_course_exercise(self.owner, self.course.id, 'New exercise', 2)
        self.assertEqual(version.status, 'DRAFT')
        self.assertEqual(exercise.assignment.status, 'DRAFT')
        self.assertFalse(exercise.assignment.recipients.exists())
        self.assertTrue(exercise.assignment.classes.filter(pk=self.english_class.pk).exists())

    def test_assign_classes_and_exercises(self):
        set_course_classes(self.owner, self.course.id, [str(self.english_class.id)])
        set_course_tags(self.owner, self.course.id, [str(self.tag.id)])
        exercise = add_course_exercise(self.owner, self.course.id, self.assignment.id, 4, [str(self.tag.id)])
        self.assertEqual(self.course.english_classes.get(), self.english_class)
        self.assertEqual(self.course.tags.get(), self.tag)
        self.assertEqual(exercise.tags.get(), self.tag)
        self.assertEqual(exercise.difficulty, 4)
        add_course_exercise(self.owner, self.course.id, self.assignment.id, 2, [])
        self.assertEqual(CourseExercise.objects.count(), 1)
        exercise.refresh_from_db()
        self.assertEqual(exercise.difficulty, 2)
        self.assertFalse(exercise.tags.exists())

    def test_reject_student_and_invalid_values_without_changes(self):
        with self.assertRaises(PermissionDenied):
            set_course_classes(self.student, self.course.id, [str(self.english_class.id)])
        with self.assertRaises(ValidationError):
            update_course(self.owner, self.course.id, 'Mới', '', 'IELTS', 6, True)
        self.course.refresh_from_db()
        self.assertEqual(self.course.name, 'IELTS')
        with self.assertRaises(ValidationError):
            set_course_classes(self.owner, self.course.id, ['invalid'])
        with self.assertRaises(ValidationError):
            add_course_exercise(self.owner, self.course.id, self.assignment.id, 1, ['invalid'])
        self.assertFalse(CourseExercise.objects.exists())

    def test_samples_are_idempotent_and_do_not_enrol_or_assign(self):
        call_command('seed_courses', stdout=StringIO())
        sample = Course.objects.get(name='IELTS nền tảng (mẫu)')
        self.assertEqual(set(sample.tags.values_list('code', flat=True)), {'READING', 'WRITING', 'SPEAKING', 'LISTENING'})
        self.assertFalse(sample.english_classes.exists())
        self.assertEqual(sample.exercises.count(), 3)
        self.assertFalse(sample.exercises.first().assignment.recipients.exists())
        self.assertFalse(sample.exercises.first().assignment.classes.exists())
        sample.description = 'Đã sửa'
        sample.save(update_fields=['description'])
        sample.tags.remove(CourseTag.objects.get(code='WRITING'))
        call_command('seed_courses', stdout=StringIO())
        sample.refresh_from_db()
        self.assertEqual(sample.description, 'Đã sửa')
        self.assertFalse(sample.tags.filter(code='WRITING').exists())
        self.assertEqual(Course.objects.filter(is_sample=True).count(), 3)
        self.assertEqual(CourseExercise.objects.filter(course__is_sample=True).count(), 6)

    def test_course_enrolment_guards_student_api_after_revocation(self):
        self.assignment.game_feedback_enabled = True
        self.assignment.opens_at = timezone.now() - timedelta(hours=1)
        self.assignment.save(update_fields=['game_feedback_enabled', 'opens_at'])
        question = Question.objects.create(version=self.assignment.version, position=1, type='SINGLE_CHOICE', skill='READING', difficulty='FOUNDATION', prompt='Choose', max_points='1')
        right = QuestionOption.objects.create(question=question, key='A', position=1, content='Yes')
        QuestionOption.objects.create(question=question, key='B', position=2, content='No')
        AnswerKeyOption.objects.create(question=question, option=right)
        recipient = AssignmentRecipient.objects.create(assignment=self.assignment, student=self.student)
        attempt, _ = start_attempt(recipient.id, self.student)
        code = rotate_code(self.student, actor=self.owner)
        self.client.post('/api/v1/auth/student-login/', json.dumps({'code': code}), content_type='application/json')
        url = f'/api/v1/attempts/{attempt.id}/'
        self.assertEqual(self.client.get(url).status_code, 200)
        add_course_exercise(self.owner, self.course.id, self.assignment.id, 2, [])
        self.assertEqual(self.client.get(url).status_code, 403)
        set_course_classes(self.owner, self.course.id, [str(self.english_class.id)])
        membership = EnglishMembership.objects.create(student=self.student, english_class=self.english_class, start_at=timezone.now()-timedelta(days=1))
        self.assertEqual(self.client.get(url).status_code, 200)
        membership.end_at = timezone.now()
        membership.save(update_fields=['end_at'])
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(f'/api/v1/assignments/{self.assignment.id}/start/').status_code, 403)
        shot_body = json.dumps({'option_id': str(right.id), 'expected_revision': 0})
        self.assertEqual(self.client.post(f'{url}responses/{question.id}/shot/', shot_body, content_type='application/json', HTTP_IDEMPOTENCY_KEY=str(uuid4())).status_code, 403)
        self.assertEqual(self.client.put(f'{url}responses/{question.id}/', json.dumps({'expected_revision': 0, 'option_ids': [str(right.id)]}), content_type='application/json').status_code, 403)
        self.assertEqual(self.client.post(f'{url}submit/', json.dumps({'expected_attempt_revision': 0}), content_type='application/json', HTTP_IDEMPOTENCY_KEY=str(uuid4())).status_code, 403)
        self.assertEqual(self.client.get('/api/v1/assignments/').json()['data'], [])

    def test_any_published_course_can_open_shared_assignment(self):
        add_course_exercise(self.owner, self.course.id, self.assignment.id, 2, [])
        another = create_course(self.owner, 'Ôn tập', '', 'SEMESTER', 1, True)
        add_course_exercise(self.owner, another.id, self.assignment.id, 1, [])
        set_course_classes(self.owner, another.id, [str(self.english_class.id)])
        EnglishMembership.objects.create(student=self.student, english_class=self.english_class, start_at=timezone.now()-timedelta(days=1))
        self.assertTrue(course_access_allowed(self.assignment.id, self.student))
        update_course(self.owner, another.id, another.name, another.description, another.category, another.difficulty, False)
        self.assertFalse(course_access_allowed(self.assignment.id, self.student))
