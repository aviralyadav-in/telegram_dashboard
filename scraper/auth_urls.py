from django.urls import path

from .views import (
    login_view,
    auth_me,
    logout_view,
)


urlpatterns = [

    path(
        "login/",
        login_view,
        name="auth-login"
    ),

    path(
        "me/",
        auth_me,
        name="auth-me"
    ),

    path(
        "logout/",
        logout_view,
        name="auth-logout"
    ),
]