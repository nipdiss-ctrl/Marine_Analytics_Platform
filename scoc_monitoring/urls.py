from django.urls import path

from . import views


app_name = "scoc_monitoring"


urlpatterns = [

    # --------------------------------------------------------
    # Upload
    # --------------------------------------------------------

    path(
        "upload/",
        views.upload_excel,
        name="upload_excel",
    ),

    # --------------------------------------------------------
    # Overview
    # --------------------------------------------------------

    path(
        "",
        views.import_result,
        name="home",
    ),

    path(
        "overview/",
        views.import_result,
        name="import_result",
    ),

    # --------------------------------------------------------
    # Routes by load condition
    # --------------------------------------------------------

    path(
        "routes/<str:load_type>/",
        views.voyage_legs,
        name="voyage_legs",
    ),

    path(
        "routes/<str:load_type>/<str:performance_type>/",
        views.voyage_legs,
        name="voyage_legs",
    ),

    # --------------------------------------------------------
    # One route → daily observations
    # --------------------------------------------------------

    path(
        "voyage/<int:leg_id>/<str:performance_type>/",
        views.voyage_detail,
        name="voyage_detail",
    ),

    # --------------------------------------------------------
    # Old observation URL
    # --------------------------------------------------------

    path(
        "observation/<int:observation_id>/",
        views.observation_detail,
        name="observation_detail",
    ),
]