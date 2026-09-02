from asgiref.sync import sync_to_async

from django.db import transaction
from django.utils import timezone

from publisher.models import (
    TelegramUser,
    ChannelUser,
    UserDestinationPermission,
    PublishedChannel,
)

from publisher.activity import log_activity

from publisher.telegram_bot import (
    send_welcome_message,
    set_user_message_permission,
)


# ============================================================
# USER NAME HELPER
# ============================================================

def username_for_log(user):

    return (
        user.username
        or user.first_name
        or str(user.user_id)
    )


# ============================================================
# GET / CREATE TELEGRAM USER
# ============================================================

def get_or_create_telegram_user(
    telegram_user,
):

    user_id = telegram_user.id

    user, created = (
        TelegramUser.objects.get_or_create(
            user_id=user_id,
            defaults={
                "username": telegram_user.username,
                "first_name": telegram_user.first_name,
                "last_name": telegram_user.last_name,
                "language_code": telegram_user.language_code,
                "status": "allowed",
                "last_seen_at": timezone.now(),
            },
        )
    )

    if not created:

        user.username = (
            telegram_user.username
        )

        user.first_name = (
            telegram_user.first_name
        )

        user.last_name = (
            telegram_user.last_name
        )

        user.language_code = (
            telegram_user.language_code
        )

        user.last_seen_at = (
            timezone.now()
        )

        user.save(
            update_fields=[
                "username",
                "first_name",
                "last_name",
                "language_code",
                "last_seen_at",
            ]
        )

    return user, created


# ============================================================
# ASYNC DATABASE WRAPPER
# ============================================================

get_or_create_telegram_user_async = sync_to_async(
    get_or_create_telegram_user,
    thread_sensitive=True,
)


# ============================================================
# TELEGRAM PERMISSION
# ============================================================

async def apply_telegram_permission(
    bot_record,
    destination,
    user,
    allowed,
):

    if not bot_record:
        return

    if not destination:
        return

    if not destination.chat_id:
        return

    try:

        await set_user_message_permission(
            bot_token=bot_record.bot_token,
            chat_id=destination.chat_id,
            user_id=user.user_id,
            allowed=allowed,
        )

        print(
            "🔐 TELEGRAM PERMISSION UPDATED:",
            username_for_log(user),
            "| ALLOWED:",
            allowed,
            "| DESTINATION:",
            destination.name,
        )

    except Exception as error:

        print(
            "❌ PERMISSION ERROR:",
            repr(error),
        )

        try:

            await sync_to_async(
                log_activity,
                thread_sensitive=True,
            )(
                event_type="permission_error",
                message=(
                    "Could not update Telegram "
                    f"permission for user "
                    f"{user.user_id}: {error}"
                ),
                bot=bot_record,
                destination=destination,
                user=user,
            )

        except Exception:

            pass


# ============================================================
# WELCOME MESSAGE
# ============================================================

async def send_user_welcome(
    bot_record,
    destination,
    user,
):

    if not bot_record:
        return

    if not destination:
        return

    if not destination.send_welcome_message:

        print(
            "⏭️ WELCOME DISABLED:",
            destination.name,
        )

        return

    if not destination.chat_id:
        return

    message = (
        destination.welcome_message
        or "👋 Welcome! Thanks for joining us."
    )

    # ========================================================
    # PLACEHOLDERS
    # ========================================================

    message = (
        message
        .replace(
            "{name}",
            user.first_name
            or user.username
            or "there",
        )
        .replace(
            "{username}",
            user.username or "",
        )
        .replace(
            "{user_id}",
            str(user.user_id),
        )
    )

    try:

        await send_welcome_message(
            bot_token=bot_record.bot_token,
            chat_id=destination.chat_id,
            message=message,
        )

        print(
            "👋 WELCOME SENT:",
            username_for_log(user),
            "| DESTINATION:",
            destination.name,
        )

        try:

            await sync_to_async(
                log_activity,
                thread_sensitive=True,
            )(
                event_type="welcome_message_sent",
                message=(
                    "Welcome message sent to "
                    f"{username_for_log(user)}."
                ),
                bot=bot_record,
                destination=destination,
                user=user,
            )

        except Exception:

            pass

    except Exception as error:

        print(
            "❌ WELCOME MESSAGE FAILED:",
            username_for_log(user),
            "| DESTINATION:",
            destination.name,
            "| ERROR:",
            repr(error),
        )

        try:

            await sync_to_async(
                log_activity,
                thread_sensitive=True,
            )(
                event_type="welcome_message_error",
                message=(
                    "Welcome message failed for "
                    f"{username_for_log(user)}: {error}"
                ),
                bot=bot_record,
                destination=destination,
                user=user,
            )

        except Exception:

            pass


