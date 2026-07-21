"""Seller services — invitation generation, activation, session management."""
import hashlib
import hmac
import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import Seller, SellerInvitation, SellerSession

logger = logging.getLogger("apps.sellers")


def _hash_token(raw_token: str) -> str:
    """SHA-256 hash with optional pepper."""
    pepper = getattr(settings, "INVITATION_TOKEN_PEPPER", "")
    return hashlib.sha256((raw_token + pepper).encode()).hexdigest()


def _verify_token(raw_token: str, stored_hash: str) -> bool:
    """Constant-time token verification."""
    computed = _hash_token(raw_token)
    return hmac.compare_digest(computed, stored_hash)


def generate_invitation(*, seller: Seller, created_by=None) -> tuple[SellerInvitation, str]:
    """Generate a new invitation, revoking previous valid ones.

    Returns (invitation, raw_token).
    """
    raw_token = secrets.token_urlsafe(32)  # 256+ bits
    token_hash = _hash_token(raw_token)

    now = timezone.now()
    expiration_hours = getattr(settings, "INVITATION_EXPIRATION_HOURS", 24)
    expires_at = now + timedelta(hours=expiration_hours)

    with transaction.atomic():
        # Revoke previous valid invitations for this seller
        SellerInvitation.objects.filter(
            seller=seller,
            used_at__isnull=True,
            revoked_at__isnull=True,
        ).update(revoked_at=now)

        invitation = SellerInvitation.objects.create(
            seller=seller,
            token_hash=token_hash,
            expires_at=expires_at,
            created_by=created_by,
        )

    logger.info("Convite criado para vendedor %s", seller.id)
    return invitation, raw_token


def consume_invitation(*, raw_token: str, request_ip: str | None = None, user_agent: str = "") -> SellerSession | None:
    """Atomically consume a valid invitation and create a session.

    Returns SellerSession if successful, None if invalid.
    """
    token_hash = _hash_token(raw_token)

    now = timezone.now()

    with transaction.atomic():
        # Lock the invitation row
        invitation = (
            SellerInvitation.objects.select_for_update()
            .filter(token_hash=token_hash)
            .first()
        )

        if invitation is None:
            logger.warning("Convite não encontrado para hash")
            return None

        # Check if already used
        if invitation.used_at is not None:
            logger.warning("Convite já utilizado: %s", invitation.id)
            return None

        # Check if revoked
        if invitation.revoked_at is not None:
            logger.warning("Convite revogado: %s", invitation.id)
            return None

        # Check expiration
        if invitation.expires_at < now:
            logger.warning("Convite expirado: %s", invitation.id)
            return None

        # Check if seller is active
        seller = invitation.seller
        if not seller.is_active:
            logger.warning("Vendedor inativo: %s", seller.id)
            return None

        # Mark as used
        invitation.used_at = now
        invitation.save(update_fields=["used_at"])

        # Create Django session
        from django.contrib.sessions.backends.db import SessionStore

        django_session = SessionStore()
        django_session["seller_id"] = str(seller.id)
        django_session.create()

        # Calculate session expiration
        session_days = getattr(settings, "SELLER_SESSION_DAYS", 30)
        session_expires = now + timedelta(days=session_days)

        # Create seller session record
        seller_session = SellerSession.objects.create(
            seller=seller,
            django_session_key=django_session.session_key,
            ip_first=request_ip,
            user_agent_summary=user_agent[:255],
            expires_at=session_expires,
            last_seen_at=now,
        )

    logger.info("Sessão criada para vendedor %s, sessão %s", seller.id, seller_session.id)
    return seller_session


def revoke_all_sessions(*, seller: Seller) -> int:
    """Revoke all active sessions for a seller. Returns count revoked."""
    now = timezone.now()
    sessions = SellerSession.objects.filter(seller=seller, revoked_at__isnull=True)
    count = sessions.count()

    for session in sessions:
        # Delete Django session
        from django.contrib.sessions.backends.db import SessionStore

        try:
            store = SessionStore(session_key=session.django_session_key)
            store.delete()
        except Exception:
            pass

        session.revoked_at = now
        session.save(update_fields=["revoked_at"])

    logger.info("Revogadas %d sessões do vendedor %s", count, seller.id)
    return count


def get_seller_from_session(request) -> Seller | None:
    """Extract seller from the current request's session.

    Returns Seller if valid session exists, None otherwise.
    """
    seller_id = request.session.get("seller_id")
    if not seller_id:
        return None

    session_key = request.session.session_key
    if not session_key:
        return None

    seller_session = (
        SellerSession.objects.select_related("seller")
        .filter(
            django_session_key=session_key,
            seller_id=seller_id,
            revoked_at__isnull=True,
            expires_at__gt=timezone.now(),
        )
        .first()
    )

    if seller_session is None:
        return None

    if not seller_session.seller.is_active:
        return None

    # Update last_seen_at (throttle to once per minute)
    now = timezone.now()
    if seller_session.last_seen_at is None or (now - seller_session.last_seen_at).total_seconds() > 60:
        seller_session.last_seen_at = now
        seller_session.save(update_fields=["last_seen_at"])

    return seller_session.seller
