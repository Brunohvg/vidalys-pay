import uuid
from datetime import date

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import user_passes_test
from django.core.paginator import Paginator
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from apps.notifications.whatsapp_service import (
    queue_invitation,
    queue_payment_link_created,
)
from apps.payment_links.use_cases import create_payment_link
from apps.sellers.models import Seller, SellerInvitation
from apps.sellers.services import generate_invitation

admin_required = user_passes_test(lambda u: u.is_superuser, login_url="admin_panel:login")


# ── Auth ─────────────────────────────────────────────────────────────────────


def panel_login(request):
    if request.user.is_authenticated and request.user.is_superuser:
        return redirect("admin_panel:dashboard")

    error = None
    username = ""

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, username=username, password=password)

        if user is not None and user.is_superuser:
            login(request, user)
            next_url = request.GET.get("next", "")
            if next_url:
                return redirect(next_url)
            return redirect("admin_panel:dashboard")

        error = "Usuário ou senha incorretos."

    return render(request, "panel/login.html", {
        "error": error,
        "username": username,
    })


def panel_logout(request):
    logout(request)
    return redirect("admin_panel:login")


# ── Dashboard ────────────────────────────────────────────────────────────────


@admin_required
@require_GET
def dashboard(request):
    sellers = Seller.objects.order_by("-created_at")
    total = sellers.count()
    active = sellers.filter(is_active=True).count()

    active_invitations = SellerInvitation.objects.filter(
        used_at__isnull=True,
        revoked_at__isnull=True,
        expires_at__gt=timezone.now(),
    ).count()

    recent = sellers[:5]

    webhook_url = request.build_absolute_uri("/api/v1/webhooks/pagarme/")

    return render(request, "panel/dashboard.html", {
        "active_page": "dashboard",
        "total_sellers": total,
        "active_sellers": active,
        "inactive_sellers": total - active,
        "pending_invitations": active_invitations,
        "recent_sellers": recent,
        "webhook_url": webhook_url,
    })


# ── Seller list ──────────────────────────────────────────────────────────────


@admin_required
@require_GET
def seller_list(request):
    query = request.GET.get("q", "").strip()
    status_filter = request.GET.get("status", "").strip()
    page_number = request.GET.get("page", "1")

    sellers_qs = Seller.objects.prefetch_related("invitations").order_by("-created_at")

    if query:
        sellers_qs = sellers_qs.filter(name__icontains=query)
        # Also try phone
        from django.db.models import Q
        sellers_qs = Seller.objects.filter(
            Q(name__icontains=query) | Q(whatsapp_phone__icontains=query)
        ).prefetch_related("invitations").order_by("-created_at")

    if status_filter == "active":
        sellers_qs = sellers_qs.filter(is_active=True)
    elif status_filter == "inactive":
        sellers_qs = sellers_qs.filter(is_active=False)
    elif status_filter == "pending":
        sellers_qs = sellers_qs.filter(
            invitations__used_at__isnull=True,
            invitations__revoked_at__isnull=True,
            invitations__expires_at__gt=timezone.now(),
        ).distinct()

    total_count = sellers_qs.count()

    paginator = Paginator(sellers_qs, 25)
    page_obj = paginator.get_page(page_number)

    seller_data = []
    for seller in page_obj:
        active_invitation = next(
            (i for i in seller.invitations.all()
             if i.used_at is None and i.revoked_at is None and i.expires_at > timezone.now()),
            None,
        )
        seller_data.append({
            "seller": seller,
            "active_invitation": active_invitation,
        })

    return render(request, "panel/sellers/list.html", {
        "active_page": "sellers",
        "sellers": seller_data,
        "query": query,
        "status_filter": status_filter,
        "total_count": total_count,
        "page_obj": page_obj,
    })


# ── Seller create page ───────────────────────────────────────────────────────


@admin_required
@require_GET
def create_seller_page(request):
    return render(request, "panel/sellers/create.html", {
        "active_page": "create_seller",
    })


# ── Seller create action ─────────────────────────────────────────────────────


