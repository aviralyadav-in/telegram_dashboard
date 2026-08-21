from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)

from publisher.models import PublishedChannel

from .models import PublishingSchedule
from .services import (
    cancel_schedule,
    prepare_schedule,
    start_schedule,
)


# ============================================================
# SCHEDULE LIST
# ============================================================

def schedule_list(request):

    schedules = (
        PublishingSchedule.objects
        .select_related("destination")
        .all()
    )

    return render(
        request,
        "scheduler/schedules.html",
        {
            "schedules": schedules,
        },
    )


# ============================================================
# CREATE + START SCHEDULE
# ============================================================

def create_schedule(request):

    channels = (
        PublishedChannel.objects
        .filter(
            status="active",
        )
        .select_related("bot")
        .order_by("name")
    )

    if request.method == "POST":

        try:

            # ------------------------------------------------
            # DESTINATION
            # ------------------------------------------------

            destination_id = request.POST.get(
                "destination"
            )

            if not destination_id:
                raise ValueError(
                    "Please select a destination channel/group."
                )

            destination = get_object_or_404(
                PublishedChannel,
                id=destination_id,
                status="active",
            )

            # ------------------------------------------------
            # DATE FILTER
            # ------------------------------------------------

            date_from = (
                request.POST.get(
                    "date_from"
                ) or None
            )

            date_to = (
                request.POST.get(
                    "date_to"
                ) or None
            )

            if (
                date_from
                and date_to
                and date_from > date_to
            ):
                raise ValueError(
                    "Date From cannot be after Date To."
                )

            # ------------------------------------------------
            # PRICE FILTER
            # ------------------------------------------------

            min_price_text = (
                request.POST.get(
                    "min_price"
                ) or ""
            ).strip()

            max_price_text = (
                request.POST.get(
                    "max_price"
                ) or ""
            ).strip()

            try:

                min_price = (
                    Decimal(min_price_text)
                    if min_price_text
                    else None
                )

                max_price = (
                    Decimal(max_price_text)
                    if max_price_text
                    else None
                )

            except InvalidOperation:

                raise ValueError(
                    "Please enter a valid price."
                )

            if (
                min_price is not None
                and max_price is not None
                and min_price > max_price
            ):

                raise ValueError(
                    "Minimum price cannot be greater "
                    "than maximum price."
                )

            if (
                min_price is not None
                and min_price < 0
            ):

                raise ValueError(
                    "Minimum price cannot be negative."
                )

            if (
                max_price is not None
                and max_price < 0
            ):

                raise ValueError(
                    "Maximum price cannot be negative."
                )

            # ------------------------------------------------
            # RATING FILTER
            # ------------------------------------------------

            min_rating_text = (
                request.POST.get(
                    "min_rating"
                ) or ""
            ).strip()

            try:

                min_rating = (
                    Decimal(min_rating_text)
                    if min_rating_text
                    else None
                )

            except InvalidOperation:

                raise ValueError(
                    "Please enter a valid rating."
                )

            if (
                min_rating is not None
                and (
                    min_rating < 0
                    or min_rating > 5
                )
            ):

                raise ValueError(
                    "Rating must be between 0 and 5."
                )

            # ------------------------------------------------
            # NUMBER OF DEALS
            # ------------------------------------------------

            try:

                deal_limit = int(
                    request.POST.get(
                        "deal_limit",
                        5,
                    )
                )

            except ValueError:

                raise ValueError(
                    "Number of deals must be a valid number."
                )

            if deal_limit < 1:

                raise ValueError(
                    "Number of deals must be at least 1."
                )

            if deal_limit > 100:

                raise ValueError(
                    "Maximum 100 deals can be scheduled."
                )

            # ------------------------------------------------
            # INTERVAL
            # ------------------------------------------------

            try:

                interval_seconds = int(
                    request.POST.get(
                        "interval_seconds",
                        10,
                    )
                )

            except ValueError:

                raise ValueError(
                    "Interval must be a valid number."
                )

            if interval_seconds < 1:

                raise ValueError(
                    "Interval must be at least 1 second."
                )

            # ------------------------------------------------
            # CREATE SCHEDULE
            # ------------------------------------------------

            schedule = PublishingSchedule.objects.create(
                destination=destination,

                date_from=date_from,
                date_to=date_to,

                min_price=min_price,
                max_price=max_price,

                min_rating=min_rating,

                deal_limit=deal_limit,

                interval_seconds=interval_seconds,

                status="pending",
            )

            # ------------------------------------------------
            # FILTER DEALS + CREATE QUEUE
            # ------------------------------------------------

            deals = prepare_schedule(
                schedule
            )

            if not deals:

                schedule.status = "completed"

                schedule.error = (
                    "No deals matched the selected filters."
                )

                schedule.save(
                    update_fields=[
                        "status",
                        "error",
                        "updated_at",
                    ]
                )

                messages.warning(
                    request,
                    "No deals matched your selected filters.",
                )

                return redirect(
                    "schedule_list"
                )

            # ------------------------------------------------
            # START BACKGROUND PUBLISHING
            # ------------------------------------------------

            started = start_schedule(
                schedule.id
            )

            if not started:

                schedule.status = "failed"

                schedule.error = (
                    "Could not start the publishing schedule."
                )

                schedule.save(
                    update_fields=[
                        "status",
                        "error",
                        "updated_at",
                    ]
                )

                messages.error(
                    request,
                    "Could not start the schedule.",
                )

                return redirect(
                    "schedule_list"
                )

            messages.success(
                request,
                (
                    f"{len(deals)} matching deal(s) "
                    f"found. Automatic publishing started "
                    f"to {destination.name}."
                ),
            )

            return redirect(
                "schedule_detail",
                schedule_id=schedule.id,
            )

        except ValueError as error:

            messages.error(
                request,
                str(error),
            )

        except Exception as error:

            messages.error(
                request,
                f"Unable to create schedule: {error}",
            )

    return render(
        request,
        "scheduler/create_schedule.html",
        {
            "channels": channels,
        },
    )


# ============================================================
# SCHEDULE DETAIL
# ============================================================

def schedule_detail(
    request,
    schedule_id,
):

    schedule = get_object_or_404(
        PublishingSchedule.objects
        .select_related(
            "destination",
        ),
        id=schedule_id,
    )

    items = (
        schedule.items
        .select_related("deal")
        .all()
        .order_by("position")
    )

    return render(
        request,
        "scheduler/schedule_detail.html",
        {
            "schedule": schedule,
            "items": items,
        },
    )


# ============================================================
# CANCEL SCHEDULE
# ============================================================

def schedule_cancel(
    request,
    schedule_id,
):

    schedule = get_object_or_404(
        PublishingSchedule,
        id=schedule_id,
    )

    if schedule.status == "running":

        cancel_schedule(
            schedule.id
        )

        messages.success(
            request,
            "Publishing schedule cancelled.",
        )

    elif schedule.status in {
        "completed",
        "cancelled",
        "failed",
    }:

        messages.info(
            request,
            "This schedule is no longer running.",
        )

    else:

        cancel_schedule(
            schedule.id
        )

        messages.success(
            request,
            "Publishing schedule cancelled.",
        )

    return redirect(
        "schedule_list"
    )