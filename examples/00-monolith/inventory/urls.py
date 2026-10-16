from django.urls import path

from . import views

urlpatterns = [
    path("", views.InventoryListView.as_view(), name="inventory-list"),
    path("/<str:sku>", views.InventoryDetailView.as_view(), name="inventory-detail"),
]
