"""Reviewed HTML creation flow for managers and sellers."""
import uuid
from datetime import date

from django.contrib import messages
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, rende
from django.views.decorators.http import require_http_methods

from apps.admin_panel.views import admin_required
from apps.boletos.forms import BoletoCreationForm
from apps.boletos.models import Boleto
from apps.boletos.permissions import BoletoActor, resolve_creation_seller, scope_boletos
from apps.boletos.selectors import boleto_list_page, boleto_metrics
from apps.boletos.services.boleto_creation import BoletoCreationData, create_boleto
from apps.notifications.models import WhatsAppMessage
from apps.sellers.decorators import seller_login_required
from apps.sellers.models import Selle

REVIEW_SALT = "boletos.creation.review.v1"
REVIEW_MAX_AGE_SECONDS = 60 * 60


@admin_required
def manager_boleto_list(request):
    actor = BoletoActor(user=request.user)
    page, query_without_page = boleto_list_page(actor=actor, params=request.GET)
    return render(
        request,
        "panel/boletos/list.html",
        {
            "active_page": "boletos",
            "page_obj": page,
            "boletos": page.object_list,
            "metrics": boleto_metrics(actor=actor),
            "sellers": Seller.objects.filter(is_active=True).order_by("name"),
            "status_choices": Boleto._meta.get_field("status").choices,
            "filters": request.GET,
            "query_without_page": query_without_page,
            "is_manager": True,
        },
    )


@seller_login_required
def seller_boleto_list(request):
    actor = BoletoActor(seller=request.seller)
    page, query_without_page = boleto_list_page(actor=actor, params=request.GET)
    return render(
        request,
        "sellers/boletos/list.html",
        {
            "seller": request.seller,
            "active_tab": "boleto",
            "page_obj": page,
            "boletos": page.object_list,
            "status_choices": Boleto._meta.get_field("status").choices,
            "filters": request.GET,
            "query_without_page": query_without_page,
        },
    )


@admin_required
@require_http_methods(["GET", "POST"])
def manager_create_boleto(request):
    actor = BoletoActor(user=request.user)
    return _creation_flow(
        request,
        actor=actor,
        template_name="panel/boletos/create.html",
        detail_route="boletos:manager_detail",
        sellers=Seller.objects.filter(is_active=True).order_by("name"),
    )


@seller_login_required
@require_http_methods(["GET", "POST"])
def seller_create_boleto(request):
    actor = BoletoActor(seller=request.seller)
    return _creation_flow(
        request,
        actor=actor,
        template_name="sellers/boletos/create.html",
        detail_route="boletos:seller_detail",
    )


@admin_required
def manager_boleto_detail(request, boleto_id):
    actor = BoletoActor(user=request.user)
    boleto = get_object_or_404(
        scope_boletos(Boleto.objects.select_related("company", "seller"), actor=actor),
        id=boleto_id,
    )
    return render(
        request,
        "panel/boletos/detail.html",
        {
            "active_page": "boletos",
            "boleto": boleto,
            "webhook_events": boleto.webhook_events.order_by("-received_at"),
            "notification_events": _notification_history(boleto),
            "show_technical": True,
        },
    )


@seller_login_required
def seller_boleto_detail(request, boleto_id):
    boleto = get_object_or_404(
        scope_boletos(
            Boleto.objects.select_related("company", "seller"),
            actor=BoletoActor(seller=request.seller),
        ),
        id=boleto_id,
    )
    return render(
        request,
        "sellers/boletos/detail.html",
        {
            "boleto": boleto,
            "seller": request.seller,
            "active_tab": "boleto",
            "notification_events": _notification_history(boleto),
            "show_technical": False,
        },
    )


def _notification_history(boleto):
    return WhatsAppMessage.objects.filter(boleto=boleto).order_by("-created_at")


