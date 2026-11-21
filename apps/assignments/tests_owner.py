import json
import tempfile
from datetime import timedelta
from pathlib import Path

from django.test import TestCase, override_settings
from django.utils import timezone
from django_otp.oath import TOTP
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.models import User
from apps.accounts.services import create_student
from apps.assignments.models import Assignment, AssignmentRecipient, Attempt, Response
from apps.classes.models import EnglishMembership
from apps.classes.services import create_english_class
from apps.content.models import Asset, Exam, ExamVersion, Question, RubricCriterion, Tag
from apps.content.services import LEVELS, RUBRICS
from apps.grading.models import ErrorOccurrence, ErrorReview


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


class OwnerAssignmentAndGradingApiTests(TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.owner = User.objects.create_user(username="owner-asg", password="OwnerPass!2026", role=User.Role.OWNER, display_name="Cô Ngọc")
        self.device = TOTPDevice.objects.create(user=self.owner, name="default", confirmed=True)
        _login_verified_owner(self.client, self.owner, "OwnerPass!2026", self.device)

        self.s1 = create_student("HS Một", "HS-ASG-1", actor=self.owner)
        self.s2 = create_student("HS Hai", "HS-ASG-2", actor=self.owner)
        self.c1 = create_english_class("Class 1", "2026-2027", actor=self.owner)
        self.c2 = create_english_class("Class 2", "2026-2027", actor=self.owner)
        now = timezone.now()
        EnglishMembership.objects.create(student=self.s1, english_class=self.c1, start_at=now - timedelta(days=1))
        # Overlapping student in both c1 and c2
        EnglishMembership.objects.create(student=self.s1, english_class=self.c2, start_at=now - timedelta(days=1))
        EnglishMembership.objects.create(student=self.s2, english_class=self.c2, start_at=now - timedelta(days=1))

        self.exam = Exam.objects.create(title="Exam Speaking/Writing", created_by=self.owner)
        self.version = ExamVersion.objects.create(exam=self.exam, number=1, status=ExamVersion.Status.PUBLISHED, published_at=now)
        self.q_audio = Question.objects.create(version=self.version, position=1, type="AUDIO", skill="SPEAKING", difficulty="STANDARD", prompt="Speak now", max_points="4.00", explanation="Model script")
        for idx, (key, label) in enumerate(RUBRICS["AUDIO"], 1):
            RubricCriterion.objects.create(question=self.q_audio, key=key, position=idx, label=label, level_descriptions=LEVELS)
        self.err_tag = Tag.objects.create(kind=Tag.Kind.ERROR, skill="SPEAKING", name="Pronunciation")
        self.err_tag_ai = Tag.objects.create(kind=Tag.Kind.ERROR, skill="SPEAKING", name="Fluency")

    def test_assignment_publish_dedup_extend_exempt_retake_and_release_answers(self):
        now = timezone.now()
        c_resp = self.client.post(
            "/api/v1/owner/assignments/",
            data=json.dumps({
                "version_id": str(self.version.id),
                "title": "HW 1",
                "class_ids": [str(self.c1.id), str(self.c2.id)],
                "opens_at": (now - timedelta(hours=4)).isoformat(),
                "due_at": (now - timedelta(hours=2)).isoformat(),
                "late_policy": "ALLOW",
                "late_until": (now - timedelta(hours=1)).isoformat(),
            }),
            content_type="application/json",
        )
        self.assertEqual(c_resp.status_code, 201)
        a_id = c_resp.json()["data"]["id"]

        p_resp = self.client.post(
            f"/api/v1/owner/assignments/{a_id}/publish/",
            data=json.dumps({"expected_revision": 0}),
            content_type="application/json",
        )
        self.assertEqual(p_resp.status_code, 200)
        # s1 in both classes was deduplicated into 2 total recipients
        self.assertEqual(AssignmentRecipient.objects.filter(assignment_id=a_id).count(), 2)

        r2 = AssignmentRecipient.objects.get(assignment_id=a_id, student=self.s2)
        ex_resp = self.client.post(
            f"/api/v1/owner/recipients/{r2.id}/exempt/",
            data=json.dumps({"reason": "Học sinh ốm"}),
            content_type="application/json",
        )
        self.assertEqual(ex_resp.status_code, 200)
        self.assertEqual(ex_resp.json()["data"]["state"], "EXEMPT")

        rel_resp = self.client.post(
            f"/api/v1/owner/assignments/{a_id}/release-answers/",
            data=json.dumps({"expected_revision": p_resp.json()["data"]["revision"]}),
            content_type="application/json",
        )
        self.assertEqual(rel_resp.status_code, 200)
        self.assertIsNotNone(rel_resp.json()["data"]["answers_released_at"])

        cur_rev = Assignment.objects.get(pk=a_id).revision
        cancel_resp = self.client.post(
            f"/api/v1/owner/assignments/{a_id}/cancel/",
            data=json.dumps({"expected_revision": cur_rev, "reason": "Hủy thử nghiệm"}),
            content_type="application/json",
        )
        self.assertEqual(cancel_resp.status_code, 200)
        self.assertEqual(cancel_resp.json()["data"]["status"], "CANCELLED")

    def test_owner_grades_student_audio_tags_errors_publishes_and_voids(self):
        with override_settings(PRIVATE_MEDIA_ROOT=Path(self.tmpdir.name)):
            now = timezone.now()
            a_resp = self.client.post(
                "/api/v1/owner/assignments/",
                data=json.dumps({
                    "version_id": str(self.version.id),
                    "title": "Speaking HW",
                    "class_ids": [str(self.c1.id)],
                    "opens_at": (now - timedelta(hours=2)).isoformat(),
                    "due_at": (now + timedelta(days=1)).isoformat(),
                    "late_policy": "ALLOW",
                    "late_until": (now + timedelta(days=2)).isoformat(),
                }),
                content_type="application/json",
            )
            a_id = a_resp.json()["data"]["id"]
            self.client.post(f"/api/v1/owner/assignments/{a_id}/publish/", data=json.dumps({"expected_revision": 0}), content_type="application/json")

            rec = AssignmentRecipient.objects.get(assignment_id=a_id, student=self.s1)
            rel_path = Path(self.tmpdir.name) / "response" / "speaking1.mp3"
            rel_path.parent.mkdir(parents=True, exist_ok=True)
            rel_path.write_bytes(b"ID3SPEAKINGDATA")
            stu_audio = Asset.objects.create(
                uploaded_by=self.s1, purpose=Asset.Purpose.RESPONSE_AUDIO, status=Asset.Status.READY,
                object_key="response/speaking1.mp3", original_name="speaking1.mp3", detected_mime="audio/mpeg", bytes=15, sha256="c" * 64,
            )
            att = Attempt.objects.create(recipient=rec, attempt_no=1, status="SUBMITTED", submitted_at=now)
            rec.current_attempt = att
            rec.save(update_fields=["current_attempt"])
            response = Response.objects.create(attempt=att, question=self.q_audio, audio_asset=stu_audio)

            # Owner can stream student RESPONSE_AUDIO
            audio_get = self.client.get(f"/api/v1/owner/assets/{stu_audio.id}/content", HTTP_RANGE="bytes=0-14")
            self.assertEqual(audio_get.status_code, 206)
            self.assertEqual(audio_get.content, b"ID3SPEAKINGDATA")

            # Tag teacher error (att.revision: 0 -> 1)
            err_post = self.client.post(
                f"/api/v1/owner/responses/{response.id}/errors/",
                data=json.dumps({"expected_revision": 0, "tag_id": str(self.err_tag.id), "note": "Ending sound /s/", "anchor": {"start_ms": 100, "end_ms": 800}}),
                content_type="application/json",
            )
            self.assertEqual(err_post.status_code, 200)
            rev = err_post.json()["data"]["attempt_revision"]

            # AI error review does not bump attempt revision
            ai_occ = ErrorOccurrence.objects.create(
                response=response, tag=self.err_tag_ai, source="AI", confidence="HIGH",
            )
            ai_rev = self.client.post(
                f"/api/v1/owner/errors/{ai_occ.id}/teacher-review/",
                data=json.dumps({"reviewed": True, "teacher_note": "Confirmed"}),
                content_type="application/json",
            )
            self.assertEqual(ai_rev.status_code, 200)
            self.assertIsNotNone(ErrorReview.objects.get(occurrence=ai_occ).teacher_reviewed_at)

            # Grade all 4 rubric criteria -> level 3 each = 3.00/4.00
            criteria_ids = [str(c.id) for c in self.q_audio.criteria.all()]
            grade_put = self.client.put(
                f"/api/v1/owner/responses/{response.id}/grade/",
                data=json.dumps({
                    "expected_revision": rev,
                    "grade_revision": 0,
                    "criterion_levels": {cid: 3 for cid in criteria_ids},
                    "feedback": "Good clarity.",
                }),
                content_type="application/json",
            )
            self.assertEqual(grade_put.status_code, 200)
            self.assertEqual(grade_put.json()["data"]["points"], "3.00")
            rev = grade_put.json()["data"]["attempt_revision"]

            pub = self.client.post(
                f"/api/v1/owner/attempts/{att.id}/publish-result/",
                data=json.dumps({"expected_revision": rev}),
                content_type="application/json",
            )
            self.assertEqual(pub.status_code, 200)
            att.refresh_from_db()

            void_resp = self.client.post(
                f"/api/v1/owner/attempts/{att.id}/void/",
                data=json.dumps({"expected_revision": att.revision, "reason": "Học sinh nộp nhầm tệp"}),
                content_type="application/json",
            )
            self.assertEqual(void_resp.status_code, 200)
            att.refresh_from_db()
            self.assertEqual(att.status, "VOID")
