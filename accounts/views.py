from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, logout
from django.views.decorators.cache import never_cache

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from .models import UserProfile
from .permissions import admin_required


# ============================================================
# LOGIN PAGE
# ============================================================

@never_cache
@require_http_methods(["GET", "POST"])
def login_page(request):

    # --------------------------------------------------------
    # Already logged in
    # --------------------------------------------------------

    if request.user.is_authenticated:
        return redirect("/")

    # --------------------------------------------------------
    # LOGIN
    # --------------------------------------------------------

    if request.method == "POST":

        username = request.POST.get(
            "username",
            ""
        ).strip()

        password = request.POST.get(
            "password",
            ""
        )

        if not username or not password:

            return render(
                request,
                "registration/login.html",
                {
                    "error":
                        "Username and password are required."
                }
            )

        user = authenticate(
            request,
            username=username,
            password=password
        )

        if user is None:

            return render(
                request,
                "registration/login.html",
                {
                    "error":
                        "Invalid username or password."
                }
            )

        if not user.is_active:

            return render(
                request,
                "registration/login.html",
                {
                    "error":
                        "Your account is inactive."
                }
            )

        # ----------------------------------------------------
        # CREATE DJANGO SESSION
        # ----------------------------------------------------

        login(request, user)

        # ----------------------------------------------------
        # ALWAYS DASHBOARD
        # ----------------------------------------------------

        return redirect("/")

    response = render(
        request,
        "registration/login.html"
    )

    response["Cache-Control"] = (
        "no-cache, no-store, must-revalidate"
    )
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"

    return response


# ============================================================
# JWT LOGIN API
# ============================================================

@api_view(["POST"])
@permission_classes([AllowAny])
def api_login(request):

    username = request.data.get(
        "username"
    )

    password = request.data.get(
        "password"
    )

    if not username or not password:

        return Response(
            {
                "error":
                    "Username and password are required."
            },
            status=400
        )

    user = authenticate(
        request,
        username=username,
        password=password
    )

    if user is None:

        return Response(
            {
                "error":
                    "Invalid username or password."
            },
            status=401
        )

    if not user.is_active:

        return Response(
            {
                "error":
                    "This account is inactive."
            },
            status=403
        )

    # --------------------------------------------------------
    # CREATE DJANGO SESSION
    # --------------------------------------------------------

    login(request, user)

    # --------------------------------------------------------
    # CREATE JWT
    # --------------------------------------------------------

    refresh = RefreshToken.for_user(user)

    # --------------------------------------------------------
    # ROLE
    # --------------------------------------------------------

    is_admin = (
        user.is_staff
        or user.is_superuser
    )

    profile, created = (
        UserProfile.objects.get_or_create(
            user=user,
            defaults={
                "role":
                    "admin"
                    if is_admin
                    else "user"
            }
        )
    )

    # Keep role synchronized

    expected_role = (
        "admin"
        if is_admin
        else "user"
    )

    if profile.role != expected_role:

        profile.role = expected_role
        profile.save(
            update_fields=["role"]
        )

    # --------------------------------------------------------
    # RESPONSE
    # --------------------------------------------------------

    return Response(
        {
            "message":
                "Login successful.",

            "access":
                str(refresh.access_token),

            "refresh":
                str(refresh),

            "user": {

                "id":
                    user.id,

                "username":
                    user.username,

                "email":
                    user.email,

                "first_name":
                    user.first_name,

                "last_name":
                    user.last_name,

                "is_staff":
                    user.is_staff,

                "is_superuser":
                    user.is_superuser,

                "role":
                    expected_role,
            }
        }
    )


# ============================================================
# JWT LOGOUT API
# ============================================================

@api_view(["POST"])
@permission_classes([AllowAny])
def api_logout(request):

    # --------------------------------------------------------
    # BLACKLIST REFRESH TOKEN IF PROVIDED
    # --------------------------------------------------------

    refresh_token = request.data.get(
        "refresh"
    )

    if refresh_token:

        try:

            token = RefreshToken(
                refresh_token
            )

            token.blacklist()

        except Exception:
            # Token may already be expired/blacklisted.
            # Logout should still continue.
            pass

    # --------------------------------------------------------
    # DESTROY DJANGO SESSION TOO
    # --------------------------------------------------------

    logout(request)

    response = Response(
        {
            "message":
                "Logged out successfully."
        }
    )

    # --------------------------------------------------------
    # PREVENT CACHE
    # --------------------------------------------------------

    response["Cache-Control"] = (
        "no-cache, no-store, must-revalidate"
    )

    response["Pragma"] = "no-cache"
    response["Expires"] = "0"

    return response


# ============================================================
# LOGOUT PAGE
# ============================================================

@never_cache
@require_http_methods(["GET", "POST"])
def logout_page(request):

    # --------------------------------------------------------
    # DESTROY DJANGO SESSION
    # --------------------------------------------------------

    logout(request)

    # --------------------------------------------------------
    # REDIRECT LOGIN
    # --------------------------------------------------------

    response = redirect(
        "/accounts/login/"
    )

    # --------------------------------------------------------
    # PREVENT BACK-CACHE
    # --------------------------------------------------------

    response["Cache-Control"] = (
        "no-cache, no-store, must-revalidate"
    )

    response["Pragma"] = "no-cache"

    response["Expires"] = "0"

    return response


