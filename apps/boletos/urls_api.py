"""Boleto support API URL patterns."""
from django.urls import path

from . import api

app_name = "boletos_api"

urlpatterns = [
    path("boletos/", api.boletos_collection_view, name="collection"),
    path("boletos/cnpj/<str:cnpj>/", api.lookup_cnpj_view, name="lookup_cnpj"),
    path("boletos/<uuid:boleto_id>/", api.get_boleto_view, name="detail"),
    path("boletos/<uuid:boleto_id>/status/", api.get_boleto_status_view, name="status"),
    path("boletos/<uuid:boleto_id>/cancel/", api.cancel_boleto_view, name="cancel"),
    path("boletos/<uuid:boleto_id>/resend/", api.resend_boleto_view, name="resend"),
    path(
        "boletos/<uuid:boleto_id>/second-copy/",
        api.create_second_copy_view,
        name="second_copy",
    ),
]
