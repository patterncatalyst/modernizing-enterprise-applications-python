from django.urls import path

from . import views

urlpatterns = [
    path("", views.ShipmentListView.as_view(), name="shipment-list"),
    path("/<int:id>", views.ShipmentDetailView.as_view(), name="shipment-detail"),
]
