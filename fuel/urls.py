from django.urls import path
from . import views


urlpatterns = [

    # Main fuel page
    path(
        "",
        views.data_center,
        name="data_center"
    ),


    # Upload history
    path(
        "history/",
        views.upload_history,
        name="upload_history"
    ),


    # Delete upload
    path(
        "delete/<int:id>/",
        views.delete_upload,
        name="delete_upload"
    ),


    # Analysis page
    path(
        "analysis/<int:id>/",
        views.upload_analysis,
        name="upload_analysis"
    ),


    # Excel download
    path(
        "excel/<int:id>/",
        views.download_excel,
        name="download_excel"
    ),


    # PDF download
    path(
        "pdf/<int:id>/",
        views.download_pdf,
        name="download_pdf"
    ),

]