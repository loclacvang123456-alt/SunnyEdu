from django.urls import path
from . import views

urlpatterns = [
    path("reports/progress/", views.progress_report, name="owner_api_progress"),
    path("reports/export.csv", views.progress_export_csv, name="owner_api_progress_export"),
    path("ranking-periods/", views.ranking_periods, name="owner_api_ranking_periods"),
    path("ranking-periods/<uuid:period_id>/", views.ranking_period_detail, name="owner_api_ranking_period_detail"),
    path("ranking-periods/<uuid:period_id>/activate/", views.ranking_activate, name="owner_api_ranking_activate"),
    path("ranking-periods/<uuid:period_id>/finalize/", views.ranking_finalize, name="owner_api_ranking_finalize"),
    path("ranking-periods/<uuid:period_id>/recompute-publish/", views.ranking_recompute_publish, name="owner_api_ranking_recompute"),
    path("ranking-periods/<uuid:period_id>/invalidate/", views.ranking_invalidate, name="owner_api_ranking_invalidate"),
]
