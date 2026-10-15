from django.urls import path

from . import views

urlpatterns = [
    path("", views.OrderListCreateView.as_view(), name="order-list-create"),
    path("/<int:id>", views.OrderDetailView.as_view(), name="order-detail"),
]
