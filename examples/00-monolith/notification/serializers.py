from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    customerId = serializers.IntegerField(source="customer_id")
    orderId = serializers.IntegerField(source="order_id", allow_null=True)
    sentAt = serializers.DateTimeField(source="sent_at")

    class Meta:
        model = Notification
        fields = ["id", "customerId", "orderId", "channel", "message", "sentAt"]
