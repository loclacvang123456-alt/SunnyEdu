from datetime import timedelta
from unittest.mock import patch
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.utils import timezone
from apps.accounts.models import User
from apps.assignments.models import Assignment, AssignmentRecipient, Attempt, RecipientEnglishClass
from apps.classes.models import EnglishClass
from apps.content.models import Exam, ExamVersion
from apps.grading.models import GradeRelease
from apps.reporting.models import RankingAssignment, RankingEntry, RankingMember, RankingPeriod
from apps.reporting.services import activate, finalize, invalidate, recompute_publish


class RankingLifecycleTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.owner = User.objects.create_user(username='owner', role='OWNER', display_name='Teacher')
        self.student = User.objects.create_user(username='pupil', role='STUDENT', display_name='Pupil')
        self.other = User.objects.create_user(username='pupil2', role='STUDENT', display_name='Pupil 2')
        self.english = EnglishClass.objects.create(code='ENG-ABC123', name='English', school_year='2026-2027')
        exam = Exam.objects.create(title='Exam', created_by=self.owner)
        version = ExamVersion.objects.create(exam=exam, number=1, status='PUBLISHED')
        self.assignment = Assignment.objects.create(version=version, title='Test', code='HW-ABC123', status='PUBLISHED', opens_at=self.now+timedelta(hours=1), due_at=self.now+timedelta(hours=2), late_until=self.now+timedelta(hours=3))
        self.period = RankingPeriod.objects.create(name='Term', school_year='2026-2027', start_at=self.now, end_at=self.now+timedelta(hours=4), scope='ENGLISH_CLASS', scope_target={'class_id':str(self.english.id)})
        RankingAssignment.objects.create(period=self.period, assignment=self.assignment)
        for number, student in enumerate((self.student,self.other)):
            member = RankingMember.objects.create(period=self.period, student=student, alias=str(number), cohort_snapshot={})
            recipient = AssignmentRecipient.objects.create(assignment=self.assignment, student=student)
            RecipientEnglishClass.objects.create(recipient=recipient, english_class=self.english, class_name_snapshot='English', school_year_snapshot='2026-2027')
            if student == self.student:
                self.member, self.recipient = member, recipient

    def test_permissions_and_activation_conditions(self):
        with self.assertRaises(PermissionDenied): activate(self.period.id, self.student, 0)
        with patch('apps.reporting.services.timezone.now', return_value=self.now+timedelta(hours=1)):
            with self.assertRaises(ValidationError): activate(self.period.id, self.owner, 0)
        self.period.refresh_from_db()
        self.assertEqual(self.period.status, 'DRAFT')
        self.assertEqual(activate(self.period.id, self.owner, 0).status, 'ACTIVE')
        with self.assertRaises(ValidationError): invalidate(self.period.id, self.owner, 0, 'reason')

    def test_publish_and_republish_snapshot(self):
        activate(self.period.id, self.owner, 0)
        attempt = Attempt.objects.create(recipient=self.recipient, attempt_no=1, status='GRADED', submitted_at=self.now+timedelta(hours=2))
        self.recipient.current_attempt = attempt
        self.recipient.save(update_fields=['current_attempt'])
        first = GradeRelease.objects.create(attempt=attempt, number=1, published_by=self.owner, total_points='8', max_points='10', snapshot={})
        with patch('apps.reporting.services.timezone.now', return_value=self.now+timedelta(hours=5)):
            snapshot = finalize(self.period.id, self.owner, 1)
        entry = RankingEntry.objects.get(snapshot=snapshot, member=self.member)
        self.assertEqual(str(entry.score), '80.00')
        self.assertEqual(entry.rank, 1)
        self.assertEqual(entry.source_release_ids, [str(first.id)])
        self.assertEqual(RankingEntry.objects.filter(snapshot=snapshot, status='INCOMPLETE').count(), 1)
        self.period.refresh_from_db()
        self.period.status = 'STALE'
        self.period.save(update_fields=['status'])
        GradeRelease.objects.create(attempt=attempt, number=2, published_by=self.owner, total_points='6', max_points='10', snapshot={})
        with patch('apps.reporting.services.timezone.now', return_value=self.now+timedelta(hours=5)):
            second = recompute_publish(self.period.id, self.owner, 2)
        self.assertEqual(second.number, 2)
        self.assertEqual(str(RankingEntry.objects.get(snapshot=second, member=self.member).score), '60.00')
        self.assertEqual(str(RankingEntry.objects.get(snapshot=snapshot, member=self.member).score), '80.00')

    def test_unpublished_grade_prevents_finalization(self):
        activate(self.period.id, self.owner, 0)
        attempt = Attempt.objects.create(recipient=self.recipient, attempt_no=1, status='GRADED', submitted_at=self.now)
        self.recipient.current_attempt = attempt
        self.recipient.save(update_fields=['current_attempt'])
        with patch('apps.reporting.services.timezone.now', return_value=self.now+timedelta(hours=5)):
            with self.assertRaises(ValidationError): finalize(self.period.id, self.owner, 1)
        self.period.refresh_from_db()
        self.assertEqual(self.period.status, 'ACTIVE')

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from django.db import close_old_connections, connection
from django.test import TransactionTestCase


class RankingConcurrencyTests(TransactionTestCase):
    setUp = RankingLifecycleTests.setUp

    def test_two_finalize_requests_create_one_snapshot(self):
        if connection.vendor != 'postgresql':
            self.skipTest('PostgreSQL row locking required')
        activate(self.period.id, self.owner, 0)
        barrier = Barrier(2)
        def worker():
            close_old_connections()
            try:
                actor = User.objects.get(pk=self.owner.id)
                barrier.wait(timeout=10)
                try:
                    finalize(self.period.id, actor, 1)
                    return 'ok'
                except ValidationError:
                    return 'conflict'
            finally:
                close_old_connections()
        with patch('apps.reporting.services.timezone.now', return_value=self.now+timedelta(hours=5)):
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(lambda _: worker(), range(2)))
        self.assertCountEqual(results, ['ok', 'conflict'])
        self.assertEqual(self.period.snapshots.count(), 1)