# ============================================================
# HANDLE CHAT MEMBER UPDATE
# ============================================================

async def handle_member_update(
    bot_record,
    update,
    bot=None,
):

    member_update = (
        update.chat_member
    )

    if not member_update:
        return

    # ========================================================
    # STATUS
    # ========================================================

    old_status = (
        member_update.old_chat_member.status
    )

    new_status = (
        member_update.new_chat_member.status
    )

    telegram_user = (
        member_update.new_chat_member.user
    )

    chat = member_update.chat

    # ========================================================
    # DEBUG
    # ========================================================

    print(
        "🔥 CHAT MEMBER UPDATE:",
        old_status,
        "→",
        new_status,
        "| USER:",
        telegram_user.id,
        "| CHAT:",
        chat.id,
    )

    # ========================================================
    # IGNORE restricted → restricted
    # ========================================================

    if (
        old_status == "restricted"
        and new_status == "restricted"
    ):

        print(
            "⏭️ IGNORED: restricted → restricted",
            "| USER:",
            telegram_user.id,
            "| CHAT:",
            chat.id,
        )

        return

    # ========================================================
    # FIND DESTINATION
    # ========================================================

    destination = await sync_to_async(
        lambda: (
            PublishedChannel.objects
            .filter(
                bot=bot_record,
                chat_id=chat.id,
            )
            .first()
        ),
        thread_sensitive=True,
    )()

    if not destination:

        print(
            "⚠️ DESTINATION NOT FOUND:",
            chat.id,
        )

        return

    # ========================================================
    # GET / CREATE USER
    # ========================================================

    user, created = (
        await get_or_create_telegram_user_async(
            telegram_user
        )
    )

    username = username_for_log(user)

    # ========================================================
    # FIRST USER SEEN
    # ========================================================

    if created:

        await sync_to_async(
            log_activity,
            thread_sensitive=True,
        )(
            event_type="user_first_seen",
            message=(
                f"User {username} was detected "
                "for the first time."
            ),
            bot=bot_record,
            destination=destination,
            user=user,
        )

    # ========================================================
    # ACTUAL JOIN / REJOIN
    # ========================================================

    if new_status in {
        "member",
        "administrator",
        "creator",
    }:

        joined_now = timezone.now()

        print(
            "🟢 USER JOINED / REJOINED:",
            username,
            "| DESTINATION:",
            destination.name,
            "| TIME:",
            joined_now,
        )

        # ====================================================
        # DATABASE OPERATION
        # ====================================================

        result = await sync_to_async(
            process_user_join,
            thread_sensitive=True,
        )(
            destination,
            user,
            username,
            bot_record,
            old_status,
            new_status,
            joined_now,
        )

        # ====================================================
        # PERMISSION
        # ====================================================

        permission_allowed = (
            result["permission_allowed"]
        )

        permission_created = (
            result["permission_created"]
        )

        channel_user_status = (
            result["channel_user_status"]
        )

        # ====================================================
        # APPLY TELEGRAM PERMISSION
        # ====================================================

        if destination.chat_type == "group":

            await apply_telegram_permission(
                bot_record,
                destination,
                user,
                permission_allowed,
            )

        # ====================================================
        # LOG PERMISSION
        # ====================================================

        if (
            permission_created
            and permission_allowed
        ):

            await sync_to_async(
                log_activity,
                thread_sensitive=True,
            )(
                event_type="user_allowed",
                message=(
                    f"User {username} was automatically "
                    f"allowed in {destination.name}."
                ),
                bot=bot_record,
                destination=destination,
                user=user,
            )

        # ====================================================
        # WELCOME
        # ====================================================

        actual_join = (
            old_status not in {
                "member",
                "administrator",
                "creator",
            }
        )

        if actual_join:

            print(
                "🎉 ACTUAL JOIN DETECTED - "
                "SENDING WELCOME:",
                username,
                "| DESTINATION:",
                destination.name,
            )

            await send_user_welcome(
                bot_record,
                destination,
                user,
            )

        else:

            print(
                "⏭️ NO WELCOME - "
                "NOT A NEW JOIN:",
                old_status,
                "→",
                new_status,
                "| USER:",
                username,
                "| DESTINATION:",
                destination.name,
            )

        return

    # ========================================================
    # USER LEFT / KICKED
    # ========================================================

    if new_status in {
        "left",
        "kicked",
    }:

        left_now = timezone.now()

        print(
            "🚪 USER LEFT/KICKED:",
            username,
            "| DESTINATION:",
            destination.name,
            "| TIME:",
            left_now,
        )

        await sync_to_async(
            process_user_left,
            thread_sensitive=True,
        )(
            destination,
            user,
            username,
            bot_record,
            left_now,
        )

        return

    # ========================================================
    # EVERYTHING ELSE
    # ========================================================

    print(
        "⏭️ IGNORED STATUS CHANGE:",
        old_status,
        "→",
        new_status,
        "| USER:",
        username,
        "| DESTINATION:",
        destination.name,
    )


