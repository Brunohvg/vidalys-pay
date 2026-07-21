"""Payment links API URL patterns."""
from django.urls import path

from . import api

app_name = "payment_links_api"

urlpatterns = [
    path("payment-links/", api.create_payment_link_view, name="create"),
    path("payment-links/<uuid:link_id>/", api.get_payment_link_view, name="detail"),
    path("payment-links/<uuid:link_id>/resend/", api.resend_payment_link_view, name="resend"),
]
