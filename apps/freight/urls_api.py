"""Freight API URL patterns."""
from django.urls import path

from . import api

app_name = "freight"

urlpatterns = [
    path("freight/calculate/", api.calculate_freight_view, name="calculate_freight"),
]
