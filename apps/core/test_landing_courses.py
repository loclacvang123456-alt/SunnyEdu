from datetime import timedelta
import json

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.services import rotate_code
from apps.assignments.models import Assignment, AssignmentRecipient
from apps.classes.models import EnglishClass, EnglishMembership
from apps.content.models import Course, CourseExercise, Exam, ExamVersion


class LandingCourseTests(TestCase):
    def test_home_uses_published_courses_and_real_exercise_counts(self):
        owner = User.objects.create_user(username='course-home-owner', role='OWNER', display_name='Teacher')
        exam = Exam.objects.create(title='Exam', created_by=owner)
        version = ExamVersion.objects.create(exam=exam, number=1, status='PUBLISHED')
        now = timezone.now()
        fields = dict(version=version, opens_at=now, due_at=now + timedelta(days=1), late_until=now + timedelta(days=2))
        published = Assignment.objects.create(title='Exercise', code='HW-HOME01', status='PUBLISHED', **fields)
        draft = Assignment.objects.create(title='Hidden draft', code='HW-HOME02', status='DRAFT', **fields)
        course = Course.objects.create(name='Public course', category='IELTS', created_by=owner, is_published=True)
        Course.objects.create(name='Private course', category='OTHER', created_by=owner, is_published=False)
        CourseExercise.objects.create(course=course, assignment=published)
        CourseExercise.objects.create(course=course, assignment=draft)
        response = self.client.get('/')
        self.assertEqual(response.context['course_count'], 1)
        self.assertEqual(response.context['exercise_count'], 1)
        self.assertEqual(response.context['featured_courses'][0].exercise_count, 1)
        self.assertContains(response, 'style="--quantity: 9;"')
        self.assertContains(response, 'Học sinh đang hoạt động', count=3)
        self.assertContains(response, '<small>Khóa học</small>', count=3, html=False)
        self.assertContains(response, '<small>Bài tập</small>', count=3, html=False)
        self.assertContains(response, 'Public course')
        self.assertNotContains(response, 'Private course')
        self.assertNotContains(response, 'Hidden draft')

    def test_dashboard_and_direct_link_follow_course_access(self):
        owner = User.objects.create_user(username='course-access-owner', role='OWNER', display_name='Teacher')
        student = User.objects.create_user(username='course-access-student', role='STUDENT', display_name='Student')
        code = rotate_code(student, actor=owner)
        self.client.post('/api/v1/auth/student-login/', json.dumps({'code': code}), content_type='application/json')
        exam = Exam.objects.create(title='Exam', created_by=owner)
        version = ExamVersion.objects.create(exam=exam, number=1, status='PUBLISHED')
        now = timezone.now()
        assignment = Assignment.objects.create(version=version, title='Course exercise', code='HW-LOCK01', status='PUBLISHED', opens_at=now-timedelta(hours=1), due_at=now+timedelta(days=1), late_until=now+timedelta(days=2))
        AssignmentRecipient.objects.create(assignment=assignment, student=student)
        course = Course.objects.create(name='Class course', category='IELTS', created_by=owner, is_published=True)
        CourseExercise.objects.create(course=course, assignment=assignment)
        link = f'/student/assignments/{assignment.id}/'
        self.assertNotContains(self.client.get('/student/'), 'Course exercise')
        self.assertEqual(self.client.get(link).status_code, 403)
        classroom = EnglishClass.objects.create(code='ENG-LOCK01', name='English', school_year='2026-2027')
        EnglishMembership.objects.create(student=student, english_class=classroom, start_at=now-timedelta(days=1))
        course.english_classes.add(classroom)
        self.assertContains(self.client.get('/student/'), 'Course exercise')
        self.assertEqual(self.client.get(link).status_code, 200)
        classroom.archived_at = now
        classroom.save(update_fields=['archived_at'])
        self.assertNotContains(self.client.get('/student/'), 'Course exercise')
        self.assertEqual(self.client.get(link).status_code, 403)

    def test_score_podium_requires_five_distinct_published_exercises(self):
        from apps.assignments.models import Attempt
        from apps.grading.models import GradeRelease

        owner = User.objects.create_user(username='ranking-owner', role='OWNER')
        beginner = User.objects.create_user(username='ranking-beginner', role='STUDENT', display_name='Beginner')
        consistent = User.objects.create_user(username='ranking-consistent', role='STUDENT', display_name='Consistent')
        exam = Exam.objects.create(title='Exam', created_by=owner)
        version = ExamVersion.objects.create(exam=exam, number=1, status='PUBLISHED')
        now = timezone.now()
        for i in range(5):
            assignment = Assignment.objects.create(title=f'Exercise {i}', code=f'RANK-{i}', version=version, status='PUBLISHED', opens_at=now, due_at=now + timedelta(days=1), late_until=now + timedelta(days=2))
            recipient = AssignmentRecipient.objects.create(assignment=assignment, student=consistent)
            attempt = Attempt.objects.create(recipient=recipient, attempt_no=1, status='SUBMITTED', submitted_at=now)
            GradeRelease.objects.create(attempt=attempt, number=1, total_points=8, max_points=10, published_by=owner, snapshot={})
            if i == 0:
                GradeRelease.objects.create(attempt=attempt, number=2, total_points=9, max_points=10, published_by=owner, snapshot={})
                recipient = AssignmentRecipient.objects.create(assignment=assignment, student=beginner)
                attempt = Attempt.objects.create(recipient=recipient, attempt_no=1, status='SUBMITTED', submitted_at=now)
                for number in range(1, 6):
                    GradeRelease.objects.create(attempt=attempt, number=number, total_points=10, max_points=10, published_by=owner, snapshot={})
        response = self.client.get('/')
        podiums = {podium['key']: podium for podium in response.context['podiums']}
        self.assertEqual(len(podiums), 3)
        first = podiums['score']['places'][1]['entry']
        self.assertEqual(first['name'], 'Consistent')
        self.assertEqual(first['display_value'], '8.2 điểm')
        self.assertIsNone(podiums['score']['places'][0]['entry'])
        self.assertContains(response, 'Tối thiểu 5 bài đã công bố điểm')
        self.assertContains(response, 'podium-avatar-wrap')
        self.assertContains(response, 'laurel-rank-1.png')
        self.assertContains(response, 'laurel-rank-2.png')
        self.assertContains(response, 'laurel-rank-3.png')
        self.assertNotContains(response, '<svg class="laurel"')
