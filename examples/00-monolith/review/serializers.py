from rest_framework import serializers

from .models import Review


class ReviewCreateSerializer(serializers.Serializer):
    customerId = serializers.IntegerField(source="customer_id")
    sku = serializers.CharField()
    rating = serializers.IntegerField(min_value=1, max_value=5)
    comment = serializers.CharField(required=False, allow_null=True, allow_blank=True)


class ReviewSerializer(serializers.ModelSerializer):
    customerId = serializers.IntegerField(source="customer_id")
    sku = serializers.CharField(source="inventory_item.sku")
    createdAt = serializers.DateTimeField(source="created_at")

    class Meta:
        model = Review
        fields = ["id", "customerId", "sku", "rating", "comment", "createdAt"]
