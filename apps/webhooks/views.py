"""Webhook receiver views — Pagar.me webhook endpoint."""
import hashlib
import hmac
import json
import logging

from django.conf import settings
from django.db import IntegrityError
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import ProcessingStatus, WebhookEvent
from .processor import process_webhook_event

logger = logging.getLogger("apps.webhooks")

MAX_BODY_SIZE = getattr(settings, "PAGARME_WEBHOOK_MAX_BODY_BYTES", 1_048_576)


@csrf_exempt
@require_POST
def pagarme_webhook(request):
    """Receive Pagar.me webhook events.

    Persists the event immediately, then processes asynchronously via on_commit.
    """
    content_type = request.content_type or ""
    if "application/json" not in content_type:
        logger.warning("Webhook rejeitado: Content-Type=%s", content_type)
        return JsonResponse({"error": "Content-Type must be application/json"}, status=400)

    body = request.body
    if len(body) > MAX_BODY_SIZE:
        logger.warning("Webhook rejeitado: body=%d bytes excede limite", len(body))
        return JsonResponse({"error": "Payload too large"}, status=400)

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        logger.warning("Webhook rejeitado: JSON inválido")
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    auth_valid, auth_reason = _validate_auth(request)
    if not auth_valid:
        logger.warning("Webhook rejeitado: autenticação inválida (%s)", auth_reason)
        return JsonResponse({"error": "Unauthorized"}, status=401)

    event_id = payload.get("id", "")
    event_type = payload.get("type", "")

    if not event_type:
        logger.warning("Webhook rejeitado: payload sem type")
        return JsonResponse({"error": "Missing event type"}, status=400)

    payload_sha256 = hashlib.sha256(body).hexdigest()

    headers_summary = {
        "content_type": request.content_type,
        "user_agent": (request.META.get("HTTP_USER_AGENT", "") or "")[:255],
    }

    try:
        event = WebhookEvent.objects.create(
            provider="pagarme",
            provider_event_id=event_id or None,
            event_type=event_type,
            payload=payload,
            payload_sha256=payload_sha256,
            headers_summary=headers_summary,
            authenticity_status="VERIFIED",
            processing_status=ProcessingStatus.RECEIVED,
        )
    except IntegrityError:
        logger.info("Evento duplicado: id=%s type=%s", event_id, event_type)
        return JsonResponse({"received": True, "event_id": event_id, "duplicate": True})

    logger.info("Webhook persistido: id=%s type=%s", event_id, event_type)

    from django.db import transaction
    transaction.on_commit(lambda: process_webhook_event(event))

    return JsonResponse({"received": True, "event_id": event_id, "duplicate": False})


def _validate_auth(request) -> tuple[bool, str]:
    """Validate webhook authentication based on configured mode."""
    auth_mode = getattr(settings, "PAGARME_WEBHOOK_AUTH_MODE", "basic")

    if auth_mode == "none":
        return True, "none"

    if auth_mode == "basic":
        return _validate_basic_auth(request)

    logger.error("PAGARME_WEBHOOK_AUTH_MODE desconhecido: %s", auth_mode)
    return False, f"unknown_mode:{auth_mode}"


def _validate_basic_auth(request) -> tuple[bool, str]:
    """Validate Basic Auth with constant-time comparison."""
    import base64

    expected_user = getattr(settings, "PAGARME_WEBHOOK_BASIC_AUTH_USER", "")
    expected_password = getattr(settings, "PAGARME_WEBHOOK_BASIC_AUTH_PASSWORD", "")

    if not expected_user:
        logger.warning("PAGARME_WEBHOOK_BASIC_AUTH_USER não configurado")
        return False, "not_configured"

    auth_header = request.META.get("HTTP_AUTHORIZATION", "")
    if not auth_header.startswith("Basic "):
        return False, "no_basic_header"

    try:
        encoded = auth_header[6:]
        decoded = base64.b64decode(encoded).decode("utf-8")
        username, password = decoded.split(":", 1)
    except Exception:
        return False, "decode_error"

    user_valid = hmac.compare_digest(username, expected_user)
    password_valid = hmac.compare_digest(password, expected_password)

    if not user_valid or not password_valid:
        return False, "credentials_mismatch"

    return True, "ok"
