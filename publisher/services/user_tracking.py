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
            error,
        )

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

    # --------------------------------------------------------
    # PLACEHOLDERS
    # --------------------------------------------------------

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

        async_to_sync(
            send_welcome_message
        )(
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

        log_activity(
            event_type="welcome_message_sent",
            message=(
                f"Welcome message sent to "
                f"{username_for_log(user)}."
            ),
            bot=bot_record,
            destination=destination,
            user=user,
        )

    except Exception as error:

        print(
            "❌ WELCOME MESSAGE FAILED:",
            username_for_log(user),
            "| DESTINATION:",
            destination.name,
            "| ERROR:",
            error,
        )

        log_activity(
            event_type="welcome_message_error",
            message=(
                f"Welcome message failed for "
                f"{username_for_log(user)}: {error}"
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
    # IGNORE RESTRICTED → RESTRICTED
    #
    # Telegram can send several of these while a user joins.
    # They must NOT create/update membership or send welcome.
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

    destination = (
        PublishedChannel.objects
        .filter(
            bot=bot_record,
            chat_id=chat.id,
        )
        .first()
    )

    if not destination:

        print(
            "⚠️ DESTINATION NOT FOUND:",
            chat.id,
        )

        return

    # ========================================================
    # GET / CREATE TELEGRAM USER
    # ========================================================

    user, created = get_or_create_telegram_user(
        telegram_user
    )

    username = username_for_log(user)

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

        with transaction.atomic():

            # =================================================
            # GET / CREATE CHANNEL USER
            # =================================================

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

            # =================================================
            # FIRST JOIN
            # =================================================

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

            # =================================================
            # REJOIN
            # =================================================

            elif channel_user.status in {
                "left",
                "blocked",
            }:

                channel_user.status = "active"

                # Current rejoin time
                channel_user.joined_at = joined_now

                # IMPORTANT:
                # DO NOT clear left_at.
                # Previous leave time is preserved.

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

            # =================================================
            # ALREADY MEMBER
            #
            # member → member
            # administrator → administrator
            # creator → creator
            #
            # Don't change joined_at.
            # Don't create duplicate welcome.
            # =================================================

            else:

                print(
                    "ℹ️ USER ALREADY ACTIVE:",
                    username,
                    "| DESTINATION:",
                    destination.name,
                )

            # =================================================
            # USER DESTINATION PERMISSION
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

                # ---------------------------------------------
                # GROUP ONLY
                # ---------------------------------------------

                if (
                    destination.chat_type == "group"
                ):

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

            # =================================================
            # EXISTING PERMISSION
            # =================================================

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

                # ---------------------------------------------
                # RE-APPLY TELEGRAM PERMISSION
                # ---------------------------------------------

                if (
                    destination.chat_type == "group"
                ):

                    apply_telegram_permission(
                        bot_record,
                        destination,
                        user,
                        permission.is_allowed,
                    )

            # =================================================
            # WELCOME MESSAGE
            #
            # EVERY ACTUAL JOIN / REJOIN:
            #
            # left → member       ✅
            # restricted → member ✅
            # kicked → member     ✅
            # new → member        ✅
            #
            # NOT:
            #
            # member → member             ❌
            # administrator → member      ❌
            # creator → member            ❌
            # restricted → restricted     ❌
            # =================================================

            actual_join = (
                old_status not in {
                    "member",
                    "administrator",
                    "creator",
                }
            )

            if actual_join:

                print(
                    "🎉 ACTUAL JOIN DETECTED - SENDING WELCOME:",
                    username,
                    "| DESTINATION:",
                    destination.name,
                )

                send_user_welcome(
                    bot_record,
                    destination,
                    user,
                )

            else:

                print(
                    "⏭️ NO WELCOME - NOT A NEW JOIN:",
                    old_status,
                    "→",
                    new_status,
                    "| USER:",
                    username,
                    "| DESTINATION:",
                    destination.name,
                )

    # ========================================================
    # USER LEFT / KICKED
    # ========================================================

    elif new_status in {
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

        # ====================================================
        # GET EXISTING MEMBERSHIP
        # OR CREATE LEFT RECORD
        # ====================================================

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

        # ====================================================
        # EXISTING MEMBERSHIP
        # ====================================================

        if not channel_created:

            channel_user.status = "left"

            # Always save current leave time
            channel_user.left_at = left_now

            channel_user.save(
                update_fields=[
                    "status",
                    "left_at",
                    "updated_at",
                ]
            )

        # ====================================================
        # CONFIRM DATABASE SAVE
        # ====================================================

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

        # ====================================================
        # NO WELCOME ON LEAVE
        # ====================================================

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

    # ========================================================
    # EVERYTHING ELSE
    # ========================================================

    else:

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