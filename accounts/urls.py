from django.urls import path

from .views import (
    login_page,
    api_login,
    api_logout,
    api_me,
    profile_page,
    update_profile,
    logout_page,
    users_page,
    add_user,
    edit_user,
    delete_user,
)


urlpatterns = [

    path(
        "login/",
        login_page,
        name="login"
    ),
 # LOGOUT
    # ============================================================

    path(
        "logout/",
        logout_page,
        name="logout"
    ),

    path(
        "api/login/",
        api_login,
        name="api-login"
    ),

    path(
        "api/logout/",
        api_logout,
        name="api-logout"
    ),

    path(
        "api/me/",
        api_me,
        name="api-me"
    ),

    path(
        "profile/",
        profile_page,
        name="profile"
    ),

    path(
        "profile/update/",
        update_profile,
        name="profile-update"
    ),

    path(
        "users/",
        users_page,
        name="users"
    ),

    path(
        "users/add/",
        add_user,
        name="add-user"
    ),

    path(
        "users/<int:user_id>/edit/",
        edit_user,
        name="edit-user"
    ),

    path(
        "users/<int:user_id>/delete/",
        delete_user,
        name="delete-user"
    ),
]