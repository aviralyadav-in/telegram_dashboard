from django.urls import path
from django.contrib.auth.views import LoginView

from .views import logout_view


urlpatterns = [

    path(
        "login/",
        LoginView.as_view(
            template_name="registration/login.html"
        ),
        name="login",
    ),

    path(
        "logout/",
        logout_view,
        name="logout",
    ),

]