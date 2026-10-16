from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .models import Order
from .serializers import OrderCreateSerializer, OrderSerializer


class OrderListCreateView(APIView):
    """GET /api/orders, POST /api/orders (checkout)."""

    def get(self, request):
        orders = services.list_all()
        return Response(OrderSerializer(orders, many=True).data)

    def post(self, request):
        command = OrderCreateSerializer(data=request.data)
        command.is_valid(raise_exception=True)
        data = command.validated_data
        order = services.place_order(
            customer_id=data["customer_id"],
            items=[{"sku": line["sku"], "quantity": line["quantity"]} for line in data["items"]],
            payment_method=data["payment_method"],
            shipping_address=data["shipping_address"],
        )
        body = OrderSerializer(order).data
        # r05/ch.23-25: derived from the order's own status, not a separate
        # mode flag -- `settings.PAYMENT_MODE = "choreographed"` leaves
        # place_order() returning a PENDING order (payment/shipping happen
        # asynchronously; see order.management.commands.order_saga_listener),
        # which this request answers `202 Accepted` for instead of the
        # synchronous flow's `201 Created` CONFIRMED.
        response_status = (
            status.HTTP_202_ACCEPTED
            if order.status == Order.Status.PENDING
            else status.HTTP_201_CREATED
        )
        return Response(
            body,
            status=response_status,
            headers={"Location": f"/api/orders/{order.id}"},
        )


class OrderDetailView(APIView):
    """GET /api/orders/{id}."""

    def get(self, request, id):
        order = services.get_by_id(id)
        return Response(OrderSerializer(order).data)
