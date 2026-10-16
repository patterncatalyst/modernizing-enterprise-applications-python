from django.urls import path

from . import views

urlpatterns = [
    path("", views.ReviewListCreateView.as_view(), name="review-list-create"),
    path("/<int:id>", views.ReviewDetailView.as_view(), name="review-detail"),
]
