from django.urls import path
from . import image_upload_views

urlpatterns = [
    path('owner/image-assets/<uuid:asset_id>/content/', image_upload_views.owner_image, name='owner-image-preview'),
    path('owner/image-assets/', image_upload_views.upload_image, name='owner-image-upload'),
    path('attempts/<uuid:attempt_id>/images/<uuid:image_id>/', image_upload_views.student_image, name='student-match-image'),
]
