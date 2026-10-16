from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .serializers import InventoryItemSerializer


class InventoryListView(APIView):
    """GET /api/inventory"""

    def get(self, request):
        items = services.list_all()
        return Response(InventoryItemSerializer(items, many=True).data)


class InventoryDetailView(APIView):
    """GET /api/inventory/{sku}"""

    def get(self, request, sku):
        item = services.get_by_sku(sku)
        return Response(InventoryItemSerializer(item).data)
