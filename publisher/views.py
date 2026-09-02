import asyncio
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from deals.models import Deal

from .models import (
    TelegramBot,
    PublishedChannel,
    PublishedDeal,
    TelegramUser,
    ChannelUser,
    UserDestinationPermission,
    ActivityLog,
)

from .activity import log_activity

from .telegram_bot import (
    verify_bot_token,
    find_telegram_chat,
    test_telegram_chat,
    publish_to_telegram,
    set_user_message_permission,
)


# ============================================================
# CHANNEL LIST / DASHBOARD
# ============================================================

def channel_list(request):

    bots = (
        TelegramBot.objects
        .all()
        .order_by("-id")
    )

    channels = (
        PublishedChannel.objects
        .select_related("bot")
        .all()
        .order_by("-id")
    )

    users = (
        TelegramUser.objects
        .all()
        .order_by("-last_seen_at", "-id")[:100]
    )

    permissions = (
        UserDestinationPermission.objects
        .select_related(
            "user",
            "destination",
            "destination__bot",
        )
        .order_by("-updated_at", "-id")[:200]
    )

    channel_users_queryset = (
        ChannelUser.objects
        .select_related(
            "channel",
            "user",
        )
        .order_by("-joined_at", "-id")[:200]
    )

    membership_paginator = Paginator(
        channel_users_queryset,
        5
    )

    membership_page_number = request.GET.get(
        "membership_page",
        1
    )

    channel_users = membership_paginator.get_page(
        membership_page_number
    )

    activities = (
        ActivityLog.objects
        .select_related(
            "bot",
            "destination",
            "user",
        )
        .order_by("-created_at", "-id")[:100]
    )

    return render(
        request,
        "publisher/channels.html",
        {
            "bots": bots,
            "channels": channels,
            "users": users,
            "permissions": permissions,
            "channel_users": channel_users,
            "activities": activities,
        },
    )


# ============================================================
# ADD BOT
# ============================================================

def add_bot(request):

    if request.method != "POST":
        return redirect("channels")

    name = request.POST.get("name", "").strip()
    token = request.POST.get("bot_token", "").strip()

    if not name or not token:
        messages.error(
            request,
            "Bot name and token are required.",
        )
        return redirect("channels")

    if TelegramBot.objects.filter(
        bot_token=token
    ).exists():

        messages.error(
            request,
            "This bot is already connected.",
        )
        return redirect("channels")

    try:

        bot_info = asyncio.run(
            verify_bot_token(token)
        )

        bot = TelegramBot.objects.create(
            name=name,
            bot_token=token,
            username=bot_info.username,
            bot_id=bot_info.id,
            status="active",
        )

        log_activity(
            event_type="bot_created",
            message=(
                f"Telegram bot "
                f"@{bot_info.username or bot_info.id} "
                f"was created and connected."
            ),
            bot=bot,
        )

        messages.success(
            request,
            f"Bot connected successfully: "
            f"@{bot_info.username}",
        )

    except Exception as error:

        messages.error(
            request,
            f"Invalid Telegram bot token: {error}",
        )

    return redirect("channels")


# ============================================================
# DELETE BOT
# ============================================================

def delete_bot(request, bot_id):

    bot = get_object_or_404(
        TelegramBot,
        id=bot_id,
    )

    if request.method == "POST":

        try:

            log_activity(
                event_type="bot_deleted",
                message=(
                    f"Telegram bot "
                    f"@{bot.username or bot.name} "
                    f"was deleted."
                ),
                bot=bot,
            )

        except Exception:
            pass

        bot.delete()

        messages.success(
            request,
            "Telegram bot deleted successfully.",
        )

    return redirect("channels")


# ============================================================
# ADD CHANNEL / GROUP
# ============================================================

