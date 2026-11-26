from django.urls import path
from . import views

urlpatterns = [
    path("exams", views.exams, name="owner-exams"),
    path("exams/quick-search", views.quick_search_exam_versions, name="owner-exams-quick-search"),
    path("exams/<uuid:exam_id>", views.exam_detail, name="owner-exam-detail"),
    path("exams/<uuid:exam_id>/archive", views.exam_archive, name="owner-exam-archive"),
    path("exams/<uuid:exam_id>/versions", views.exam_versions, name="owner-exam-versions"),
    path("versions/<uuid:version_id>", views.version_detail, name="owner-version-detail"),
    path("versions/<uuid:version_id>/clone", views.version_clone, name="owner-version-clone"),
    path("versions/<uuid:version_id>/archive", views.version_archive, name="owner-version-archive"),
    path("versions/<uuid:version_id>/publish", views.version_publish, name="owner-version-publish"),
    path("versions/<uuid:version_id>/passages", views.version_passages, name="owner-version-passages"),
    path("passages/<uuid:passage_id>", views.passage_detail, name="owner-passage-detail"),
    path("versions/<uuid:version_id>/questions", views.version_questions, name="owner-version-questions"),
    path("questions/<uuid:question_id>", views.question_detail, name="owner-question-detail"),
    path("tags", views.tags, name="owner-tags"),
    path("tags/<uuid:tag_id>/archive", views.tag_archive, name="owner-tag-archive"),
    path("assets", views.assets, name="owner-assets"),
    path("assets/<uuid:asset_id>/content", views.asset_content, name="owner-asset-content"),
    path("imports/preview", views.import_preview, name="owner-import-preview"),
    path("imports/batch-preview", views.batch_import_preview, name="owner-batch-import-preview"),
    path("imports/batch-commit", views.batch_import_commit, name="owner-batch-import-commit"),
    path("imports/<uuid:batch_id>", views.import_detail, name="owner-import-detail"),
    path("imports/<uuid:batch_id>/commit", views.import_commit, name="owner-import-commit"),
]
