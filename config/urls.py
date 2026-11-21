from django.contrib import admin
from django.urls import include, path
from two_factor.admin import AdminSiteOTPRequiredMixin
from two_factor.urls import urlpatterns as tf_urls

from apps.accounts.auth_views import OwnerDisableView, OwnerLoginView, OwnerSetupView
from apps.core import course_views, views


class OwnerAdminSite(AdminSiteOTPRequiredMixin, admin.AdminSite):
    """Enforce OTP verification for Django admin access."""


if not isinstance(admin.site, OwnerAdminSite):
    admin.site.__class__ = OwnerAdminSite

urlpatterns = [
    path('', views.home, name='home'),
    path('courses/', course_views.catalog, name='course_catalog'),
    path('courses/<uuid:course_id>/', course_views.detail, name='course_detail'),
    path('student/', views.student_dashboard, name='student_dashboard'),
    path('student/assignments/<uuid:assignment_id>/', views.student_assignment, name='student_assignment'),
    path('student/assignments/<uuid:assignment_id>/result/', views.student_assignment_result, name='student_assignment_result'),
    path('logout/', views.sign_out, name='sign_out'),
    path('teacher/login/', OwnerLoginView.as_view(), name='owner_login'),
    path('account/login/', OwnerLoginView.as_view(), name='owner_account_login'),
    path('account/two_factor/setup/', OwnerSetupView.as_view(), name='owner_two_factor_setup'),
    path('account/two_factor/disable/', OwnerDisableView.as_view(), name='owner_two_factor_disable'),
    path('', include(tf_urls)),
    path('teacher/', include('apps.core.owner_urls')),
    path('admin/', admin.site.urls),
    path('', include('apps.accounts.urls')),
    path('', include('apps.grading.pronunciation_urls')),
    path('api/v1/', include('apps.assignments.urls')),
    path('api/v1/', include('apps.grading.writing_urls')),
    path('api/v1/', include('apps.content.image_upload_urls')),
    path('api/v1/owner/', include('apps.accounts.owner_urls')),
    path('api/v1/owner/', include('apps.classes.urls')),
    path('api/v1/owner/', include('apps.content.urls')),
    path('api/v1/owner/', include('apps.assignments.owner_urls')),
    path('api/v1/owner/', include('apps.grading.urls')),
    path('api/v1/owner/', include('apps.reporting.urls')),
]
