import os
import re
import threading
import random

from django.conf import settings
from django.db import transaction
from publisher.services.publishing import auto_publish_deal
from asgiref.sync import sync_to_async

from telethon import TelegramClient
from telethon.errors import FloodWaitError

from deals.models import Deal


USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/138.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:141.0) Gecko/20100101 Firefox/141.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Version/18.0 Safari/605.1.15",
]


# ============================================================
# SCRAPER STATUS
# ============================================================

scraper_status = {
    "status": "idle",
    "channel": None,
    "limit": 0,
    "messages_scraped": 0,
    "messages_saved": 0,
    "current_deal": None,
    "error": None,
}

scraper_lock = threading.Lock()
stop_event = threading.Event()


# ============================================================
# STATUS HELPERS
# ============================================================

def update_status(**kwargs):

    with scraper_lock:
        scraper_status.update(kwargs)


def get_status():

    with scraper_lock:
        return scraper_status.copy()


# ============================================================
# DATABASE HELPERS
# IMPORTANT:
# Django ORM is synchronous, so it must run through sync_to_async.
# ============================================================

@sync_to_async(thread_sensitive=True)
def deal_exists(channel_name, message_id):

    return Deal.objects.filter(
        message_id=message_id,
        channel=channel_name
    ).exists()


@sync_to_async(thread_sensitive=True)
def save_deal(
    message_id,
    date,
    content,
    product_link,
    image_path,
    channel_name
):

    with transaction.atomic():

        deal = Deal.objects.create(
            message_id=message_id,
            date=date,
            content=content,
            product_link=product_link,
            image_path=image_path,
            channel=channel_name,
            status="new",
        )
        try:
            auto_publish_deal(deal)
        except Exception as error:
            print(f"Auto publish error for deal {deal.id}: {error}")

    return deal


# ============================================================
# HELPERS
# ============================================================

def extract_link(message):

    # Telegram button URL
    if message.buttons:

        for row in message.buttons:

            for button in row:

                url = getattr(
                    button,
                    "url",
                    None
                )

                if url:
                    return url

    # URL from message text
    if message.text:

        links = re.findall(
            r'https?://\S+',
            message.text
        )

        if links:

            return links[0].rstrip(
                ").,]"
            )

    return ""


def validate_product_link(url):

    if not url:
        return

    try:

        import requests

        headers = {
            "User-Agent": random.choice(
                USER_AGENTS
            )
        }

        requests.get(
            url,
            headers=headers,
            timeout=5,
            allow_redirects=True
        )

    except Exception:

        # Product link validation should
        # never stop the scraper.
        pass

def get_image_folder():

    folder = os.path.join(
        settings.MEDIA_ROOT,
        "images"
    )

    os.makedirs(
        folder,
        exist_ok=True
    )

    return folder


# ============================================================
# MAIN ASYNC SCRAPER
# ============================================================

async def scrape_channel(
    client,
    channel_name,
    limit
):

    messages_scraped = 0
    messages_saved = 0
    current_deal = None

    update_status(
        status="running",
        channel=channel_name,
        limit=limit,
        messages_scraped=0,
        messages_saved=0,
        current_deal=None,
        error=None
    )

    image_folder = get_image_folder()

    try:

        # ----------------------------------------------------
        # GET TELEGRAM CHANNEL
        # ----------------------------------------------------

        channel = await client.get_entity(
            channel_name
        )

        # ----------------------------------------------------
        # READ TELEGRAM MESSAGES
        # ----------------------------------------------------

        async for message in client.iter_messages(
            channel,
            limit=int(limit)
        ):

            # ------------------------------------------------
            # STOP REQUEST
            # ------------------------------------------------

            if stop_event.is_set():

                update_status(
                    status="stopped",
                    current_deal=current_deal
                )

                break

            # ------------------------------------------------
            # IGNORE EMPTY MESSAGES
            # ------------------------------------------------

            if not (
                message.text
                or message.photo
            ):
                continue

            current_deal = (
                f"Message ID {message.id}"
            )

            update_status(
                current_deal=current_deal
            )

            # ------------------------------------------------
            # DUPLICATE CHECK
            # IMPORTANT: async-safe ORM
            # ------------------------------------------------

            exists = await deal_exists(
                channel_name,
                message.id
            )

            if exists:

                print(
                    f"Duplicate skipped: {message.id}"
                )

                continue

            # ------------------------------------------------
            # MESSAGE CONTENT
            # ------------------------------------------------

            content = (
                message.text
                if message.text
                else ""
            )

            # Remove markdown **
            content = re.sub(
                r"\*\*",
                "",
                content
            )

            # ------------------------------------------------
            # PRODUCT LINK
            # ------------------------------------------------

            product_link = extract_link(
                message
            )

            validate_product_link(
                product_link
            )

            