# ============================================================
# PROCESS USER JOIN - DATABASE ONLY
# ============================================================

def process_user_join(
    destination,
    user,
    username,
    bot_record,
    old_status,
    new_status,
    joined_now,
):

    with transaction.atomic():

        # ====================================================
        # CHANNEL USER
        # ====================================================

        channel_user, channel_created = (
            ChannelUser.objects.get_or_create(
                channel=destination,
                user=user,
                defaults={
                    "status": "active",
                    "joined_at": joined_now,
                    "left_at": None,
                },
            )
        )

        # ====================================================
        # FIRST JOIN
        # ====================================================

        if channel_created:

            print(
                "🆕 NEW MEMBERSHIP:",
                channel_user.id,
            )

            log_activity(
                event_type="user_joined",
                message=(
                    f"User {username} joined "
                    f"{destination.name}."
                ),
                bot=bot_record,
                destination=destination,
                user=user,
            )

        # ====================================================
        # REJOIN
        # ====================================================

        elif channel_user.status in {
            "left",
            "blocked",
        }:

            channel_user.status = "active"

            channel_user.joined_at = joined_now

            # Previous left_at intentionally preserved.

            channel_user.save(
                update_fields=[
                    "status",
                    "joined_at",
                    "updated_at",
                ]
            )

            print(
                "🔄 REJOIN SAVED:",
                "ChannelUser ID =",
                channel_user.id,
                "| joined_at =",
                channel_user.joined_at,
                "| previous left_at =",
                channel_user.left_at,
            )

            log_activity(
                event_type="user_joined",
                message=(
                    f"User {username} joined/rejoined "
                    f"{destination.name}."
                ),
                bot=bot_record,
                destination=destination,
                user=user,
            )

        # ====================================================
        # ALREADY ACTIVE
        # ====================================================

        else:

            print(
                "ℹ️ USER ALREADY ACTIVE:",
                username,
                "| DESTINATION:",
                destination.name,
            )

        # ====================================================
        # PERMISSION
        # ====================================================

        permission, permission_created = (
            UserDestinationPermission.objects
            .get_or_create(
                user=user,
                destination=destination,
                defaults={
                    "can_message": (
                        destination.auto_allow_users
                    ),
                    "is_allowed": (
                        destination.auto_allow_users
                    ),
                    "can_publish": False,
                },
            )
        )

        # ====================================================
        # NEW PERMISSION
        # ====================================================

        if permission_created:

            allowed = (
                destination.auto_allow_users
            )

            if allowed:

                channel_user.status = "allowed"

            else:

                channel_user.status = "active"

            channel_user.save(
                update_fields=[
                    "status",
                    "updated_at",
                ]
            )

        # ====================================================
        # EXISTING PERMISSION
        # ====================================================

        else:

            if permission.is_allowed:

                channel_user.status = "allowed"

            else:

                channel_user.status = "active"

            channel_user.save(
                update_fields=[
                    "status",
                    "updated_at",
                ]
            )

        return {
            "permission_allowed": (
                permission.is_allowed
            ),
            "permission_created": (
                permission_created
            ),
            "channel_user_status": (
                channel_user.status
            ),
        }


# ============================================================
# PROCESS USER LEFT - DATABASE ONLY
# ============================================================

def process_user_left(
    destination,
    user,
    username,
    bot_record,
    left_now,
):

    channel_user, channel_created = (
        ChannelUser.objects.get_or_create(
            channel=destination,
            user=user,
            defaults={
                "status": "left",
                "joined_at": None,
                "left_at": left_now,
            },
        )
    )

    if not channel_created:

        channel_user.status = "left"

        channel_user.left_at = left_now

        channel_user.save(
            update_fields=[
                "status",
                "left_at",
                "updated_at",
            ]
        )

    print(
        "✅ LEFT SAVED:",
        "ChannelUser ID =",
        channel_user.id,
        "| status =",
        channel_user.status,
        "| joined_at =",
        channel_user.joined_at,
        "| left_at =",
        channel_user.left_at,
    )

    log_activity(
        event_type="user_left",
        message=(
            f"User {username} left "
            f"{destination.name}."
        ),
        bot=bot_record,
        destination=destination,
        user=user,
    )