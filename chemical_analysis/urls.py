from django.urls import path

from . import views
from .effectiveness_views import (
    effectiveness_report,
)

from .power_sfoc_views import (
    power_sfoc_analysis,
)


app_name = "chemical_analysis"


urlpatterns = [

    path(
        "",
        views.chemical_dashboard,
        name="dashboard",
    ),

    path(
        "performance/",
        views.performance_analysis,
        name="performance_analysis",
    ),

    path(
        "sfoc-power/",
        power_sfoc_analysis,
        name="power_sfoc",
    ),

    path(
        "effectiveness/",
        effectiveness_report,
        name="effectiveness",
    ),

    path(
        "upload/",
        views.upload_data,
        name="upload",
    ),

    path(
        "history/",
        views.import_history,
        name="history",
    ),

    path(
        "history/delete/<int:import_id>/",
        views.delete_import,
        name="delete_import",
    ),
]