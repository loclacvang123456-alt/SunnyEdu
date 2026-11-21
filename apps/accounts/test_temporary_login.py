from django.test import TestCase, override_settings
from django_otp.plugins.otp_totp.models import TOTPDevice
from apps.accounts.models import User


@override_settings(TEACHER_OTP_BYPASS=True)
class TemporaryTeacherLoginTests(TestCase):
    def test_password_login_and_permissions(self):
        owner = User.objects.create_user(username='test-bypass', password='StrongPass123!', role=User.Role.OWNER)
        TOTPDevice.objects.create(user=owner, name='default', confirmed=True)
        response = self.client.post('/teacher/login/', {
            'owner_login_view-current_step': 'auth',
            'auth-username': owner.username,
            'auth-password': 'StrongPass123!',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get('/teacher/').status_code, 200)
        self.assertEqual(self.client.get('/api/v1/owner/students/').status_code, 200)
        self.assertEqual(self.client.get('/admin/').status_code, 302)

    def test_remembered_login_has_extended_session(self):
        owner = User.objects.create_user(username='remember-owner', password='StrongPass123!', role=User.Role.OWNER)
        response = self.client.post('/teacher/login/', {
            'owner_login_view-current_step': 'auth',
            'auth-username': owner.username,
            'auth-password': 'StrongPass123!',
            'remember_device': 'on',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.client.session['remember_device'])
        self.assertEqual(self.client.session.get_expiry_age(), 30 * 86400)

    @override_settings(TEACHER_OTP_BYPASS=False)
    def test_otp_can_be_restored(self):
        owner = User.objects.create_user(username='test-otp', password='StrongPass123!', role=User.Role.OWNER)
        TOTPDevice.objects.create(user=owner, name='default', confirmed=True)
        response = self.client.post('/teacher/login/', {
            'owner_login_view-current_step': 'auth',
            'auth-username': owner.username,
            'auth-password': 'StrongPass123!',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'token-otp_token')
