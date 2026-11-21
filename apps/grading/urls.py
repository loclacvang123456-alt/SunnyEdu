from django.urls import path
from . import views

app_name = 'grading'
urlpatterns = [
    path('grading-queue/', views.queue, name='queue'),
    path('attempts/<uuid:attempt_id>/grading/', views.attempt_detail, name='attempt_detail'),
    path('responses/<uuid:response_id>/grade/', views.grade, name='grade'),
    path('responses/<uuid:response_id>/errors/', views.errors, name='errors'),
    path('errors/<uuid:occurrence_id>/teacher-review/', views.teacher_review, name='teacher_review'),
    path('attempts/<uuid:attempt_id>/publish-result/', views.publish, name='publish'),
    path('attempts/<uuid:attempt_id>/void/', views.void, name='void'),
]