# ============================================================
# CURRENT USER API
# ============================================================

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_me(request):

    user = request.user

    is_admin = (
        user.is_staff
        or user.is_superuser
    )

    profile, created = (
        UserProfile.objects.get_or_create(
            user=user,
            defaults={
                "role":
                    "admin"
                    if is_admin
                    else "user"
            }
        )
    )

    expected_role = (
        "admin"
        if is_admin
        else "user"
    )

    if profile.role != expected_role:

        profile.role = expected_role
        profile.save(
            update_fields=["role"]
        )

    return Response(
        {
            "id":
                user.id,

            "username":
                user.username,

            "email":
                user.email,

            "first_name":
                user.first_name,

            "last_name":
                user.last_name,

            "role":
                expected_role,

            "is_staff":
                user.is_staff,

            "is_superuser":
                user.is_superuser,

            "phone":
                profile.phone,

            "designation":
                profile.designation,
        }
    )


# ============================================================
# PROFILE PAGE
# ============================================================

@never_cache
@login_required
def profile_page(request):

    user = request.user

    profile, created = (
        UserProfile.objects.get_or_create(
            user=user,
            defaults={
                "role":
                    "admin"
                    if user.is_staff
                    or user.is_superuser
                    else "user"
            }
        )
    )

    return render(
        request,
        "accounts/profile.html",
        {
            "profile":
                profile,

            "user_obj":
                user,

            "is_admin":
                (
                    user.is_staff
                    or user.is_superuser
                )
        }
    )


# ============================================================
# PROFILE UPDATE
# ============================================================

@login_required
@require_http_methods(["POST"])
def update_profile(request):

    user = request.user

    profile, created = (
        UserProfile.objects.get_or_create(
            user=user,
            defaults={
                "role":
                    "admin"
                    if user.is_staff
                    or user.is_superuser
                    else "user"
            }
        )
    )

    user.first_name = request.POST.get(
        "first_name",
        ""
    ).strip()

    user.last_name = request.POST.get(
        "last_name",
        ""
    ).strip()

    user.email = request.POST.get(
        "email",
        ""
    ).strip()

    profile.phone = request.POST.get(
        "phone",
        ""
    ).strip()

    profile.designation = request.POST.get(
        "designation",
        ""
    ).strip()

    user.save()
    profile.save()

    return redirect(
        "/accounts/profile/"
    )


# ============================================================
# ADMIN - USERS PAGE
# ============================================================

@admin_required
def users_page(request):

    users = (
        User.objects
        .select_related("profile")
        .order_by("-date_joined")
    )

    return render(
        request,
        "accounts/users.html",
        {
            "users":
                users
        }
    )


# ============================================================
# ADMIN - ADD USER
# ============================================================

@admin_required
@require_http_methods(["GET", "POST"])
def add_user(request):

    if request.method == "POST":

        username = request.POST.get(
            "username",
            ""
        ).strip()

        email = request.POST.get(
            "email",
            ""
        ).strip()

        password = request.POST.get(
            "password",
            ""
        )

        first_name = request.POST.get(
            "first_name",
            ""
        ).strip()

        last_name = request.POST.get(
            "last_name",
            ""
        ).strip()

        role = request.POST.get(
            "role",
            "user"
        )

        if role not in ["admin", "user"]:

            role = "user"

        if not username or not password:

            return render(
                request,
                "accounts/user_form.html",
                {
                    "error":
                        "Username and password are required.",

                    "form_title":
                        "Add User"
                }
            )

        if User.objects.filter(
            username=username
        ).exists():

            return render(
                request,
                "accounts/user_form.html",
                {
                    "error":
                        "Username already exists.",

                    "form_title":
                        "Add User"
                }
            )

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name
        )

        if role == "admin":

            user.is_staff = True
            user.save(
                update_fields=["is_staff"]
            )

        UserProfile.objects.update_or_create(
            user=user,
            defaults={
                "role":
                    role
            }
        )

        return redirect(
            "/accounts/users/"
        )

    return render(
        request,
        "accounts/user_form.html",
        {
            "form_title":
                "Add User"
        }
    )


# ============================================================
# ADMIN - EDIT USER
# ============================================================

@admin_required
@require_http_methods(["GET", "POST"])
def edit_user(request, user_id):

    user = get_object_or_404(
        User,
        id=user_id
    )

    profile, created = (
        UserProfile.objects.get_or_create(
            user=user,
            defaults={
                "role":
                    "admin"
                    if user.is_staff
                    or user.is_superuser
                    else "user"
            }
        )
    )

    if request.method == "POST":

        user.email = request.POST.get(
            "email",
            ""
        ).strip()

        user.first_name = request.POST.get(
            "first_name",
            ""
        ).strip()

        user.last_name = request.POST.get(
            "last_name",
            ""
        ).strip()

        role = request.POST.get(
            "role",
            "user"
        )

        password = request.POST.get(
            "password",
            ""
        )

        if role not in ["admin", "user"]:

            role = "user"

        if password:

            user.set_password(
                password
            )

        # Superuser must remain admin

        if user.is_superuser:

            user.is_staff = True
            final_role = "admin"

        elif role == "admin":

            user.is_staff = True
            final_role = "admin"

        else:

            user.is_staff = False
            final_role = "user"

        user.save()

        profile.role = final_role
        profile.save()

        return redirect(
            "/accounts/users/"
        )

    return render(
        request,
        "accounts/user_form.html",
        {
            "form_title":
                "Edit User",

            "edit_user":
                user,

            "profile":
                profile
        }
    )


# ============================================================
# ADMIN - DELETE USER
# ============================================================

@admin_required
@require_http_methods(["POST"])
def delete_user(request, user_id):

    user = get_object_or_404(
        User,
        id=user_id
    )

    # --------------------------------------------------------
    # ADMIN CANNOT DELETE HIMSELF
    # --------------------------------------------------------

    if user.id == request.user.id:

        return redirect(
            "/accounts/users/"
        )

    user.delete()

    return redirect(
        "/accounts/users/"
    )