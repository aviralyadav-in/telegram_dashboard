import asyncio

from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render
)

from deals.models import Deal

from .models import (
    TelegramBot,
    PublishedChannel,
    PublishedDeal,
    TelegramUser,
    UserDestinationPermission
)

from .telegram_bot import (
    verify_bot_token,
    find_telegram_chat,
    test_telegram_chat,
    publish_to_telegram
)


def channel_list(request):

    bots = TelegramBot.objects.all()

    channels = PublishedChannel.objects.select_related(
        "bot"
    ).all()

    users = TelegramUser.objects.all()[:20]

    return render(
        request,
        "publisher/channels.html",
        {
            "bots": bots,
            "channels": channels,
            "users": users
        }
    )


def add_bot(request):

    if request.method != "POST":
        return redirect("channels")

    name = request.POST.get(
        "name",
        ""
    ).strip()

    token = request.POST.get(
        "bot_token",
        ""
    ).strip()

    if not name or not token:

        messages.error(
            request,
            "Bot name and token are required."
        )

        return redirect("channels")

    if TelegramBot.objects.filter(
        bot_token=token
    ).exists():

        messages.error(
            request,
            "This bot is already connected."
        )

        return redirect("channels")

    try:

        bot_info = asyncio.run(
            verify_bot_token(token)
        )

        TelegramBot.objects.create(
            name=name,
            bot_token=token,
            username=bot_info.username,
            bot_id=bot_info.id,
            status="active"
        )

        messages.success(
            request,
            f"Bot connected successfully: @{bot_info.username}"
        )

    except Exception as error:

        messages.error(
            request,
            f"Invalid Telegram bot token: {error}"
        )

    return redirect("channels")


def delete_bot(request, bot_id):

    bot = get_object_or_404(
        TelegramBot,
        id=bot_id
    )

    if request.method == "POST":

        bot.delete()

        messages.success(
            request,
            "Bot deleted successfully."
        )

    return redirect("channels")


def add_channel(request):

    if request.method != "POST":
        return redirect("channels")

    name = request.POST.get(
        "name",
        ""
    ).strip()

    username = request.POST.get(
        "username",
        ""
    ).strip()

    chat_id = request.POST.get(
        "chat_id",
        ""
    ).strip()

    chat_type = request.POST.get(
        "chat_type",
        "channel"
    )

    bot_id = request.POST.get("bot_id")

    description = request.POST.get(
        "description",
        ""
    ).strip()

    auto_allow_users = (
        request.POST.get("auto_allow_users")
        == "on"
    )

    allow_direct_messages = (
        request.POST.get("allow_direct_messages")
        == "on"
    )

    if not name:

        messages.error(
            request,
            "Destination name is required."
        )

        return redirect("channels")

    if chat_type not in {
        "channel",
        "group"
    }:

        chat_type = "channel"

    if username:

        username = username.lstrip("@")
        username = "@" + username

    if not username and not chat_id:

        messages.error(
            request,
            "Username or Chat ID is required."
        )

        return redirect("channels")

    parsed_chat_id = None

    if chat_id:

        try:
            parsed_chat_id = int(chat_id)

        except ValueError:

            messages.error(
                request,
                "Chat ID must be a valid number."
            )

            return redirect("channels")

    if username and PublishedChannel.objects.filter(
        username__iexact=username
    ).exists():

        messages.error(
            request,
            "This destination already exists."
        )

        return redirect("channels")

    if (
        parsed_chat_id
        and PublishedChannel.objects.filter(
            chat_id=parsed_chat_id
        ).exists()
    ):

        messages.error(
            request,
            "This Chat ID already exists."
        )

        return redirect("channels")

    bot = None

    if bot_id:

        bot = get_object_or_404(
            TelegramBot,
            id=bot_id
        )

    PublishedChannel.objects.create(
        name=name,
        username=username or "",
        chat_id=parsed_chat_id,
        chat_type=chat_type,
        bot=bot,
        description=description,
        auto_allow_users=auto_allow_users,
        allow_direct_messages=allow_direct_messages,
        status="active"
    )

    messages.success(
        request,
        "Destination added successfully."
    )

    return redirect("channels")


