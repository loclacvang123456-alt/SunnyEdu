from django.urls import include, path

urlpatterns = [path('api/v1/owner/', include('apps.grading.urls'))]
