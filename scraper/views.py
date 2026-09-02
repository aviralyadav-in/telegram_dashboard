import json
import threading

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.cache import never_cache

from .scraper_service import (
    run_scraper,
    get_status,
    stop_scraper,
)


# ============================================================
# SCRAPING PAGE
# ============================================================

@never_cache
@login_required
@require_GET
def scraping_page(request):

    return render(
        request,
        "scraper/scraping.html"
    )


# ============================================================
# SCRAPING STATUS
# ============================================================

@never_cache
@login_required
@require_GET
def scraping_status(request):

    status = get_status()

    response = JsonResponse(status)

    # Prevent browser from caching old status
    response["Cache-Control"] = (
        "no-cache, no-store, must-revalidate"
    )
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"

    return response


# ============================================================
# START SCRAPING
# ============================================================

@login_required
@require_POST
def start_scraping(request):

    # --------------------------------------------------------
    # Check existing scraper
    # --------------------------------------------------------

    current_status = get_status()

    if current_status["status"] in {
        "starting",
        "running",
        "stopping",
    }:

        return JsonResponse(
            {
                "error": "Scraper is already running.",
                "status": current_status,
            },
            status=409
        )


    # --------------------------------------------------------
    # Read JSON body
    # --------------------------------------------------------

    try:

        data = json.loads(
            request.body.decode("utf-8")
        )

    except (
        json.JSONDecodeError,
        UnicodeDecodeError
    ):

        return JsonResponse(
            {
                "error": "Invalid JSON request."
            },
            status=400
        )


    # --------------------------------------------------------
    # Channel
    # --------------------------------------------------------

    channel = str(
        data.get("channel", "")
    ).strip()


    if not channel:

        return JsonResponse(
            {
                "error":
                    "Telegram channel is required."
            },
            status=400
        )


    # --------------------------------------------------------
    # Limit
    # --------------------------------------------------------

    try:

        limit = int(
            data.get("limit", 10)
        )

    except (
        TypeError,
        ValueError
    ):

        return JsonResponse(
            {
                "error":
                    "Limit must be a valid number."
            },
            status=400
        )


    if limit < 1 or limit > 100:

        return JsonResponse(
            {
                "error":
                    "Limit must be between 1 and 100."
            },
            status=400
        )


    # --------------------------------------------------------
    # Normalize Telegram channel
    # --------------------------------------------------------

    if (
        not channel.startswith("@")
        and not channel.startswith("https://t.me/")
        and not channel.startswith("http://t.me/")
    ):

        channel = "@" + channel


    # --------------------------------------------------------
    # Start scraper in background thread
    # --------------------------------------------------------

    def scraper_worker():

        try:

            run_scraper(
                channel_name=channel,
                limit=limit
            )

        except Exception as error:

            print(
                "SCRAPER WORKER ERROR:",
                error
            )


    thread = threading.Thread(
        target=scraper_worker,
        daemon=True
    )

    thread.start()


    # --------------------------------------------------------
    # Response
    # --------------------------------------------------------

    return JsonResponse(
        {
            "message":
                "Scraping started successfully.",

            "status":
                "starting",

            "channel":
                channel,

            "limit":
                limit,
        },
        status=202
    )


# ============================================================
# STOP SCRAPING
# ============================================================

@login_required
@require_POST
def stop_scraping(request):

    try:

        result = stop_scraper()

        return JsonResponse(
            result
        )

    except Exception as error:

        return JsonResponse(
            {
                "error":
                    str(error)
            },
            status=500
        )
