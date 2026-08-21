from django.urls import path

from . import views


urlpatterns = [
    path(
        "",
        views.schedule_list,
        name="schedule_list",
    ),

    path(
        "create/",
        views.create_schedule,
        name="create_schedule",
    ),

    path(
        "<int:schedule_id>/",
        views.schedule_detail,
        name="schedule_detail",
    ),

    path(
        "<int:schedule_id>/cancel/",
        views.schedule_cancel,
        name="schedule_cancel",
    ),
]