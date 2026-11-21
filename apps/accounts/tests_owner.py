import json
from datetime import timedelta
from io import StringIO

from django.core.management import CommandError, call_command
from django.test import TestCase
from django.utils import timezone
from django_otp import DEVICE_ID_SESSION_KEY
from django_otp.oath import TOTP
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.models import PrivacyRequest, StudentProfile, User
from apps.accounts.services import create_student, generate_student_ref, initialize_session, rotate_code
from apps.assignments.models import Assignment, AssignmentRecipient, Attempt, RecipientEnglishClass, Response
from apps.classes.services import create_english_class, generate_school_code, generate_student_import_template, parse_students
from apps.classes.models import EnglishMembership, School, SchoolMembership
from apps.content.models import Asset, Exam, ExamVersion, Question
from apps.grading.models import GradeRelease
from apps.reporting.models import RankingAssignment, RankingMember, RankingPeriod
from apps.reporting.services import activate, finalize


def _totp_token(device):
    return str(TOTP(device.bin_key, step=device.step, t0=device.t0, digits=device.digits).token()).zfill(device.digits)


def _login_verified_owner(client, owner, password, device):
    get_resp = client.get("/teacher/login/")
    assert get_resp.status_code == 200
    resp1 = client.post("/teacher/login/", {
        "owner_login_view-current_step": "auth",
        "auth-username": owner.username,
        "auth-password": password,
    })
    assert resp1.status_code == 200
    resp2 = client.post("/teacher/login/", {
        "owner_login_view-current_step": "token",
        "token-otp_token": _totp_token(device),
    })
    assert resp2.status_code in (302, 200)


class OwnerAuthAndMfaTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner1",
            password="StrongPassword!2026",
            role=User.Role.OWNER,
            display_name="Cô Lan",
            is_staff=True,
            is_superuser=True,
        )
        self.device = TOTPDevice.objects.create(user=self.owner, name="default", confirmed=True)
        self.student = create_student("Học Sinh A", "HS-AUTH-01", actor=self.owner)
        self.student.set_password("StudentPass!2026")
        self.student.save(update_fields=["password"])

    def test_student_and_unverified_owner_are_blocked_everywhere(self):
        # Student cannot access owner login even with valid username/password
        resp = self.client.post("/teacher/login/", {
            "owner_login_view-current_step": "auth",
            "auth-username": self.student.username,
            "auth-password": "StudentPass!2026",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.wsgi_request.user.is_authenticated)

        # Student authenticated via student code login is blocked with 403 from /teacher/ and /api/v1/owner/
        stu_code = rotate_code(self.student, actor=self.owner)
        self.assertEqual(self.client.post("/api/v1/auth/student-login/", data=json.dumps({"code": stu_code}), content_type="application/json").status_code, 200)
        self.assertEqual(self.client.get("/teacher/").status_code, 403)
        self.assertEqual(self.client.get("/api/v1/owner/students/").status_code, 403)
        self.assertIn(self.client.get("/admin/").status_code, (302, 403))

        # OWNER logged in WITHOUT OTP verification in session is blocked
        self.client.force_login(self.owner)
        sess = self.client.session
        sess["auth_epoch"] = self.owner.auth_epoch
        sess["issued_at"] = timezone.now().isoformat()
        sess["last_activity"] = timezone.now().isoformat()
        sess.save()
        self.assertEqual(self.client.get("/teacher/").status_code, 302)
        self.assertEqual(self.client.get("/api/v1/owner/students/").status_code, 403)
        self.assertEqual(self.client.get("/admin/").status_code, 302)

    def test_real_two_factor_login_unlocks_teacher_and_admin(self):
        _login_verified_owner(self.client, self.owner, "StrongPassword!2026", self.device)
        self.assertEqual(self.client.get("/teacher/").status_code, 200)
        self.assertEqual(self.client.get("/api/v1/owner/students/").status_code, 200)
        self.assertEqual(self.client.get("/admin/").status_code, 200)
        self.assertTrue(self.client.session.get("mfa_verified_at"))

    def test_owner_login_rate_limit_blocks_after_five_failures(self):
        for _ in range(5):
            r = self.client.post("/teacher/login/", {
                "owner_login_view-current_step": "auth",
                "auth-username": "owner1",
                "auth-password": "WrongPassword",
            })
            self.assertEqual(r.status_code, 200)
        blocked = self.client.post("/teacher/login/", {
            "owner_login_view-current_step": "auth",
            "auth-username": "owner1",
            "auth-password": "WrongPassword",
        })
        self.assertEqual(blocked.status_code, 429)
        self.assertIn("Retry-After", blocked)

    def test_disable_mfa_blocked_for_owner_and_management_commands_work(self):
        _login_verified_owner(self.client, self.owner, "StrongPassword!2026", self.device)
        self.assertEqual(self.client.get("/account/two_factor/disable/").status_code, 302)
        self.assertEqual(self.client.post("/account/two_factor/disable/").status_code, 403)

        out = StringIO()
        call_command("reset_owner_mfa", "--username", "owner1", "--reason", "Lost device", stdout=out)
        self.assertEqual(TOTPDevice.objects.filter(user=self.owner).count(), 0)

        with self.assertRaises(CommandError):
            call_command("create_owner", "--username", "owner2", "--password", "AnotherPass!99", "--display-name", "Thầy Minh", stdout=out)


class OwnerBootstrapCommandTests(TestCase):
    def test_create_owner_bootstraps_first_owner(self):
        out = StringIO()
        call_command("create_owner", "--username", "owner-boot", "--password", "BootPass!2026", "--display-name", "Cô Trang", stdout=out)
        owner = User.objects.get(username="owner-boot")
        self.assertEqual(owner.role, User.Role.OWNER)
        self.assertTrue(owner.is_superuser)


class OwnerStudentsAndPrivacyTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner-mfa", password="OwnerPass!2026", role=User.Role.OWNER, display_name="Cô Hoa")
        self.device = TOTPDevice.objects.create(user=self.owner, name="default", confirmed=True)
        _login_verified_owner(self.client, self.owner, "OwnerPass!2026", self.device)
        self.student = create_student("Trần Minh", "HS-PRIV-01", actor=self.owner)

    def test_rotate_code_requires_recent_mfa_and_returns_qr_svg(self):
        sess = self.client.session
        sess["mfa_verified_at"] = (timezone.now() - timedelta(minutes=11)).isoformat()
        sess.save()

        ok = self.client.post(f"/api/v1/owner/students/{self.student.id}/rotate-code/", data="{}", content_type="application/json")
        self.assertEqual(ok.status_code, 200)
        body = ok.json()["data"]
        self.assertIn("code", body)
        self.assertIn("<svg", body["qr_svg"])
        active_code = self.student.access_codes.filter(revoked_at__isnull=True).first()
        self.assertIsNotNone(active_code)
        self.assertNotIn(body["code"], active_code.code_digest)

        # Web student detail rotate_code action also works without OTP re-entry
        web_resp = self.client.post(f"/teacher/students/{self.student.id}/", {"action": "rotate_code"})
        self.assertEqual(web_resp.status_code, 200)
        self.assertIn("Mã cá nhân mới", web_resp.content.decode("utf-8"))

    def test_status_change_and_revoke_sessions_increment_auth_epoch(self):
        old_epoch = self.student.auth_epoch
        resp = self.client.post(f"/api/v1/owner/students/{self.student.id}/revoke-sessions/", data="{}", content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        self.student.refresh_from_db()
        self.assertEqual(self.student.auth_epoch, old_epoch + 1)

        resp2 = self.client.patch(
            f"/api/v1/owner/students/{self.student.id}/",
            data=json.dumps({"status": "SUSPENDED", "reason": "Tạm nghỉ học"}),
            content_type="application/json",
        )
        self.assertEqual(resp2.status_code, 200)
        self.student.refresh_from_db()
        self.assertEqual(self.student.status, "SUSPENDED")
        self.assertEqual(self.student.auth_epoch, old_epoch + 2)

    def test_privacy_export_and_erase_anonymizes_student_and_keeps_shared_prompt_audio(self):
        prompt_audio = Asset.objects.create(
            uploaded_by=self.owner, purpose=Asset.Purpose.PROMPT_AUDIO, status=Asset.Status.READY,
            object_key="prompt/shared.mp3", original_name="shared.mp3", detected_mime="audio/mpeg", bytes=128, sha256="a" * 64,
        )
        resp_audio = Asset.objects.create(
            uploaded_by=self.student, purpose=Asset.Purpose.RESPONSE_AUDIO, status=Asset.Status.READY,
            object_key="response/stu.mp3", original_name="stu.mp3", detected_mime="audio/mpeg", bytes=64, sha256="b" * 64,
        )
        exam = Exam.objects.create(title="Exam Priv", created_by=self.owner)
        version = ExamVersion.objects.create(exam=exam, number=1, status=ExamVersion.Status.PUBLISHED, published_at=timezone.now())
        question = Question.objects.create(version=version, position=1, type="TEXT", skill="WRITING", difficulty="STANDARD", prompt="Write", max_points="4.00")
        now = timezone.now()
        ec = create_english_class("EC Priv", "2026-2027", actor=self.owner)
        EnglishMembership.objects.create(student=self.student, english_class=ec, start_at=now - timedelta(days=2))
        assignment = Assignment.objects.create(version=version, title="A Priv", code="ASG-PRV01", opens_at=now + timedelta(minutes=10), due_at=now + timedelta(days=2), late_until=now + timedelta(days=3), status="PUBLISHED")
        rec = AssignmentRecipient.objects.create(assignment=assignment, student=self.student)
        RecipientEnglishClass.objects.create(recipient=rec, english_class=ec, class_name_snapshot=ec.name, school_year_snapshot=ec.school_year)

        # Activate ranking before student submits, then student submits/gets graded, then finalize
        period = RankingPeriod.objects.create(
            name="P Priv", school_year="2026-2027", start_at=now, end_at=now + timedelta(days=5),
            scope="ENGLISH_CLASS", scope_target={"class_id": str(ec.id)},
        )
        RankingAssignment.objects.create(period=period, assignment=assignment)
        RankingMember.objects.create(period=period, student=self.student, alias="Bút Chì Xanh", cohort_snapshot={"display_name": self.student.display_name})
        activate(period.id, self.owner, period.revision)

        attempt = Attempt.objects.create(recipient=rec, attempt_no=1, status="GRADED", submitted_at=now)
        response_obj = Response.objects.create(attempt=attempt, question=question, text_answer="My private essay", audio_asset=resp_audio)
        rec.current_attempt = attempt
        rec.save(update_fields=["current_attempt"])
        release_obj = GradeRelease.objects.create(attempt=attempt, number=1, total_points="3.00", max_points="4.00", published_by=self.owner, snapshot={"responses": []})

        period.refresh_from_db()
        Assignment.objects.filter(pk=assignment.id).update(opens_at=now - timedelta(days=4), due_at=now - timedelta(days=2), late_until=now - timedelta(hours=2))
        RankingPeriod.objects.filter(pk=period.id).update(start_at=now - timedelta(days=5), end_at=now - timedelta(hours=1))
        finalize(period.id, self.owner, period.revision)

        exp = self.client.post("/api/v1/owner/privacy-requests/", data=json.dumps({"student_id": str(self.student.id), "kind": "EXPORT", "reason": "Phụ huynh yêu cầu sao lưu"}), content_type="application/json")
        self.assertEqual(exp.status_code, 201)
        exp_id = exp.json()["data"]["id"]
        self.assertEqual(self.client.post(f"/api/v1/owner/privacy-requests/{exp_id}/approve/", data="{}", content_type="application/json").status_code, 200)
        exp_dl = self.client.get(f"/api/v1/owner/privacy-requests/{exp_id}/export/")
        self.assertEqual(exp_dl.status_code, 200)
        self.assertEqual(json.loads(exp_dl.content)["student"]["student_ref"], "HS-PRIV-01")

        erase = self.client.post("/api/v1/owner/privacy-requests/", data=json.dumps({"student_id": str(self.student.id), "kind": "ERASE", "reason": "Yêu cầu phụ huynh"}), content_type="application/json")
        self.assertEqual(erase.status_code, 201)
        erase_id = erase.json()["data"]["id"]
        erase_app = self.client.post(f"/api/v1/owner/privacy-requests/{erase_id}/approve/", data="{}", content_type="application/json")
        self.assertEqual(erase_app.status_code, 200)
        self.assertEqual(erase_app.json()["data"]["status"], PrivacyRequest.Status.COMPLETED)

        self.student.refresh_from_db()
        self.assertEqual(self.student.status, User.Status.ARCHIVED)
        self.assertNotEqual(self.student.display_name, "Trần Minh")
        response_obj.refresh_from_db()
        self.assertEqual(response_obj.text_answer, "")
        resp_audio.refresh_from_db()
        self.assertEqual(resp_audio.status, Asset.Status.DELETING)
        release_obj.refresh_from_db()
        self.assertTrue(release_obj.snapshot.get("erased"))
        period.refresh_from_db()
        self.assertEqual(period.status, "INVALID")
        self.assertTrue(Asset.objects.filter(pk=prompt_audio.id, status=Asset.Status.READY).exists())

    def test_create_student_auto_ref_and_school_and_default_class_web(self):
        ec = create_english_class("Lớp Tiếng Anh 7A", "2026-2027", actor=self.owner)
        resp = self.client.post("/teacher/students/", {
            "action": "create_student",
            "display_name": "Lê Bảo Ngọc",
            "student_ref": "",
            "school_id": "__other__",
            "new_school_name": "THCS Lê Quý Đôn",
            "english_class_id": str(ec.id),
            "owner_note": "Học sinh mới",
        })
        self.assertEqual(resp.status_code, 302)
        new_stu = User.objects.get(display_name="Lê Bảo Ngọc")
        self.assertTrue(new_stu.student_profile.student_ref.startswith(f"HS{timezone.now().year}-"))
        # Verify school was created and saved
        school = School.objects.get(name="THCS Lê Quý Đôn")
        self.assertIsNotNone(school)
        # Verify school membership
        sm = SchoolMembership.objects.filter(student=new_stu, end_at__isnull=True).first()
        self.assertIsNotNone(sm)
        self.assertEqual(sm.school_class.school, school)
        # Verify English class membership
        em = EnglishMembership.objects.filter(student=new_stu, english_class=ec, end_at__isnull=True).first()
        self.assertIsNotNone(em)

        # Create second student reusing existing school
        resp2 = self.client.post("/teacher/students/", {
            "action": "create_student",
            "display_name": "Nguyễn Hoàng Nam",
            "student_ref": "",
            "school_id": str(school.id),
            "english_class_id": str(ec.id),
        })
        self.assertEqual(resp2.status_code, 302)
        stu2 = User.objects.get(display_name="Nguyễn Hoàng Nam")
        self.assertNotEqual(new_stu.student_profile.student_ref, stu2.student_profile.student_ref)
        sm2 = SchoolMembership.objects.filter(student=stu2, end_at__isnull=True).first()
        self.assertEqual(sm2.school_class.school, school)

    def test_create_student_api_auto_ref(self):
        res = self.client.post(
            "/api/v1/owner/students/",
            data=json.dumps({"display_name": "Hoàng Yến"}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 201)
        data = res.json()["data"]
        self.assertTrue(data["student_ref"].startswith(f"HS{timezone.now().year}-"))
        self.assertEqual(data["display_name"], "Hoàng Yến")

    def test_student_import_template_download_csv_and_xlsx(self):
        # 1. Test CSV web download
        csv_resp = self.client.get("/teacher/students/template/?format=csv")
        self.assertEqual(csv_resp.status_code, 200)
        self.assertIn("text/csv", csv_resp["Content-Type"])
        self.assertIn("mau_nhap_hoc_sinh.csv", csv_resp["Content-Disposition"])
        # Verify parseable by parse_students
        parsed_csv = parse_students(csv_resp.content, "template.csv")
        self.assertGreaterEqual(len(parsed_csv), 2)
        self.assertEqual(parsed_csv[0]["student_ref"], "HS2026-0001")

        # 2. Test XLSX web download
        xlsx_resp = self.client.get("/teacher/students/template/?format=xlsx")
        self.assertEqual(xlsx_resp.status_code, 200)
        self.assertIn("openxmlformats", xlsx_resp["Content-Type"])
        self.assertIn("mau_nhap_hoc_sinh.xlsx", xlsx_resp["Content-Disposition"])
        parsed_xlsx = parse_students(xlsx_resp.content, "template.xlsx")
        self.assertGreaterEqual(len(parsed_xlsx), 2)
        self.assertEqual(parsed_xlsx[0]["student_ref"], "HS2026-0001")

        # 3. Test API template download
        api_csv = self.client.get("/api/v1/owner/students/template/?format=csv")
        self.assertEqual(api_csv.status_code, 200)
        api_xlsx = self.client.get("/api/v1/owner/students/template/?format=xlsx")
        self.assertEqual(api_xlsx.status_code, 200)
