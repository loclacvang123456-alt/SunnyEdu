import json
import tempfile
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django_otp.oath import TOTP
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.models import User
from apps.classes.models import EnglishClass, EnglishMembership
from apps.content.models import Exam, ExamVersion, Passage, Question, Tag


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


class OwnerContentAndImportTests(TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.owner = User.objects.create_user(username="owner-cnt", password="OwnerPass!2026", role=User.Role.OWNER, display_name="Cô Mai")
        self.device = TOTPDevice.objects.create(user=self.owner, name="default", confirmed=True)
        _login_verified_owner(self.client, self.owner, "OwnerPass!2026", self.device)

    def test_exam_clone_question_crud_and_revision_conflict(self):
        ex_resp = self.client.post("/api/v1/owner/exams", data=json.dumps({"title": "Đề Unit 1"}), content_type="application/json")
        self.assertEqual(ex_resp.status_code, 201)
        exam_id = ex_resp.json()["data"]["id"]
        v_id = ex_resp.json()["data"]["version_id"]

        # Create passage (initial ExamVersion revision=0) + question (revision becomes 1)
        p_resp = self.client.post(
            f"/api/v1/owner/versions/{v_id}/passages",
            data=json.dumps({"expected_revision": 0, "ref": "P1", "text_body": "Reading passage"}),
            content_type="application/json",
        )
        self.assertEqual(p_resp.status_code, 201)
        p_id = p_resp.json()["data"]["id"]

        q_resp = self.client.post(
            f"/api/v1/owner/versions/{v_id}/questions",
            data=json.dumps({
                "expected_revision": 1,
                "type": "SINGLE_CHOICE",
                "skill": "READING",
                "difficulty": "STANDARD",
                "max_points": "2.00",
                "passage_id": p_id,
                "prompt": "Pick A",
                "options": [{"content": "A text"}, {"content": "B text"}],
                "correct_options": ["A"],
                "topic_tags": ["Present simple"],
            }),
            content_type="application/json",
        )
        self.assertEqual(q_resp.status_code, 201)
        q_id = q_resp.json()["data"]["id"]

        # Stale expected_revision triggers 409 CONFLICT
        stale = self.client.patch(
            f"/api/v1/owner/questions/{q_id}",
            data=json.dumps({
                "expected_revision": 1,
                "type": "SINGLE_CHOICE",
                "skill": "READING",
                "difficulty": "STANDARD",
                "max_points": "2.00",
                "prompt": "Stale",
                "options": [{"content": "A"}, {"content": "B"}],
                "correct_options": ["A"],
                "topic_tags": ["Present simple"],
            }),
            content_type="application/json",
        )
        self.assertEqual(stale.status_code, 409)

        # Publish & clone (v1 revision=2 after passage + question)
        pub = self.client.post(f"/api/v1/owner/versions/{v_id}/publish", data=json.dumps({"expected_revision": 2}), content_type="application/json")
        self.assertEqual(pub.status_code, 200)
        clone = self.client.post(f"/api/v1/owner/versions/{v_id}/clone", data="{}", content_type="application/json")
        self.assertEqual(clone.status_code, 201)
        v2_id = clone.json()["data"]["id"]
        self.assertEqual(ExamVersion.objects.get(pk=v2_id).number, 2)
        self.assertEqual(Question.objects.filter(version_id=v2_id).count(), 1)
        self.assertEqual(Passage.objects.filter(version_id=v2_id).count(), 1)
        self.assertTrue(Exam.objects.filter(pk=exam_id).exists())

    @override_settings(DEBUG=True)
    def test_prompt_audio_upload_validation_and_range_streaming(self):
        with override_settings(PRIVATE_MEDIA_ROOT=Path(self.tmpdir.name)):
            bad = SimpleUploadedFile("bad.mp3", b"NOT_AN_AUDIO_FILE", content_type="audio/mpeg")
            bad_resp = self.client.post("/api/v1/owner/assets", {"file": bad, "purpose": "PROMPT_AUDIO"})
            self.assertEqual(bad_resp.status_code, 422)

            mp3 = SimpleUploadedFile("track.mp3", b"ID3\x03\x00\x00\x00\x00\x00\x00FRAMEBYTES123456", content_type="audio/mpeg")
            ok_resp = self.client.post("/api/v1/owner/assets", {"file": mp3, "purpose": "PROMPT_AUDIO"})
            self.assertEqual(ok_resp.status_code, 201)
            asset_id = ok_resp.json()["data"]["id"]

            range_resp = self.client.get(f"/api/v1/owner/assets/{asset_id}/content", HTTP_RANGE="bytes=0-2")
            self.assertEqual(range_resp.status_code, 206)
            self.assertEqual(range_resp.content, b"ID3")
            self.assertEqual(range_resp["Accept-Ranges"], "bytes")
            self.assertEqual(range_resp["X-Content-Type-Options"], "nosniff")
            self.assertIn("no-store", range_resp["Cache-Control"])

    def test_student_csv_import_validation_and_commit(self):
        ec = EnglishClass.objects.create(name="6A Import", school_year="2026-2027")
        bad_csv = SimpleUploadedFile(
            "students.csv",
            b"student_ref,display_name,school_code,school_year,grade,school_class_name\nHS01,An,,,,\nHS01,Binh,,,,\n",
            content_type="text/csv",
        )
        bad_prev = self.client.post("/api/v1/owner/imports/preview", {"file": bad_csv, "kind": "STUDENTS"})
        self.assertEqual(bad_prev.status_code, 201)
        bad_data = bad_prev.json()["data"]
        self.assertTrue(bad_data["rows"][1]["errors"])
        commit_err = self.client.post(
            f"/api/v1/owner/imports/{bad_data['id']}/commit",
            data=json.dumps({"expected_digest": bad_data["source_digest"], "class_id": str(ec.id)}),
            content_type="application/json",
        )
        self.assertEqual(commit_err.status_code, 422)

        good_csv = SimpleUploadedFile(
            "students.csv",
            b"student_ref,display_name,school_code,school_year,grade,school_class_name\nHS-NEW-1,Nguyen An,,,,\nHS-NEW-2,Tran Binh,,,,\n",
            content_type="text/csv",
        )
        good_prev = self.client.post("/api/v1/owner/imports/preview", {"file": good_csv, "kind": "STUDENTS"})
        self.assertEqual(good_prev.status_code, 201)
        good_data = good_prev.json()["data"]
        commit_ok = self.client.post(
            f"/api/v1/owner/imports/{good_data['id']}/commit",
            data=json.dumps({"expected_digest": good_data["source_digest"], "class_id": str(ec.id)}),
            content_type="application/json",
        )
        self.assertEqual(commit_ok.status_code, 200)
        self.assertEqual(commit_ok.json()["data"]["created"], 2)
        self.assertEqual(commit_ok.json()["data"]["joined"], 2)
        self.assertEqual(EnglishMembership.objects.filter(english_class=ec, end_at__isnull=True).count(), 2)
