import csv
import io
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.assignments.models import Assignment, AssignmentRecipient, Attempt, RecipientEnglishClass
from apps.classes.models import EnglishClass
from apps.content.models import Course, CourseExercise, Exam, ExamVersion
from apps.grading.models import GradeRelease
from .report_services import export_scores_csv


class ScoreExportTests(TestCase):
    def test_filters_scores_and_csv_safety(self):
        owner = User.objects.create_user(username='export-owner', role='OWNER')
        student = User.objects.create_user(username='export-student', role='STUDENT', display_name='=unsafe')
        classroom = EnglishClass.objects.create(name='Class A', code='EXPORT-A', school_year='2026-2027')
        course = Course.objects.create(name='Course', category='OTHER', created_by=owner)
        course.english_classes.add(classroom)
        exam = Exam.objects.create(title='Exam', created_by=owner)
        version = ExamVersion.objects.create(exam=exam, number=1, status='PUBLISHED')
        now = timezone.now()
        assignment = Assignment.objects.create(version=version, title='Test', code='EXP-TEST1', status='PUBLISHED', opens_at=now-timedelta(days=1), due_at=now+timedelta(days=1), late_until=now+timedelta(days=2), published_at=now)
        CourseExercise.objects.create(course=course, assignment=assignment)
        recipient = AssignmentRecipient.objects.create(assignment=assignment, student=student)
        RecipientEnglishClass.objects.create(recipient=recipient, english_class=classroom, class_name_snapshot=classroom.name, school_year_snapshot=classroom.school_year)
        attempt = Attempt.objects.create(recipient=recipient, attempt_no=1, status='GRADED', submitted_at=now, is_late=True)
        recipient.current_attempt = attempt
        recipient.save(update_fields=['current_attempt'])
        GradeRelease.objects.create(attempt=attempt, number=1, total_points=8, max_points=10, published_by=owner, snapshot={})
        other_class = EnglishClass.objects.create(name='Class B', code='EXPORT-B', school_year='2026-2027')
        other_student = User.objects.create_user(username='export-other', role='STUDENT', display_name='Other')
        other_recipient = AssignmentRecipient.objects.create(assignment=assignment, student=other_student)
        RecipientEnglishClass.objects.create(recipient=other_recipient, english_class=other_class, class_name_snapshot=other_class.name, school_year_snapshot=other_class.school_year)
        text = export_scores_csv(owner, 'course', str(assignment.id), str(classroom.id), str(course.id))
        rows = list(csv.reader(io.StringIO(text.lstrip('\ufeff'))))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][1], "'=unsafe")
        self.assertEqual(rows[1][4:6], ['8.0', 'Nộp muộn'])
        self.assertEqual(len(list(csv.reader(io.StringIO(export_scores_csv(owner, 'course', course_id=str(course.id)).lstrip('\ufeff'))))), 2)
        self.assertEqual(len(list(csv.reader(io.StringIO(export_scores_csv(owner, 'class', class_id=str(classroom.id)).lstrip('\ufeff'))))), 2)
        with self.assertRaises(ValidationError):
            export_scores_csv(owner, 'assignment')
