from django.urls import path
from . import views

urlpatterns = [
    path("schools/", views.schools, name="owner_api_schools"),
    path("schools/<uuid:school_id>/archive/", views.school_archive, name="owner_api_school_archive"),
    path("school-classes/", views.school_classes, name="owner_api_school_classes"),
    path("school-classes/<uuid:class_id>/archive/", views.school_class_archive, name="owner_api_school_class_archive"),
    path("english-classes/", views.english_classes, name="owner_api_english_classes"),
    path("english-classes/<uuid:class_id>/archive/", views.english_class_archive, name="owner_api_english_class_archive"),
    path("students/<uuid:student_id>/school-transfer/", views.school_transfer, name="owner_api_school_transfer"),
    path("english-classes/<uuid:class_id>/members/", views.english_members, name="owner_api_english_members"),
    path("english-classes/<uuid:class_id>/members/<uuid:student_id>/leave/", views.english_member_leave, name="owner_api_english_member_leave"),
]
