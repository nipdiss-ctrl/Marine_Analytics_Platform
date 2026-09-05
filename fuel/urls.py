from django.urls import path
from . import views


urlpatterns = [

    # =====================================================
    # MAIN FUEL PAGE / DATA CENTER
    # =====================================================

    path(
        "",
        views.data_center,
        name="data_center"
    ),


    # =====================================================
    # UPLOAD HISTORY
    # =====================================================

    path(
        "history/",
        views.upload_history,
        name="upload_history"
    ),


    # =====================================================
    # DELETE UPLOAD
    # =====================================================

    path(
        "delete/<int:id>/",
        views.delete_upload,
        name="delete_upload"
    ),


    # =====================================================
    # ANALYSIS PAGE
    # =====================================================

    path(
        "analysis/<int:id>/",
        views.upload_analysis,
        name="upload_analysis"
    ),


    # =====================================================
    # EXCEL DOWNLOAD
    # =====================================================

    path(
        "excel/<int:id>/",
        views.download_excel,
        name="download_excel"
    ),


    # =====================================================
    # PDF DOWNLOAD
    # =====================================================

    path(
        "pdf/<int:id>/",
        views.download_pdf,
        name="download_pdf"
    ),


    # =====================================================
    # FUTURE ANALYSIS
    # =====================================================

    path(
        "future-analysis/",
        views.future_analysis,
        name="future_analysis"
    ),


    # =====================================================
    # FUTURE ANALYSIS EXCEL
    # =====================================================

    path(
        "future-analysis/excel/",
        views.future_analysis_excel,
        name="future_analysis_excel"
    ),


    # =====================================================
    # FUTURE ANALYSIS GRAPH
    # =====================================================

    path(
        "future-analysis/graph/",
        views.future_analysis_graph,
        name="future_analysis_graph"
    ),

]