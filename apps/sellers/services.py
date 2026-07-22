"""Seller services — invitation generation, activation, session management."""
import hashlib
import hmac
import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.db import transaction
from django.utils import timezone

from .models import Seller, SellerInvitation, SellerSession

logger = logging.getLogger("apps.sellers")


def _hash_token(raw_token: str) -> str:
    pepper = getattr(settings, "INVITATION_TOKEN_PEPPER", "")
    return hashlib.sha256((raw_token + pepper).encode()).hexdigest()


def _verify_token(raw_token: str, stored_hash: str) -> bool:
    computed = _hash_token(raw_token)
    return hmac.compare_digest(computed, stored_hash)


def generate_invitation(*, seller: Seller, created_by=None) -> tuple[SellerInvitation, str]:
    raw_token = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw_token)

    now = timezone.now()
    expiration_hours = getattr(settings, "INVITATION_EXPIRATION_HOURS", 24)
    expires_at = now + timedelta(hours=expiration_hours)

    with transaction.atomic():
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


def validate_invitation(*, raw_token: str) -> tuple[dict | None, str | None, str | None]:
    """Validate invitation without consuming it.

    Returns (context_dict, error_message, None) on success.
    Returns (None, error_message, None) on failure.

    context_dict contains: invitation_id, seller_name, seller_id, expires_at
    """
    token_hash = _hash_token(raw_token)
    now = timezone.now()

    invitation = (
        SellerInvitation.objects
        .select_related("seller")
        .select_for_update()
        .filter(token_hash=token_hash)
        .first()
    )

    if invitation is None:
        logger.warning("Convite não encontrado para hash")
        return None, "Link não encontrado. Solicite um novo convite.", None

    if invitation.used_at is not None:
        logger.warning("Convite já utilizado: %s", invitation.id)
        return None, "Este link já foi utilizado.", None

    if invitation.revoked_at is not None:
        logger.warning("Convite revogado: %s", invitation.id)
        return None, "Este link foi revogado. Solicite um novo convite.", None

    if invitation.expires_at < now:
        logger.warning("Convite expirado: %s", invitation.id)
        return None, "Este link expirou. Solicite um novo convite.", None

    seller = invitation.seller
    if not seller.is_active:
        logger.warning("Vendedor inativo: %s", seller.id)
        return None, "Seu acesso foi desativado. Entre em contato com o administrador.", None

    logger.info("Convite validado para vendedor %s", seller.id)

    return {
        "invitation_id": str(invitation.id),
        "seller_name": seller.name,
        "seller_id": str(seller.id),
        "expires_at": invitation.expires_at,
    }, None, token_hash


def activate_session(
    *,
    token_hash: str,
    request_ip: str | None,
    user_agent: str,
    get_response_callback,
) -> tuple[SellerSession | None, str | None]:
    """Complete activation within an atomic transaction.

    1. Locks and validates the invitation
    2. Creates Django session via the callback
    3. Creates SellerSession
    4. Marks invitation as used

    The get_response_callback receives the seller and returns a response object.
    All DB operations happen inside a single atomic block.

    Returns (SellerSession, None) on success, (None, error_message) on failure.
    """
    now = timezone.now()

    try:
        with transaction.atomic():
            invitation = (
                SellerInvitation.objects
                .select_related("seller")
                .select_for_update()
                .filter(token_hash=token_hash)
                .first()
            )

            if invitation is None:
                logger.warning("Convite não encontrado na confirmação")
                return None, "Link não encontrado."

            if invitation.used_at is not None:
                logger.warning("Convite já utilizado na confirmação: %s", invitation.id)
                return None, "Este link já foi utilizado."

            if invitation.revoked_at is not None:
                logger.warning("Convite revogado na confirmação: %s", invitation.id)
                return None, "Este link foi revogado."

            if invitation.expires_at < now:
                logger.warning("Convite expirado na confirmação: %s", invitation.id)
                return None, "Este link expirou."

            seller = invitation.seller
            if not seller.is_active:
                logger.warning("Vendedor inativo na confirmação: %s", seller.id)
                return None, "Seu acesso foi desativado."

            session_days = getattr(settings, "SELLER_SESSION_DAYS", 30)
            session_seconds = session_days * 24 * 60 * 60
            expires_at = now + timedelta(seconds=session_seconds)

            response = get_response_callback(seller)

            session_key = response.session_key
            if not session_key:
                raise RuntimeError("Django não gerou uma session_key.")

            seller_id_from_session = response.session_data.get("seller_id")
            if seller_id_from_session != str(seller.id):
                raise RuntimeError(
                    f"seller_id divergente na sessão: {seller_id_from_session} != {seller.id}"
                )

            if not Session.objects.filter(session_key=session_key).exists():
                raise RuntimeError("A sessão Django não foi persistida.")

            session_suffix = session_key[-6:]
            logger.info(
                "Sessão Django persistida; seller=%s session_suffix=%s",
                seller.id,
                session_suffix,
            )

            seller_session = SellerSession.objects.create(
                seller=seller,
                django_session_key=session_key,
                ip_first=request_ip,
                user_agent_summary=user_agent[:255],
                expires_at=expires_at,
                last_seen_at=now,
            )

            logger.info(
                "SellerSession persistida; seller=%s session_suffix=%s",
                seller.id,
                session_suffix,
            )

            invitation.used_at = now
            invitation.save(update_fields=["used_at"])

            logger.info(
                "Convite marcado como utilizado; seller=%s invitation=%s",
                seller.id,
                invitation.id,
            )

        logger.info(
            "Ativação concluída; seller=%s session_suffix=%s",
            seller.id,
            session_key[-6:],
        )
        return seller_session, None

    except Exception:
        logger.exception("Falha ao ativar convite")
        return None, "Erro interno ao ativar o convite. Tente novamente."


def revoke_all_sessions(*, seller: Seller) -> int:
    now = timezone.now()
    sessions = SellerSession.objects.filter(seller=seller, revoked_at__isnull=True)
    count = sessions.count()

    for session in sessions:
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
    cookie_present = settings.SESSION_COOKIE_NAME in request.COOKIES

    seller_id = request.session.get("seller_id")
    if not seller_id:
        if cookie_present:
            logger.warning(
                "Sessão de vendedor inválida: seller_id ausente; cookie_presente=True"
            )
        return None

    session_key = request.session.session_key
    if not session_key:
        logger.warning(
            "Sessão de vendedor inválida: session_key ausente; seller_id=%s",
            seller_id,
        )
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
        logger.warning(
            "SellerSession não encontrada; seller_id=%s session_suffix=%s",
            seller_id,
            session_key[-6:],
        )
        return None

    if not seller_session.seller.is_active:
        logger.warning(
            "Vendedor inativo; seller_id=%s session_suffix=%s",
            seller_id,
            session_key[-6:],
        )
        return None

    now = timezone.now()
    if seller_session.last_seen_at is None or (now - seller_session.last_seen_at).total_seconds() > 60:
        seller_session.last_seen_at = now
        seller_session.save(update_fields=["last_seen_at"])

    return seller_session.seller
