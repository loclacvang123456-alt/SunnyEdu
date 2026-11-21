import json
from datetime import timedelta
from uuid import uuid4
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.utils import timezone
from apps.accounts.models import User
from apps.accounts.services import rotate_code
from apps.content.models import Exam, ExamVersion, Question, QuestionOption, AnswerKeyOption
from apps.reporting.models import RankingPeriod, RankingAssignment
from .models import Assignment, AssignmentRecipient, PracticeShot, Response
from .services import ConflictError, fire_practice_shot, save_response, start_attempt, submit_attempt


class PirateShotTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='game-owner', role='OWNER', display_name='Teacher')
        self.student = User.objects.create_user(username='game-student', role='STUDENT', display_name='Student')
        self.other = User.objects.create_user(username='game-other', role='STUDENT', display_name='Other')
        exam = Exam.objects.create(title='Game', created_by=self.owner)
        version = ExamVersion.objects.create(exam=exam, number=1, status='PUBLISHED')
        self.question = Question.objects.create(version=version, position=1, type='SINGLE_CHOICE', skill='READING', difficulty='FOUNDATION', prompt='Choose', max_points='2.00')
        self.right = QuestionOption.objects.create(question=self.question, key='A', position=1, content='Yes')
        self.wrong = QuestionOption.objects.create(question=self.question, key='B', position=2, content='No')
        AnswerKeyOption.objects.create(question=self.question, option=self.right)
        now = timezone.now()
        self.assignment = Assignment.objects.create(version=version, title='Game', code='HW-GAME01', status='PUBLISHED', mode='PRACTICE', game_feedback_enabled=True, opens_at=now-timedelta(hours=1), due_at=now+timedelta(hours=1), late_until=now+timedelta(days=1))
        self.recipient = AssignmentRecipient.objects.create(assignment=self.assignment, student=self.student)
        self.attempt, _ = start_attempt(self.recipient.id, self.student)

    def fire(self, option=None, key=None, revision=0, student=None):
        return fire_practice_shot(self.attempt.id, self.question.id, student or self.student, option or self.right.id, revision, key or uuid4())

    def test_fired_choice_is_locked_and_scored_once(self):
        key = uuid4()
        shot = self.fire(self.wrong.id, key)
        self.assertFalse(shot.correct)
        self.assertEqual(self.fire(self.wrong.id, key).id, shot.id)
        with self.assertRaises(ConflictError):
            self.fire(self.right.id, key)
        with self.assertRaises(ConflictError):
            save_response(self.attempt.id, self.question.id, self.student, shot.response_revision, option_ids=[])
        self.assertEqual(PracticeShot.objects.count(), 1)
        self.attempt.refresh_from_db()
        result = submit_attempt(self.attempt.id, self.student, self.attempt.revision, uuid4())
        self.assertEqual(result['status'], 'GRADED')
        self.assertEqual(Response.objects.get(attempt=self.attempt, question=self.question).grade.points, 0)

    def test_rejects_unopted_exam_other_student_or_ranked(self):
        self.assignment.game_feedback_enabled = False
        self.assignment.save(update_fields=['game_feedback_enabled'])
        with self.assertRaises(PermissionDenied): self.fire()
        self.assignment.mode = 'EXAM'
        self.assignment.save(update_fields=['mode'])
        with self.assertRaises(PermissionDenied): self.fire()
        self.assignment.mode, self.assignment.game_feedback_enabled = 'PRACTICE', True
        self.assignment.save(update_fields=['mode', 'game_feedback_enabled'])
        with self.assertRaises(type(self.attempt).DoesNotExist): self.fire(student=self.other)
        now = timezone.now()
        period = RankingPeriod.objects.create(name='rank', school_year='2026-2027', start_at=now-timedelta(days=1), end_at=now+timedelta(days=3), scope='SCHOOL', scope_target={})
        RankingAssignment.objects.create(period=period, assignment=self.assignment)
        with self.assertRaises(PermissionDenied): self.fire()

    def test_view_does_not_leak_answers_and_replays_receipt(self):
        code = rotate_code(self.student, actor=self.owner)
        client = self.client_class(enforce_csrf_checks=True)
        client.get('/api/v1/auth/csrf/')
        csrf = client.cookies['csrftoken'].value
        self.assertEqual(client.post('/api/v1/auth/student-login/', data=json.dumps({'code': code}), content_type='application/json', HTTP_X_CSRFTOKEN=csrf).status_code, 200)
        csrf = client.cookies['csrftoken'].value
        path = f'/api/v1/attempts/{self.attempt.id}/responses/{self.question.id}/shot/'
        body = json.dumps({'option_id': str(self.right.id), 'expected_revision': 0})
        key = str(uuid4())
        self.assertEqual(client.post(path, body, content_type='application/json', HTTP_IDEMPOTENCY_KEY=key).status_code, 403)
        before = client.get(f'/api/v1/attempts/{self.attempt.id}/').json()['data']
        self.assertIsNone(before['questions'][0]['shot'])
        self.assertNotIn('answer_keys', json.dumps(before))
        response = client.post(path, body, content_type='application/json', HTTP_X_CSRFTOKEN=csrf, HTTP_IDEMPOTENCY_KEY=key)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['data']['correct'])
        self.assertEqual(set(response.json()['data']), {'option_id','correct','response_revision','attempt_revision'})
        self.assertEqual(client.post(path, body, content_type='application/json', HTTP_X_CSRFTOKEN=csrf, HTTP_IDEMPOTENCY_KEY=key).json(), response.json())
        after = client.get(f'/api/v1/attempts/{self.attempt.id}/').json()['data']
        self.assertEqual(after['questions'][0]['shot'], response.json()['data'])

    def test_only_selected_questions_allow_game_in_game_assignment(self):
        self.question.pirate_game = False
        self.question.save(update_fields=['pirate_game'])
        with self.assertRaises(PermissionDenied):
            self.fire()
        self.question.pirate_game = True
        self.question.save(update_fields=['pirate_game'])
        self.assertTrue(self.fire().correct)

    def test_another_student_cannot_fire_at_my_attempt(self):
        code = rotate_code(self.other, actor=self.owner)
        self.client.post('/api/v1/auth/student-login/', data=json.dumps({'code': code}), content_type='application/json')
        path = f'/api/v1/attempts/{self.attempt.id}/responses/{self.question.id}/shot/'
        result = self.client.post(path, json.dumps({'option_id': str(self.right.id), 'expected_revision': 0}),
                                  content_type='application/json', HTTP_IDEMPOTENCY_KEY=str(uuid4()))
        self.assertEqual(result.status_code, 404)
        self.assertFalse(PracticeShot.objects.exists())

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from django.db import close_old_connections
from django.test import TransactionTestCase


class PirateShotRaceTests(TransactionTestCase):
    reset_sequences = True
    setUp = PirateShotTests.setUp

    def race(self, options, keys):
        barrier = Barrier(2)
        def run(index):
            close_old_connections()
            try:
                barrier.wait(timeout=5)
                shot = fire_practice_shot(self.attempt.id, self.question.id, self.student, options[index], 0, keys[index])
                return ('ok', shot.id)
            except ConflictError:
                return ('conflict', None)
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as executor:
            return list(executor.map(run, range(2)))

    def test_two_different_shots_cannot_both_score(self):
        result = self.race([self.right.id, self.wrong.id], [uuid4(), uuid4()])
        self.assertCountEqual([item[0] for item in result], ['ok', 'conflict'])
        self.assertEqual(PracticeShot.objects.count(), 1)

    def test_parallel_retry_with_same_key_has_one_receipt(self):
        key = uuid4()
        result = self.race([self.right.id, self.right.id], [key, key])
        self.assertEqual([item[0] for item in result], ['ok', 'ok'])
        self.assertEqual(result[0][1], result[1][1])
        self.assertEqual(PracticeShot.objects.count(), 1)
