import threading
import time

from django.db import transaction
from django.utils import timezone
from publisher.models import PublishedDeal

from deals.models import Deal

from publisher.services.publishing import (
    publish_deal_to_channel,
)

from .models import (
    PublishingSchedule,
    ScheduledPublishItem,
)


# ============================================================
# RUNNING SCHEDULES
# ============================================================

_running_schedules = {}

_schedule_lock = threading.Lock()


# ============================================================
# GET MATCHING DEALS
# ============================================================

def get_matching_deals(schedule):
 
    queryset = Deal.objects.all()

    # --------------------------------------------------------
    # DATE FILTER
    # --------------------------------------------------------

    if schedule.date_from:
        queryset = queryset.filter(
            date__date__gte=schedule.date_from
        )

    if schedule.date_to:
        queryset = queryset.filter(
            date__date__lte=schedule.date_to
        )

    # --------------------------------------------------------
    # PRICE FILTER
    # --------------------------------------------------------

    if schedule.min_price is not None:
        queryset = queryset.filter(
            price__gte=schedule.min_price
        )

    if schedule.max_price is not None:
        queryset = queryset.filter(
            price__lte=schedule.max_price
        )

    # --------------------------------------------------------
    # RATING FILTER
    # --------------------------------------------------------

    if schedule.min_rating is not None:
        queryset = queryset.filter(
            rating__gte=schedule.min_rating
        )

    # --------------------------------------------------------
    # REJECTED DEALS EXCLUDED
    # --------------------------------------------------------

    queryset = queryset.exclude(
        status="rejected"
    )
    
    published_deal_ids = PublishedDeal.objects.filter(
    channel=schedule.destination,
    status="success",
    ).values_list(
    "deal_id",
    flat=True,
    )

    queryset = queryset.exclude(
    id__in=published_deal_ids
    )

    # --------------------------------------------------------
    # NEWEST FIRST
    # --------------------------------------------------------

    queryset = queryset.order_by(
        "-date",
        "-id",
    )[:schedule.deal_limit]

    return queryset


# ============================================================
# PREPARE SCHEDULE
# ============================================================

def prepare_schedule(schedule):
    """
    Find matching deals and create the publishing queue.
    """

    deals = list(
        get_matching_deals(schedule)
    )

    print(
        f"[SCHEDULER] Schedule #{schedule.id}: "
        f"{len(deals)} matching deal(s) found."
    )

    with transaction.atomic():

        # Remove previous queue
        schedule.items.all().delete()

        queue_items = []

        for position, deal in enumerate(
            deals,
            start=1,
        ):

            queue_items.append(
                ScheduledPublishItem(
                    schedule=schedule,
                    deal=deal,
                    position=position,
                    status="pending",
                )
            )

            print(
                f"[SCHEDULER] Queue position={position} "
                f"deal={deal.id} "
                f"price={deal.price} "
                f"rating={deal.rating}"
            )

        if queue_items:

            ScheduledPublishItem.objects.bulk_create(
                queue_items
            )

        schedule.total_deals = len(
            queue_items
        )

        schedule.published_count = 0
        schedule.failed_count = 0
        schedule.skipped_count = 0
        schedule.status = "pending"
        schedule.error = None

        schedule.save(
            update_fields=[
                "total_deals",
                "published_count",
                "failed_count",
                "skipped_count",
                "status",
                "error",
            ]
        )

    return deals


# ============================================================
# RUN SCHEDULE
# ============================================================

