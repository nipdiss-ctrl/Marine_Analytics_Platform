from django.urls import path

from . import views

app_name = "scoc_monitoring"

urlpatterns = [
    path("upload/", views.upload_excel, name="upload_excel"),
    path("", views.dashboard, name="home"),
    path("overview/<int:vessel_id>/", views.import_result, name="import_result"),

    path("routes/", views.routes_home, name="routes_home"),
    path(
        "routes/<int:vessel_id>/<str:load_type>/",
        views.voyage_legs,
        name="voyage_legs",
    ),
    path(
        "routes/<int:vessel_id>/<str:load_type>/<str:performance_type>/",
        views.voyage_legs,
        name="voyage_legs",
    ),
    path("route/<int:leg_id>/", views.voyage_detail, name="voyage_detail"),
    path(
        "observation/<int:observation_id>/",
        views.observation_detail,
        name="observation_detail",
    ),

    path("vessels/", views.vessel_list, name="vessel_list"),
    path("vessels/add/", views.vessel_create, name="vessel_create"),
    path(
        "vessels/<int:vessel_id>/edit/",
        views.vessel_edit,
        name="vessel_edit",
    ),
]
