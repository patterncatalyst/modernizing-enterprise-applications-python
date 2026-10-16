from rest_framework import serializers

from .models import Payment


class PaymentSerializer(serializers.ModelSerializer):
    orderId = serializers.IntegerField(source="order_id")
    amountCents = serializers.IntegerField(source="amount_cents")
    createdAt = serializers.DateTimeField(source="created_at")

    class Meta:
        model = Payment
        fields = ["id", "orderId", "amountCents", "method", "status", "createdAt"]
