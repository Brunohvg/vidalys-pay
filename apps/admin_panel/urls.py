from django.urls import path

from . import views

app_name = "admin_panel"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("criar/", views.create_seller, name="create_seller"),
    path("<uuid:seller_id>/toggle/", views.toggle_seller, name="toggle_seller"),
    path("<uuid:seller_id>/convidar/", views.regenerate_invitation, name="regenerate_invitation"),
]
