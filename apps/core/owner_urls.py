from django.urls import path
from . import owner_course_views, owner_report_views, owner_teaching_views, owner_views

urlpatterns = [
    path("", owner_views.dashboard, name="owner_dashboard"),
    path("students/", owner_views.students, name="owner_students"),
    path("students/template/", owner_views.student_import_template, name="owner_student_template"),
    path("students/<uuid:student_id>/", owner_views.student_detail, name="owner_student_detail"),
    path("courses/", owner_course_views.courses, name="owner_courses"),
    path("courses/<uuid:course_id>/", owner_course_views.course_detail, name="owner_course_detail"),
    path("exams/", owner_teaching_views.exams, name="owner_exams"),
    path("exams/import/", owner_teaching_views.exam_import, name="owner_exam_import"),
    path("exams/<uuid:exam_id>/versions/<uuid:version_id>/", owner_teaching_views.version_editor, name="owner_version_editor"),
    path("exams/<uuid:exam_id>/versions/<uuid:version_id>/preview/", owner_teaching_views.version_preview, name="owner_version_preview"),
    path("assignments/", owner_teaching_views.assignments, name="owner_assignments"),
    path("assignments/new/", owner_teaching_views.assignment_new, name="owner_assignment_new"),
    path("assignments/<uuid:assignment_id>/", owner_teaching_views.assignment_detail, name="owner_assignment_detail"),
    path("grading/", owner_teaching_views.grading_queue, name="owner_grading_queue"),
    path("grading/<uuid:attempt_id>/", owner_teaching_views.grading_detail, name="owner_grading_detail"),
    path("reports/", owner_report_views.reports, name="owner_reports"),
    path("rankings/", owner_report_views.rankings, name="owner_rankings"),
    path("rankings/new/", owner_report_views.ranking_new, name="owner_ranking_new"),
    path("rankings/<uuid:period_id>/", owner_report_views.ranking_detail, name="owner_ranking_detail"),
    path("settings/", owner_views.settings_view, name="owner_settings"),
]
