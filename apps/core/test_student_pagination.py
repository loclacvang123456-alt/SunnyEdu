from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User


@override_settings(TEACHER_OTP_BYPASS=True)
class StudentPaginationTests(TestCase):
    def test_students_beyond_first_hundred_and_filters(self):
        owner = User.objects.create_user(username='pagination-owner', role='OWNER')
        User.objects.bulk_create([
            User(username=f'page-{i:03}', display_name=f'Student {i:03}', role='STUDENT', status='ACTIVE')
            for i in range(105)
        ])
        self.client.force_login(owner)
        response = self.client.get(reverse('owner_students'), {'page': 11, 'q': 'Student'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['student_page'].paginator.count, 105)
        self.assertEqual(len(response.context['student_rows']), 5)
        self.assertContains(response, 'Student 104')
        self.assertContains(response, 'q=Student')
