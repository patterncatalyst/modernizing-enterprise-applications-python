from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .serializers import PaymentSerializer


class PaymentListView(APIView):
    """GET /api/payments?orderId=."""

    def get(self, request):
        order_id = request.query_params.get("orderId")
        if order_id is None:
            raise ValidationError({"orderId": "This query parameter is required."})
        payments = services.list_by_order_id(order_id)
        return Response(PaymentSerializer(payments, many=True).data)


class PaymentDetailView(APIView):
    """GET /api/payments/{id}."""

    def get(self, request, id):
        payment = services.get_by_id(id)
        return Response(PaymentSerializer(payment).data)
