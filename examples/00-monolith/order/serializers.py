from rest_framework import serializers

from .models import Order, OrderItem


class OrderLineSerializer(serializers.Serializer):
    sku = serializers.CharField()
    quantity = serializers.IntegerField(min_value=1)


class OrderCreateSerializer(serializers.Serializer):
    """Checkout request payload, camelCase to match the Java monolith's
    `OrderCreate` contract.

    `paymentMethod` is a deliberately simple demo seam: any value containing
    "DECLINE" (case-insensitive) makes payment.services.charge() simulate a
    decline, and `shippingAddress` containing "SHIP-FAIL" makes
    shipping.services.dispatch() simulate a dispatch failure -- both
    deterministic, so the Newman collection can exercise the failure paths
    without a real payment gateway or carrier.
    """

    customerId = serializers.IntegerField(source="customer_id")
    items = OrderLineSerializer(many=True, allow_empty=False)
    paymentMethod = serializers.CharField(source="payment_method")
    shippingAddress = serializers.CharField(source="shipping_address")


class OrderItemSerializer(serializers.ModelSerializer):
    """r04/ch.19: `sku` now reads straight off OrderItem's own denormalized
    snapshot column (no more `inventory_item.sku` cross-app join; DRF treats
    an explicit `source="sku"` matching the field name as redundant and
    raises on it) -- the wire shape is byte-for-byte unchanged."""

    sku = serializers.CharField()
    unitPriceCents = serializers.IntegerField(source="unit_price_cents")

    class Meta:
        model = OrderItem
        fields = ["sku", "quantity", "unitPriceCents"]


class OrderSerializer(serializers.ModelSerializer):
    """Order read model, camelCase to match the Java monolith's `OrderDto`."""

    customerId = serializers.IntegerField(source="customer_id")
    totalCents = serializers.IntegerField(source="total_cents")
    createdAt = serializers.DateTimeField(source="created_at")
    items = OrderItemSerializer(many=True)

    class Meta:
        model = Order
        fields = ["id", "customerId", "status", "totalCents", "createdAt", "items"]
