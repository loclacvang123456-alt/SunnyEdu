from django.urls import path
from . import views
urlpatterns = [
    path('assignments/', views.assignments),
    path('assignments/<uuid:assignment_id>/start/', views.start),
    path('attempts/<uuid:attempt_id>/submit/', views.submit),
    path('attempts/<uuid:attempt_id>/visibility/', views.record_visibility),
    path('attempts/<uuid:attempt_id>/reset/', views.reset_practice_game),
    path('attempts/<uuid:attempt_id>/', views.attempt_detail),
    path('attempts/<uuid:attempt_id>/responses/<uuid:question_id>/shot/', views.fire_shot),
    path('attempts/<uuid:attempt_id>/responses/<uuid:question_id>/', views.save),
]

