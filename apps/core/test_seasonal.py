from datetime import date
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.template.loader import get_template, render_to_string
from django.template.loader_tags import BlockNode
from django.utils import timezone
from apps.accounts.models import User
from .models import SiteAppearance
from .seasonal import active_theme, context, holidays


class SeasonalCalendarTests(SimpleTestCase):
    def test_automatic_window_and_manual_choice(self):
        self.assertEqual(active_theme('auto', date(2026, 11, 12)), '')
        self.assertEqual(active_theme('auto', date(2026, 11, 13)), 'teachers-day')
        self.assertEqual(active_theme('auto', date(2026, 11, 20)), 'teachers-day')
        self.assertEqual(active_theme('auto', date(2026, 11, 21)), '')
        self.assertEqual(active_theme('christmas', date(2026, 11, 20)), 'christmas')
        self.assertEqual(active_theme('off', date(2026, 11, 20)), '')
        self.assertEqual(active_theme('invalid', date(2026, 11, 20)), '')

    def test_vietnamese_lunar_dates(self):
        self.assertIn((date(2026, 2, 17), 'tet'), holidays(2026))
        self.assertIn((date(2026, 9, 25), 'mid-autumn'), holidays(2026))
        self.assertIn((date(2027, 2, 6), 'tet'), holidays(2027))
        self.assertIn((date(2027, 9, 14), 'mid-autumn'), holidays(2027))
        self.assertEqual(active_theme('auto', date(2027, 1, 30)), 'tet')

    def test_disabled_pages(self):
        self.assertIn('data-theme="christmas"', render_to_string('base.html', {'seasonal_theme': 'christmas'}))
        for name in ('owner/base.html', 'student/assignment.html', 'student/speaking_practice.html', 'owner/version_preview.html'):
            blocks = {b.name: b for b in get_template(name).template.nodelist.get_nodes_by_type(BlockNode)}
            self.assertIn('seasonal', blocks)
            self.assertFalse(blocks['seasonal'].nodelist)


@override_settings(TEACHER_OTP_BYPASS=True)
class SeasonalSettingsTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(username='theme-teacher', password='test-pass', role='OWNER', status='ACTIVE')
        self.student = User.objects.create_user(username='theme-student', password='test-pass', role='STUDENT', status='ACTIVE')

    def login_user(self, user):
        self.client.force_login(user)
        session = self.client.session
        now = timezone.now().isoformat()
        session.update({'auth_epoch': user.auth_epoch, 'issued_at': now, 'last_activity': now})
        session.save()

    def test_teacher_can_save_and_invalid_values_are_rejected(self):
        self.login_user(self.teacher)
        response = self.client.post('/teacher/settings/', {'action': 'save_theme', 'theme': 'christmas'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(context(RequestFactory().get('/'))['seasonal_theme'], 'christmas')
        self.assertContains(self.client.get('/teacher/settings/'), 'value="christmas" selected')
        self.client.post('/teacher/settings/', {'action': 'save_theme', 'theme': 'invalid'})
        self.assertEqual(SiteAppearance.objects.get(pk=1).theme, 'christmas')
        self.client.post('/teacher/settings/', {'action': 'save_theme', 'theme': 'off'})
        self.assertEqual(context(RequestFactory().get('/'))['seasonal_theme'], '')
        self.client.post('/teacher/settings/', {'action': 'save_theme', 'theme': 'auto'})
        self.assertEqual(SiteAppearance.objects.get(pk=1).theme, 'auto')

    def test_student_cannot_change_theme(self):
        self.login_user(self.student)
        self.assertEqual(self.client.post('/teacher/settings/', {'action': 'save_theme', 'theme': 'christmas'}).status_code, 403)
        self.assertFalse(SiteAppearance.objects.exists())
