from rest_framework import serializers

from .models import Shipment


class ShipmentSerializer(serializers.ModelSerializer):
    orderId = serializers.IntegerField(source="order_id")
    createdAt = serializers.DateTimeField(source="created_at")

    class Meta:
        model = Shipment
        fields = ["id", "orderId", "address", "status", "createdAt"]
