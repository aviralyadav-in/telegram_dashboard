import os

from django.conf import settings

from telegram import Bot, ChatPermissions


# ============================================================
# VERIFY BOT
# ============================================================

async def verify_bot_token(bot_token):

    if not bot_token:
        raise ValueError("Bot token is required.")

    bot = Bot(token=bot_token)

    try:
        return await bot.get_me()

    finally:
        await bot.shutdown()


# ============================================================
# FIND TELEGRAM CHAT
# ============================================================

async def find_telegram_chat(bot_token, username):

    if not bot_token:
        raise ValueError("Bot token is required.")

    if not username:
        raise ValueError("Telegram username is required.")

    username = str(username).strip()

    if not username.startswith("@"):
        username = "@" + username

    bot = Bot(token=bot_token)

    try:
        return await bot.get_chat(chat_id=username)

    finally:
        await bot.shutdown()


# ============================================================
# TEST TELEGRAM CHAT
# ============================================================

async def test_telegram_chat(bot_token, chat_id):

    if not bot_token:
        raise ValueError("Bot token is required.")

    if not chat_id:
        raise ValueError("Chat ID is required.")

    bot = Bot(token=bot_token)

    try:
        return await bot.send_message(
            chat_id=chat_id,
            text="✅ Telegram Deals Publisher test message.",
        )

    finally:
        await bot.shutdown()


# ============================================================
# IMAGE PATH
# ============================================================

def get_image_path(image_path):

    if not image_path:
        return None

    if os.path.isabs(image_path):
        return image_path

    return os.path.join(
        settings.MEDIA_ROOT,
        image_path,
    )


# ============================================================
# PUBLISH DEAL
# ============================================================

async def publish_to_telegram(
    bot_token,
    channel_username,
    content="",
    image_path="",
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

    try:

        actual_image_path = get_image_path(image_path)

        if (
            actual_image_path
            and os.path.isfile(actual_image_path)
        ):

            with open(
                actual_image_path,
                "rb",
            ) as photo:

                return await bot.send_photo(
                    chat_id=channel_username,
                    photo=photo,
                    caption=content or "",
                )

        return await bot.send_message(
            chat_id=channel_username,
            text=content or "",
        )

    finally:
        await bot.shutdown()

# ============================================================
# WELCOME MESSAGE
# ============================================================

async def send_welcome_message(
    bot_token,
    chat_id,
    message,
):
    if not bot_token:
        raise ValueError(
            "Telegram bot token is not configured."
        )

    if not chat_id:
        raise ValueError(
            "Telegram chat ID is required."
        )

    if not message:
        return None

    bot = Bot(token=bot_token)

    try:
        return await bot.send_message(
            chat_id=int(chat_id),
            text=message,
        )

    finally:
        await bot.shutdown()

# ============================================================
# USER PERMISSIONS
# ============================================================

def get_full_chat_permissions():

    return ChatPermissions(
        can_send_messages=True,
        can_send_audios=True,
        can_send_documents=True,
        can_send_photos=True,
        can_send_videos=True,
        can_send_video_notes=True,
        can_send_voice_notes=True,
        can_send_polls=True,
        can_send_other_messages=True,
        can_add_web_page_previews=True,
    )


def get_restricted_chat_permissions():

    return ChatPermissions(
        can_send_messages=False,
        can_send_audios=False,
        can_send_documents=False,
        can_send_photos=False,
        can_send_videos=False,
        can_send_video_notes=False,
        can_send_voice_notes=False,
        can_send_polls=False,
        can_send_other_messages=False,
        can_add_web_page_previews=False,
    )


# ============================================================
# SET USER MESSAGE PERMISSION
# ============================================================

async def set_user_message_permission(
    bot_token,
    chat_id,
    user_id,
    allowed,
):

    if not bot_token:
        raise ValueError(
            "Bot token is required."
        )

    if not chat_id:
        raise ValueError(
            "Chat ID is required."
        )

    if not user_id:
        raise ValueError(
            "Telegram user ID is required."
        )

    bot = Bot(token=bot_token)

    permissions = (
        get_full_chat_permissions()
        if allowed
        else get_restricted_chat_permissions()
    )

    try:

        return await bot.restrict_chat_member(
            chat_id=int(chat_id),
            user_id=int(user_id),
            permissions=permissions,
        )

    finally:
        await bot.shutdown()