# IMAGE / MEDIA DOWNLOAD
# ------------------------------------------------

            image_path = ""

            # Telegram message ke paas koi media ho
            if message.media:

                safe_channel_name = re.sub(
                    r"[^A-Za-z0-9_-]",
                    "_",
                    channel_name
                )

                image_name = (
                    f"{safe_channel_name}_{message.id}.jpg"
                )

                image_file = os.path.join(
                    image_folder,
                    image_name
                )

                try:

                    # Media ko download karo
                    downloaded_path = (
                        await message.download_media(
                            file=image_file
                        )
                    )

                    if downloaded_path:

                        # Sirf image/photo ko Deal model mein
                        # image path ke roop mein save karo.
                        if (
                            message.photo
                            or str(downloaded_path).lower().endswith(
                                (
                                    ".jpg",
                                    ".jpeg",
                                    ".png",
                                    ".webp"
                                )
                            )
                        ):

                            image_path = (
                                f"images/{image_name}"
                            )
                            print( f"[IMAGE DEBUG] Saved image path: " f"{image_path}" )
                        else:

                            print( f"[IMAGE DEBUG] Media is not an image " f"for message {message.id}" )
                except Exception as error:

                    print(
                        f"Image/media download error "
                        f"for message {message.id}:",
                        error
                    )


            # SAVE DEAL
            # IMPORTANT: async-safe ORM
            # ------------------------------------------------

            try:

                await save_deal(
                    message_id=message.id,
                    date=message.date,
                    content=content,
                    product_link=product_link,
                    image_path=image_path,
                    channel_name=channel_name
                )

                messages_scraped += 1
                messages_saved += 1

                update_status(
                    messages_scraped=messages_scraped,
                    messages_saved=messages_saved,
                    current_deal=current_deal
                )

                print(
                    f"Deal saved successfully: {message.id}"
                )

            except Exception as error:

                print(
                    f"Database save error for message "
                    f"{message.id}: {error}"
                )

                # Continue scraping remaining messages.
                continue

        # ----------------------------------------------------
        # COMPLETED
        # ----------------------------------------------------

        if not stop_event.is_set():

            update_status(
                status="completed",
                channel=channel_name,
                limit=limit,
                current_deal=current_deal,
                messages_scraped=messages_scraped,
                messages_saved=messages_saved,
                error=None
            )

        return {
            "messages_scraped": messages_scraped,
            "messages_saved": messages_saved,
            "current_deal": current_deal
        }

    except FloodWaitError as error:

        update_status(
            status="error",
            error=(
                f"Telegram flood wait: "
                f"{error.seconds} seconds"
            )
        )

        raise

    except Exception as error:

        update_status(
            status="error",
            error=str(error),
            current_deal=current_deal,
            messages_scraped=messages_scraped,
            messages_saved=messages_saved
        )

        raise


# ============================================================
# START SCRAPER
# ============================================================

def run_scraper(
    channel_name,
    limit
):

    api_id = getattr(
        settings,
        "TELEGRAM_API_ID",
        None
    )

    api_hash = getattr(
        settings,
        "TELEGRAM_API_HASH",
        None
    )

    if not api_id or not api_hash:

        raise ValueError(
            "Telegram API credentials are not configured."
        )

    # New scraping job
    stop_event.clear()

    update_status(
        status="starting",
        channel=channel_name,
        limit=limit,
        messages_scraped=0,
        messages_saved=0,
        current_deal=None,
        error=None
    )

    client = TelegramClient(
        "django_scraper_session",
        int(api_id),
        api_hash
    )

    try:

        with client:

            result = client.loop.run_until_complete(
                scrape_channel(
                    client,
                    channel_name,
                    limit
                )
            )

            return result

    except Exception as error:

        update_status(
            status="error",
            channel=channel_name,
            error=str(error)
        )

        raise


# ============================================================
# STOP SCRAPER
# ============================================================

def stop_scraper():

    current = get_status()

    if current["status"] not in {
        "starting",
        "running"
    }:

        return {
            "message": "Scraper is not currently running.",
            "status": current
        }

    stop_event.set()

    update_status(
        status="stopping"
    )

    return {
        "message": "Scraper stop requested.",
        "status": "stopping"
    }