def _creation_flow(request, *, actor, template_name, detail_route, sellers=None):
    context = {
        "form": BoletoCreationForm(),
        "sellers": sellers,
        "minimum_due_date": date.today().isoformat(),
        "active_page": "boletos",
        "active_tab": "boleto",
    }
    if actor.is_seller:
        context["seller"] = actor.selle

    if request.method == "GET":
        return render(request, template_name, context)

    action = request.POST.get("action", "review")
    if action == "confirm":
        return _confirm_creation(request, actor, template_name, detail_route, context)
    if action == "edit":
        return _edit_review(request, template_name, context)

    form = BoletoCreationForm(request.POST)
    context["form"] = form
    if not form.is_valid():
        return render(request, template_name, context, status=400)

    requested_seller = _requested_seller(form.cleaned_data.get("seller_id"))
    try:
        seller = resolve_creation_seller(actor=actor, requested_seller=requested_seller)
    except PermissionDenied as exc:
        form.add_error("seller_id", str(exc))
        return render(request, template_name, context, status=403)

    if form.cleaned_data["amount_display"] > seller.max_payment_amount_cents:
        form.add_error("amount_display", "O valor excede o limite do vendedor.")
        return render(request, template_name, context, status=400)

    review_payload = _review_payload(form.cleaned_data, seller)
    context.update(
        {
            "review": review_payload,
            "review_token": signing.dumps(review_payload, salt=REVIEW_SALT, compress=True),
        }
    )
    return render(request, template_name, context)


def _confirm_creation(request, actor, template_name, detail_route, context):
    token = request.POST.get("review_token", "")
    try:
        payload = signing.loads(
            token,
            salt=REVIEW_SALT,
            max_age=REVIEW_MAX_AGE_SECONDS,
        )
    except signing.BadSignature:
        messages.error(request, "A revisão expirou ou foi alterada. Revise os dados novamente.")
        return render(request, template_name, context, status=400)

    requested_seller = _requested_seller(payload.get("seller_id"))
    try:
        seller = resolve_creation_seller(actor=actor, requested_seller=requested_seller)
    except PermissionDenied:
        raise PermissionDenied("Vendedor não autorizado para esta emissão.") from None

    data = BoletoCreationData(
        cnpj=payload["cnpj"],
        legal_name=payload["legal_name"],
        trade_name=payload["trade_name"],
        email=payload["email"],
        phone=payload["phone"],
        whatsapp_phone=payload["whatsapp_phone"],
        zip_code=payload["zip_code"],
        street=payload["street"],
        number=payload["number"],
        complement=payload["complement"],
        district=payload["district"],
        city=payload["city"],
        state=payload["state"],
        amount_cents=payload["amount_cents"],
        due_date=date.fromisoformat(payload["due_date"]),
        description=payload["description"],
        internal_reference=payload["internal_reference"],
        internal_notes=payload["internal_notes"],
    )
    result = create_boleto(
        seller=seller,
        actor_user=actor.user,
        actor_seller=actor.seller,
        data=data,
        idempotency_key=payload["idempotency_key"],
    )
    if result.boleto and (result.success or result.uncertain):
        if result.uncertain:
            messages.warning(request, result.error_message)
        return redirect(detail_route, boleto_id=result.boleto.id)

    context["review"] = payload
    context["review_token"] = token
    context["creation_error"] = result.error_message
    return render(request, template_name, context, status=400)


def _edit_review(request, template_name, context):
    try:
        payload = signing.loads(
            request.POST.get("review_token", ""),
            salt=REVIEW_SALT,
            max_age=REVIEW_MAX_AGE_SECONDS,
        )
    except signing.BadSignature:
        messages.error(request, "A revisão expirou. Preencha os dados novamente.")
        return render(request, template_name, context, status=400)

    initial = {
        **payload,
        "amount_display": (
            f"{payload['amount_cents'] // 100},{payload['amount_cents'] % 100:02d}"
        ),
    }
    context["form"] = BoletoCreationForm(initial=initial)
    return render(request, template_name, context)


def _requested_seller(seller_id):
    if not seller_id:
        return None
    return Seller.objects.filter(id=seller_id).first()


def _review_payload(cleaned_data, seller):
    return {
        "cnpj": cleaned_data["cnpj"],
        "legal_name": cleaned_data["legal_name"],
        "trade_name": cleaned_data["trade_name"],
        "email": cleaned_data["email"],
        "phone": cleaned_data["phone"],
        "whatsapp_phone": cleaned_data["whatsapp_phone"],
        "zip_code": cleaned_data["zip_code"],
        "street": cleaned_data["street"],
        "number": cleaned_data["number"],
        "complement": cleaned_data["complement"],
        "district": cleaned_data["district"],
        "city": cleaned_data["city"],
        "state": cleaned_data["state"],
        "amount_cents": cleaned_data["amount_display"],
        "due_date": cleaned_data["due_date"].isoformat(),
        "description": cleaned_data["description"],
        "internal_reference": cleaned_data["internal_reference"],
        "internal_notes": cleaned_data["internal_notes"],
        "seller_id": str(seller.id),
        "seller_name": seller.name,
        "idempotency_key": str(uuid.uuid4()),
    }
