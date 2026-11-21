from django.urls import path
from . import writing_views

urlpatterns = [
    path('writing/responses/<uuid:response_id>/check/', writing_views.check, name='writing-check'),
]
