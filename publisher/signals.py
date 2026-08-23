from django.db.models.signals import post_save
from django.dispatch import receiver

from deals.models import Deal

from publisher.services.publishing import (
    auto_publish_deal,
)


@receiver(
    post_save,
    sender=Deal
)
def deal_created_signal(
    sender,
    instance,
    created,
    **kwargs
):

    if not created:
        return

    try:

        auto_publish_deal(
            instance
        )

    except Exception as error:

        print(
            f"Automatic deal publishing failed "
            f"for Deal #{instance.id}: "
            f"{error}"
        )