"""HTML routes for manager and seller boleto flows."""
from django.urls import path

from . import views

app_name = "boletos"

urlpatterns = [
    path("painel/boletos/criar/", views.manager_create_boleto, name="manager_create"),
    path("painel/boletos/<uuid:boleto_id>/", views.manager_boleto_detail, name="manager_detail"),
    path("app/boletos/criar/", views.seller_create_boleto, name="seller_create"),
    path("app/boletos/<uuid:boleto_id>/", views.seller_boleto_detail, name="seller_detail"),
]