def add_channel(request):

    if request.method != "POST":
        return redirect("channels")

    name = request.POST.get("name", "").strip()
    username = request.POST.get("username", "").strip()
    chat_id = request.POST.get("chat_id", "").strip()

    chat_type = request.POST.get(
        "chat_type",
        "channel",
    )

    bot_id = request.POST.get("bot_id")

    description = request.POST.get(
        "description",
        "",
    ).strip()

    auto_allow_users = (
        request.POST.get("auto_allow_users") == "on"
    )

    allow_direct_messages = (
        request.POST.get("allow_direct_messages") == "on"
    )

    auto_publish_deals = (
        request.POST.get("auto_publish_deals") == "on"
    )

    send_welcome_message_enabled = (
        request.POST.get("send_welcome_message") == "on"
    )

    welcome_message = request.POST.get(
        "welcome_message",
        "",
    ).strip()

    if not name:

        messages.error(
            request,
            "Destination name is required.",
        )

        return redirect("channels")

    if chat_type not in {
        "channel",
        "group",
    }:

        chat_type = "channel"

    if username:

        username = username.lstrip("@")
        username = "@" + username

    if not username and not chat_id:

        messages.error(
            request,
            "Username or Chat ID is required.",
        )

        return redirect("channels")

    parsed_chat_id = None

    if chat_id:

        try:
            parsed_chat_id = int(chat_id)

        except ValueError:

            messages.error(
                request,
                "Chat ID must be a valid number.",
            )

            return redirect("channels")

    if username:

        if PublishedChannel.objects.filter(
            username__iexact=username
        ).exists():

            messages.error(
                request,
                "This destination already exists.",
            )

            return redirect("channels")

    if parsed_chat_id is not None:

        if PublishedChannel.objects.filter(
            chat_id=parsed_chat_id
        ).exists():

            messages.error(
                request,
                "This Chat ID already exists.",
            )

            return redirect("channels")

    bot = None

    if bot_id:

        bot = get_object_or_404(
            TelegramBot,
            id=bot_id,
        )

        if bot.status != "active":

            messages.error(
                request,
                "Selected bot is not active.",
            )

            return redirect("channels")

    channel = PublishedChannel.objects.create(

        name=name,

        username=username or "",

        chat_id=parsed_chat_id,

        chat_type=chat_type,

        bot=bot,

        description=description,

        auto_allow_users=auto_allow_users,

        allow_direct_messages=allow_direct_messages,

        auto_publish_deals=auto_publish_deals,

        send_welcome_message=(
            send_welcome_message_enabled
        ),

        welcome_message=(
            welcome_message
            or PublishedChannel._meta
            .get_field("welcome_message")
            .get_default()
        ),

        status="active",
    )

    log_activity(
        event_type="destination_created",
        message=(
            f"Destination '{channel.name}' "
            f"was created."
        ),
        bot=bot,
        destination=channel,
    )

    # --------------------------------------------------------
    # TELEGRAM SYNC
    # --------------------------------------------------------

    if bot:

        target = (
            channel.chat_id
            if channel.chat_id
            else channel.username
        )

        if target:

            try:

                chat = asyncio.run(
                    find_telegram_chat(
                        bot.bot_token,
                        str(target),
                    )
                )

                channel.chat_id = chat.id

                if getattr(chat, "username", None):

                    channel.username = (
                        "@"
                        + chat.username.lstrip("@")
                    )

                if getattr(
                    chat,
                    "description",
                    None,
                ):

                    channel.description = (
                        chat.description
                    )

                if chat.type in {
                    "group",
                    "supergroup",
                }:

                    channel.chat_type = "group"

                elif chat.type == "channel":

                    channel.chat_type = "channel"

                channel.save()

                log_activity(
                    event_type="destination_updated",
                    message=(
                        f"Destination '{channel.name}' "
                        f"was synchronized with Telegram."
                    ),
                    bot=bot,
                    destination=channel,
                )

                messages.success(
                    request,
                    (
                        f"{name} connected successfully "
                        f"with @{bot.username}."
                    ),
                )

            except Exception as error:

                messages.warning(
                    request,
                    (
                        "Destination created, but Telegram "
                        f"verification failed: {error}"
                    ),
                )

    else:

        messages.success(
            request,
            "Destination added successfully.",
        )

    return redirect("channels")


