from django.db import models
from deals.models import Deal


class TelegramBot(models.Model):

    STATUS_CHOICES = [
        ("active", "Active"),
        ("inactive", "Inactive"),
        ("error", "Error"),
    ]

    name = models.CharField(max_length=255)

    bot_token = models.CharField(
        max_length=255,
        unique=True,
    )

    username = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )

    bot_id = models.BigIntegerField(
        blank=True,
        null=True,
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="active",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    def __str__(self):
        return self.name


class PublishedChannel(models.Model):

    CHAT_TYPE_CHOICES = [
        ("channel", "Channel"),
        ("group", "Group"),
    ]

    STATUS_CHOICES = [
        ("active", "Active"),
        ("inactive", "Inactive"),
    ]

    name = models.CharField(
        max_length=255,
    )

    username = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )

    chat_id = models.BigIntegerField(
        blank=True,
        null=True,
    )

    chat_type = models.CharField(
        max_length=20,
        choices=CHAT_TYPE_CHOICES,
        default="channel",
    )

    description = models.TextField(
        blank=True,
        null=True,
    )

    bot = models.ForeignKey(
        TelegramBot,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="destinations",
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="active",
    )

    auto_allow_users = models.BooleanField(
        default=True,
    )

    allow_direct_messages = models.BooleanField(
        default=True,
    )

    auto_publish_deals = models.BooleanField(
        default=True,
    )

    send_welcome_message = models.BooleanField(
        default=True,
    )

    welcome_message = models.TextField(
        blank=True,
        default=(
            "👋 Welcome {name}!\n\n"
            "You are now connected with our Telegram community.\n\n"
            "🎁 Stay tuned for the latest deals and offers!"
        ),
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"{self.name} "
            f"({self.username or self.chat_id or 'No ID'})"
        )


class TelegramUser(models.Model):

    STATUS_CHOICES = [
        ("allowed", "Allowed"),
        ("blocked", "Blocked"),
    ]

    user_id = models.BigIntegerField(
        unique=True,
    )

    username = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )

    first_name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )

    last_name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )

    language_code = models.CharField(
        max_length=20,
        blank=True,
        null=True,
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="allowed",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    last_seen_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["-last_seen_at"]

    def __str__(self):
        return (
            f"{self.first_name or ''} "
            f"@{self.username or self.user_id}"
        )


class ChannelUser(models.Model):

    STATUS_CHOICES = [
        ("active", "Active"),
        ("allowed", "Allowed"),
        ("blocked", "Blocked"),
        ("left", "Left"),
    ]

    channel = models.ForeignKey(
        PublishedChannel,
        on_delete=models.CASCADE,
        related_name="users",
    )

    user = models.ForeignKey(
        TelegramUser,
        on_delete=models.CASCADE,
        related_name="channel_memberships",
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="active",
    )

    joined_at = models.DateTimeField(
        auto_now_add=True,
    )

    left_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["channel", "user"],
                name="unique_channel_user",
            )
        ]

        ordering = ["-joined_at"]

    def __str__(self):
        return f"{self.user} -> {self.channel}"

class UserDestinationPermission(models.Model):

    user = models.ForeignKey(
        TelegramUser,
        on_delete=models.CASCADE,
        related_name="destination_permissions",
    )

    destination = models.ForeignKey(
        PublishedChannel,
        on_delete=models.CASCADE,
        related_name="user_permissions",
    )

    can_message = models.BooleanField(
        default=True,
    )

    can_publish = models.BooleanField(
        default=False,
    )

    is_allowed = models.BooleanField(
        default=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "destination"],
                name="unique_user_destination_permission",
            )
        ]

    def __str__(self):
        return f"{self.user} -> {self.destination}"


class PublishedDeal(models.Model):

    STATUS_CHOICES = [
        ("success", "Success"),
        ("failed", "Failed"),
        ("skipped", "Skipped"),
    ]

    deal = models.ForeignKey(
        Deal,
        on_delete=models.CASCADE,
        related_name="published_records",
    )

    channel = models.ForeignKey(
        PublishedChannel,
        on_delete=models.CASCADE,
        related_name="published_deals",
    )

    published_at = models.DateTimeField(
        auto_now_add=True,
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
    )

    telegram_message_id = models.BigIntegerField(
        blank=True,
        null=True,
    )

    error = models.TextField(
        blank=True,
        null=True,
    )

    class Meta:
        ordering = ["-published_at"]

    def __str__(self):
        return f"{self.deal} -> {self.channel}"
    
class ActivityLog(models.Model):

    EVENT_CHOICES = [
        ("bot_created", "Bot Created"),
        ("bot_updated", "Bot Updated"),

        ("destination_created", "Destination Created"),
        ("destination_updated", "Destination Updated"),

        ("user_first_seen", "User First Seen"),
        ("user_joined", "User Joined"),
        ("user_left", "User Left"),

        ("user_allowed", "User Allowed"),
        ("user_blocked", "User Blocked"),

        ("deal_published", "Deal Published"),
        ("deal_publish_failed", "Deal Publish Failed"),
    ]

    event_type = models.CharField(
        max_length=50,
        choices=EVENT_CHOICES
    )

    message = models.TextField()

    bot = models.ForeignKey(
        TelegramBot,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activity_logs"
    )

    destination = models.ForeignKey(
        PublishedChannel,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activity_logs"
    )

    user = models.ForeignKey(
        TelegramUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activity_logs"
    )

    deal = models.ForeignKey(
        Deal,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activity_logs"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"{self.get_event_type_display()} - "
            f"{self.created_at}"
        )