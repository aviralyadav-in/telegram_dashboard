from django.db import models

from deals.models import Deal
from publisher.models import PublishedChannel


class PublishingSchedule(models.Model):

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("running", "Running"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
        ("failed", "Failed"),
    ]

    destination = models.ForeignKey(
        PublishedChannel,
        on_delete=models.CASCADE,
        related_name="publishing_schedules",
    )

    date_from = models.DateField(
        null=True,
        blank=True,
    )

    date_to = models.DateField(
        null=True,
        blank=True,
    )

    min_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )

    max_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )

    min_rating = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        null=True,
        blank=True,
    )

    deal_limit = models.PositiveIntegerField(
        default=5,
    )

    interval_seconds = models.PositiveIntegerField(
        default=10,
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
    )

    total_deals = models.PositiveIntegerField(
        default=0,
    )

    published_count = models.PositiveIntegerField(
        default=0,
    )

    failed_count = models.PositiveIntegerField(
        default=0,
    )
    
    skipped_count = models.PositiveIntegerField(
        default=0,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    started_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    completed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    error = models.TextField(
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"Schedule #{self.id} - "
            f"{self.destination.name}"
        )


class ScheduledPublishItem(models.Model):

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("success", "Success"),
        ("failed", "Failed"),
        ("skipped", "Skipped"),
    ]

    schedule = models.ForeignKey(
        PublishingSchedule,
        on_delete=models.CASCADE,
        related_name="items",
    )

    deal = models.ForeignKey(
        Deal,
        on_delete=models.CASCADE,
        related_name="scheduled_publish_items",
    )

    position = models.PositiveIntegerField()

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
    )

    error = models.TextField(
        null=True,
        blank=True,
    )

    published_record_id = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    published_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["position"]

        constraints = [
            models.UniqueConstraint(
                fields=["schedule", "deal"],
                name="unique_schedule_deal",
            )
        ]

    def __str__(self):
        return (
            f"Schedule {self.schedule_id} "
            f"- Deal {self.deal_id}"
        )