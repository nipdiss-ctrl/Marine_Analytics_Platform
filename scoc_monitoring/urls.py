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
        views.dashboard,
        name="home",
    ),

    #(
       # "",
      #  views.import_result,
       # name="home",
    #),
    path(
        "overview/<int:vessel_id>/",
        views.import_result,
        name="import_result",
    ),

    # --------------------------------------------------------
    # Routes by load condition
    # --------------------------------------------------------
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
   

    # --------------------------------------------------------
    # One route → daily observations
    # --------------------------------------------------------

    path(
        "route/<int:leg_id>/",
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