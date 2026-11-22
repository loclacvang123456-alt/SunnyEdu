import json
from pathlib import Path
from django.conf import settings
from django.test import TestCase
from django.utils import timezone
from apps.accounts.models import User
from apps.accounts.services import rotate_code
from apps.assignments.models import Assignment, AssignmentRecipient, Attempt
from apps.content.models import Exam, ExamVersion


class LandingFlowTests(TestCase):
    def test_guest_sees_landing_with_actual_active_student_count(self):
        User.objects.create_user(username='s1', role='STUDENT', display_name='Một em')
        User.objects.create_user(username='s2', role='STUDENT', display_name='Em nghỉ', status='ARCHIVED')
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'landing.html')
        self.assertEqual(response.context['student_count'], 1)
        self.assertContains(response, 'Sunny Edu')
        self.assertContains(response, '/login/')
        self.assertContains(response, '/teacher/login/')
        html = response.content.decode('utf-8')
        nav_start = html.index('<nav class="nav-links"')
        nav_end = html.index('</nav>', nav_start)
        nav_html = html[nav_start:nav_end]
        self.assertIn('<a href="/teacher/login/">Giáo viên</a>', nav_html)
        self.assertNotIn('#ky-nang', nav_html)
        self.assertNotIn('#cach-hoc', nav_html)
        self.assertNotIn('#giao-vien', nav_html)

    def test_zero_students_is_a_real_count(self):
        response = self.client.get('/')
        self.assertEqual(response.context['student_count'], 0)
        self.assertContains(response, '>0<', html=False)

    def test_student_returns_to_dashboard_and_logout_to_home(self):
        teacher = User.objects.create_user(username='owner', role='OWNER', display_name='Giáo viên')
        student = User.objects.create_user(username='student', role='STUDENT', display_name='Học sinh')
        code = rotate_code(student, actor=teacher)
        login = self.client.post('/api/v1/auth/student-login/', data=json.dumps({'code': code, 'remember_device': True}), content_type='application/json')
        self.assertEqual(login.status_code, 200)
        self.assertRedirects(self.client.get('/'), '/student/', fetch_redirect_response=False)
        self.assertRedirects(self.client.post('/logout/'), '/', fetch_redirect_response=False)
        self.assertTemplateUsed(self.client.get('/'), 'landing.html')

    def test_teacher_can_return_to_home_and_logout_to_home(self):
        from django_otp import DEVICE_ID_SESSION_KEY
        from django_otp.plugins.otp_totp.models import TOTPDevice
        teacher = User.objects.create_user(username='owner_test', role='OWNER', display_name='Thầy Nam')
        device = TOTPDevice.objects.create(user=teacher, name="default", confirmed=True)
        self.client.force_login(teacher)
        session = self.client.session
        session[DEVICE_ID_SESSION_KEY] = device.persistent_id
        session.save()
        # Teacher visiting home can see landing page with link back to teacher portal
        home = self.client.get('/')
        self.assertEqual(home.status_code, 200)
        self.assertTemplateUsed(home, 'landing.html')
        self.assertContains(home, 'Trang giáo viên')
        self.assertContains(home, 'Đăng xuất')
        # Teacher dashboard has return-to-home and logout
        dashboard = self.client.get('/teacher/')
        self.assertEqual(dashboard.status_code, 200)
        self.assertContains(dashboard, 'Về trang chủ')
        self.assertContains(dashboard, 'Đăng xuất')
        # Logging out via POST redirects to home '/'
        self.assertRedirects(self.client.post('/logout/'), '/', fetch_redirect_response=False)
        # Logging out via GET also redirects to home '/'
        self.client.force_login(teacher)
        self.assertRedirects(self.client.get('/logout/'), '/', fetch_redirect_response=False)

    def test_landing_and_login_reference_existing_illustrations(self):
        home = self.client.get('/')
        self.assertContains(home, 'img/sunny-edu/slider%201.png')
        self.assertContains(home, 'img/sunny-edu/slider%202.png')
        self.assertContains(home, 'img/sunny-edu/slider%203.png')
        self.assertContains(home, 'img/sunny-edu/trust-mascot.png')
        self.assertContains(home, 'img/sunny-edu/champions-mascot.png')
        self.assertContains(home, 'class="trust-center-logo"')
        self.assertContains(home, 'class="btn-mascot"')
        self.assertNotContains(home, 'btnCloud')
        self.assertContains(home, 'class="sunny-button" href="/courses/"')
        self.assertContains(home, 'id="sunny-topup"')
        self.assertContains(home, 'img/sunny-edu/topup.png')
        self.assertContains(home, 'id="giao-vien"')

        login = self.client.get('/login/')
        self.assertEqual(login.status_code, 200)
        self.assertContains(login, 'img/sunny-edu/student-login.png')
        self.assertNotContains(login, 'class="circle circle-12"')

        asset_dir = Path(settings.BASE_DIR) / 'static' / 'img' / 'sunny-edu'
        for name in (
            'slider 1.png',
            'slider 2.png',
            'slider 3.png',
            'home-hero-desktop.png',
            'home-four-skills.png',
            'home-how-it-works.png',
            'home-teacher-feedback.png',
            'skill-listening.png',
            'student-login.png',
            'empty-assignments.png',
            'submission-success.png',
            'home-background.png',
            'trust-mascot.png',
            'champions-mascot.png',
            'button-mascot.png',
            'topup.png',
        ):
            self.assertTrue((asset_dir / name).is_file(), f'Missing image: {name}')

    def test_student_empty_state_and_submission_receipt_visibility(self):
        teacher = User.objects.create_user(username='owner2', role='OWNER', display_name='Cô Hoa')
        student = User.objects.create_user(username='student2', role='STUDENT', display_name='Minh')
        code = rotate_code(student, actor=teacher)
        self.client.post('/api/v1/auth/student-login/', data=json.dumps({'code': code}), content_type='application/json')

        dash = self.client.get('/student/')
        self.assertEqual(dash.status_code, 200)
        self.assertContains(dash, 'img/sunny-edu/empty-assignments.png')

        exam = Exam.objects.create(title='Đề thử', created_by=teacher)
        version = ExamVersion.objects.create(exam=exam, number=1, status='PUBLISHED')
        now = timezone.now()
        assignment = Assignment.objects.create(
            title='Bài 1',
            version=version,
            code='HW-TEST01',
            status='PUBLISHED',
            opens_at=now - timezone.timedelta(hours=1),
            due_at=now + timezone.timedelta(hours=2),
            late_until=now + timezone.timedelta(hours=4),
        )
        recipient = AssignmentRecipient.objects.create(assignment=assignment, student=student, state='ASSIGNED')
        attempt = Attempt.objects.create(recipient=recipient, attempt_no=1, status='IN_PROGRESS')
        recipient.current_attempt = attempt
        recipient.save(update_fields=['current_attempt'])

        in_progress = self.client.get(f'/student/assignments/{assignment.id}/')
        self.assertEqual(in_progress.status_code, 200)
        self.assertContains(in_progress, 'id="submission-receipt" class="receipt-card" role="status" aria-live="polite" hidden')

        attempt.status = 'SUBMITTED'
        attempt.submitted_at = now
        attempt.save(update_fields=['status', 'submitted_at'])
        submitted = self.client.get(f'/student/assignments/{assignment.id}/')
        self.assertContains(submitted, 'img/sunny-edu/submission-success.png')
        self.assertContains(submitted, 'Đã nộp lúc ')
        self.assertNotContains(submitted, 'id="submission-receipt" class="receipt-card" role="status" aria-live="polite" hidden')

    def test_student_leaderboard_tabs_and_pagination_modal(self):
        teacher = User.objects.create_user(username='teacher_lb', role='OWNER', display_name='Thầy An')
        main_student = User.objects.create_user(username='student_lb', role='STUDENT', display_name='Em Linh')
        code = rotate_code(main_student, actor=teacher)
        self.client.post('/api/v1/auth/student-login/', data=json.dumps({'code': code}), content_type='application/json')

        from apps.classes.models import EnglishClass, EnglishMembership
        from apps.content.models import Course, CourseExercise
        from apps.grading.models import GradeRelease

        e_class = EnglishClass.objects.create(code='ENG-LB01', name='Lớp 6A Leaderboard', school_year='2026-2027')
        course1 = Course.objects.create(name='IELTS Basic', category='IELTS', is_published=True, created_by=teacher)
        course1.english_classes.add(e_class)

        # Create 12 students in total to test pagination (> 10 items)
        students = [main_student]
        for i in range(1, 12):
            s = User.objects.create_user(username=f'stu_lb_{i}', role='STUDENT', display_name=f'Bạn {i:02d}')
            students.append(s)
            EnglishMembership.objects.create(student=s, english_class=e_class, start_at=timezone.now() - timezone.timedelta(days=10))

        EnglishMembership.objects.create(student=main_student, english_class=e_class, start_at=timezone.now() - timezone.timedelta(days=10))

        exam = Exam.objects.create(title='Đề kiểm tra LB', created_by=teacher)
        version = ExamVersion.objects.create(exam=exam, number=1, status='PUBLISHED')
        now = timezone.now()
        assignment = Assignment.objects.create(
            title='Bài thi LB', version=version, code='HW-LB01', status='PUBLISHED',
            opens_at=now - timezone.timedelta(days=2), due_at=now + timezone.timedelta(days=2),
            late_until=now + timezone.timedelta(days=3),
        )
        CourseExercise.objects.create(course=course1, assignment=assignment, difficulty=3)

        # Add attempts and scores
        rec = AssignmentRecipient.objects.create(assignment=assignment, student=main_student, state='ASSIGNED')
        att = Attempt.objects.create(
            recipient=rec, attempt_no=1, status='SUBMITTED', submitted_at=now,
        )
        Attempt.objects.filter(pk=att.pk).update(started_at=now - timezone.timedelta(hours=2))
        GradeRelease.objects.create(attempt=att, number=1, total_points='9.00', max_points='10.00', published_by=teacher, snapshot={})

        resp = self.client.get('/student/')
        self.assertEqual(resp.status_code, 200)

        # Context checks
        self.assertIn('leaderboards', resp.context)
        lb = resp.context['leaderboards']
        self.assertIn('hours', lb)
        self.assertIn('score', lb)
        self.assertIn('courses', lb)

        # Top 10 has at most 10 items
        self.assertEqual(len(lb['hours']['top10']), 10)
        # Full list has all 12 students
        self.assertEqual(len(lb['hours']['full_list']), 12)

        # Main student should have is_me=True
        my_item = next(it for it in lb['hours']['full_list'] if it['is_me'])
        self.assertEqual(my_item['student_id'], str(main_student.id))
        self.assertEqual(my_item['name'], 'Em Linh')
        self.assertEqual(my_item['display_value'], '2.0 giờ')

        # Score ranking check
        self.assertFalse(any(it['is_me'] for it in lb['score']['full_list']))

        # HTML checks for tabs, modal and pagination
        self.assertContains(resp, 'Bảng xếp hạng')
        self.assertContains(resp, 'data-tab="hours"')
        self.assertContains(resp, 'data-tab="score"')
        self.assertContains(resp, 'data-tab="courses"')
        self.assertContains(resp, 'id="ranking-modal"')
        self.assertContains(resp, 'id="modal-page-controls"')
        self.assertContains(resp, 'id="leaderboards-data"')

    def test_student_assignment_card_layout_and_urgent_deadline(self):
        from apps.classes.models import EnglishClass, EnglishMembership
        teacher = User.objects.create_user(username='card_owner', role='OWNER', display_name='GV Card')
        student = User.objects.create_user(username='card_stu', role='STUDENT', display_name='HS Card')
        code = rotate_code(student, actor=teacher)
        self.client.post('/api/v1/auth/student-login/', data=json.dumps({'code': code}), content_type='application/json')

        now = timezone.now()
        ec = EnglishClass.objects.create(code='ENG-6A1', name='Lớp 6A1', school_year='2026-2027')
        EnglishMembership.objects.create(student=student, english_class=ec, start_at=now - timezone.timedelta(days=2))

        exam = Exam.objects.create(title='Đề card', created_by=teacher)
        version = ExamVersion.objects.create(exam=exam, number=1, status='PUBLISHED')

        soon_assignment = Assignment.objects.create(
            title='Bài sắp hết hạn', version=version, code='HW-SOON', status='PUBLISHED',
            opens_at=now - timezone.timedelta(days=1), due_at=now + timezone.timedelta(hours=12),
            late_until=now + timezone.timedelta(days=2),
        )
        soon_assignment.classes.add(ec)
        AssignmentRecipient.objects.create(assignment=soon_assignment, student=student, state='ASSIGNED')

        normal_assignment = Assignment.objects.create(
            title='Bài còn nhiều thời gian', version=version, code='HW-NORM', status='PUBLISHED',
            opens_at=now - timezone.timedelta(days=1), due_at=now + timezone.timedelta(days=3),
            late_until=now + timezone.timedelta(days=4),
        )
        normal_assignment.classes.add(ec)
        rec_prog = AssignmentRecipient.objects.create(assignment=normal_assignment, student=student, state='ASSIGNED')
        att_prog = Attempt.objects.create(recipient=rec_prog, attempt_no=1, status='IN_PROGRESS')
        rec_prog.current_attempt = att_prog
        rec_prog.save(update_fields=['current_attempt'])

        resp = self.client.get('/student/')
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode('utf-8')

        self.assertIn('assignment-card-header', html)
        self.assertIn('assignment-header-sub', html)
        self.assertIn('Lớp: Lớp 6A1', html)
        self.assertNotIn('class="assignment-symbol"', html)

        self.assertIn('status-ribbon ribbon-unattempted', html)
        self.assertIn('status-ribbon ribbon-in_progress', html)
        self.assertIn('deadline-bar is-urgent', html)
        self.assertIn('class="deadline-bar "', html)

        self.assertIn('assignment-action-btn', html)
        self.assertIn('Bắt đầu làm bài', html)
        self.assertIn('Làm tiếp', html)
        self.assertNotIn('Bắt đầu làm bài <span aria-hidden="true">→</span>', html)
        self.assertNotIn('Làm tiếp <span aria-hidden="true">→</span>', html)

    def test_student_assignment_start_page_layout_and_single_click_start(self):
        teacher = User.objects.create_user(username='start_owner', role='OWNER', display_name='GV Start')
        student = User.objects.create_user(username='start_stu', role='STUDENT', display_name='HS Start')
        code = rotate_code(student, actor=teacher)
        self.client.post('/api/v1/auth/student-login/', data=json.dumps({'code': code}), content_type='application/json')

        exam = Exam.objects.create(title='Đề Start', created_by=teacher)
        version = ExamVersion.objects.create(exam=exam, number=1, status='PUBLISHED')
        now = timezone.now()
        assignment = Assignment.objects.create(
            title='Bài kiểm tra bắt đầu',
            version=version,
            code='HW-STRT01',
            status='PUBLISHED',
            opens_at=now - timezone.timedelta(hours=1),
            due_at=now + timezone.timedelta(hours=5),
            late_until=now + timezone.timedelta(hours=10),
        )
        recipient = AssignmentRecipient.objects.create(assignment=assignment, student=student, state='ASSIGNED')

        start_page = self.client.get(f'/student/assignments/{assignment.id}/')
        self.assertEqual(start_page.status_code, 200)
        self.assertTemplateUsed(start_page, 'student/assignment_start.html')
        self.assertContains(start_page, 'assignment-start-panel')
        self.assertContains(start_page, 'assignment-start-btn')
        self.assertContains(start_page, '<h1>Bài kiểm tra bắt đầu</h1>')
        self.assertContains(start_page, 'Hạn nộp:')
        self.assertContains(start_page, '>Bắt đầu</button>')
        self.assertNotContains(start_page, 'Hạn đóng:')

        started = self.client.post(f'/student/assignments/{assignment.id}/', follow=True)
        self.assertEqual(started.status_code, 200)
        self.assertTemplateUsed(started, 'student/assignment.html')
        recipient.refresh_from_db()
        self.assertIsNotNone(recipient.current_attempt)
        self.assertEqual(recipient.current_attempt.status, 'IN_PROGRESS')


