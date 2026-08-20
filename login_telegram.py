import os
import asyncio
import django

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "config.settings"
)

django.setup()

from django.conf import settings
from telethon import TelegramClient


async def login_telegram():

    client = TelegramClient(
        "django_scraper_session",
        int(settings.TELEGRAM_API_ID),
        settings.TELEGRAM_API_HASH
    )

    await client.start()

    me = await client.get_me()

    print("================================")
    print("Telegram login successful")
    print("User ID:", me.id)
    print("Username:", me.username)
    print("Name:", me.first_name)
    print("================================")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(login_telegram())