from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from accounts.views import login_page


urlpatterns = [

    # =====================================================
    # ADMIN
    # =====================================================

    path(
        "admin/",
        admin.site.urls
    ),

    # =====================================================
    # LOGIN
    # =====================================================

    path(
        "login/",
        login_page,
        name="login"
    ),

    # =====================================================
    # DASHBOARD / DEALS
    # =====================================================

    path(
        "",
        include("deals.urls")
    ),

    # =====================================================
    # ACCOUNTS
    # =====================================================

    path(
        "accounts/",
        include("accounts.urls")
    ),

    # =====================================================
    # SCRAPING
    # =====================================================

    path(
        "scraping/",
        include("scraper.urls")
    ),

    # =====================================================
    # CHANNELS
    # =====================================================

    path(
        "channels/",
        include("publisher.urls")
    ),

    # =====================================================
    # SCHEDULES
    # =====================================================

    path(
        "schedules/",
        include("scheduler.urls")
    ),
]


if settings.DEBUG:

    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT
    )