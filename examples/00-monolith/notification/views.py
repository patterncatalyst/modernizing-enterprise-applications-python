from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .serializers import NotificationSerializer


class NotificationListView(APIView):
    """GET /api/notifications?customerId=."""

    def get(self, request):
        customer_id = request.query_params.get("customerId")
        if customer_id is None:
            raise ValidationError({"customerId": "This query parameter is required."})
        notifications = services.list_by_customer_id(customer_id)
        return Response(NotificationSerializer(notifications, many=True).data)
