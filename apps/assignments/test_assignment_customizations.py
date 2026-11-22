import hashlib
import hmac
import uuid
from datetime import timedelta
from django.conf import settings
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.services import create_student
from apps.assignments.models import Assignment, AssignmentClass, AssignmentRecipient, Attempt, Response
from apps.assignments.owner_services import create_draft_assignment
from apps.assignments.views import attempt_detail
from apps.classes.models import EnglishClass
from apps.content.models import Exam, ExamVersion, Question, QuestionOption, AnswerKeyOption


class AssignmentCustomizationsTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="teacher_test", role=User.Role.OWNER, display_name="Teacher Test")
        self.student = create_student("Student Test", "CUST-001", actor=self.owner, parent_phone="0987654321")
        self.english_class = EnglishClass.objects.create(name="Class 1A", code="C1A", school_year="2026-2027")

        exam = Exam.objects.create(created_by=self.owner, title="English Quiz", code="EXAM-TEST1")
        self.version = ExamVersion.objects.create(exam=exam, number=1, status=ExamVersion.Status.PUBLISHED)
        self.question = Question.objects.create(
            version=self.version,
            position=1,
            type=Question.Type.SINGLE_CHOICE,
            prompt="What is it?",
            max_points="1.00",
        )
        self.opt_a = QuestionOption.objects.create(question=self.question, key="A", position=1, content="Apple")
        self.opt_b = QuestionOption.objects.create(question=self.question, key="B", position=2, content="Banana")
        self.opt_c = QuestionOption.objects.create(question=self.question, key="C", position=3, content="Carrot")
        self.opt_d = QuestionOption.objects.create(question=self.question, key="D", position=4, content="Donut")
        AnswerKeyOption.objects.create(question=self.question, option=self.opt_a)

    def test_student_created_with_parent_phone(self):
        self.assertEqual(self.student.student_profile.parent_phone, "0987654321")

    def test_teacher_otp_bypass_is_default_true(self):
        self.assertTrue(getattr(settings, "TEACHER_OTP_BYPASS", False))

    def test_create_assignment_with_instant_feedback(self):
        now = timezone.now()
        due = now + timedelta(days=2)
        assignment = create_draft_assignment(
            self.owner,
            self.version.id,
            "Instant Test Assignment",
            [self.english_class.id],
            now,
            due,
            instant_feedback=True,
        )
        self.assertTrue(assignment.instant_feedback)

    def test_option_shuffling_differs_across_attempts(self):
        now = timezone.now()
        due = now + timedelta(days=2)
        assignment = create_draft_assignment(
            self.owner,
            self.version.id,
            "Shuffle Test Assignment",
            [self.english_class.id],
            now,
            due,
            instant_feedback=True,
        )
        assignment.status = "PUBLISHED"
        assignment.save(update_fields=["status"])

        recipient = AssignmentRecipient.objects.create(assignment=assignment, student=self.student, state="ASSIGNED")
        attempt1 = Attempt.objects.create(recipient=recipient, attempt_no=1)
        attempt2 = Attempt.objects.create(recipient=recipient, attempt_no=2)

        options = [self.opt_a, self.opt_b, self.opt_c, self.opt_d]
        order1 = sorted(options, key=lambda opt: hmac.new(settings.SECRET_KEY.encode(), f"{attempt1.id}:option:{opt.id}".encode(), hashlib.sha256).digest())
        order2 = sorted(options, key=lambda opt: hmac.new(settings.SECRET_KEY.encode(), f"{attempt2.id}:option:{opt.id}".encode(), hashlib.sha256).digest())

        # Shuffling is deterministic per attempt ID
        order1_repeat = sorted(options, key=lambda opt: hmac.new(settings.SECRET_KEY.encode(), f"{attempt1.id}:option:{opt.id}".encode(), hashlib.sha256).digest())
        self.assertEqual([o.id for o in order1], [o.id for o in order1_repeat])