# ============================================================
# EDIT CHANNEL / GROUP
# ============================================================

def edit_channel(request, channel_id):

    channel = get_object_or_404(
        PublishedChannel,
        id=channel_id,
    )

    bots = (
        TelegramBot.objects
        .all()
        .order_by("-id")
    )

    if request.method == "POST":

        name = request.POST.get(
            "name",
            "",
        ).strip()

        username = request.POST.get(
            "username",
            "",
        ).strip()

        chat_id = request.POST.get(
            "chat_id",
            "",
        ).strip()

        chat_type = request.POST.get(
            "chat_type",
            "channel",
        )

        bot_id = request.POST.get("bot_id")

        description = request.POST.get(
            "description",
            "",
        ).strip()

        status = request.POST.get(
            "status",
            "active",
        )

        auto_allow_users = (
            request.POST.get(
                "auto_allow_users"
            ) == "on"
        )

        allow_direct_messages = (
            request.POST.get(
                "allow_direct_messages"
            ) == "on"
        )

        auto_publish_deals = (
            request.POST.get(
                "auto_publish_deals"
            ) == "on"
        )

        send_welcome_message_enabled = (
            request.POST.get(
                "send_welcome_message"
            ) == "on"
        )

        welcome_message = request.POST.get(
            "welcome_message",
            "",
        ).strip()

        # ----------------------------------------------------
        # VALIDATION
        # ----------------------------------------------------

        if not name:

            messages.error(
                request,
                "Destination name is required.",
            )

            return redirect(
                "edit-channel",
                channel_id=channel.id,
            )

        if chat_type not in {
            "channel",
            "group",
        }:

            chat_type = "channel"

        if status not in {
            "active",
            "inactive",
        }:

            status = "active"

        if username:

            username = username.lstrip("@")
            username = "@" + username

        if not username and not chat_id:

            messages.error(
                request,
                "Username or Chat ID is required.",
            )

            return redirect(
                "edit-channel",
                channel_id=channel.id,
            )

        parsed_chat_id = None

        if chat_id:

            try:

                parsed_chat_id = int(chat_id)

            except ValueError:

                messages.error(
                    request,
                    "Chat ID must be a valid number.",
                )

                return redirect(
                    "edit-channel",
                    channel_id=channel.id,
                )

        # ----------------------------------------------------
        # DUPLICATE USERNAME
        # ----------------------------------------------------

        if username:

            duplicate = (
                PublishedChannel.objects
                .filter(
                    username__iexact=username
                )
                .exclude(
                    id=channel.id
                )
                .exists()
            )

            if duplicate:

                messages.error(
                    request,
                    "Another destination has this username.",
                )

                return redirect(
                    "edit-channel",
                    channel_id=channel.id,
                )

        # ----------------------------------------------------
        # DUPLICATE CHAT ID
        # ----------------------------------------------------

        if parsed_chat_id is not None:

            duplicate = (
                PublishedChannel.objects
                .filter(
                    chat_id=parsed_chat_id
                )
                .exclude(
                    id=channel.id
                )
                .exists()
            )

            if duplicate:

                messages.error(
                    request,
                    "Another destination has this Chat ID.",
                )

                return redirect(
                    "edit-channel",
                    channel_id=channel.id,
                )

        # ----------------------------------------------------
        # BOT
        # ----------------------------------------------------

        bot = None

        if bot_id:

            bot = get_object_or_404(
                TelegramBot,
                id=bot_id,
            )

            if bot.status != "active":

                messages.error(
                    request,
                    "Selected bot is not active.",
                )

                return redirect(
                    "edit-channel",
                    channel_id=channel.id,
                )

        old_name = channel.name

        # ----------------------------------------------------
        # UPDATE
        # ----------------------------------------------------

        channel.name = name

        channel.username = username or ""

        channel.chat_id = parsed_chat_id

        channel.chat_type = chat_type

        channel.bot = bot

        channel.description = description

        channel.status = status

        channel.auto_allow_users = (
            auto_allow_users
        )

        channel.allow_direct_messages = (
            allow_direct_messages
        )

        channel.auto_publish_deals = (
            auto_publish_deals
        )

        channel.send_welcome_message = (
            send_welcome_message_enabled
        )

        # IMPORTANT:
        # Empty textarea ko purana welcome message
        # overwrite nahi karna.
        if welcome_message:

            channel.welcome_message = (
                welcome_message
            )

        channel.save()

        log_activity(
            event_type="destination_updated",
            message=(
                f"Destination '{old_name}' "
                f"was updated. "
                f"Current name: '{channel.name}'."
            ),
            bot=bot,
            destination=channel,
        )

        messages.success(
            request,
            "Destination updated successfully.",
        )

        return redirect("channels")

    return render(
        request,
        "publisher/edit_channel.html",
        {
            "channel": channel,
            "bots": bots,
        },
    )


