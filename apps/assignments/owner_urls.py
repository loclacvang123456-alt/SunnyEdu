from django.urls import path
from . import owner_views

urlpatterns = [
    path("assignments/", owner_views.assignments, name="owner_api_assignments"),
    path("assignments/<uuid:assignment_id>/", owner_views.assignment_detail, name="owner_api_assignment_detail"),
    path("assignments/<uuid:assignment_id>/publish/", owner_views.assignment_publish, name="owner_api_assignment_publish"),
    path("assignments/<uuid:assignment_id>/extend/", owner_views.assignment_extend, name="owner_api_assignment_extend"),
    path("assignments/<uuid:assignment_id>/cancel/", owner_views.assignment_cancel, name="owner_api_assignment_cancel"),
    path("assignments/<uuid:assignment_id>/recipients/", owner_views.assignment_recipients, name="owner_api_assignment_recipients"),
    path("assignments/<uuid:assignment_id>/release-answers/", owner_views.assignment_release_answers, name="owner_api_assignment_release_answers"),
    path("recipients/<uuid:recipient_id>/exempt/", owner_views.recipient_exempt, name="owner_api_recipient_exempt"),
    path("recipients/<uuid:recipient_id>/retake/", owner_views.recipient_retake, name="owner_api_recipient_retake"),
]
