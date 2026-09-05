from django.urls import path

from . import views


urlpatterns = [

    # =====================================================
    # VESSELS
    # =====================================================

    path(
        "vessels/",
        views.vessel_list,
        name="vessel_list",
    ),

    path(
        "vessels/create/",
        views.vessel_create,
        name="vessel_create",
    ),

    path(
        "vessels/<int:pk>/edit/",
        views.vessel_edit,
        name="vessel_edit",
    ),

    path(
        "vessels/<int:pk>/delete/",
        views.vessel_delete,
        name="vessel_delete",
    ),

    # =====================================================
    # INSPECTIONS
    # =====================================================

    path(
        "",
        views.inspection_list,
        name="inspection_list",
    ),

    path(
        "create/",
        views.inspection_create,
        name="inspection_create",
    ),

    path(
        "<int:pk>/findings/",
        views.inspection_findings,
        name="inspection_findings",
    ),

    path(
        "<int:inspection_id>/findings/create/",
        views.finding_create,
        name="finding_create",
    ),

    # =====================================================
    # CHECKLIST
    # =====================================================

    path(
        "checklist-items/new/",
        views.checklistitem_create,
        name="checklistitem_create",
    ),

    path(
        "checklist-items/",
        views.checklistitem_list,
        name="checklistitem_list",
    ),

    # =====================================================
    # IMPORT
    # =====================================================

    path(
        "import/",
        views.inspection_import,
        name="inspection_import",
    ),

    # =====================================================
    # RISK
    # =====================================================

    path(
        "finding/<int:pk>/edit-risk/",
        views.finding_edit_risk,
        name="finding_edit_risk",
    ),


    path(
        "finding/<int:pk>/delete/",
        views.finding_delete,
        name="finding_delete",
    ),

    # =====================================================
    # RIGHTSHIP DASHBOARD
    # =====================================================

    path(
        "dashboard/",
        views.rightship_dashboard,
        name="rightship_dashboard",
    ),

]