# ============================================================
# DELETE CHANNEL
# ============================================================

def delete_channel(request, channel_id):

    channel = get_object_or_404(
        PublishedChannel,
        id=channel_id,
    )

    if request.method == "POST":

        channel_name = channel.name
        bot = channel.bot

        try:

            log_activity(
                event_type="destination_deleted",
                message=(
                    f"Destination '{channel_name}' "
                    f"was deleted."
                ),
                bot=bot,
                destination=channel,
            )

        except Exception:
            pass

        channel.delete()

        messages.success(
            request,
            "Destination deleted successfully.",
        )

    return redirect("channels")


# ============================================================
# FIND TELEGRAM CHAT
# ============================================================

def find_chat(request):

    if request.method != "POST":

        return JsonResponse(
            {
                "success": False,
                "error": "POST request required.",
            },
            status=405,
        )

    bot_id = request.POST.get("bot_id")

    username = request.POST.get(
        "username",
        "",
    ).strip()

    if not bot_id:

        return JsonResponse(
            {
                "success": False,
                "error": "Please select a bot.",
            }
        )

    if not username:

        return JsonResponse(
            {
                "success": False,
                "error": "Username is required.",
            }
        )

    bot = get_object_or_404(
        TelegramBot,
        id=bot_id,
    )

    if bot.status != "active":

        return JsonResponse(
            {
                "success": False,
                "error": "Selected bot is not active.",
            }
        )

    try:

        chat = asyncio.run(
            find_telegram_chat(
                bot.bot_token,
                username,
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
                        None,
                    ),
                    "username": getattr(
                        chat,
                        "username",
                        None,
                    ),
                    "type": chat.type,
                    "description": getattr(
                        chat,
                        "description",
                        None,
                    ),
                },
            }
        )

    except Exception as error:

        return JsonResponse(
            {
                "success": False,
                "error": str(error),
            }
        )


# ============================================================
# TEST CHANNEL
# ============================================================

def test_channel(request, channel_id):

    channel = get_object_or_404(
        PublishedChannel.objects.select_related(
            "bot"
        ),
        id=channel_id,
    )

    if request.method != "POST":
        return redirect("channels")

    if not channel.bot:

        messages.error(
            request,
            "No bot is connected to this destination.",
        )

        return redirect("channels")

    if channel.bot.status != "active":

        messages.error(
            request,
            "Connected bot is not active.",
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
            "Chat ID or username is required.",
        )

        return redirect("channels")

    try:

        asyncio.run(
            test_telegram_chat(
                channel.bot.bot_token,
                target,
            )
        )

        messages.success(
            request,
            f"Connectivity successful: "
            f"{channel.name}",
        )

    except Exception as error:

        messages.error(
            request,
            f"Connectivity failed: {error}",
        )

    return redirect("channels")


