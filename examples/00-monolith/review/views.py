from rest_framework import status
from rest_framework.authentication import BasicAuthentication
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .serializers import ReviewCreateSerializer, ReviewSerializer


class ReviewListCreateView(APIView):
    """GET /api/reviews (optional ?sku= filter), POST /api/reviews.

    # SMELL[ch.15]: POST is gated by HTTP Basic auth against THIS module's
    shared `django.contrib.auth` `auth_user` table (see
    `common/management/commands/seed.py` for the seeded `reviewer` demo
    credentials) -- the same shared-security surface every other context in
    this monolith would reach for if it needed auth. Review has no runtime
    dependency on order/inventory/payment/shipping/notification (REST-only,
    no synchronous collaborator -- see `review/models.py`), yet here it is,
    borrowing that machinery anyway. GET stays open: the gate is wired
    per-view (`authentication_classes`/`get_permissions()` below), NOT via
    `REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"]`, which would require auth
    on every other context's reads too. Cured in ch.15, when review gets ITS
    OWN, independent auth configuration in `examples/02-review-service`.
    """

    authentication_classes = [BasicAuthentication]

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated()]
        return [AllowAny()]

    def perform_authentication(self, request):
        # Resolve credentials eagerly only for the write path. If we let the
        # default (unconditional) perform_authentication run for GET too, a
        # malformed/garbage Authorization header on a READ would raise 401
        # even though GET has no permission gate -- skipping it here means
        # reads are fully open regardless of what's in that header.
        if request.method == "POST":
            super().perform_authentication(request)

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
