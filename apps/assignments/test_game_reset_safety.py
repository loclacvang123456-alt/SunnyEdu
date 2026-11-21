import json
from uuid import uuid4

from django.test import TestCase

from apps.accounts.services import rotate_code
from apps.assignments.models import PracticeShot, Response
from apps.assignments.services import fire_practice_shot, submit_attempt
from apps.assignments.test_pirate_shot import PirateShotTests


class GameResetSafetyTests(TestCase):
    setUp = PirateShotTests.setUp

    def login(self, student):
        code = rotate_code(student, actor=self.owner)
        self.client.post('/api/v1/auth/student-login/', json.dumps({'code': code}), content_type='application/json')

    def fire(self):
        return fire_practice_shot(self.attempt.id, self.question.id, self.student, self.wrong.id, 0, uuid4())

    def test_reset_cannot_erase_in_progress_or_other_students_attempt(self):
        shot = self.fire()
        response = Response.objects.get(pk=shot.response_id)
        response.text_answer = 'saved answer'
        response.ordered_option_ids = ['saved-order']
        response.match_pairs = [{'image_id': 'saved-image', 'word_id': 'saved-word'}]
        response.save(update_fields=['text_answer', 'ordered_option_ids', 'match_pairs'])
        original_revision = response.revision
        self.attempt.refresh_from_db()
        attempt_revision = self.attempt.revision
        path = f'/api/v1/attempts/{self.attempt.id}/reset/'
        self.assertEqual(self.client.post(path).status_code, 401)
        self.login(self.other)
        self.assertEqual(self.client.post(path).status_code, 410)
        self.client.post('/logout/')
        self.login(self.student)
        result = self.client.post(path)
        self.assertEqual(result.status_code, 410)
        self.assertEqual(result.json()['error']['code'], 'NOT_AVAILABLE')
        response.refresh_from_db()
        self.attempt.refresh_from_db()
        self.assertEqual(response.text_answer, 'saved answer')
        self.assertEqual(response.ordered_option_ids, ['saved-order'])
        self.assertEqual(response.match_pairs, [{'image_id': 'saved-image', 'word_id': 'saved-word'}])
        self.assertEqual(list(response.options.values_list('id', flat=True)), [self.wrong.id])
        self.assertEqual(response.revision, original_revision)
        self.assertEqual(self.attempt.revision, attempt_revision)
        self.assertEqual(self.attempt.status, 'IN_PROGRESS')
        self.assertTrue(PracticeShot.objects.filter(pk=shot.pk).exists())

    def test_reset_cannot_reopen_submitted_attempt_or_change_grade(self):
        shot = self.fire()
        self.attempt.refresh_from_db()
        submit_attempt(self.attempt.id, self.student, self.attempt.revision, uuid4())
        self.attempt.refresh_from_db()
        response = Response.objects.get(pk=shot.response_id)
        grade = response.grade
        previous = (self.attempt.status, self.attempt.submitted_at, self.attempt.revision, grade.points)
        self.login(self.student)
        self.assertEqual(self.client.post(f'/api/v1/attempts/{self.attempt.id}/reset/').status_code, 410)
        self.attempt.refresh_from_db()
        grade.refresh_from_db()
        self.assertEqual((self.attempt.status, self.attempt.submitted_at, self.attempt.revision, grade.points), previous)
        self.assertTrue(PracticeShot.objects.filter(pk=shot.pk).exists())
        self.assertEqual(list(response.options.values_list('id', flat=True)), [self.wrong.id])
