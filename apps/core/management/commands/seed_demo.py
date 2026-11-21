import secrets
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.accounts.models import StudentProfile, User
from apps.accounts.services import rotate_code
from apps.assignments.models import Assignment, AssignmentClass, AssignmentRecipient, RecipientEnglishClass
from apps.classes.models import EnglishClass, EnglishMembership
from apps.content.models import Exam
from apps.content.services import create_imported_exam, parse_questions, publish_version


class Command(BaseCommand):
    help = "Create local demo data only."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Demo data can only be created in DEBUG mode.")
        teacher, _ = User.objects.get_or_create(
            username="demo-owner",
            defaults={"role": "OWNER", "display_name": "Giáo viên mẫu", "is_staff": True, "is_superuser": True},
        )
        student, _ = User.objects.get_or_create(
            username="demo-student",
            defaults={"role": "STUDENT", "display_name": "Học sinh mẫu"},
        )
        if teacher.role != "OWNER" or student.role != "STUDENT":
            raise CommandError("Demo usernames are already in use.")
        owner_password = secrets.token_urlsafe(10)
        teacher.set_password(owner_password)
        teacher.is_staff = True
        teacher.is_superuser = True
        teacher.auth_epoch += 1
        teacher.save(update_fields=["password", "is_staff", "is_superuser", "auth_epoch"])

        StudentProfile.objects.get_or_create(user=student, defaults={"student_ref": "DEMO001"})
        code = rotate_code(student, actor=teacher)

        eng_class, _ = EnglishClass.objects.get_or_create(
            code="ENG-DEMO01",
            defaults={"name": "Lớp tiếng Anh mẫu 6A", "school_year": "2026-2027"},
        )
        now = timezone.now()
        if not EnglishMembership.objects.filter(student=student, english_class=eng_class, end_at__isnull=True).exists():
            EnglishMembership.objects.create(student=student, english_class=eng_class, start_at=now - timedelta(days=2))

        exam = Exam.objects.filter(title="Bài tập mẫu", created_by=teacher).first()
        if not exam:
            rows = parse_questions((settings.BASE_DIR / "docs/examples/questions.csv").read_bytes(), "questions.csv")
            version = create_imported_exam(teacher, "Bài tập mẫu", rows)
            publish_version(version.id, version.revision)
        else:
            version = exam.versions.filter(status="PUBLISHED").first()
            if not version:
                raise CommandError("Demo exam has no published version.")

        assignment, _ = Assignment.objects.get_or_create(
            code="HW-DEMO01",
            defaults={
                "version": version,
                "title": "Bài tập mẫu",
                "status": "PUBLISHED",
                "opens_at": now - timedelta(days=1),
                "due_at": now + timedelta(days=7),
                "late_until": now + timedelta(days=14),
                "published_at": now,
            },
        )
        AssignmentClass.objects.get_or_create(assignment=assignment, english_class=eng_class)
        recipient, _ = AssignmentRecipient.objects.get_or_create(assignment=assignment, student=student)
        RecipientEnglishClass.objects.get_or_create(
            recipient=recipient,
            english_class=eng_class,
            defaults={"class_name_snapshot": eng_class.name, "school_year_snapshot": eng_class.school_year},
        )
        self.stdout.write(f"Local demo owner: username=demo-owner password={owner_password}")
        self.stdout.write("Local demo student code: " + code)
