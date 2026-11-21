import json
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from django_otp.oath import TOTP
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.models import User
from apps.accounts.services import create_student
from apps.assignments.models import Assignment, AssignmentRecipient, Attempt, RecipientEnglishClass
from apps.classes.models import EnglishMembership, School, SchoolClass, SchoolMembership
from apps.classes.services import create_english_class
from apps.content.models import Exam, ExamVersion, Question
from apps.grading.models import GradeRelease
from apps.reporting.models import RankingPeriod


def _login_verified_owner(client, owner, password, device):
    client.get("/teacher/login/")
    client.post("/teacher/login/", {
        "owner_login_view-current_step": "auth",
        "auth-username": owner.username,
        "auth-password": password,
    })
    token = str(TOTP(device.bin_key, step=device.step, t0=device.t0, digits=device.digits).token()).zfill(device.digits)
    client.post("/teacher/login/", {
        "owner_login_view-current_step": "token",
        "token-otp_token": token,
    })


class OwnerReportingRankingAndUiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner-rep", password="OwnerPass!2026", role=User.Role.OWNER, display_name="Thầy Nam")
        self.device = TOTPDevice.objects.create(user=self.owner, name="default", confirmed=True)
        _login_verified_owner(self.client, self.owner, "OwnerPass!2026", self.device)

        self.school = School.objects.create(code="THCS_A", name="THCS An Khánh")
        self.sc = SchoolClass.objects.create(school=self.school, school_year="2026-2027", grade=6, name="6A1")
        self.ec = create_english_class("Tiếng Anh 6A", "2026-2027", actor=self.owner)
        # Student display_name starts with "=" to test CSV formula neutralization
        self.student = create_student("=SUM(1,2)", "HS-REP-01", actor=self.owner)
        now = timezone.now()
        SchoolMembership.objects.create(student=self.student, school_class=self.sc, start_at=now - timedelta(days=5))
        EnglishMembership.objects.create(student=self.student, english_class=self.ec, start_at=now - timedelta(days=5))

        self.exam = Exam.objects.create(title="Exam Rep", created_by=self.owner)
        self.version = ExamVersion.objects.create(exam=self.exam, number=1, status=ExamVersion.Status.PUBLISHED, published_at=now)
        Question.objects.create(version=self.version, position=1, type="SINGLE_CHOICE", skill="READING", difficulty="STANDARD", prompt="Q1", max_points="2.00")

        # Past/submitted assignment for Progress Report & Grading UI smoke test
        self.assignment = Assignment.objects.create(
            version=self.version, title="Bài Progress", code="ASG-REP01", opens_at=now - timedelta(days=1),
            due_at=now + timedelta(days=2), late_until=now + timedelta(days=3), status="PUBLISHED",
        )
        self.rec = AssignmentRecipient.objects.create(
            assignment=self.assignment, student=self.student,
            school=self.school, grade=6, school_class=self.sc, school_year="2026-2027",
        )
        RecipientEnglishClass.objects.create(recipient=self.rec, english_class=self.ec, class_name_snapshot=self.ec.name, school_year_snapshot="2026-2027")
        self.attempt = Attempt.objects.create(recipient=self.rec, attempt_no=1, status="GRADED", submitted_at=now)
        self.rec.current_attempt = self.attempt
        self.rec.save(update_fields=["current_attempt"])
        GradeRelease.objects.create(
            attempt=self.attempt, number=1, total_points="2.00", max_points="2.00", published_by=self.owner,
            snapshot={"responses": [{"skill": "READING", "points": "2.00", "max_points": "2.00", "difficulty": "STANDARD", "topics": [{"name": "Grammar"}], "errors": []}]},
        )

        # Upcoming unsubmitted assignment for RankingPeriod lifecycle test (must open in future before activate)
        self.rank_assignment = Assignment.objects.create(
            version=self.version, title="Bài Ranking", code="ASG-RNK01", opens_at=now + timedelta(minutes=20),
            due_at=now + timedelta(days=2), late_until=now + timedelta(days=3), status="PUBLISHED",
        )
        self.rank_rec = AssignmentRecipient.objects.create(
            assignment=self.rank_assignment, student=self.student,
            school=self.school, grade=6, school_class=self.sc, school_year="2026-2027",
        )
        RecipientEnglishClass.objects.create(recipient=self.rank_rec, english_class=self.ec, class_name_snapshot=self.ec.name, school_year_snapshot="2026-2027")

    def test_progress_report_validation_and_csv_formula_injection_defense(self):
        bad = self.client.get("/api/v1/owner/reports/progress/?grade=6")
        self.assertEqual(bad.status_code, 422)

        ok = self.client.get(f"/api/v1/owner/reports/progress/?school_id={self.school.id}&grade=6")
        self.assertEqual(ok.status_code, 200)
        data = ok.json()["data"]
        self.assertEqual(data["skills"]["READING"]["percent"], "100.00")

        # Export CSV succeeds within 10m MFA and neutralizes leading '='
        csv_resp = self.client.get("/api/v1/owner/reports/export.csv")
        self.assertEqual(csv_resp.status_code, 200)
        csv_text = csv_resp.content.decode("utf-8-sig")
        self.assertIn("'=SUM(1,2)", csv_text)

        # Stale MFA blocks CSV export
        sess = self.client.session
        sess["mfa_verified_at"] = (timezone.now() - timedelta(minutes=11)).isoformat()
        sess.save()
        stale_csv = self.client.get("/api/v1/owner/reports/export.csv")
        self.assertEqual(stale_csv.status_code, 403)

    def test_ranking_period_api_lifecycle_and_all_owner_ui_routes(self):
        now = timezone.now()
        rp_resp = self.client.post(
            "/api/v1/owner/ranking-periods/",
            data=json.dumps({
                "name": "Bảng tháng 11",
                "school_year": "2026-2027",
                "scope": "ENGLISH_CLASS",
                "scope_target": {"class_id": str(self.ec.id)},
                "start_at": now.isoformat(),
                "end_at": (now + timedelta(days=5)).isoformat(),
                "student_ids": [str(self.student.id)],
                "assignment_ids": [str(self.rank_assignment.id)],
                "show_peers": True,
            }),
            content_type="application/json",
        )
        self.assertEqual(rp_resp.status_code, 201)
        p_id = rp_resp.json()["data"]["id"]

        act = self.client.post(f"/api/v1/owner/ranking-periods/{p_id}/activate/", data=json.dumps({"expected_revision": 0}), content_type="application/json")
        self.assertEqual(act.status_code, 200)
        Assignment.objects.filter(pk=self.rank_assignment.id).update(opens_at=now - timedelta(days=4), due_at=now - timedelta(days=2), late_until=now - timedelta(hours=2))
        RankingPeriod.objects.filter(pk=p_id).update(start_at=now - timedelta(days=5), end_at=now - timedelta(hours=1))
        fin = self.client.post(f"/api/v1/owner/ranking-periods/{p_id}/finalize/", data=json.dumps({"expected_revision": 1}), content_type="application/json")
        self.assertEqual(fin.status_code, 200)
        self.assertEqual(RankingPeriod.objects.get(pk=p_id).status, "FINAL")

        ui_urls = [
            "/teacher/",
            "/teacher/students/",
            "/teacher/students/?tab=english",
            "/teacher/students/?tab=school",
            "/teacher/students/?tab=import",
            f"/teacher/students/{self.student.id}/",
            "/teacher/exams/",
            "/teacher/exams/import/",
            f"/teacher/exams/{self.exam.id}/versions/{self.version.id}/",
            f"/teacher/exams/{self.exam.id}/versions/{self.version.id}/preview/",
            "/teacher/assignments/",
            "/teacher/assignments/new/",
            f"/teacher/assignments/{self.assignment.id}/",
            "/teacher/grading/",
            "/teacher/grading/?status=ALL",
            f"/teacher/grading/{self.attempt.id}/",
            "/teacher/reports/",
            "/teacher/rankings/",
            "/teacher/rankings/new/",
            f"/teacher/rankings/{p_id}/",
            "/teacher/settings/",
        ]
        for url in ui_urls:
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 200, msg=f"UI route failed: {url}")
