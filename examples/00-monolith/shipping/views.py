from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .serializers import ShipmentSerializer


class ShipmentListView(APIView):
    """GET /api/shipments?orderId=."""

    def get(self, request):
        order_id = request.query_params.get("orderId")
        if order_id is None:
            raise ValidationError({"orderId": "This query parameter is required."})
        shipments = services.list_by_order_id(order_id)
        return Response(ShipmentSerializer(shipments, many=True).data)


class ShipmentDetailView(APIView):
    """GET /api/shipments/{id}."""

    def get(self, request, id):
        shipment = services.get_by_id(id)
        return Response(ShipmentSerializer(shipment).data)
