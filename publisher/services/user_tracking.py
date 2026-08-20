import asyncio

from django.db import transaction
from django.utils import timezone

from publisher.models import (
    TelegramUser,
    PublishedChannel,
    ChannelUser,
    UserDestinationPermission,
)

from publisher.telegram_bot import (
    send_welcome_message,
)


ACTIVE_MEMBER_STATUSES = {
    "member",
    "administrator",
    "creator",
}

INACTIVE_MEMBER_STATUSES = {
    "left",
    "kicked",
}


def save_telegram_user(telegram_user):
    user, created = TelegramUser.objects.update_or_create(
        user_id=telegram_user.id,
        defaults={
            "username": telegram_user.username,
            "first_name": telegram_user.first_name,
            "last_name": telegram_user.last_name,
            "language_code": telegram_user.language_code,
        },
    )

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


def get_display_name(user):
    if user.first_name:
        return user.first_name

    if user.username:
        return f"@{user.username}"

    return str(user.user_id)


def handle_member_update(bot_record, update):

    member_update = update.chat_member

    if not member_update:
        return

    telegram_user = member_update.new_chat_member.user
    chat = member_update.chat

    user, created = save_telegram_user(
        telegram_user
    )

    channel = (
        PublishedChannel.objects
        .filter(
            bot=bot_record,
            chat_id=chat.id,
        )
        .first()
    )

    if not channel:
        return

    old_status = (
        member_update
        .old_chat_member
        .status
    )

    new_status = (
        member_update
        .new_chat_member
        .status
    )

    joined = (
        old_status in INACTIVE_MEMBER_STATUSES
        and new_status in ACTIVE_MEMBER_STATUSES
    )

    left = (
        new_status in INACTIVE_MEMBER_STATUSES
        and old_status in ACTIVE_MEMBER_STATUSES
    )

    # -------------------------------------------------
    # USER JOINED / REJOINED
    # -------------------------------------------------

    if joined:

        with transaction.atomic():

            membership, membership_created = (
                ChannelUser.objects.update_or_create(
                    channel=channel,
                    user=user,
                    defaults={
                        "status": (
                            "allowed"
                            if channel.auto_allow_users
                            else "blocked"
                        )
                    },
                )
            )

            UserDestinationPermission.objects.update_or_create(
                user=user,
                destination=channel,
                defaults={
                    "can_message": (
                        channel.allow_direct_messages
                    ),
                    "can_publish": False,
                    "is_allowed": (
                        channel.auto_allow_users
                    ),
                },
            )

        # Send welcome only when user joins for the first time
        # or when you explicitly want welcome on every rejoin.
        if (
            channel.send_welcome_message
            and channel.auto_allow_users
        ):

            name = get_display_name(
                telegram_user
            )

            welcome = (
                channel.welcome_message
                .replace(
                    "{name}",
                    name,
                )
                .replace(
                    "{username}",
                    telegram_user.username or "",
                )
                .replace(
                    "{user_id}",
                    str(telegram_user.id),
                )
            )

            try:

                asyncio.run(
                    send_welcome_message(
                        bot_record.bot_token,
                        chat.id,
                        welcome,
                    )
                )

            except Exception as error:

                print(
                    f"Welcome message failed "
                    f"for user {telegram_user.id}: "
                    f"{error}"
                )

        return

    # -------------------------------------------------
    # USER LEFT / KICKED
    # -------------------------------------------------

    if left:

        ChannelUser.objects.filter(
            channel=channel,
            user=user,
        ).update(
            status="blocked"
        )

        UserDestinationPermission.objects.filter(
            user=user,
            destination=channel,
        ).update(
            is_allowed=False,
            can_message=False,
            can_publish=False,
        )

        return