@admin_required
@require_POST
def create_seller(request):
    name = request.POST.get("name", "").strip()
    whatsapp = request.POST.get("whatsapp", "").strip()
    max_amount = request.POST.get("max_amount", "").strip()

    if not name or not whatsapp:
        return render(request, "panel/sellers/create.html", {
            "active_page": "create_seller",
            "error": "Nome e WhatsApp são obrigatórios.",
            "form_data": {"name": name, "phone": whatsapp, "max_amount": max_amount},
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
        _invitation, raw_token = generate_invitation(seller=seller)

    activation_url = f"{settings.APP_BASE_URL.rstrip('/')}/acesso/{raw_token}/"
    queue_invitation(seller=seller, activation_url=activation_url)

    messages.success(request, f"Vendedor '{seller.name}' criado. Convite enviado para {seller.whatsapp_phone}.")
    return redirect("admin_panel:seller_list")


# ── Seller actions ───────────────────────────────────────────────────────────


@admin_required
@require_POST
def toggle_seller(request, seller_id):
    seller = get_object_or_404(Seller, id=seller_id)
    seller.is_active = not seller.is_active
    seller.save(update_fields=["is_active"])
    status = "ativado" if seller.is_active else "desativado"
    messages.success(request, f"Vendedor '{seller.name}' {status}.")
    return redirect("admin_panel:seller_list")


@admin_required
@require_POST
def regenerate_invitation(request, seller_id):
    seller = get_object_or_404(Seller, id=seller_id)
    _invitation, raw_token = generate_invitation(seller=seller)
    activation_url = f"{settings.APP_BASE_URL.rstrip('/')}/acesso/{raw_token}/"
    queue_invitation(seller=seller, activation_url=activation_url)
    messages.success(request, f"Novo convite enviado para {seller.whatsapp_phone}.")
    return redirect("admin_panel:seller_list")


@admin_required
@require_POST
def revoke_invitation(request, seller_id):
    seller = get_object_or_404(Seller, id=seller_id)
    count = SellerInvitation.objects.filter(
        seller=seller,
        used_at__isnull=True,
        revoked_at__isnull=True,
    ).update(revoked_at=timezone.now())

    if count:
        messages.success(request, f"Convite de {seller.name} revogado.")
    else:
        messages.warning(request, f"{seller.name} não possui convite ativo para revogar.")
    return redirect("admin_panel:seller_list")


@admin_required
@require_POST
def delete_seller(request, seller_id):
    seller = get_object_or_404(Seller, id=seller_id)
    name = seller.name
    seller.delete()
    messages.success(request, f"Vendedor '{name}' excluído permanentemente.")
    return redirect("admin_panel:seller_list")


# ── Create link ──────────────────────────────────────────────────────────────


@admin_required
def create_link(request, seller_id):
    seller = get_object_or_404(Seller, id=seller_id)

    if request.method == "POST":
        return _handle_create_link_post(request, seller)

    return render(request, "panel/payment_links/create.html", {
        "active_page": "sellers",
        "seller": seller,
    })


def _handle_create_link_post(request, seller):
    amount_display = request.POST.get("amount_display", "").strip()
    installments = request.POST.get("installments", "1").strip()
    customer_name = request.POST.get("customer_name", "").strip() or None
    customer_phone = request.POST.get("customer_phone", "").strip() or None

    try:
        clean = amount_display.replace(".", "").replace(",", ".")
        amount_cents = int(float(clean) * 100)
    except (ValueError, TypeError):
        return render(request, "panel/payment_links/create.html", {
            "active_page": "sellers",
            "seller": seller,
            "error": "Informe um valor válido.",
            "form_data": {
                "amount_display": amount_display,
                "installments": int(installments),
                "customer_name": customer_name,
                "customer_phone": customer_phone,
            },
        })

    try:
        installments = int(installments)
    except (ValueError, TypeError):
        installments = 1

    today = date.today()
    ref_suffix = uuid.uuid4().hex[:4].upper()
    reference = f"{today.strftime('%Y%m%d')}-{ref_suffix}"

    idempotency_key = str(uuid.uuid4())

    result = create_payment_link(
        seller=seller,
        reference=reference,
        amount_cents=amount_cents,
        installments=installments,
        idempotency_key=idempotency_key,
        customer_name=customer_name,
        customer_phone=customer_phone,
    )

    if not result.success:
        return render(request, "panel/payment_links/create.html", {
            "active_page": "sellers",
            "seller": seller,
            "error": result.error_message,
            "form_data": {
                "amount_display": amount_display,
                "installments": installments,
                "customer_name": customer_name,
                "customer_phone": customer_phone,
            },
        })

    payment_link = result.payment_link
    whatsapp_status = None
    if payment_link.payment_url:
        queue_payment_link_created(seller=seller, payment_link=payment_link)
        whatsapp_status = "ENVIADO"

    return render(request, "panel/payment_links/create.html", {
        "active_page": "sellers",
        "seller": seller,
        "success": True,
        "payment_link": payment_link,
        "whatsapp_status": whatsapp_status,
    })
