from django.urls import path

from . import views

urlpatterns = [
    path("", views.PaymentListView.as_view(), name="payment-list"),
    path("/<int:id>", views.PaymentDetailView.as_view(), name="payment-detail"),
]
