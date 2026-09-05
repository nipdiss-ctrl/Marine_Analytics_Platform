from django.contrib import admin
from django.urls import include, path


urlpatterns = [

    path(
        "admin/",
        admin.site.urls,
    ),

    path(
        "core/",
        include("core.urls"),
    ),

    path(
        "",
        include("accounts.urls"),
    ),

    path(
        "fuel/",
        include("fuel.urls"),
    ),

    # Main platform dashboard
    path(
        "dashboard/",
        include("dashboard.urls"),
    ),

    # RightShip / inspection module
    path(
        "rightship/",
        include("inspections.urls"),
    ),

    # Chemical analysis project
    path(
        "chemical_analysis/",
        include("chemical_analysis.urls"),
    ),

    # SCoC Monitoring
    path(
        "scoc/",
        include("scoc_monitoring.urls"),
    ),
]