# ============================================================
# PUBLISH PAGE

def publish_page(request):

    deals = (
        Deal.objects
        .all()
        .order_by("-date", "-id")
    )

    channels = (
        PublishedChannel.objects
        .filter(status="active")
        .select_related("bot")
        .order_by("name")
    )

    records = (
        PublishedDeal.objects
        .select_related(
            "deal",
            "channel",
        )
        .order_by("-published_at", "-id")
    )

    total_records = (
        PublishedDeal.objects.count()
    )

    successful_records = (
        PublishedDeal.objects
        .filter(status="success")
        .count()
    )

    failed_records = (
        PublishedDeal.objects
        .filter(status="failed")
        .count()
    )

    skipped_records = (
        PublishedDeal.objects
        .filter(status="skipped")
        .count()
    )

    active_destinations = (
        channels.count()
    )

    connected_destinations = (
        PublishedChannel.objects
        .filter(
            status="active",
            bot__isnull=False,
            bot__status="active",
        )
        .count()
    )

    return render(
        request,
        "publisher/publish.html",
        {
            "deals": deals,
            "channels": channels,
            "records": records[:50],
            "total_records": total_records,
            "successful_records": successful_records,
            "failed_records": failed_records,
            "skipped_records": skipped_records,
            "active_destinations": active_destinations,
            "connected_destinations": connected_destinations,
            "published_count": successful_records,
            "publish_success_count": successful_records,
            "publish_failed_count": failed_records,
        },
    )


# ============================================================
# SINGLE PUBLISH
# ============================================================

def publish_deal(request):

    if request.method != "POST":
        return redirect("publish-page")

    deal_id = request.POST.get("deal_id")
    channel_id = request.POST.get("channel_id")

    if not deal_id:

        messages.error(
            request,
            "Please select a deal.",
        )

        return redirect("publish-page")

    if not channel_id:

        messages.error(
            request,
            "Please select a destination.",
        )

        return redirect("publish-page")

    deal = get_object_or_404(
        Deal,
        id=deal_id,
    )

    channel = get_object_or_404(
        PublishedChannel.objects.select_related(
            "bot"
        ),
        id=channel_id,
        status="active",
    )

    if not channel.bot:

        messages.error(
            request,
            "No bot is connected to this destination.",
        )

        return redirect("publish-page")

    if channel.bot.status != "active":

        messages.error(
            request,
            "Connected bot is not active.",
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
            "Destination Chat ID/Username is missing.",
        )

        return redirect("publish-page")

    if PublishedDeal.objects.filter(
        deal=deal,
        channel=channel,
        status="success",
    ).exists():

        messages.warning(
            request,
            "This deal has already been published here.",
        )

        return redirect("publish-page")

    try:

        sent_message = asyncio.run(
            publish_to_telegram(
                channel.bot.bot_token,
                target,
                deal.content or "",
                deal.image_path or "",
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
                    None,
                ),
                error=None,
            )

            deal.status = "published"

            deal.save(
                update_fields=[
                    "status",
                    "updated_at",
                ]
            )

        log_activity(
            event_type="deal_published",
            message=(
                f"Deal #{deal.id} was published "
                f"successfully to "
                f"'{channel.name}'."
            ),
            bot=channel.bot,
            destination=channel,
        )

        messages.success(
            request,
            (
                f"Deal #{deal.id} published "
                f"successfully to "
                f"{channel.name}."
            ),
        )

    except Exception as error:

        PublishedDeal.objects.create(
            deal=deal,
            channel=channel,
            status="failed",
            telegram_message_id=None,
            error=str(error),
        )

        log_activity(
            event_type="deal_publish_failed",
            message=(
                f"Deal #{deal.id} failed to publish "
                f"to '{channel.name}'. "
                f"Error: {error}"
            ),
            bot=channel.bot,
            destination=channel,
        )

        messages.error(
            request,
            f"Publishing failed: {error}",
        )

    return redirect("publish-page")


