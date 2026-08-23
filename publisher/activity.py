from .models import ActivityLog


def log_activity(
    event_type,
    message,
    bot=None,
    destination=None,
    user=None,
    deal=None,
):
    try:
        return ActivityLog.objects.create(
            event_type=event_type,
            message=message,
            bot=bot,
            destination=destination,
            user=user,
            deal=deal,
        )
    except Exception as error:
        # Activity logging must never break
        # the main application.
        print(
            f"Activity log error: {error}"
        )

    return None