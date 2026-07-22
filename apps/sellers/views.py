"""Seller views — invitation activation, app pages, profile."""
import logging

from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST

from .decorators import seller_login_required
from .services import consume_invitation, revoke_all_sessions

logger = logging.getLogger("apps.sellers")


# --- Activation ---


@require_GET
def activate_invitation(request, token):
    """Activate an invitation from WhatsApp link.

    Consumes the token atomically and creates a session.
    Redirects to /app on success.
    """
    ip = _get_client_ip(request)
    user_agent = request.META.get("HTTP_USER_AGENT", "")[:255]

    seller_session, error_message = consume_invitation(
        raw_token=token,
        request_ip=ip,
        user_agent=user_agent,
    )

    if seller_session is None:
        return render(request, "sellers/activation_invalid.html", {
            "error_message": error_message or "Este link de acesso não é válido, já foi utilizado ou expirou.",
        }, status=400)

    # Migrate session data to current request session
    from django.contrib.sessions.backends.db import SessionStore
    from django.contrib.sessions.models import Session

    store = SessionStore(session_key=seller_session.django_session_key)
    request.session.update(dict(store))
    request.session["seller_id"] = str(seller_session.seller_id)
    request.session.save()

    seller_session.django_session_key = request.session.session_key
    seller_session.save(update_fields=["django_session_key"])

    response = redirect("/app/")
    response["Referrer-Policy"] = "no-referrer"
    return response


# --- App Pages ---


@seller_login_required
@require_GET
def app_new_link(request):
    """New payment link form page."""
    seller = request.seller
    return render(request, "sellers/app_new_link.html", {
        "seller": seller,
        "active_tab": "new",
    })


@seller_login_required
@require_GET
def app_history(request):
    """Payment links history page."""
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
    """Seller profile page."""
    seller = request.seller
    from apps.sellers.models import SellerSession

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
    """Payment link created success page."""
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


# --- API (JSON) ---


@seller_login_required
@require_GET
def seller_profile(request):
    """Return seller profile as JSON."""
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
    """Logout current seller session."""
    from django.utils import timezone

    seller_id = request.session.get("seller_id")
    session_key = request.session.session_key

    if seller_id and session_key:
        from .models import SellerSession

        SellerSession.objects.filter(
            django_session_key=session_key,
            seller_id=seller_id,
        ).update(revoked_at=timezone.now())

    request.session.flush()
    return JsonResponse({}, status=204)


@require_POST
def seller_logout_all(request):
    """Logout all sessions for current seller."""
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
    """Mask phone for display: +55319****9999."""
    if len(phone) <= 7:
        return phone
    return phone[:5] + "*" * (len(phone) - 8) + phone[-3:]


@require_GET
def index(request):
    """Redireciona raiz para a página principal do app."""
    return redirect("sellers:app_new_link")
