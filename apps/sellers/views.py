"""Seller views — invitation activation, app pages, profile."""
import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .decorators import seller_login_required
from .models import SellerSession
from .services import (
    activate_session,
    generate_invitation,
    get_seller_from_session,
    revoke_all_sessions,
    validate_invitation,
)

logger = logging.getLogger("apps.sellers")


# --- Activation ---


@require_GET
def activate_invitation(request, token):
    """Show confirmation page. Does NOT consume the invitation."""
    context, error_message, _token_hash = validate_invitation(raw_token=token)

    if context is None:
        return render(request, "sellers/activation_invalid.html", {
            "error_message": error_message or "Este link de acesso não é válido.",
        }, status=400)

    request.session["_invitation_token_hash"] = _token_hash
    if request.session.session_key is None:
        request.session.create()

    return render(request, "sellers/activation_confirm.html", {
        "seller_name": context["seller_name"],
        "token": token,
    })


@require_POST
def confirm_activation(request, token):
    """Confirm activation: create session and consume invitation atomically."""
    stored_hash = request.session.pop("_invitation_token_hash", None)
    if stored_hash is None:
        context, error_message, _token_hash = validate_invitation(raw_token=token)
        if context is None:
            return render(request, "sellers/activation_invalid.html", {
                "error_message": error_message or "Este link de acesso não é válido.",
            }, status=400)
        stored_hash = _token_hash

    ip = _get_client_ip(request)
    user_agent = request.META.get("HTTP_USER_AGENT", "")[:255]

    def create_session_callback(seller):
        """Callback that creates the Django session inside the atomic block."""
        request.session.cycle_key()
        request.session["seller_id"] = str(seller.id)

        session_days = getattr(settings, "SELLER_SESSION_DAYS", 30)
        session_seconds = session_days * 24 * 60 * 60
        request.session.set_expiry(session_seconds)
        request.session.save()

        return SessionData(
            session_key=request.session.session_key,
            session_data={"seller_id": str(seller.id)},
        )

    seller_session, error_message = activate_session(
        token_hash=stored_hash,
        request_ip=ip,
        user_agent=user_agent,
        get_response_callback=create_session_callback,
    )

    if seller_session is None:
        return render(request, "sellers/activation_invalid.html", {
            "error_message": error_message or "Não foi possível ativar o convite.",
        }, status=400)

    return redirect("sellers:app_new_link")


# --- App Pages ---


@seller_login_required
@require_GET
def app_new_link(request):
    seller = request.seller
    return render(request, "sellers/app_new_link.html", {
        "seller": seller,
        "active_tab": "new",
    })


@seller_login_required
@require_GET
def app_history(request):
    seller = request.seller
    from apps.payment_links.models import PaymentLink

    status_filter = request.GET.get("status", "")
    links = PaymentLink.objects.filter(seller=seller)

    if status_filter:
        links = links.filter(status=status_filter)

    links = links.select_related()[:50]

    return render(request, "sellers/app_history.html", {
        "seller": seller,
        "links": links,
        "status_filter": status_filter,
        "active_tab": "history",
    })


@seller_login_required
@require_GET
def app_profile(request):
    seller = request.seller
    sessions = SellerSession.objects.filter(
        seller=seller,
        revoked_at__isnull=True,
    ).order_by("-last_seen_at")

    return render(request, "sellers/app_profile.html", {
        "seller": seller,
        "sessions": sessions,
        "active_tab": "profile",
    })


@seller_login_required
@require_GET
def app_success(request):
    seller = request.seller
    link_id = request.GET.get("link_id")

    from apps.payment_links.models import PaymentLink

    link = None
    if link_id:
        link = PaymentLink.objects.filter(id=link_id, seller=seller).first()

    return render(request, "sellers/app_success.html", {
        "seller": seller,
        "link": link,
        "active_tab": "new",
    })


# --- Session invalid page ---


@require_GET
def session_invalid(request):
    """Friendly page shown when seller session is invalid."""
    return render(request, "sellers/session_invalid.html", status=401)


# --- API (JSON) ---


@seller_login_required
@require_GET
def seller_profile(request):
    seller = request.seller
    return JsonResponse({
        "data": {
            "id": str(seller.id),
            "name": seller.name,
            "whatsapp_phone": _mask_phone(seller.whatsapp_phone),
        }
    })


@require_POST
def seller_logout(request):
    seller_id = request.session.get("seller_id")
    session_key = request.session.session_key

    if seller_id and session_key:
        SellerSession.objects.filter(
            django_session_key=session_key,
            seller_id=seller_id,
        ).update(revoked_at=timezone.now())

    request.session.flush()
    return JsonResponse({}, status=204)


@require_POST
def seller_logout_all(request):
    seller_id = request.session.get("seller_id")
    if seller_id:
        from .models import Seller
        try:
            seller = Seller.objects.get(id=seller_id)
            revoke_all_sessions(seller=seller)
        except Seller.DoesNotExist:
            pass

    request.session.flush()
    return JsonResponse({}, status=204)


# --- Helpers ---


def _get_client_ip(request) -> str | None:
    x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded:
        return x_forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _mask_phone(phone: str) -> str:
    if len(phone) <= 7:
        return phone
    return phone[:5] + "*" * (len(phone) - 8) + phone[-3:]


@require_GET
def index(request):
    return redirect("sellers:app_new_link")


# --- Internal helpers ---


class SessionData:
    """Simple container for session data passed from view callback to service."""
    def __init__(self, session_key: str, session_data: dict):
        self.session_key = session_key
        self.session_data = session_data
