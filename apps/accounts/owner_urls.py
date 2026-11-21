from django.urls import path
from . import owner_views

urlpatterns = [
    path("students/", owner_views.students, name="owner_api_students"),
    path("students/template/", owner_views.student_import_template, name="owner_api_student_template"),
    path("students/<uuid:student_id>/", owner_views.student_detail, name="owner_api_student_detail"),
    path("students/<uuid:student_id>/rotate-code/", owner_views.student_rotate_code, name="owner_api_student_rotate_code"),
    path("students/<uuid:student_id>/revoke-sessions/", owner_views.student_revoke_sessions, name="owner_api_student_revoke_sessions"),
    path("students/<uuid:student_id>/progress/", owner_views.student_progress, name="owner_api_student_progress"),
    path("privacy-requests/", owner_views.privacy_requests, name="owner_api_privacy_requests"),
    path("privacy-requests/<uuid:request_id>/", owner_views.privacy_request_detail, name="owner_api_privacy_request_detail"),
    path("privacy-requests/<uuid:request_id>/approve/", owner_views.privacy_request_approve, name="owner_api_privacy_request_approve"),
    path("privacy-requests/<uuid:request_id>/export/", owner_views.privacy_request_export, name="owner_api_privacy_request_export"),
]
