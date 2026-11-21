from unittest.mock import patch
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.assignments.owner_services import update_draft_assignment
from apps.assignments.models import PracticeShot, Response, ResponseOption
from apps.assignments.services import fire_practice_shot
from apps.assignments.test_pirate_shot import PirateShotTests
from apps.accounts.models import PrivacyRequest
from apps.accounts.services import execute_privacy_request, export_student_data
from apps.classes.models import School
from apps.reporting.report_services import create_ranking_period


class PirateSettingsTests(TestCase):
    setUp = PirateShotTests.setUp

    def test_game_requires_art_and_practice_mode(self):
        self.assignment.status = 'DRAFT'
        self.assignment.game_feedback_enabled = False
        self.assignment.save(update_fields=['status', 'game_feedback_enabled'])
        with patch('apps.assignments.owner_services.missing_game_assets', return_value=['cannonball.png']):
            with self.assertRaises(ValidationError):
                update_draft_assignment(self.owner, self.assignment.id, 0, game_feedback_enabled=True)
        with patch('apps.assignments.owner_services.missing_game_assets', return_value=[]):
            assignment = update_draft_assignment(self.owner, self.assignment.id, 0, game_feedback_enabled=True)
            self.assertTrue(assignment.game_feedback_enabled)
            with self.assertRaises(ValidationError):
                update_draft_assignment(self.owner, assignment.id, assignment.revision, mode='EXAM')
            assignment.refresh_from_db()
            self.assertEqual(assignment.mode, 'PRACTICE')
            assignment.status = 'PUBLISHED'
            assignment.save(update_fields=['status'])
            with self.assertRaises(ValidationError):
                update_draft_assignment(self.owner, assignment.id, assignment.revision, game_feedback_enabled=False)

    def test_game_assignment_cannot_be_added_to_ranking(self):
        school = School.objects.create(code='GAME', name='School')
        with self.assertRaisesMessage(ValidationError, 'không thể dùng để xếp hạng'):
            create_ranking_period(
                self.owner, 'Rank', '2026-2027', self.assignment.opens_at,
                self.assignment.late_until, 'SCHOOL', {'school_id': str(school.id)},
                [self.student.id], [self.assignment.id],
            )

    def test_shot_is_exported_and_erased_with_student_data(self):
        fire_practice_shot(self.attempt.id, self.question.id, self.student, self.right.id, 0, uuid4())
        response = Response.objects.get(attempt=self.attempt, question=self.question)
        response.ordered_option_ids = [str(self.right.id)]
        response.match_pairs = [{'image_id': 'image', 'word_id': 'word'}]
        response.save(update_fields=['ordered_option_ids', 'match_pairs'])
        data = export_student_data(self.student.id, self.owner)
        saved = data['assignments'][0]['attempts'][0]['responses'][0]
        self.assertEqual(saved['selected_option_ids'], [str(self.right.id)])
        self.assertEqual(saved['ordered_option_ids'], [str(self.right.id)])
        self.assertTrue(saved['match_pairs'])
        request = PrivacyRequest.objects.create(student=self.student, kind='ERASE', requested_by=self.owner, reason='test')
        execute_privacy_request(request.id, self.owner)
        response.refresh_from_db()
        self.assertFalse(PracticeShot.objects.filter(response=response).exists())
        self.assertFalse(ResponseOption.objects.filter(response=response).exists())
        self.assertEqual(response.ordered_option_ids, [])
        self.assertEqual(response.match_pairs, [])