# ============================================================
# BULK PUBLISH
# ============================================================

def bulk_publish_deals(request):

    if request.method != "POST":
        return redirect("deal-list")

    deal_ids = request.POST.getlist("deal_ids")
    channel_ids = request.POST.getlist("channel_ids")

    if not deal_ids:

        messages.error(
            request,
            "Please select at least one deal.",
        )

        return redirect("deal-list")

    if not channel_ids:

        messages.error(
            request,
            "Please select at least one destination.",
        )

        return redirect("deal-list")

    deals = Deal.objects.filter(
        id__in=deal_ids
    )

    channels = (
        PublishedChannel.objects
        .filter(
            id__in=channel_ids,
            status="active",
        )
        .select_related("bot")
    )

    success_count = 0
    failed_count = 0
    skipped_count = 0

    for deal in deals:

        deal_published = False

        for channel in channels:

            if not channel.bot:

                failed_count += 1

                continue

            if channel.bot.status != "active":

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

            if PublishedDeal.objects.filter(
                deal=deal,
                channel=channel,
                status="success",
            ).exists():

                PublishedDeal.objects.create(
                    deal=deal,
                    channel=channel,
                    status="skipped",
                    error="Already published here.",
                )

                skipped_count += 1

                continue

            try:

                sent_message = asyncio.run(
                    publish_to_telegram(
                        channel.bot.bot_token,
                        target,
                        deal.content or "",
                        deal.image_path or "",
                    )
                )

                PublishedDeal.objects.create(
                    deal=deal,
                    channel=channel,
                    status="success",
                    telegram_message_id=getattr(
                        sent_message,
                        "id",
                        None,
                    ),
                    error=None,
                )

                success_count += 1
                deal_published = True

                log_activity(
                    event_type="deal_published",
                    message=(
                        f"Deal #{deal.id} was published "
                        f"successfully to "
                        f"'{channel.name}'."
                    ),
                    bot=channel.bot,
                    destination=channel,
                )

            except Exception as error:

                PublishedDeal.objects.create(
                    deal=deal,
                    channel=channel,
                    status="failed",
                    telegram_message_id=None,
                    error=str(error),
                )

                failed_count += 1

        if deal_published:

            deal.status = "published"

            deal.save(
                update_fields=[
                    "status",
                    "updated_at",
                ]
            )

    messages.success(
        request,
        (
            f"Publishing completed: "
            f"{success_count} succeeded, "
            f"{failed_count} failed, "
            f"{skipped_count} skipped."
        ),
    )

    return redirect("deal-list")


# ============================================================
# PUBLISHED HISTORY
# ============================================================

def published_deals(request):

    records = (
        PublishedDeal.objects
        .select_related(
            "deal",
            "channel",
        )
        .order_by("-published_at", "-id")
    )

    successful_count = (
        PublishedDeal.objects
        .filter(status="success")
        .count()
    )

    failed_count = (
        PublishedDeal.objects
        .filter(status="failed")
        .count()
    )

    skipped_count = (
        PublishedDeal.objects
        .filter(status="skipped")
        .count()
    )

    return render(
        request,
        "publisher/published_deals.html",
        {
            "records": records,
            "successful_count": successful_count,
            "failed_count": failed_count,
            "skipped_count": skipped_count,
            "published_count": successful_count,
        },
    )


# ============================================================
# ALLOW USER
# ============================================================

