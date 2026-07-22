"""Seller URL patterns."""
from django.urls import path

from . import views

app_name = "sellers"

urlpatterns = [
    path("sw.js", views.service_worker, name="service_worker"),
    path("", views.index, name="index"),
    # Activation
    path("acesso/<str:token>/", views.activate_invitation, name="activate"),
    path("acesso/<str:token>/confirmar/", views.confirm_activation, name="confirm_activation"),
    # App pages
    path("app/", views.app_new_link, name="app_new_link"),
    path("app/historico/", views.app_history, name="app_history"),
    path("app/frete/", views.app_freight, name="app_freight"),
    path("app/perfil/", views.app_profile, name="app_profile"),
    path("app/sucesso/", views.app_success, name="app_success"),
    # Session
    path("sessao-invalida/", views.session_invalid, name="session_invalid"),
    # API
    path("api/v1/me/", views.seller_profile, name="profile"),
    path("api/v1/me/logout/", views.seller_logout, name="logout"),
    path("api/v1/me/logout-all/", views.seller_logout_all, name="logout-all"),
]
