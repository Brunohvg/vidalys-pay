from django.urls import path

from . import views

app_name = "admin_panel"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("criar/", views.create_seller, name="create_seller"),
    path("<uuid:seller_id>/toggle/", views.toggle_seller, name="toggle_seller"),
    path("<uuid:seller_id>/convidar/", views.regenerate_invitation, name="regenerate_invitation"),
    path("<uuid:seller_id>/revogar-convite/", views.revoke_invitation, name="revoke_invitation"),
    path("<uuid:seller_id>/excluir/", views.delete_seller, name="delete_seller"),
    path("<uuid:seller_id>/criar-link/", views.create_link, name="create_link"),
]
