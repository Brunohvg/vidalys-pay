"""Boleto support API URL patterns."""
from django.urls import path

from . import api

app_name = "boletos_api"

urlpatterns = [
    path("boletos/cnpj/<str:cnpj>/", api.lookup_cnpj_view, name="lookup_cnpj"),
]
