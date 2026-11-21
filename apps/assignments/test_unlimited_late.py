from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.core.exceptions import PermissionDenied
from django.test import SimpleTestCase
from django.utils import timezone

from .owner_services import _validate_schedule
from .services import check_window


class LateSubmissionTests(SimpleTestCase):
    def test_open_ended_late_submission_and_blocked_deadline(self):
        now = timezone.now()
        due = now - timedelta(days=30)
        opens = due - timedelta(days=1)
        self.assertIsNone(_validate_schedule(opens, due, "ALLOW"))
        self.assertEqual(_validate_schedule(opens, due, "BLOCK"), due)
        assignment = SimpleNamespace(id=1, status="PUBLISHED", opens_at=opens, due_at=due, late_until=None)
        recipient = SimpleNamespace(assignment=assignment, state="ASSIGNED", due_at_override=None, student=object())
        with patch("apps.assignments.services.course_access_allowed", return_value=True):
            check_window(recipient)
            assignment.late_until = due
            with self.assertRaises(PermissionDenied):
                check_window(recipient)
