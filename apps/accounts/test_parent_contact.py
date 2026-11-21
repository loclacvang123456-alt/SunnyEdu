from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.accounts.models import PrivacyRequest, User
from apps.accounts.services import create_privacy_request, create_student, execute_privacy_request, export_student_data, update_student


class ParentContactTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="teacher", role=User.Role.OWNER, display_name="Teacher")
        self.student = create_student("Student", "CONTACT-1", actor=self.owner)

    def test_save_validate_export_and_erase_phone(self):
        update_student(self.student.id, self.owner, parent_phone="+84 912 345 678")
        self.student.student_profile.refresh_from_db()
        self.assertEqual(self.student.student_profile.parent_phone, "0912345678")
        self.assertEqual(export_student_data(self.student.id, self.owner)["student"]["parent_phone"], "0912345678")
        with self.assertRaises(ValidationError):
            update_student(self.student.id, self.owner, parent_phone="invalid")
        self.student.student_profile.refresh_from_db()
        self.assertEqual(self.student.student_profile.parent_phone, "0912345678")
        request = create_privacy_request(self.student.id, PrivacyRequest.Kind.ERASE, self.owner, "Requested")
        execute_privacy_request(request.id, self.owner)
        self.student.student_profile.refresh_from_db()
        self.assertEqual(self.student.student_profile.parent_phone, "")

    def test_detail_displays_zalo_link(self):
        from django_otp import DEVICE_ID_SESSION_KEY
        from django_otp.plugins.otp_totp.models import TOTPDevice

        device = TOTPDevice.objects.create(user=self.owner, confirmed=True)
        self.client.force_login(self.owner)
        session = self.client.session
        session[DEVICE_ID_SESSION_KEY] = device.persistent_id
        session.save()
        url = f"/teacher/students/{self.student.id}/"
        response = self.client.post(url, {"action": "update_profile", "display_name": "Student", "owner_note": "", "parent_phone": "0912345678"})
        self.assertEqual(response.status_code, 302)
        self.assertContains(self.client.get(url), 'href="https://zalo.me/0912345678"')
