import threading
import secrets
from django.contrib.auth.decorators import login_required

from django.shortcuts import render
from django.contrib.auth import authenticate
from django.contrib.auth.models import User

from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

from .scraper_service import (
    run_scraper,
    stop_scraper,
    get_status,
)


# =========================================================
# TEMPORARY LOGIN SESSIONS
# =========================================================

sessions = {}


# =========================================================
# SCRAPING PAGE
# =========================================================
@login_required
def scraping_page(request):
    return render(
        request,
        "scraper/scraping.html"
    )


# =========================================================
# LOGIN
# =========================================================

@api_view(["POST"])
def login_view(request):

    email = request.data.get("email")
    password = request.data.get("password")

    if not email or not password:
        return Response(
            {
                "error": "Email and password are required"
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    email = str(email).strip()

    try:
        user = User.objects.get(
            email__iexact=email
        )

    except User.DoesNotExist:
        return Response(
            {
                "error": "Invalid email or password"
            },
            status=status.HTTP_401_UNAUTHORIZED
        )

    authenticated_user = authenticate(
        username=user.username,
        password=password
    )

    if authenticated_user is None:
        return Response(
            {
                "error": "Invalid email or password"
            },
            status=status.HTTP_401_UNAUTHORIZED
        )

    token = secrets.token_hex(32)

    sessions[token] = user.id

    role = (
        "admin"
        if user.is_staff or user.is_superuser
        else "user"
    )

    return Response(
        {
            "message": "Login successful",
            "token": token,
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "is_staff": user.is_staff,
                "is_superuser": user.is_superuser,
                "role": role,
            },
        },
        status=status.HTTP_200_OK
    )


# =========================================================
# CURRENT USER
# =========================================================

@api_view(["GET"])
def auth_me(request):

    auth_header = request.headers.get(
        "Authorization",
        ""
    )

    if not auth_header.startswith("Bearer "):
        return Response(
            {
                "error": "Authentication required"
            },
            status=status.HTTP_401_UNAUTHORIZED
        )

    token = auth_header.replace(
        "Bearer ",
        "",
        1
    ).strip()

    user_id = sessions.get(token)

    if not user_id:
        return Response(
            {
                "error": "Invalid or expired token"
            },
            status=status.HTTP_401_UNAUTHORIZED
        )

    try:
        user = User.objects.get(
            id=user_id
        )

    except User.DoesNotExist:

        sessions.pop(
            token,
            None
        )

        return Response(
            {
                "error": "User not found"
            },
            status=status.HTTP_401_UNAUTHORIZED
        )

    role = (
        "admin"
        if user.is_staff or user.is_superuser
        else "user"
    )

    return Response(
        {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "is_staff": user.is_staff,
            "is_superuser": user.is_superuser,
            "role": role,
        },
        status=status.HTTP_200_OK
    )


# =========================================================
# LOGOUT
# =========================================================

@api_view(["POST"])
def logout_view(request):

    auth_header = request.headers.get(
        "Authorization",
        ""
    )

    if auth_header.startswith("Bearer "):

        token = auth_header.replace(
            "Bearer ",
            "",
            1
        ).strip()

        sessions.pop(
            token,
            None
        )

    return Response(
        {
            "message": "Logout successful"
        },
        status=status.HTTP_200_OK
    )


# =========================================================
# START SCRAPING
# =========================================================

@api_view(["POST"])
def start_scraping(request):

    channel = request.data.get("channel")
    limit = request.data.get("limit", 10)

    # -----------------------------------------------------
    # CHANNEL VALIDATION
    # -----------------------------------------------------

    if not channel:

        return Response(
            {
                "error": "Telegram channel is required"
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    channel = str(channel).strip()

    if not channel:

        return Response(
            {
                "error": "Telegram channel cannot be empty"
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    # Remove https://t.me/ if user enters full URL
    if "t.me/" in channel:

        channel = channel.rstrip("/").split(
            "t.me/"
        )[-1]

    if channel.startswith("@"):

        channel = channel[1:]

    if not channel:

        return Response(
            {
                "error": "Invalid Telegram channel"
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    # -----------------------------------------------------
    # LIMIT VALIDATION
    # -----------------------------------------------------

    try:

        limit = int(limit)

    except (ValueError, TypeError):

        return Response(
            {
                "error": "Number of messages must be a number"
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    if limit < 1 or limit > 100:

        return Response(
            {
                "error": "Number of messages must be between 1 and 100"
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    # -----------------------------------------------------
    # CHECK CURRENT STATUS
    # -----------------------------------------------------

    try:

        current_status = get_status()

    except Exception as error:

        return Response(
            {
                "error": str(error)
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    current_state = current_status.get(
        "status",
        "idle"
    )

    if current_state in {
        "starting",
        "running",
        "stopping"
    }:

        return Response(
            {
                "error": "Scraper is already running",
                "status": current_status
            },
            status=status.HTTP_409_CONFLICT
        )

    # -----------------------------------------------------
    # START BACKGROUND SCRAPER
    # -----------------------------------------------------

    def background_job():

        try:

            run_scraper(
                channel,
                limit
            )

        except Exception as error:

            print(
                "Scraper background error:",
                error
            )

    thread = threading.Thread(
        target=background_job,
        daemon=True
    )

    thread.start()

    return Response(
        {
            "message": "Scraping started successfully",
            "channel": channel,
            "limit": limit
        },
        status=status.HTTP_202_ACCEPTED
    )


# =========================================================
# STOP SCRAPING
# =========================================================

@api_view(["POST"])
def stop_scraping(request):

    try:

        current_status = get_status()

        current_state = current_status.get(
            "status"
        )

        if current_state not in {
            "starting",
            "running"
        }:

            return Response(
                {
                    "message": "Scraper is not currently running",
                    "status": current_status
                },
                status=status.HTTP_200_OK
            )

        result = stop_scraper()

        return Response(
            result,
            status=status.HTTP_200_OK
        )

    except Exception as error:

        return Response(
            {
                "error": str(error)
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# =========================================================
# SCRAPING STATUS
# =========================================================

@api_view(["GET"])
def scraping_status(request):

    try:

        result = get_status()

        return Response(
            result,
            status=status.HTTP_200_OK
        )

    except Exception as error:

        return Response(
            {
                "error": str(error)
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )