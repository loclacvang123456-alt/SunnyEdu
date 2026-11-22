from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.http import QueryDict
from django.test import SimpleTestCase
from django.utils import timezone

from .owner_teaching_views import _quick_assign


class QuickAssignmentTests(SimpleTestCase):
    @patch('apps.core.owner_teaching_views.EnglishMembership.objects.filter')
    @patch('apps.core.owner_teaching_views.EnglishClass.objects.filter')
    @patch('apps.core.owner_teaching_views.Course.objects.filter')
    @patch('apps.core.owner_teaching_views.redirect')
    @patch('apps.core.owner_teaching_views.messages.success')
    @patch('apps.core.owner_teaching_views.assign_targets_with_schedule')
    @patch('apps.core.owner_teaching_views.create_draft_assignment')
    @patch('apps.core.owner_teaching_views.transaction.atomic')
    @patch('apps.core.owner_teaching_views._quick_assign_context')
    def test_multiple_versions_only_enable_game_for_eligible(self, context, atomic, create, publish, success, redirect, courses, classes, memberships):
        courses.return_value.count.return_value = 0
        classes.return_value.values_list.return_value = []
        memberships.return_value.exists.return_value = True
        versions = [SimpleNamespace(id=uuid4(), exam=SimpleNamespace(title='Game'), has_game_questions=True),
                    SimpleNamespace(id=uuid4(), exam=SimpleNamespace(title='Text'), has_game_questions=False)]
        context.return_value = {'quick_versions': MagicMock()}
        context.return_value['quick_versions'].filter.return_value = versions
        atomic.return_value.__enter__.return_value = None
        create.side_effect = [SimpleNamespace(id=uuid4(), revision=0), SimpleNamespace(id=uuid4(), revision=0)]
        data = QueryDict('', mutable=True)
        data.setlist('version_ids', [str(v.id) for v in versions])
        data.setlist('class_ids', [str(uuid4())])
        data.update({'due_at': (timezone.now() + timedelta(days=1)).isoformat(), 'game_feedback_enabled': 'on'})
        _quick_assign(SimpleNamespace(POST=data, user=object()))
        self.assertEqual([call.kwargs['game_feedback_enabled'] for call in create.call_args_list], [True, False])
        self.assertEqual(publish.call_count, 2)

    @patch('apps.core.owner_teaching_views.redirect')
    @patch('apps.core.owner_teaching_views.messages.success')
    @patch('apps.core.owner_teaching_views.assign_targets_with_schedule')
    @patch('apps.core.owner_teaching_views.create_draft_assignment')
    @patch('apps.core.owner_teaching_views.transaction.atomic')
    @patch('apps.core.owner_teaching_views.EnglishMembership.objects.filter')
    @patch('apps.core.owner_teaching_views.EnglishClass.objects.filter')
    @patch('apps.core.owner_teaching_views.Course.objects.filter')
    @patch('apps.core.owner_teaching_views._quick_assign_context')
    def test_course_and_individual_are_combined(self, context, courses, classes, memberships, atomic, create, assign, success, redirect):
        version = SimpleNamespace(id=uuid4(), exam=SimpleNamespace(title='Test'), has_game_questions=False)
        context.return_value = {'quick_versions': MagicMock()}
        context.return_value['quick_versions'].filter.return_value = [version]
        course_id, class_id, student_id = uuid4(), uuid4(), uuid4()
        courses.return_value.count.return_value = 1
        classes.return_value.values_list.return_value = [class_id]
        memberships.return_value.exists.return_value = True
        create.return_value = SimpleNamespace(id=uuid4())
        data = QueryDict('', mutable=True)
        data.setlist('version_ids', [str(version.id)])
        data.setlist('course_ids', [str(course_id)])
        data.setlist('student_ids', [str(student_id)])
        data['due_at'] = (timezone.now() + timedelta(days=1)).isoformat()
        _quick_assign(SimpleNamespace(POST=data, user=object()))
        self.assertEqual(assign.call_args.args[2:4], ([class_id], [student_id]))
        self.assertTrue(create.call_args.kwargs['allow_individuals'])

    def test_empty_selection_rejected(self):
        with self.assertRaises(ValidationError):
            _quick_assign(SimpleNamespace(POST=QueryDict(''), user=object()))
