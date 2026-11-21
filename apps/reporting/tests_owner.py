import json
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from django_otp.oath import TOTP
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.models import User
from apps.accounts.services import create_student
from apps.assignments.models import (
    Assignment,
    AssignmentRecipient,
    Attempt,
    AttemptVisibilityEvent,
    RecipientEnglishClass,
    Response,
)
from apps.classes.models import EnglishMembership, School, SchoolClass, SchoolMembership
from apps.classes.services import create_english_class
from apps.content.models import Course, CourseExercise, CourseTag, Exam, ExamVersion, Question, QuestionOption
from apps.grading.models import Grade, GradeRelease
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

        # CSV export works without requiring recent 10m OTP re-verification
        sess = self.client.session
        sess["mfa_verified_at"] = (timezone.now() - timedelta(minutes=11)).isoformat()
        sess.save()
        stale_csv = self.client.get("/api/v1/owner/reports/export.csv")
        self.assertEqual(stale_csv.status_code, 200)

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
            if url == "/teacher/exams/":
                exams_html = resp.content.decode("utf-8")
                self.assertIn('title="Soạn câu hỏi"', exams_html)
                self.assertIn('title="Tạo bản mới', exams_html)
                self.assertIn("st-action-btn", exams_html)

    def test_general_report_metrics_auto_weakness_and_ielts_tab(self):
        now = timezone.now()
        # Non-IELTS primary course with auto-graded WORD_ORDER weakness and a similar exercise for recommendation
        wo_tag, _ = CourseTag.objects.get_or_create(code="WORD_ORDER", defaults={"name": "Sắp xếp câu", "kind": CourseTag.Kind.EXAM})
        primary_course = Course.objects.create(
            name="Tiếng Anh Tiểu học 4", category=Course.Category.PRIMARY, is_published=True, created_by=self.owner,
        )
        wo_exam = Exam.objects.create(title="Đề Sắp xếp câu", created_by=self.owner)
        wo_ver = ExamVersion.objects.create(exam=wo_exam, number=1, status=ExamVersion.Status.PUBLISHED, published_at=now)
        wo_q = Question.objects.create(
            version=wo_ver, position=1, type="WORD_ORDER", skill="READING", difficulty="FOUNDATION",
            prompt="She played football yesterday (Sắp xếp câu bị động)", max_points="4.00",
        )
        wo_opt1 = QuestionOption.objects.create(question=wo_q, key="A", position=1, content="Football")
        wo_opt2 = QuestionOption.objects.create(question=wo_q, key="B", position=2, content="was played")
        failed_asg = Assignment.objects.create(
            version=wo_ver, title="Luyện sắp xếp câu 1", code="ASG-WO001", opens_at=now - timedelta(days=1),
            due_at=now + timedelta(days=2), late_until=now + timedelta(days=3), status="PUBLISHED",
        )
        ce1 = CourseExercise.objects.create(course=primary_course, assignment=failed_asg, difficulty=1)
        ce1.tags.add(wo_tag)

        # Similar unattempted exercise that should be recommended automatically
        sim_exam = Exam.objects.create(title="Đề Sắp xếp câu ôn tập", created_by=self.owner)
        sim_ver = ExamVersion.objects.create(exam=sim_exam, number=1, status=ExamVersion.Status.PUBLISHED, published_at=now)
        Question.objects.create(
            version=sim_ver, position=1, type="WORD_ORDER", skill="READING", difficulty="FOUNDATION", prompt="Order 2", max_points="2.00",
        )
        sim_asg = Assignment.objects.create(
            version=sim_ver, title="Bài ôn Sắp xếp câu bổ sung", code="ASG-WO002", opens_at=now - timedelta(days=1),
            due_at=now + timedelta(days=5), late_until=now + timedelta(days=7), status="PUBLISHED",
        )
        ce2 = CourseExercise.objects.create(course=primary_course, assignment=sim_asg, difficulty=1)
        ce2.tags.add(wo_tag)

        # Higher-level course exercise (alphabetically earlier) should NOT outrank student's PRIMARY course recommendation
        hs_course = Course.objects.create(
            name="Tiếng Anh THPT", category=Course.Category.HIGH_SCHOOL, is_published=True, created_by=self.owner,
        )
        hs_asg = Assignment.objects.create(
            version=sim_ver, title="AAA Bài sắp xếp câu THPT", code="ASG-WOHS1", opens_at=now - timedelta(days=1),
            due_at=now + timedelta(days=5), late_until=now + timedelta(days=7), status="PUBLISHED",
        )
        ce_hs = CourseExercise.objects.create(course=hs_course, assignment=hs_asg, difficulty=4)
        ce_hs.tags.add(wo_tag)

        rec_wo = AssignmentRecipient.objects.create(
            assignment=failed_asg, student=self.student,
            school=self.school, grade=6, school_class=self.sc, school_year="2026-2027",
        )
        # Attempt 1 marked VOID (cheat signal 1), Attempt 2 late + visibility > 5s (cheat signal 2), auto-graded 0/4 WITHOUT ErrorOccurrence or GradeRelease
        Attempt.objects.create(recipient=rec_wo, attempt_no=1, status="VOID", void_reason="Gian lận")
        att2 = Attempt.objects.create(recipient=rec_wo, attempt_no=2, status="GRADED", submitted_at=now, is_late=True)
        AttemptVisibilityEvent.objects.create(attempt=att2, duration_ms=7200)
        resp_wo = Response.objects.create(attempt=att2, question=wo_q, ordered_option_ids=[str(wo_opt2.id), str(wo_opt1.id)])
        Grade.objects.create(response=resp_wo, source="AUTO", points="0.00", graded_at=now)
        rec_wo.current_attempt = att2
        rec_wo.save(update_fields=["current_attempt"])

        # Add an IELTS student enrolled/assigned to an IELTS course
        ielts_student = create_student("Học sinh IELTS", "HS-IELTS-1", actor=self.owner)
        ielts_course = Course.objects.create(
            name="IELTS Foundation", category=Course.Category.IELTS, is_published=True, created_by=self.owner,
        )
        ielts_asg = Assignment.objects.create(
            version=self.version, title="IELTS Reading 1", code="ASG-IEL01", opens_at=now - timedelta(days=1),
            due_at=now + timedelta(days=2), late_until=now + timedelta(days=3), status="PUBLISHED",
        )
        CourseExercise.objects.create(course=ielts_course, assignment=ielts_asg, difficulty=3)
        rec_ielts = AssignmentRecipient.objects.create(assignment=ielts_asg, student=ielts_student)
        att_ielts = Attempt.objects.create(recipient=rec_ielts, attempt_no=1, status="GRADED", submitted_at=now)
        rec_ielts.current_attempt = att_ielts
        rec_ielts.save(update_fields=["current_attempt"])
        GradeRelease.objects.create(
            attempt=att_ielts, number=1, total_points="1.50", max_points="2.00", published_by=self.owner,
            snapshot={"responses": [{"skill": "READING", "points": "1.50", "max_points": "2.00", "difficulty": "STANDARD", "topics": [], "errors": []}]},
        )

        # 1. Default outside view renders only the concise sortable/paginated list
        general_resp = self.client.get("/teacher/reports/")
        self.assertEqual(general_resp.status_code, 200)
        general_html = general_resp.content.decode("utf-8")
        for label in (
            'data-sortable-table data-page-size="10"',
            "data-sort-col",
            "Học sinh",
            "Lớp",
            "Đã làm / Được giao",
            "Điểm trung bình",
            "Chi tiết",
            "Xem chi tiết",
            "2 / 3",
            "5,0/10",
            "Tiếng Anh 6A",
        ):
            self.assertIn(label, general_html)
        for hidden_outside in (
            "summary-grid",
            "tab-patterns",
            "Xếp hạng Lớp &amp; Khóa",
            "Bài sai nhiều nhất",
            "4 kỹ năng IELTS",
            "Reading",
            "Speaking",
        ):
            self.assertNotIn(hidden_outside, general_html)

        self.assertIn(f'href="/teacher/students/{self.student.id}/"', general_html)
        self.assertIn('type="search" name="q"', general_html)
        self.assertIn('id="report-filter-toggle"', general_html)
        self.assertIn('id="report-filter-drawer" hidden', general_html)
        self.assertNotIn('name="student_id"', general_html)

        # Filtering by search query q filters the concise list by name or student_ref
        search_resp = self.client.get("/teacher/reports/?q=HS-REP-01")
        self.assertEqual(search_resp.status_code, 200)
        search_html = search_resp.content.decode("utf-8")
        self.assertIn("Tiếng Anh 6A", search_html)
        self.assertNotIn("Học sinh IELTS", search_html)

        # Legacy ?student_id=... redirects directly to /teacher/students/<id>/
        redir_resp = self.client.get(f"/teacher/reports/?student_id={self.student.id}")
        self.assertRedirects(redir_resp, f"/teacher/students/{self.student.id}/", fetch_redirect_response=False)

        # Student detail page opens unified 1-panel tabbed evaluation with sortable/paginated tables, popup modal, and keyword analyzer
        detail_resp = self.client.get(f"/teacher/students/{self.student.id}/")
        self.assertEqual(detail_resp.status_code, 200)
        detail_html = detail_resp.content.decode("utf-8")
        for label in (
            "Quay lại danh sách học sinh",
            "Chi Tiết Học Tập",
            'id="modal-st-zalo"',
            'id="modal-st-classes"',
            'id="st-tab-english"',
            'id="st-tab-school"',
            'data-modal-open="modal-st-zalo"',
            'data-modal-open="modal-st-classes"',
            'data-modal-open="modal-st-code"',
            'data-modal-open="modal-st-profile"',
            'data-page-size="5" data-fixed-page-size="1"',
            "data-tab-group",
            'data-tab-target="tab-patterns"',
            'data-tab-target="tab-most-wrong"',
            'data-tab-target="tab-topics"',
            'data-tab-target="tab-formats"',
            'data-tab-target="tab-assignments"',
            'data-tab-target="tab-ranks"',
            'data-sortable-table data-page-size="5"',
            'id="student-keyword-analyzer"',
            'id="student-question-log-data"',
            'id="modal-student-qlog"',
            'id="qlog-pane-correct"',
            'id="qlog-pane-wrong"',
            'data-qlog-open="pattern"',
            'data-qlog-open="topic"',
            'data-qlog-open="qtype"',
            "Quá khứ đơn &amp; Động từ đuôi -ed / Bất quy tắc",
            "Câu bị động (Passive Voice)",
            "Bài sai nhiều nhất",
            "Tiếng Anh Tiểu học 4",
            "Sắp xếp từ thành câu",
            "Sắp xếp câu",
            "Grammar",
            "Bài ôn Sắp xếp câu bổ sung",
            "Bài Ranking",
            "Rời trang 1 lần &gt; 5s",
            "Hủy bài (VOID): Gian lận",
        ):
            self.assertIn(label, detail_html)
        self.assertNotIn("IELTS Reading 1", detail_html)
        self.assertNotIn("Đánh giá học tập toàn diện", detail_html)
        self.assertNotIn("Cần bù đắp:", detail_html)

        # 2. API reflects pattern_breakdown, most_wrong_assignments, category-aware recommendations, rankings, and student_assignments
        api_resp = self.client.get("/api/v1/owner/reports/progress/")
        self.assertEqual(api_resp.status_code, 200)
        payload = api_resp.json()["data"]
        stu_row = next(s for s in payload["students"] if s["student_id"] == str(self.student.id))
        self.assertEqual(stu_row["avg_score"], 5.0)
        self.assertEqual(stu_row["submitted"], 2)
        self.assertEqual(stu_row["assigned"], 3)
        self.assertEqual(stu_row["late_count"], 1)
        self.assertEqual(stu_row["missing_count"], 1)
        self.assertEqual(stu_row["cheat_count"], 2)
        self.assertEqual(len(stu_row["class_ranks"]), 2)
        self.assertEqual(stu_row["class_ranks"][0]["rank"], 1)
        self.assertEqual(len(stu_row["course_ranks"]), 1)
        self.assertEqual(stu_row["course_ranks"][0]["course_name"], "Tiếng Anh Tiểu học 4")
        self.assertEqual(stu_row["course_ranks"][0]["rank"], 1)
        self.assertEqual(len(stu_row["weak_question_types"]), 1)
        self.assertEqual(stu_row["weak_question_types"][0]["type"], "WORD_ORDER")
        self.assertEqual(stu_row["weak_question_types"][0]["recommended_exercises"][0]["title"], "Bài ôn Sắp xếp câu bổ sung")
        self.assertTrue(any(p["pattern"] == "Quá khứ đơn & Động từ đuôi -ed / Bất quy tắc" and p["wrong_percent"] == 100.0 for p in stu_row["pattern_breakdown"]))
        self.assertTrue(any(p["pattern"] == "Câu bị động (Passive Voice)" and p["total_count"] == 1 for p in stu_row["pattern_breakdown"]))
        self.assertEqual(len(stu_row["most_wrong_assignments"]), 1)
        self.assertEqual(stu_row["most_wrong_assignments"][0]["title"], "Luyện sắp xếp câu 1")
        self.assertEqual(stu_row["most_wrong_assignments"][0]["wrong_questions"], 1)
        self.assertEqual(stu_row["most_wrong_assignments"][0]["similar_exercises"][0]["title"], "Bài ôn Sắp xếp câu bổ sung")
        self.assertEqual(len(stu_row["student_assignments"]), 3)
        wo_asg_entry = next(item for item in stu_row["student_assignments"] if item["title"] == "Luyện sắp xếp câu 1")
        self.assertEqual(wo_asg_entry["status_code"], "late")
        self.assertEqual(wo_asg_entry["score_10"], 0.0)
        self.assertEqual(len(wo_asg_entry["cheat_reasons"]), 2)
        self.assertEqual(stu_row["evaluation_level"], "danger")
        self.assertFalse(stu_row["is_ielts"])
        self.assertTrue(any(w["topic"] == "Sắp xếp câu" and w["recommended_exercises"][0]["title"] == "Bài ôn Sắp xếp câu bổ sung" for w in stu_row["weak_areas"]))
        self.assertTrue(any(t["topic"] == "Grammar" and not t["is_weak"] for t in stu_row["topic_breakdown"]))
        wo_log = next(entry for entry in stu_row["question_log"] if entry["question_type"] == "WORD_ORDER")
        self.assertEqual(wo_log["question_type_label"], "Sắp xếp từ thành câu")
        self.assertEqual(wo_log["student_answer"], "was played Football")
        self.assertEqual(wo_log["correct_answer"], "Football was played")
        self.assertEqual(len(payload["ielts_students"]), 1)
        self.assertEqual(payload["ielts_students"][0]["student_id"], str(ielts_student.id))

        # 3. IELTS tab outside shows concise sortable IELTS list; clicking Xem chi tiết shows full IELTS tabbed breakdown
        ielts_resp = self.client.get("/teacher/reports/?view=ielts")
        self.assertEqual(ielts_resp.status_code, 200)
        ielts_html = ielts_resp.content.decode("utf-8")
        self.assertIn("Danh sách học sinh IELTS", ielts_html)
        self.assertIn('data-sortable-table data-page-size="10"', ielts_html)
        self.assertIn("Reading", ielts_html)
        self.assertIn("Speaking", ielts_html)
        self.assertIn("Học sinh IELTS", ielts_html)
        self.assertIn("IELTS Foundation", ielts_html)
        self.assertIn("Xem chi tiết", ielts_html)
        self.assertNotIn("Luyện sắp xếp câu 1", ielts_html)
        self.assertNotIn("tab-ranks", ielts_html)

        self.assertIn(f'href="/teacher/students/{ielts_student.id}/"', ielts_html)

        ielts_detail = self.client.get(f"/teacher/students/{ielts_student.id}/").content.decode("utf-8")
        self.assertIn("Tiến độ 4 kỹ năng IELTS", ielts_detail)
        self.assertIn('data-tab-target="tab-ranks"', ielts_detail)
        self.assertIn("IELTS Foundation", ielts_detail)