def allow_user(request, permission_id):

    if request.method != "POST":
        return redirect("channels")

    permission = get_object_or_404(
        UserDestinationPermission.objects.select_related(
            "user",
            "destination",
            "destination__bot",
        ),
        id=permission_id,
    )

    destination = permission.destination

    if not destination.bot:

        messages.error(
            request,
            "No bot is connected to this destination.",
        )

        return redirect("channels")

    if destination.bot.status != "active":

        messages.error(
            request,
            "Connected bot is inactive.",
        )

        return redirect("channels")

    if not destination.chat_id:

        messages.error(
            request,
            "Destination Chat ID is missing.",
        )

        return redirect("channels")

    # --------------------------------------------------------
    # TELEGRAM GROUP PERMISSION
    # --------------------------------------------------------

    if destination.chat_type == "group":

        try:

            asyncio.run(
                set_user_message_permission(
                    destination.bot.bot_token,
                    destination.chat_id,
                    permission.user.user_id,
                    True,
                )
            )

        except Exception as error:

            messages.error(
                request,
                f"Telegram allow failed: {error}",
            )

            return redirect("channels")

    # --------------------------------------------------------
    # DATABASE
    # --------------------------------------------------------

    permission.is_allowed = True

    permission.can_message = (
        destination.allow_direct_messages
    )

    permission.save(
        update_fields=[
            "is_allowed",
            "can_message",
            "updated_at",
        ]
    )

    ChannelUser.objects.filter(
        channel=destination,
        user=permission.user,
    ).update(
        status="allowed",
    )

    user = permission.user

    username = (
        user.username
        or user.first_name
        or str(user.user_id)
    )

    log_activity(
        event_type="user_allowed",
        message=(
            f"User {username} was allowed "
            f"for '{destination.name}'."
        ),
        bot=destination.bot,
        destination=destination,
        user=user,
    )

    messages.success(
        request,
        (
            f"User {username} is now allowed "
            f"for {destination.name}."
        ),
    )

    return redirect("channels")


# ============================================================
# BLOCK USER
# ============================================================

def block_user(request, permission_id):

    if request.method != "POST":
        return redirect("channels")

    permission = get_object_or_404(
        UserDestinationPermission.objects.select_related(
            "user",
            "destination",
            "destination__bot",
        ),
        id=permission_id,
    )

    destination = permission.destination

    if not destination.bot:

        messages.error(
            request,
            "No bot is connected to this destination.",
        )

        return redirect("channels")

    if destination.bot.status != "active":

        messages.error(
            request,
            "Connected bot is inactive.",
        )

        return redirect("channels")

    if not destination.chat_id:

        messages.error(
            request,
            "Destination Chat ID is missing.",
        )

        return redirect("channels")

    # --------------------------------------------------------
    # TELEGRAM GROUP PERMISSION
    # --------------------------------------------------------

    if destination.chat_type == "group":

        try:

            asyncio.run(
                set_user_message_permission(
                    destination.bot.bot_token,
                    destination.chat_id,
                    permission.user.user_id,
                    False,
                )
            )

        except Exception as error:

            messages.error(
                request,
                f"Telegram block failed: {error}",
            )

            return redirect("channels")

    # --------------------------------------------------------
    # DATABASE
    # --------------------------------------------------------

    permission.is_allowed = False
    permission.can_message = False
    permission.can_publish = False

    permission.save(
        update_fields=[
            "is_allowed",
            "can_message",
            "can_publish",
            "updated_at",
        ]
    )

    ChannelUser.objects.filter(
        channel=destination,
        user=permission.user,
    ).update(
        status="blocked",
    )

    user = permission.user

    username = (
        user.username
        or user.first_name
        or str(user.user_id)
    )

    log_activity(
        event_type="user_blocked",
        message=(
            f"User {username} was blocked "
            f"from '{destination.name}'."
        ),
        bot=destination.bot,
        destination=destination,
        user=user,
    )

    messages.success(
        request,
        (
            f"User {username} is now blocked "
            f"for {destination.name}."
        ),
    )

    return redirect("channels")


# ============================================================
# ACTIVITY HISTORY
# ============================================================

def activity_history(request):

    activities = (
        ActivityLog.objects
        .select_related(
            "bot",
            "destination",
            "user",
        )
        .order_by("-created_at", "-id")
    )

    return render(
        request,
        "publisher/activity.html",
        {
            "activities": activities,
        },
    )