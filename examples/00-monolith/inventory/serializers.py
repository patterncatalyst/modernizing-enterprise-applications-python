from rest_framework import serializers

from .models import InventoryItem


class InventoryItemSerializer(serializers.ModelSerializer):
    """camelCase JSON to match the Java monolith's `StockDto` contract (the
    ported Newman collection asserts on these exact field names)."""

    priceCents = serializers.IntegerField(source="price_cents")
    quantityOnHand = serializers.IntegerField(source="quantity_on_hand")

    class Meta:
        model = InventoryItem
        fields = ["sku", "name", "priceCents", "quantityOnHand"]
