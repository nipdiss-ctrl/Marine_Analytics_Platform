from django.urls import path
from . import views


urlpatterns = [

    path(
        "",
        views.launcher,
        name="launcher"
    ),

]