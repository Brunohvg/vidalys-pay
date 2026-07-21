"""API Key authentication for integrations (n8n, etc.)."""
import hashlib
import logging

from django.conf import settings
from django.utils import timezone

from apps.integrations.n8n.models import ApiClient

logger = logging.getLogger("apps.integrations")

# Available scopes
SCOPES = [
    "payment_links:read",
    "payment_links:write",
    "notifications:write",
]


def hash_api_key(key: str) -> str:
    """Hash an API key with pepper."""
    pepper = getattr(settings, "API_KEY_PEPPER", "")
    return hashlib.sha256((key + pepper).encode()).hexdigest()


def generate_api_key() -> tuple[str, str]:
    """Generate a new API key.

    Returns (raw_key, key_prefix).
    The raw_key is shown only once. The prefix is stored for identification.
    """
    import secrets

    raw_key = "vly_live_" + secrets.token_urlsafe(32)
    key_prefix = raw_key[:12]
    return raw_key, key_prefix


def authenticate_api_key(auth_header: str) -> ApiClient | None:
    """Authenticate an API key from Authorization header.

    Format: Bearer vly_live_xxxxx
    """
    if not auth_header.startswith("Bearer "):
        return None

    token = auth_header[7:]
    if not token.startswith("vly_live_"):
        return None

    key_hash = hash_api_key(token)

    try:
        client = ApiClient.objects.get(
            key_hash=key_hash,
            is_active=True,
        )
    except ApiClient.DoesNotExist:
        return None

    # Update last_used_at (throttle to once per minute)
    now = timezone.now()
    if client.last_used_at is None or (now - client.last_used_at).total_seconds() > 60:
        client.last_used_at = now
        client.save(update_fields=["last_used_at"])

    return client


def has_scope(client: ApiClient, scope: str) -> bool:
    """Check if an API client has a specific scope."""
    return scope in (client.scopes or [])
