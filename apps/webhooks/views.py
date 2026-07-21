"""Webhook receiver views — Pagar.me webhook endpoint."""
import hashlib
import json
import logging

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import ProcessingStatus, WebhookEvent
from .processor import process_webhook_event

logger = logging.getLogger("apps.webhooks")

MAX_BODY_SIZE = 1_048_576  # 1MB


@csrf_exempt
@require_POST
def pagarme_webhook(request):
    """Receive Pagar.me webhook events.

    Authentication: Basic Auth with PAGARME_WEBHOOK_BASIC_AUTH_USER as username.
    """
    # Validate Content-Type
    content_type = request.content_type or ""
    if "application/json" not in content_type:
        logger.warning("Content-Type inválido: %s", content_type)
        return JsonResponse(
            {"error": "Content-Type must be application/json"},
            status=400,
        )

    # Validate body size
    body = request.body
    if len(body) > MAX_BODY_SIZE:
        logger.warning("Body excede tamanho máximo: %d bytes", len(body))
        return JsonResponse(
            {"error": "Payload too large"},
            status=400,
        )

    # Parse JSON
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as e:
        logger.warning("JSON inválido: %s", e)
        return JsonResponse(
            {"error": "Invalid JSON"},
            status=400,
        )

    # Validate Basic Auth
    auth_valid = _validate_basic_auth(request)
    if not auth_valid:
        logger.warning("Autenticação inválida")
        return JsonResponse(
            {"error": "Unauthorized"},
            status=401,
        )

    # Calculate payload hash
    payload_sha256 = hashlib.sha256(body).hexdigest()

    # Extract event info
    event_id = payload.get("id", "")
    event_type = payload.get("type", "")

    if not event_type:
        logger.warning("Evento sem type: %s", event_id)
        return JsonResponse(
            {"error": "Missing event type"},
            status=400,
        )

    # Check for duplicate
    existing = None
    if event_id:
        existing = WebhookEvent.objects.filter(provider_event_id=event_id).first()
        if existing:
            logger.info("Evento duplicado: %s", event_id)
            return JsonResponse({
                "received": True,
                "event_id": event_id,
                "duplicate": True,
            })

    # Extract allowed headers
    headers_summary = {
        "content_type": request.content_type,
        "user_agent": request.META.get("HTTP_USER_AGENT", "")[:255],
    }

    # Create webhook event record
    event = WebhookEvent.objects.create(
        provider="pagarme",
        provider_event_id=event_id,
        event_type=event_type,
        payload=payload,
        payload_sha256=payload_sha256,
        headers_summary=headers_summary,
        authenticity_status="VERIFIED",
        processing_status=ProcessingStatus.RECEIVED,
    )

    logger.info(
        "Webhook recebido: id=%s type=%s",
        event_id,
        event_type,
    )

    # Process event
    process_webhook_event(event)

    return JsonResponse({
        "received": True,
        "event_id": event_id,
        "duplicate": False,
    })


def _validate_basic_auth(request) -> bool:
    """Validate Basic Auth header.

    Pagar.me sends: Authorization: Basic base64(username:)
    Where username is the webhook secret configured in Pagar.me dashboard.
    """
    import base64

    expected_user = settings.PAGARME_WEBHOOK_BASIC_AUTH_USER
    if not expected_user:
        logger.warning("PAGARME_WEBHOOK_BASIC_AUTH_USER não configurado")
        return False

    auth_header = request.META.get("HTTP_AUTHORIZATION", "")
    if not auth_header.startswith("Basic "):
        return False

    try:
        encoded = auth_header[6:]
        decoded = base64.b64decode(encoded).decode("utf-8")
        # Format: "username:" (password is empty)
        username, password = decoded.split(":", 1)
        return username == expected_user and password == ""
    except Exception:
        return False
