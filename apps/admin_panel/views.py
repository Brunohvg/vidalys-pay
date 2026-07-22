from django.conf import settings
from django.contrib.auth.decorators import user_passes_test
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from apps.sellers.models import Seller, SellerInvitation
from apps.sellers.services import generate_invitation

admin_required = user_passes_test(lambda u: u.is_superuser, login_url="admin:login")


@admin_required
@require_GET
def dashboard(request):
    sellers = Seller.objects.prefetch_related("invitations").order_by("-created_at")

    base_url = settings.APP_BASE_URL.rstrip("/")

    seller_data = []
    for seller in sellers:
        active_invitation = next(
            (i for i in seller.invitations.all() if i.used_at is None and i.revoked_at is None and i.expires_at > timezone.now()),
            None,
        )
        seller_data.append({
            "seller": seller,
            "active_invitation": active_invitation,
            "invitation_url": (
                f"{base_url}/acesso/{active_invitation.token_hash}/"
                if active_invitation
                else None
            ),
        })

    return render(request, "admin_panel/dashboard.html", {
        "seller_data": seller_data,
        "base_url": base_url,
    })


@admin_required
@require_POST
def create_seller(request):
    name = request.POST.get("name", "").strip()
    whatsapp = request.POST.get("whatsapp", "").strip()
    max_amount = request.POST.get("max_amount", "").strip()

    if not name or not whatsapp:
        sellers = Seller.objects.order_by("-created_at")
        return render(request, "admin_panel/dashboard.html", {
            "seller_data": [],
            "error": "Nome e WhatsApp são obrigatórios.",
        })

    try:
        max_amount_cents = int(float(max_amount) * 100) if max_amount else 50000
    except (ValueError, TypeError):
        max_amount_cents = 50000

    with transaction.atomic():
        seller = Seller.objects.create(
            name=name,
            whatsapp_phone=whatsapp,
            max_payment_amount_cents=max_amount_cents,
            is_active=True,
        )
        generate_invitation(seller=seller)

    return redirect("admin_panel:dashboard")


@admin_required
@require_POST
def toggle_seller(request, seller_id):
    seller = get_object_or_404(Seller, id=seller_id)
    seller.is_active = not seller.is_active
    seller.save(update_fields=["is_active"])
    return redirect("admin_panel:dashboard")


@admin_required
@require_POST
def regenerate_invitation(request, seller_id):
    seller = get_object_or_404(Seller, id=seller_id)
    generate_invitation(seller=seller)
    return redirect("admin_panel:dashboard")
