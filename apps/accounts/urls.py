from django.urls import path
from . import views

app_name = "accounts"
urlpatterns = [
    path("login/", views.student_login_page, name="student_login"),
    path("api/v1/auth/csrf/", views.csrf, name="csrf"),
    path("api/v1/auth/student-login/", views.student_login, name="student_login_api"),
    path("api/v1/auth/logout/", views.student_logout, name="logout"),
    path("api/v1/me/", views.me, name="me"),
]
