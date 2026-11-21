from django.urls import path
from . import pronunciation_views

urlpatterns = [
    path('speaking/practice/', pronunciation_views.practice, name='speaking-practice'),
    path('api/v1/speaking/practice/check/', pronunciation_views.check, name='speaking-practice-check'),
]
