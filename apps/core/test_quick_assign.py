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
    @patch('apps.core.owner_teaching_views.redirect')
    @patch('apps.core.owner_teaching_views.messages.success')
    @patch('apps.core.owner_teaching_views.publish_assignment')
    @patch('apps.core.owner_teaching_views.create_draft_assignment')
    @patch('apps.core.owner_teaching_views.transaction.atomic')
    @patch('apps.core.owner_teaching_views._quick_assign_context')
    def test_multiple_versions_only_enable_game_for_eligible(self, context, atomic, create, publish, success, redirect):
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

    def test_empty_selection_rejected(self):
        with self.assertRaises(ValidationError):
            _quick_assign(SimpleNamespace(POST=QueryDict(''), user=object()))
