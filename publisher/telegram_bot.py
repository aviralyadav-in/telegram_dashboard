import os

from telegram import Bot
from django.conf import settings


async def verify_bot_token(bot_token):

    if not bot_token:
        raise ValueError("Bot token is required.")

    bot = Bot(token=bot_token)

    return await bot.get_me()


async def find_telegram_chat(bot_token, username):

    if not bot_token:
        raise ValueError("Bot token is required.")

    if not username:
        raise ValueError("Telegram username is required.")

    if not username.startswith("@"):
        username = "@" + username

    bot = Bot(token=bot_token)

    return await bot.get_chat(
        chat_id=username
    )


async def test_telegram_chat(bot_token, chat_id):

    if not bot_token:
        raise ValueError("Bot token is required.")

    if not chat_id:
        raise ValueError("Chat ID is required.")

    bot = Bot(token=bot_token)

    return await bot.send_message(
        chat_id=chat_id,
        text="✅ Telegram Deals Publisher test message."
    )


def get_image_path(image_path):

    if not image_path:
        return None

    if os.path.isabs(image_path):
        return image_path

    return os.path.join(
        settings.MEDIA_ROOT,
        image_path
    )


async def publish_to_telegram(
    bot_token,
    channel_username,
    content="",
    image_path=""
):

    if not bot_token:
        raise ValueError(
            "Telegram bot token is not configured."
        )

    if not channel_username:
        raise ValueError(
            "Telegram chat ID/username is required."
        )

    bot = Bot(token=bot_token)

    actual_image_path = get_image_path(
        image_path
    )

    if (
        actual_image_path
        and os.path.isfile(actual_image_path)
    ):

        with open(
            actual_image_path,
            "rb"
        ) as photo:

            return await bot.send_photo(
                chat_id=channel_username,
                photo=photo,
                caption=content or ""
            )

    return await bot.send_message(
        chat_id=channel_username,
        text=content or ""
    )


async def send_welcome_message(
    bot_token,
    chat_id,
    message
):

    if not bot_token:
        raise ValueError(
            "Bot token is not configured."
        )

    if not chat_id:
        raise ValueError(
            "Chat ID is required."
        )

    bot = Bot(token=bot_token)

    return await bot.send_message(
        chat_id=chat_id,
        text=message
    )