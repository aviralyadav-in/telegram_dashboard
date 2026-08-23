from asgiref.sync import async_to_sync
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
# GET / CREATE TELEGRAM USER
# ============================================================

def get_or_create_telegram_user(telegram_user):

    user_id = telegram_user.id

    user, created = TelegramUser.objects.get_or_create(
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

    if not created:

        user.username = telegram_user.username
        user.first_name = telegram_user.first_name
        user.last_name = telegram_user.last_name
        user.language_code = telegram_user.language_code
        user.last_seen_at = timezone.now()

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
# TELEGRAM PERMISSION HELPER
# ============================================================

def apply_telegram_permission(
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

        async_to_sync(
            set_user_message_permission
        )(
            bot_token=bot_record.bot_token,
            chat_id=destination.chat_id,
            user_id=user.user_id,
            allowed=allowed,
        )

    except Exception as error:

        log_activity(
            event_type="permission_error",
            message=(
                f"Could not update Telegram permission "
                f"for user {user.user_id}: {error}"
            ),
            bot=bot_record,
            destination=destination,
            user=user,
        )


# ============================================================
# WELCOME MESSAGE HELPER
# ============================================================

def send_user_welcome(
    bot_record,
    destination,
    user,
):

    if not bot_record:
        return

    if not destination:
        return

    if not destination.send_welcome_message:
        return

    message = (
        destination.welcome_message
        or "👋 Welcome! Thanks for joining us."
    )

    try:

        async_to_sync(
            send_welcome_message
        )(
            bot_token=bot_record.bot_token,
            chat_id=destination.chat_id,

            message=message,
        )

        log_activity(
            event_type="welcome_message_sent",
            message=(
                f"Welcome message sent to "
                f"{user.username or user.user_id}."
            ),
            bot=bot_record,
            destination=destination,
            user=user,
        )

    except Exception as error:

        log_activity(
            event_type="welcome_message_error",
            message=(
                f"Welcome message failed for "
                f"{user.username or user.user_id}: {error}"
            ),
            bot=bot_record,
            destination=destination,
            user=user,
        )


# ============================================================
# HANDLE CHAT MEMBER UPDATE
# ============================================================

def handle_member_update(
    bot_record,
    update,
):

    member_update = update.chat_member

    if not member_update:
        return

    telegram_user = (
        member_update.new_chat_member.user
    )

    chat = member_update.chat

    new_status = (
        member_update
        .new_chat_member
        .status
    )

    destination = (
        PublishedChannel.objects
        .filter(
            bot=bot_record,
            chat_id=chat.id,
        )
        .first()
    )

    if not destination:
        return

    # ========================================================
    # USER
    # ========================================================

    user, created = get_or_create_telegram_user(
        telegram_user
    )

    username = (
        user.username
        or user.first_name
        or str(user.user_id)
    )

    # ========================================================
    # FIRST USER SEEN
    # ========================================================

    if created:

        log_activity(
            event_type="user_first_seen",
            message=(
                f"User {username} was detected "
                f"for the first time."
            ),
            bot=bot_record,
            destination=destination,
            user=user,
        )

    # ========================================================
    # USER JOINED
    # ========================================================

    if new_status in {
        "member",
        "administrator",
        "creator",
    }:

        with transaction.atomic():

            channel_user, channel_created = (
                ChannelUser.objects.get_or_create(
                    channel=destination,
                    user=user,
                    defaults={
                        "status": "active",
                        "joined_at": timezone.now(),
                    },
                )
            )

            # =================================================
            # NEW MEMBERSHIP
            # =================================================

            if channel_created:

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

            # =================================================
            # REJOIN
            # =================================================

            elif channel_user.status in {
                "left",
                "blocked",
            }:

                channel_user.status = "active"
                channel_user.left_at = None

                channel_user.save(
                    update_fields=[
                        "status",
                        "left_at",
                        "updated_at",
                    ]
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

            # =================================================
            # PERMISSION
            # =================================================

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

            # =================================================
            # NEW PERMISSION
            # =================================================

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

                # Actually apply Telegram permission
                if destination.chat_type == "group":

                    apply_telegram_permission(
                        bot_record,
                        destination,
                        user,
                        allowed,
                    )

                if allowed:

                    log_activity(
                        event_type="user_allowed",
                        message=(
                            f"User {username} was automatically "
                            f"allowed in {destination.name}."
                        ),
                        bot=bot_record,
                        destination=destination,
                        user=user,
                    )

                # Welcome only for a newly detected user
                if  channel_created:

                    send_user_welcome(
                        bot_record,
                        destination,
                        user,
                    )

            # =================================================
            # EXISTING PERMISSION
            # =================================================

            else:

                if permission.is_allowed:

                    channel_user.status = "allowed"

                    channel_user.save(
                        update_fields=[
                            "status",
                            "updated_at",
                        ]
                    )

                else:

                    channel_user.status = "active"

                    channel_user.save(
                        update_fields=[
                            "status",
                            "updated_at",
                        ]
                    )

    # ========================================================
    # USER LEFT / KICKED
    # ========================================================

    elif new_status in {
        "left",
        "kicked",
    }:

        channel_user = (
            ChannelUser.objects
            .filter(
                channel=destination,
                user=user,
            )
            .first()
        )

        if channel_user:

            channel_user.status = "left"
            channel_user.left_at = timezone.now()

            channel_user.save(
                update_fields=[
                    "status",
                    "left_at",
                    "updated_at",
                ]
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