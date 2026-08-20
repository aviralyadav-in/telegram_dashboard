from django.db import models


# ============================================================
# CATEGORY MODEL
# ============================================================

class Category(models.Model):

    STATUS_CHOICES = [
        ("active", "Active"),
        ("inactive", "Inactive"),
    ]

    name = models.CharField(
        max_length=100,
        unique=True
    )

    description = models.TextField(
        blank=True,
        null=True
    )

    keywords = models.TextField(
        blank=True,
        null=True,
        help_text="Comma-separated keywords"
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="active"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        db_table = "categories"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def get_keywords_list(self):

        if not self.keywords:
            return []

        return [
            keyword.strip().lower()
            for keyword in self.keywords.split(",")
            if keyword.strip()
        ]


# ============================================================
# DEAL MODEL
# ============================================================

class Deal(models.Model):

    STATUS_CHOICES = [
        ("new", "New"),
        ("processed", "Processed"),
        ("published", "Published"),
        ("expired", "Expired"),
        ("rejected", "Rejected"),
    ]

    message_id = models.BigIntegerField()

    date = models.DateTimeField()

    content = models.TextField(
        blank=True,
        null=True
    )

    product_link = models.TextField(
        blank=True,
        null=True
    )

    image_path = models.TextField(
        blank=True,
        null=True
    )

    channel = models.CharField(
        max_length=255
    )

    # --------------------------------------------------------
    # PRICE
    # --------------------------------------------------------

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="Product/deal price"
    )

    # --------------------------------------------------------
    # PRODUCT RATING
    # --------------------------------------------------------

    rating = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="Product rating, e.g. 4.50"
    )

    # --------------------------------------------------------
    # DEAL STATUS
    # --------------------------------------------------------

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="new"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:

        db_table = "deals"

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "channel",
                    "message_id"
                ],
                name="unique_channel_message"
            )
        ]

        ordering = [
            "-date"
        ]

    def __str__(self):
        return f"Deal {self.id} - {self.channel}"