def run_schedule(schedule_id):
    """
    Publish scheduled deals one-by-one.

    Example:

        Deal 1
        wait 10 sec
        Deal 2
        wait 10 sec
        Deal 3
    """

    # --------------------------------------------------------
    # PREVENT DUPLICATE RUNNING
    # --------------------------------------------------------

    with _schedule_lock:

        if schedule_id in _running_schedules:

            print(
                f"[SCHEDULER] Schedule #{schedule_id} "
                f"is already running."
            )

            return False

        stop_event = threading.Event()

        _running_schedules[
            schedule_id
        ] = stop_event

    try:

        print(
            f"[SCHEDULER] Starting schedule #{schedule_id}"
        )

        # ----------------------------------------------------
        # LOAD SCHEDULE
        # ----------------------------------------------------

        schedule = (
            PublishingSchedule.objects
            .select_related(
                "destination",
                "destination__bot",
            )
            .get(
                id=schedule_id
            )
        )

        print(
            f"[SCHEDULER] Destination: "
            f"{schedule.destination.name}"
        )

        print(
            f"[SCHEDULER] Bot: "
            f"{getattr(schedule.destination.bot, 'username', None)}"
        )

        print(
            f"[SCHEDULER] Interval: "
            f"{schedule.interval_seconds}s"
        )

        # ----------------------------------------------------
        # MARK RUNNING
        # ----------------------------------------------------

        schedule.status = "running"
        schedule.started_at = timezone.now()
        schedule.completed_at = None
        schedule.error = None

        schedule.save(
            update_fields=[
                "status",
                "started_at",
                "completed_at",
                "error",
            ]
        )

        # ----------------------------------------------------
        # LOAD QUEUE
        # ----------------------------------------------------

        items = list(
            schedule.items
            .select_related("deal")
            .filter(
                status="pending"
            )
            .order_by(
                "position"
            )
        )

        print(
            f"[SCHEDULER] Pending queue: "
            f"{len(items)} deal(s)"
        )

        # ----------------------------------------------------
        # NO DEALS
        # ----------------------------------------------------

        if not items:

            print(
                f"[SCHEDULER] Schedule #{schedule_id}: "
                f"No pending deals."
            )

            schedule.status = "completed"
            schedule.completed_at = timezone.now()

            schedule.save(
                update_fields=[
                    "status",
                    "completed_at",
                ]
            )

            return True

        # ----------------------------------------------------
        # PUBLISH ONE BY ONE
        # ----------------------------------------------------

        for index, item in enumerate(items):

            # ------------------------------------------------
            # CANCEL CHECK
            # ------------------------------------------------

            if stop_event.is_set():

                print(
                    f"[SCHEDULER] Schedule #{schedule_id} "
                    f"cancel event detected."
                )

                break

            # ------------------------------------------------
            # REFRESH STATUS
            # ------------------------------------------------

            schedule.refresh_from_db(
                fields=[
                    "status",
                ]
            )

            if schedule.status == "cancelled":

                print(
                    f"[SCHEDULER] Schedule #{schedule_id} "
                    f"was cancelled."
                )

                stop_event.set()
                break

            # ------------------------------------------------
            # CURRENT DEAL INFO
            # ------------------------------------------------

            print(
                f"[SCHEDULER] Publishing "
                f"{index + 1}/{len(items)} "
                f"Deal #{item.deal.id}"
            )

            print(
                f"[SCHEDULER] Price={item.deal.price} "
                f"Rating={item.deal.rating}"
            )

            print(
                f"[SCHEDULER] Destination="
                f"{schedule.destination.name}"
            )

            # ------------------------------------------------
            # PUBLISH
            # ------------------------------------------------

            try:

                result = publish_deal_to_channel(
                    item.deal,
                    schedule.destination,
                )

                print(
                    f"[SCHEDULER] Publish result for "
                    f"Deal #{item.deal.id}: "
                    f"{result}"
                )

            except Exception as error:

                print(
                    f"[SCHEDULER ERROR] Exception while "
                    f"publishing Deal #{item.deal.id}: "
                    f"{error}"
                )

                result = {
                    "status": "failed",
                    "error": str(error),
                }

            # ------------------------------------------------
            # SUCCESS
            # ------------------------------------------------

            if result.get("status") == "success":

                item.status = "success"

                item.published_record_id = (
                    result.get(
                        "record_id"
                    )
                )

                item.published_at = timezone.now()

                item.error = None

                item.save(
                    update_fields=[
                        "status",
                        "published_record_id",
                        "published_at",
                        "error",
                    ]
                )

                schedule.published_count += 1

                print(
                    f"[SCHEDULER] ✅ Deal "
                    f"#{item.deal.id} published."
                )

            # ------------------------------------------------
            # ALREADY PUBLISHED / SKIPPED
            # ------------------------------------------------

            elif result.get("status") == "skipped":

                item.status = "skipped"

                item.error = result.get(
                    "reason",
                    "Already published",
                )

                item.save(
                    update_fields=[
                        "status",
                        "error",
                    ]
                )

                schedule.skipped_count += 1

                print(
                    f"[SCHEDULER] ⏭ Deal "
                    f"#{item.deal.id} skipped: "
                    f"{item.error}"
                )

            # ------------------------------------------------
            # FAILED
            # ------------------------------------------------

            else:

                item.status = "failed"

                item.error = result.get(
                    "error",
                    "Unknown publishing error",
                )

                item.save(
                    update_fields=[
                        "status",
                        "error",
                    ]
                )

                schedule.failed_count += 1

                print(
                    f"[SCHEDULER] ❌ Deal "
                    f"#{item.deal.id} failed: "
                    f"{item.error}"
                )

            # ------------------------------------------------
            # SAVE PROGRESS
            # ------------------------------------------------

            schedule.save(
                update_fields=[
                    "published_count",
                    "skipped_count",
                    "failed_count",
                ]
            )

            print(
                f"[SCHEDULER] Progress: "
                f"{schedule.published_count} published, "
                f"{schedule.skipped_count} skipped, "
                f"{schedule.failed_count} failed "
                f"out of {schedule.total_deals}."
            )

            # ------------------------------------------------
            # WAIT BEFORE NEXT DEAL
            # ------------------------------------------------

            if index < len(items) - 1:

                wait_seconds = max(
                    1,
                    int(
                        schedule.interval_seconds
                    )
                )

                print(
                    f"[SCHEDULER] Waiting "
                    f"{wait_seconds} seconds "
                    f"before next deal..."
                )

                remaining = wait_seconds

                while remaining > 0:

                    if stop_event.is_set():

                        print(
                            "[SCHEDULER] Wait interrupted "
                            "by cancellation."
                        )

                        break

                    sleep_time = min(
                        0.5,
                        remaining
                    )

                    time.sleep(
                        sleep_time
                    )

                    remaining -= sleep_time

                if stop_event.is_set():
                    break

        # ----------------------------------------------------
        # FINAL STATUS
        # ----------------------------------------------------

        schedule.refresh_from_db()

        if schedule.status != "cancelled":

            pending_exists = (
                schedule.items
                .filter(
                    status="pending"
                )
                .exists()
            )

            if pending_exists:

                schedule.status = "cancelled"

                print(
                    f"[SCHEDULER] Schedule #{schedule_id} "
                    f"stopped with pending deals."
                )

            else:

                schedule.status = "completed"

                print(
                    f"[SCHEDULER] Schedule #{schedule_id} "
                    f"completed."
                )

            schedule.completed_at = timezone.now()

            schedule.save(
                update_fields=[
                    "status",
                    "completed_at",
                ]
            )

        return True

    except Exception as error:

        print(
            f"[SCHEDULER ERROR] "
            f"Schedule #{schedule_id} crashed: "
            f"{error}"
        )

        import traceback

        traceback.print_exc()

        PublishingSchedule.objects.filter(
            id=schedule_id
        ).update(
            status="failed",
            error=str(error),
            completed_at=timezone.now(),
        )

        return False

    finally:

        with _schedule_lock:

            _running_schedules.pop(
                schedule_id,
                None
            )

        print(
            f"[SCHEDULER] Schedule #{schedule_id} "
            f"worker stopped."
        )


# ============================================================
# START SCHEDULE
# ============================================================

def start_schedule(schedule_id):
    """
    Start schedule in a background thread.
    """

    with _schedule_lock:

        if schedule_id in _running_schedules:

            print(
                f"[SCHEDULER] Schedule #{schedule_id} "
                f"is already active."
            )

            return False

    print(
        f"[SCHEDULER] Starting background worker "
        f"for schedule #{schedule_id}"
    )

    thread = threading.Thread(
        target=run_schedule,
        args=(schedule_id,),
        daemon=True,
    )

    thread.start()

    return True


# ============================================================
# CANCEL SCHEDULE
# ============================================================

def cancel_schedule(schedule_id):
    """
    Cancel a running schedule.
    """

    schedule = (
        PublishingSchedule.objects.get(
            id=schedule_id
        )
    )

    schedule.status = "cancelled"
    schedule.completed_at = timezone.now()

    schedule.save(
        update_fields=[
            "status",
            "completed_at",
        ]
    )

    print(
        f"[SCHEDULER] Cancel requested "
        f"for schedule #{schedule_id}"
    )

    # Signal background worker
    with _schedule_lock:

        stop_event = _running_schedules.get(
            schedule_id
        )

        if stop_event:

            stop_event.set()

    return schedule