def edit_channel(request, channel_id):

    channel = get_object_or_404(
        PublishedChannel,
        id=channel_id
    )

    bots = TelegramBot.objects.all()

    if request.method == "POST":

        name = request.POST.get(
            "name",
            ""
        ).strip()

        username = request.POST.get(
            "username",
            ""
        ).strip()

        chat_id = request.POST.get(
            "chat_id",
            ""
        ).strip()

        chat_type = request.POST.get(
            "chat_type",
            "channel"
        )

        bot_id = request.POST.get("bot_id")

        description = request.POST.get(
            "description",
            ""
        ).strip()

        status = request.POST.get(
            "status",
            "active"
        )

        auto_allow_users = (
            request.POST.get("auto_allow_users")
            == "on"
        )

        allow_direct_messages = (
            request.POST.get("allow_direct_messages")
            == "on"
        )

        if not name:

            messages.error(
                request,
                "Destination name is required."
            )

            return redirect(
                "edit-channel",
                channel_id=channel.id
            )

        if chat_type not in {
            "channel",
            "group"
        }:

            chat_type = "channel"

        if status not in {
            "active",
            "inactive"
        }:

            status = "active"

        if username:

            username = username.lstrip("@")
            username = "@" + username

        if not username and not chat_id:

            messages.error(
                request,
                "Username or Chat ID is required."
            )

            return redirect(
                "edit-channel",
                channel_id=channel.id
            )

        if username:

            duplicate = PublishedChannel.objects.filter(
                username__iexact=username
            ).exclude(
                id=channel.id
            ).exists()

            if duplicate:

                messages.error(
                    request,
                    "Another destination has this username."
                )

                return redirect(
                    "edit-channel",
                    channel_id=channel.id
                )

        parsed_chat_id = None

        if chat_id:

            try:

                parsed_chat_id = int(chat_id)

            except ValueError:

                messages.error(
                    request,
                    "Chat ID must be a valid number."
                )

                return redirect(
                    "edit-channel",
                    channel_id=channel.id
                )

            duplicate_chat_id = PublishedChannel.objects.filter(
                chat_id=parsed_chat_id
            ).exclude(
                id=channel.id
            ).exists()

            if duplicate_chat_id:

                messages.error(
                    request,
                    "Another destination has this Chat ID."
                )

                return redirect(
                    "edit-channel",
                    channel_id=channel.id
                )

        bot = None

        if bot_id:

            bot = get_object_or_404(
                TelegramBot,
                id=bot_id
            )

        channel.name = name
        channel.username = username or ""
        channel.chat_id = parsed_chat_id
        channel.chat_type = chat_type
        channel.bot = bot
        channel.description = description
        channel.status = status
        channel.auto_allow_users = auto_allow_users
        channel.allow_direct_messages = allow_direct_messages

        channel.save()

        messages.success(
            request,
            "Destination updated successfully."
        )

        return redirect("channels")

    return render(
        request,
        "publisher/edit_channel.html",
        {
            "channel": channel,
            "bots": bots
        }
    )


def delete_channel(request, channel_id):

    channel = get_object_or_404(
        PublishedChannel,
        id=channel_id
    )

    if request.method == "POST":

        channel.delete()

        messages.success(
            request,
            "Destination deleted successfully."
        )

    return redirect("channels")


def find_chat(request):

    if request.method != "POST":

        return JsonResponse(
            {
                "success": False,
                "error": "POST request required."
            },
            status=405
        )

    bot_id = request.POST.get("bot_id")

    username = request.POST.get(
        "username",
        ""
    ).strip()

    if not bot_id:

        return JsonResponse({
            "success": False,
            "error": "Please select a bot."
        })

    if not username:

        return JsonResponse({
            "success": False,
            "error": "Username is required."
        })

    bot = get_object_or_404(
        TelegramBot,
        id=bot_id
    )

    try:

        chat = asyncio.run(
            find_telegram_chat(
                bot.bot_token,
                username
            )
        )

        return JsonResponse(
            {
                "success": True,
                "chat": {
                    "id": chat.id,
                    "title": getattr(
                        chat,
                        "title",
                        None
                    ),
                    "username": getattr(
                        chat,
                        "username",
                        None
                    ),
                    "type": chat.type,
                    "description": getattr(
                        chat,
                        "description",
                        None
                    )
                }
            }
        )

    except Exception as error:

        return JsonResponse(
            {
                "success": False,
                "error": str(error)
            }
        )


def test_channel(request, channel_id):

    channel = get_object_or_404(
        PublishedChannel,
        id=channel_id
    )

    if request.method != "POST":
        return redirect("channels")

    if not channel.bot:

        messages.error(
            request,
            "No bot is connected to this destination."
        )

        return redirect("channels")

    target = (
        channel.chat_id
        if channel.chat_id
        else channel.username
    )

    if not target:

        messages.error(
            request,
            "Chat ID or username is required."
        )

        return redirect("channels")

    try:

        asyncio.run(
            test_telegram_chat(
                channel.bot.bot_token,
                target
            )
        )

        messages.success(
            request,
            "Test message sent successfully."
        )

    except Exception as error:

        messages.error(
            request,
            f"Test failed: {error}"
        )

    return redirect("channels")


def publish_page(request):

    deals = Deal.objects.all().order_by(
        "-date"
    )

    channels = PublishedChannel.objects.filter(
        status="active"
    ).select_related(
        "bot"
    ).order_by(
        "name"
    )

    records = PublishedDeal.objects.select_related(
        "deal",
        "channel"
    ).all()[:50]

    return render(
        request,
        "publisher/publish.html",
        {
            "deals": deals,
            "channels": channels,
            "records": records
        }
    )


