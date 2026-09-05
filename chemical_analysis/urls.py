from django.urls import path

from . import views


app_name = "chemical_analysis"


urlpatterns = [

    # -----------------------------------------------------
    # DASHBOARD
    # -----------------------------------------------------

    path(
        "",
        views.chemical_dashboard,
        name="dashboard"
    ),

        # -----------------------------------------------------
    # PERFORMANCE ANALYSIS
    # -----------------------------------------------------

    path(
        "performance/",
        views.performance_analysis,
        name="performance_analysis"
    ),
    
    # -----------------------------------------------------
    # UPLOAD
    # -----------------------------------------------------

    path(
        "upload/",
        views.upload_data,
        name="upload"
    ),

    # -----------------------------------------------------
    # IMPORT HISTORY
    # -----------------------------------------------------

    path(
        "history/",
        views.import_history,
        name="history"
    ),

    path(
    "history/delete/<int:import_id>/",
    views.delete_import,
    name="delete_import"
),

]