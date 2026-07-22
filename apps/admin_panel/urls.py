from django.urls import path

from . import views

app_name = "admin_panel"

urlpatterns = [
    # Auth
    path("login/", views.panel_login, name="login"),
    path("logout/", views.panel_logout, name="logout"),

    # Dashboard
    path("", views.dashboard, name="dashboard"),

    # Link creation
    path("links/criar/", views.create_link_standalone, name="create_link_standalone"),

    # Seller management
    path("vendedores/", views.seller_list, name="seller_list"),
    path("vendedores/criar/", views.create_seller_page, name="create_seller_page"),
    path("criar/", views.create_seller, name="create_seller"),

    # Seller actions (preserved)
    path("<uuid:seller_id>/toggle/", views.toggle_seller, name="toggle_seller"),
    path("<uuid:seller_id>/convidar/", views.regenerate_invitation, name="regenerate_invitation"),
    path("<uuid:seller_id>/revogar-convite/", views.revoke_invitation, name="revoke_invitation"),
    path("<uuid:seller_id>/excluir/", views.delete_seller, name="delete_seller"),
    path("<uuid:seller_id>/criar-link/", views.create_link, name="create_link"),

    # Settings
    path("configuracoes/", views.settings_page, name="settings_page"),
]