def publish_deal(request):

    if request.method != "POST":
        return redirect("publish-page")

    deal_id = request.POST.get("deal_id")
    channel_id = request.POST.get("channel_id")

    if not deal_id:

        messages.error(
            request,
            "Please select a deal."
        )

        return redirect("publish-page")

    if not channel_id:

        messages.error(
            request,
            "Please select a destination."
        )

        return redirect("publish-page")

    deal = get_object_or_404(
        Deal,
        id=deal_id
    )

    channel = get_object_or_404(
        PublishedChannel.objects.select_related("bot"),
        id=channel_id,
        status="active"
    )

    if not channel.bot:

        messages.error(
            request,
            "No bot is connected to this destination."
        )

        return redirect("publish-page")

    target = (
        channel.chat_id
        if channel.chat_id
        else channel.username
    )

    if not target:

        messages.error(
            request,
            "Destination Chat ID/Username is missing."
        )

        return redirect("publish-page")

    if PublishedDeal.objects.filter(
        deal=deal,
        channel=channel,
        status="success"
    ).exists():

        messages.warning(
            request,
            "This deal has already been published here."
        )

        return redirect("publish-page")

    try:

        sent_message = asyncio.run(
            publish_to_telegram(
                channel.bot.bot_token,
                target,
                deal.content or "",
                deal.image_path or ""
            )
        )

        with transaction.atomic():

            PublishedDeal.objects.create(
                deal=deal,
                channel=channel,
                status="success",
                telegram_message_id=getattr(
                    sent_message,
                    "id",
                    None
                ),
                error=None
            )

            deal.status = "published"

            deal.save(
                update_fields=[
                    "status",
                    "updated_at"
                ]
            )

        messages.success(
            request,
            "Deal published successfully."
        )

    except Exception as error:

        PublishedDeal.objects.create(
            deal=deal,
            channel=channel,
            status="failed",
            telegram_message_id=None,
            error=str(error)
        )

        messages.error(
            request,
            f"Publishing failed: {error}"
        )

    return redirect("publish-page")


def bulk_publish_deals(request):

    if request.method != "POST":
        return redirect("deal-list")

    deal_ids = request.POST.getlist("deal_ids")
    channel_ids = request.POST.getlist("channel_ids")

    if not deal_ids:

        messages.error(
            request,
            "Please select at least one deal."
        )

        return redirect("deal-list")

    if not channel_ids:

        messages.error(
            request,
            "Please select at least one destination."
        )

        return redirect("deal-list")

    deals = Deal.objects.filter(
        id__in=deal_ids
    )

    channels = PublishedChannel.objects.filter(
        id__in=channel_ids,
        status="active"
    ).select_related("bot")

    success_count = 0
    failed_count = 0
    skipped_count = 0

    for deal in deals:

        deal_published = False

        for channel in channels:

            if not channel.bot:

                failed_count += 1
                continue

            target = (
                channel.chat_id
                if channel.chat_id
                else channel.username
            )

            if not target:

                failed_count += 1
                continue

            already_published = PublishedDeal.objects.filter(
                deal=deal,
                channel=channel,
                status="success"
            ).exists()

            if already_published:

                skipped_count += 1
                continue

            try:

                sent_message = asyncio.run(
                    publish_to_telegram(
                        channel.bot.bot_token,
                        target,
                        deal.content or "",
                        deal.image_path or ""
                    )
                )

                PublishedDeal.objects.create(
                    deal=deal,
                    channel=channel,
                    status="success",
                    telegram_message_id=getattr(
                        sent_message,
                        "id",
                        None
                    )
                )

                success_count += 1
                deal_published = True

            except Exception as error:

                PublishedDeal.objects.create(
                    deal=deal,
                    channel=channel,
                    status="failed",
                    error=str(error)
                )

                failed_count += 1

        if deal_published:

            deal.status = "published"

            deal.save(
                update_fields=[
                    "status",
                    "updated_at"
                ]
            )

    messages.success(
        request,
        (
            f"Publishing completed: "
            f"{success_count} succeeded, "
            f"{failed_count} failed, "
            f"{skipped_count} skipped."
        )
    )

    return redirect("deal-list")


def published_deals(request):

    records = PublishedDeal.objects.select_related(
        "deal",
        "channel"
    ).all()

    return render(
        request,
        "publisher/published_deals.html",
        {
            "records": records
        }
    )


def allow_user(request, permission_id):

    permission = get_object_or_404(
        UserDestinationPermission,
        id=permission_id
    )

    if request.method == "POST":

        permission.is_allowed = True

        permission.save(
            update_fields=[
                "is_allowed",
                "updated_at"
            ]
        )

        messages.success(
            request,
            "User allowed successfully."
        )

    return redirect("channels")


def block_user(request, permission_id):

    permission = get_object_or_404(
        UserDestinationPermission,
        id=permission_id
    )

    if request.method == "POST":

        permission.is_allowed = False

        permission.save(
            update_fields=[
                "is_allowed",
                "updated_at"
            ]
        )

        messages.success(
            request,
            "User blocked successfully."
        )

    return redirect("channels")