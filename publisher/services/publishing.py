import asyncio

from django.db import transaction

from publisher.models import (
    PublishedChannel,
    PublishedDeal,
)

from publisher.telegram_bot import (
    publish_to_telegram,
)

from publisher.activity import (
    log_activity,
)


def publish_deal_to_channel(
    deal,
    channel,
):

    if not channel.bot:
        raise ValueError(
            "No bot connected to destination."
        )

    if channel.status != "active":
        raise ValueError(
            "Destination is inactive."
        )

    target = (
        channel.chat_id
        if channel.chat_id
        else channel.username
    )

    if not target:
        raise ValueError(
            "Destination Chat ID/Username is missing."
        )

    already_published = (
        PublishedDeal.objects
        .filter(
            deal=deal,
            channel=channel,
            status="success",
        )
        .exists()
    )

    if already_published:

        return {
            "status": "skipped",
            "reason": "Already published",
        }

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

            record = PublishedDeal.objects.create(
                deal=deal,
                channel=channel,
                status="success",
                telegram_message_id=(
                    getattr(
                        sent_message,
                        "id",
                        None,
                    )
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
                f"{channel.name}."
            ),
            bot=channel.bot,
            destination=channel,
            deal=deal,
        )

        return {
            "status": "success",
            "record_id": record.id,
        }

    except Exception as error:

        try:

            PublishedDeal.objects.create(
                deal=deal,
                channel=channel,
                status="failed",
                telegram_message_id=None,
                error=str(error),
            )

        except Exception:
            pass

        log_activity(
            event_type="deal_publish_failed",
            message=(
                f"Deal #{deal.id} failed to publish "
                f"to {channel.name}. "
                f"Reason: {error}"
            ),
            bot=channel.bot,
            destination=channel,
            deal=deal,
        )

        return {
            "status": "failed",
            "error": str(error),
        }


def auto_publish_deal(
    deal,
):

    channels = list(
        PublishedChannel.objects
        .filter(
            status="active",
            auto_publish_deals=True,
        )
        .select_related("bot")
    )

    if not channels:
        return []

    results = []

    for channel in channels:

        result = publish_deal_to_channel(
            deal,
            channel,
        )

        results.append(
            {
                "channel": channel.id,
                **result,
            }
        )

    return results