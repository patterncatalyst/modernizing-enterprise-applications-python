"""Root URL configuration.

One router for all six bounded contexts -- another facet of SMELL[ch.18]: in a
decomposed system each context would have its own API surface served by its own
process, not one shared `urlpatterns` list.
"""

from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path("api/orders", include("order.urls")),
    path("api/inventory", include("inventory.urls")),
    path("api/payments", include("payment.urls")),
    path("api/shipments", include("shipping.urls")),
    path("api/notifications", include("notification.urls")),
    path("api/reviews", include("review.urls")),
    path("api/schema", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/schema/swagger-ui",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
]
