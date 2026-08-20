from rest_framework import serializers
from .models import Deal


class DealSerializer(serializers.ModelSerializer):

    class Meta:
        model = Deal
        fields = [
            "id",
            "message_id",
            "date",
            "content",
            "product_link",
            "image_path",
            "channel",
            "status",
        ]