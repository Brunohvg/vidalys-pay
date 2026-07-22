"""Authenticated Web Push subscription endpoints for the seller app."""
import json

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from apps.notifications.models import PushSubscription

from .decorators import seller_login_required


@seller_login_required
@require_http_methods(["GET", "POST", "DELETE"])
def push_subscriptions(request):
    if request.method == "GET":
        return JsonResponse({"data": {
            "available": bool(settings.WEBPUSH_VAPID_PUBLIC_KEY and settings.WEBPUSH_VAPID_PRIVATE_KEY),
            "public_key": settings.WEBPUSH_VAPID_PUBLIC_KEY,
            "active_devices": PushSubscription.objects.filter(seller=request.seller, is_active=True).count(),
        }})
    try:
        payload = json.loads(request.body or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "JSON inválido."}, status=400)
    endpoint = str(payload.get("endpoint", "")).strip()
    if not endpoint:
        return JsonResponse({"error": "Assinatura não informada."}, status=400)
    if request.method == "DELETE":
        PushSubscription.objects.filter(seller=request.seller, endpoint=endpoint).update(is_active=False)
        return JsonResponse({}, status=204)
    keys = payload.get("keys") or {}
    p256dh = str(keys.get("p256dh", "")).strip()
    auth = str(keys.get("auth", "")).strip()
    if not p256dh or not auth:
        return JsonResponse({"error": "Chaves da assinatura não informadas."}, status=400)
    if not settings.WEBPUSH_VAPID_PUBLIC_KEY or not settings.WEBPUSH_VAPID_PRIVATE_KEY:
        return JsonResponse({"error": "Notificações ainda não foram configuradas."}, status=503)
    subscription, created = PushSubscription.objects.update_or_create(
        endpoint=endpoint,
        defaults={"seller": request.seller, "p256dh": p256dh, "auth": auth,
                  "user_agent": request.META.get("HTTP_USER_AGENT", "")[:255],
                  "is_active": True, "failure_count": 0},
    )
    return JsonResponse({"data": {"id": str(subscription.id), "created": created}}, status=201 if created else 200)
