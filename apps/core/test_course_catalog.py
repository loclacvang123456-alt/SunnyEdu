from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.assignments.models import Assignment, AssignmentRecipient
from apps.classes.models import EnglishClass, EnglishMembership
from apps.content.models import Course, CourseExercise, CourseTag, Exam, ExamVersion, Question


class CourseCatalogTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='catalog-owner', role='OWNER', display_name='Giáo viên')
        self.student = User.objects.create_user(username='catalog-student', role='STUDENT', display_name='Học sinh')
        self.other = User.objects.create_user(username='catalog-other', role='STUDENT', display_name='Học sinh khác')
        self.course = Course.objects.create(name='Ôn tiếng Anh', category='SEMESTER', difficulty=3, is_published=True, created_by=self.owner)
        self.draft_course = Course.objects.create(name='Khóa nội bộ', category='OTHER', is_published=False, created_by=self.owner)
        self.reading = CourseTag.objects.create(code='READING', name='Đọc', kind='SKILL')
        self.grammar = CourseTag.objects.create(code='PAST_TENSE', name='Thì quá khứ', kind='GRAMMAR')
        self.secret_tag = CourseTag.objects.create(code='SECRET_DRAFT', name='Bí mật bản nháp', kind='GRAMMAR')
        self.course.tags.add(self.reading)
        self.english_class = EnglishClass.objects.create(code='ENG-CTEST1', name='Lớp thử', school_year='2026-2027')
        self.course.english_classes.add(self.english_class)
        self.now = timezone.now()
        exam = Exam.objects.create(title='Đề riêng', created_by=self.owner)
        version = ExamVersion.objects.create(exam=exam, number=1, status='PUBLISHED')
        Question.objects.create(version=version, position=1, type='SINGLE_CHOICE', skill='READING', difficulty='FOUNDATION', prompt='Đề bí mật', max_points='1.00')
        self.assignment = Assignment.objects.create(version=version, title='Bài riêng học sinh', code='HW-CTEST1', status='PUBLISHED', opens_at=self.now-timedelta(days=1), due_at=self.now+timedelta(days=1), late_until=self.now+timedelta(days=2))
        self.exercise = CourseExercise.objects.create(course=self.course, assignment=self.assignment, difficulty=4)
        self.exercise.tags.add(self.grammar)
        self.draft_assignment = Assignment.objects.create(version=version, title='Bài nháp bí mật', code='HW-CTEST2', status='DRAFT', opens_at=self.now-timedelta(days=1), due_at=self.now+timedelta(days=1), late_until=self.now+timedelta(days=2))
        draft = CourseExercise.objects.create(course=self.course, assignment=self.draft_assignment, difficulty=1)
        draft.tags.add(self.secret_tag)
        AssignmentRecipient.objects.create(assignment=self.assignment, student=self.student)

    def login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session.update({'issued_at': self.now.isoformat(), 'last_activity': self.now.isoformat(), 'auth_epoch': user.auth_epoch})
        session.save()

    def test_public_catalog_hides_drafts_and_exercise_contents(self):
        response = self.client.get('/courses/')
        self.assertContains(response, 'Ôn tiếng Anh')
        self.assertContains(response, '1 bài tập')
        self.assertNotContains(response, 'Khóa nội bộ')
        self.assertNotContains(response, 'Bí mật bản nháp')
        detail = self.client.get(f'/courses/{self.course.id}/')
        self.assertContains(detail, 'Khóa học chưa mở')
        self.assertNotContains(detail, 'Bài riêng học sinh')
        self.assertNotContains(detail, 'Đề bí mật')
        self.assertEqual(self.client.get(f'/courses/{self.draft_course.id}/').status_code, 404)

    def test_filters_include_course_tags_and_published_exercise_tags_only(self):
        for query in ('skill=READING', 'tag=PAST_TENSE', 'type=SINGLE_CHOICE', 'q=Ôn'):
            self.assertContains(self.client.get('/courses/?' + query), 'Ôn tiếng Anh')
        self.assertNotContains(self.client.get('/courses/?tag=SECRET_DRAFT'), 'Ôn tiếng Anh')

    def test_student_needs_membership_and_assignment_recipient(self):
        self.login(self.student)
        path = f'/courses/{self.course.id}/'
        self.assertNotContains(self.client.get(path), 'Bài riêng học sinh')
        EnglishMembership.objects.create(student=self.student, english_class=self.english_class, start_at=self.now-timedelta(days=1))
        self.assertContains(self.client.get(path), 'Bài riêng học sinh')
        self.login(self.other)
        EnglishMembership.objects.create(student=self.other, english_class=self.english_class, start_at=self.now-timedelta(days=1))
        self.assertNotContains(self.client.get(path), 'Bài riêng học sinh')

    def test_student_cannot_open_direct_assignment_without_course_membership(self):
        self.login(self.student)
        path = f'/student/assignments/{self.assignment.id}/'
        self.assertIn(self.client.get(path).status_code, (403, 404))
        self.assertIn(self.client.post(f'/api/v1/assignments/{self.assignment.id}/start/').status_code, (403, 404))

    def test_course_access_is_revoked_for_existing_attempt_when_class_closes(self):
        membership = EnglishMembership.objects.create(student=self.student, english_class=self.english_class, start_at=self.now-timedelta(days=1))
        self.login(self.student)
        response = self.client.post(f'/api/v1/assignments/{self.assignment.id}/start/')
        self.assertEqual(response.status_code, 201)
        attempt_id = response.json()['data']['attempt_id']
        self.assertEqual(self.client.get(f'/api/v1/attempts/{attempt_id}/').status_code, 200)
        membership.end_at = timezone.now()
        membership.save(update_fields=['end_at'])
        self.assertIn(self.client.get(f'/api/v1/attempts/{attempt_id}/').status_code, (403, 404))
        self.assertNotContains(self.client.get('/student/'), 'Bài riêng học sinh')
        self.assertNotContains(self.client.get(f'/courses/{self.course.id}/'), 'Bài riêng học sinh')

    def test_student_header_preserved_on_courses_pages(self):
        resp_anon = self.client.get('/courses/')
        self.assertContains(resp_anon, 'catalog-header')
        self.assertNotContains(resp_anon, 'student-header')

        self.login(self.student)
        resp_list = self.client.get('/courses/')
        self.assertContains(resp_list, 'student-header')
        self.assertNotContains(resp_list, 'catalog-header')
        self.assertContains(resp_list, self.student.display_name)
        self.assertContains(resp_list, '<a href="/courses/" aria-current="page">Khóa học</a>')

        resp_detail = self.client.get(f'/courses/{self.course.id}/')
        self.assertContains(resp_detail, 'student-header')
        self.assertNotContains(resp_detail, 'catalog-header')
        self.assertContains(resp_detail, self.student.display_name)
        self.assertContains(resp_detail, '<a href="/courses/" aria-current="page">Khóa học</a>')

    def test_catalog_paginates_at_most_9_courses_per_page(self):
        for i in range(1, 12):
            Course.objects.create(name=f'Khóa bổ sung {i:02d}', category='SEMESTER', difficulty=2, is_published=True, created_by=self.owner)

        page1 = self.client.get('/courses/')
        self.assertEqual(page1.status_code, 200)
        self.assertEqual(len(page1.context['courses'].object_list), 9)
        self.assertEqual(page1.context['total_courses'], 12)
        self.assertContains(page1, '12 khóa')
        self.assertContains(page1, 'id="catalog-sort-toggle"')
        self.assertContains(page1, 'id="catalog-sort-drawer"')
        self.assertContains(page1, 'class="catalog-pagination"')
        self.assertContains(page1, '?page=2')

        page2 = self.client.get('/courses/?page=2')
        self.assertEqual(page2.status_code, 200)
        self.assertEqual(len(page2.context['courses'].object_list), 3)
        self.assertContains(page2, '?page=1')

