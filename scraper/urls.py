from django.urls import path

from .views import (
    scraping_page,
    start_scraping,
    stop_scraping,
    scraping_status,
)


urlpatterns = [

    path(
        "",
        scraping_page,
        name="scraping-page"
    ),

    path(
        "start/",
        start_scraping,
        name="scrape-start"
    ),

    path(
        "stop/",
        stop_scraping,
        name="scrape-stop"
    ),

    path(
        "status/",
        scraping_status,
        name="scrape-status"
    ),

]