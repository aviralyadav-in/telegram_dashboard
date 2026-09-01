from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, logout

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from django.views.decorators.cache import never_cache

from .models import UserProfile
from .permissions import admin_required


# ============================================================
# LOGIN PAGE
# ============================================================

@never_cache
def login_page(request):

    # Already logged in -> dashboard
    if request.user.is_authenticated:
        return redirect("/")

    # Normal Django form login
    if request.method == "POST":

        username = request.POST.get(
            "username",
            ""
        ).strip()

        password = request.POST.get(
            "password",
            ""
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

        # Create Django session
        login(request, user)

        # Always go to dashboard.
        # Do NOT use ?next= after login.
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

    # ========================================================
    # CREATE DJANGO SESSION
    # ========================================================

    login(request, user)

    # ========================================================
    # CREATE JWT TOKENS
    # ========================================================

    refresh = RefreshToken.for_user(user)

    # ========================================================
    # ADMIN / USER ROLE
    # ========================================================

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

    # Keep profile role synchronized
    if is_admin and profile.role != "admin":

        profile.role = "admin"
        profile.save()

    elif not is_admin and profile.role != "user":

        profile.role = "user"
        profile.save()

    # ========================================================
    # RESPONSE
    # ========================================================

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
                    "admin"
                    if is_admin
                    else "user",
            }
        }
    )


# ============================================================
# LOGOUT API
# ============================================================

@api_view(["POST"])
@permission_classes([AllowAny])
def api_logout(request):

    # Destroy Django session
    logout(request)

    response = Response(
        {
            "message":
                "Logged out successfully."
        }
    )

    # Prevent cached authenticated response
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
@require_http_methods(["POST", "GET"])
def logout_page(request):

    # ========================================================
    # DESTROY DJANGO SESSION
    # ========================================================

    logout(request)

    # ========================================================
    # ALWAYS REDIRECT TO LOGIN
    # ========================================================

    response = redirect(
        "/accounts/login/"
    )

    # ========================================================
    # PREVENT BROWSER CACHE
    # ========================================================

    response["Cache-Control"] = (
        "no-cache, no-store, must-revalidate"
    )

    response["Pragma"] = "no-cache"

    response["Expires"] = "0"

    return response


# ============================================================
# CURRENT USER
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
                "admin"
                if is_admin
                else "user",

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
            user.save()

        profile, created = (
            UserProfile.objects.get_or_create(
                user=user,
                defaults={
                    "role":
                        role
                }
            )
        )

        if not created:

            profile.role = role
            profile.save()

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

        if password:

            user.set_password(
                password
            )

        if user.is_superuser:

            user.is_staff = True

        elif role == "admin":

            user.is_staff = True

        else:

            user.is_staff = False

        user.save()

        profile.role = (
            "admin"
            if user.is_staff
            or user.is_superuser
            else "user"
        )

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

    # Admin cannot delete himself
    if user.id == request.user.id:

        return redirect(
            "/accounts/users/"
        )

    user.delete()

    return redirect(
        "/accounts/users/"
    )
