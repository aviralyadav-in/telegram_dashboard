from publisher.models import (
    TelegramUser,
    UserDestinationPermission,
    PublishedChannel,
)

from publisher.services.user_tracking import (
    get_or_create_telegram_user,
)

from publisher.telegram_bot import (
    send_welcome_message,
)


def handle_private_message(
    bot_record,
    update,
):

    message = update.message

    if not message:
        return

    if not message.from_user:
        return

    telegram_user = message.from_user

    user, created = get_or_create_telegram_user(
        telegram_user
    )

    # --------------------------------------------------------
    # Find destinations connected with this bot
    # --------------------------------------------------------

    destinations = PublishedChannel.objects.filter(
        bot=bot_record,
        status="active",
    )

    # --------------------------------------------------------
    # Check whether user is allowed anywhere
    # --------------------------------------------------------

    permission = (
        UserDestinationPermission.objects
        .filter(
            user=user,
            destination__in=destinations,
        )
        .select_related("destination")
        .first()
    )

    if permission and permission.is_allowed:

        if permission.destination.allow_direct_messages:

            return

    # --------------------------------------------------------
    # Direct messages disabled / user not allowed
    # --------------------------------------------------------

    # Do not automatically allow private messages.
    # The UI/database permission remains the source of truth.

    return