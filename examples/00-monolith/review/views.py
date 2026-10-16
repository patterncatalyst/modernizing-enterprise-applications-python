from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .serializers import ReviewCreateSerializer, ReviewSerializer


class ReviewListCreateView(APIView):
    """GET /api/reviews (optional ?sku= filter), POST /api/reviews."""

    def get(self, request):
        sku = request.query_params.get("sku")
        reviews = services.list_by_sku(sku) if sku else services.list_all()
        return Response(ReviewSerializer(reviews, many=True).data)

    def post(self, request):
        command = ReviewCreateSerializer(data=request.data)
        command.is_valid(raise_exception=True)
        data = command.validated_data
        review = services.create_review(
            customer_id=data["customer_id"],
            sku=data["sku"],
            rating=data["rating"],
            comment=data.get("comment"),
        )
        body = ReviewSerializer(review).data
        return Response(
            body,
            status=status.HTTP_201_CREATED,
            headers={"Location": f"/api/reviews/{review.id}"},
        )


class ReviewDetailView(APIView):
    """GET /api/reviews/{id}."""

    def get(self, request, id):
        review = services.get_by_id(id)
        return Response(ReviewSerializer(review).data)
