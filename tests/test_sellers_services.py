"""Tests for seller services — invitations, sessions, access control."""
from datetime import timedelta

import pytest
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.utils import timezone

from apps.sellers.models import Seller, SellerInvitation, SellerSession
from apps.sellers.services import (
    _hash_token,
    activate_session,
    generate_invitation,
    revoke_all_sessions,
    validate_invitation,
)


@pytest.fixture
def seller(db):
    return Seller.objects.create(
        name="Bruno Vendas",
        whatsapp_phone="+5531999999999",
        max_payment_amount_cents=1000000,
        is_active=True,
    )


@pytest.fixture
def inactive_seller(db):
    return Seller.objects.create(
        name="Seller Inativo",
        whatsapp_phone="+5531888888888",
        max_payment_amount_cents=500000,
        is_active=False,
    )


# --- Invitation Generation ---


@pytest.mark.django_db
def test_generate_invitation_creates_token(seller):
    invitation, raw_token = generate_invitation(seller=seller)

    assert invitation.pk is not None
    assert len(raw_token) >= 40
    assert invitation.seller == seller
    assert invitation.used_at is None
    assert invitation.revoked_at is None
    assert invitation.expires_at > timezone.now()


@pytest.mark.django_db
def test_generate_invitation_revokes_previous(seller):
    inv1, _ = generate_invitation(seller=seller)
    inv2, _ = generate_invitation(seller=seller)

    inv1.refresh_from_db()
    assert inv1.revoked_at is not None
    assert inv2.revoked_at is None


@pytest.mark.django_db
def test_generate_invitation_stores_hash_not_token(seller):
    invitation, raw_token = generate_invitation(seller=seller)

    assert SellerInvitation.objects.filter(token_hash=raw_token).count() == 0
    assert invitation.token_hash != raw_token
    assert len(invitation.token_hash) == 64


# --- Invitation Validation (GET — does NOT consume) ---


@pytest.mark.django_db
def test_validate_invitation_success(seller):
    _, raw_token = generate_invitation(seller=seller)

    context, error, _ = validate_invitation(raw_token=raw_token)

    assert context is not None
    assert context["seller_name"] == seller.name
    assert error is None

    invitation = SellerInvitation.objects.get(seller=seller)
    assert invitation.used_at is None


@pytest.mark.django_db
def test_validate_invitation_fails_for_used(seller):
    _, raw_token = generate_invitation(seller=seller)

    invitation = SellerInvitation.objects.get(seller=seller)
    invitation.used_at = timezone.now()
    invitation.save(update_fields=["used_at"])

    context, error, _ = validate_invitation(raw_token=raw_token)

    assert context is None
    assert "já foi utilizado" in error


@pytest.mark.django_db
def test_validate_invitation_fails_for_inactive_seller(inactive_seller):
    _, raw_token = generate_invitation(seller=inactive_seller)

    context, error, _ = validate_invitation(raw_token=raw_token)

    assert context is None
    assert "desativado" in error


@pytest.mark.django_db
def test_validate_invitation_fails_for_invalid_token(seller):
    generate_invitation(seller=seller)

    context, error, _ = validate_invitation(raw_token="invalid-token-12345")

    assert context is None
    assert "encontrado" in error


@pytest.mark.django_db
def test_validate_invitation_fails_for_expired(seller):
    invitation, raw_token = generate_invitation(seller=seller)

    invitation.expires_at = timezone.now() - timedelta(hours=1)
    invitation.save(update_fields=["expires_at"])

    context, error, _ = validate_invitation(raw_token=raw_token)

    assert context is None
    assert "expirou" in error


# --- Activation (POST — consumes) ---


def _make_callback(seller):
    """Create a callback that creates a real Django session."""
    def callback(s):
        assert s == seller
        django_session = SessionStore()
        django_session["seller_id"] = str(s.id)
        django_session.create()
        return SessionData(session_key=django_session.session_key, session_data={"seller_id": str(s.id)})
    return callback


class SessionData:
    def __init__(self, session_key, session_data):
        self.session_key = session_key
        self.session_data = session_data


@pytest.mark.django_db
def test_activate_session_success(seller):
    _, raw_token = generate_invitation(seller=seller)
    token_hash = _hash_token(raw_token)

    seller_session, error = activate_session(
        token_hash=token_hash,
        request_ip="127.0.0.1",
        user_agent="TestAgent/1.0",
        get_response_callback=_make_callback(seller),
    )

    assert seller_session is not None
    assert error is None
    assert seller_session.seller == seller
    assert seller_session.ip_first == "127.0.0.1"

    invitation = SellerInvitation.objects.get(seller=seller)
    assert invitation.used_at is not None

    assert Session.objects.filter(session_key=seller_session.django_session_key).exists()


@pytest.mark.django_db
def test_activate_session_fails_twice(seller):
    _, raw_token = generate_invitation(seller=seller)
    token_hash = _hash_token(raw_token)

    session1, error1 = activate_session(
        token_hash=token_hash,
        request_ip="127.0.0.1",
        user_agent="TestAgent/1.0",
        get_response_callback=_make_callback(seller),
    )
    session2, error2 = activate_session(
        token_hash=token_hash,
        request_ip="127.0.0.1",
        user_agent="TestAgent/2.0",
        get_response_callback=_make_callback(seller),
    )

    assert session1 is not None
    assert session2 is None
    assert "já foi utilizado" in (error2 or "")
    assert SellerSession.objects.filter(seller=seller).count() == 1


@pytest.mark.django_db
def test_activate_session_fails_for_inactive_seller(inactive_seller):
    _, raw_token = generate_invitation(seller=inactive_seller)
    token_hash = _hash_token(raw_token)

    session, error = activate_session(
        token_hash=token_hash,
        request_ip="127.0.0.1",
        user_agent="TestAgent",
        get_response_callback=_make_callback(inactive_seller),
    )

    assert session is None
    assert "desativado" in (error or "")

    invitation = SellerInvitation.objects.get(seller=inactive_seller)
    assert invitation.used_at is None


@pytest.mark.django_db
def test_activate_session_marks_used_only_on_success(seller):
    """Invitation should NOT be marked as used if session creation fails."""
    _, raw_token = generate_invitation(seller=seller)
    token_hash = _hash_token(raw_token)

    def failing_callback(s):
        raise RuntimeError("Falha simulada ao criar sessão")

    session, error = activate_session(
        token_hash=token_hash,
        request_ip="127.0.0.1",
        user_agent="TestAgent",
        get_response_callback=failing_callback,
    )

    assert session is None
    assert error is not None

    invitation = SellerInvitation.objects.get(seller=seller)
    assert invitation.used_at is None


@pytest.mark.django_db
def test_activate_session_concurrent_only_one(seller):
    """Concurrent activations should only create one session."""
    _, raw_token = generate_invitation(seller=seller)
    token_hash = _hash_token(raw_token)

    session1, _ = activate_session(
        token_hash=token_hash,
        request_ip="127.0.0.1",
        user_agent="A",
        get_response_callback=_make_callback(seller),
    )
    session2, _ = activate_session(
        token_hash=token_hash,
        request_ip="127.0.0.1",
        user_agent="B",
        get_response_callback=_make_callback(seller),
    )

    assert (session1 is not None) != (session2 is not None)
    assert SellerSession.objects.filter(seller=seller).count() == 1


# --- Revocation ---


@pytest.mark.django_db
def test_revoke_all_sessions(seller):
    _, raw_token1 = generate_invitation(seller=seller)
    activate_session(
        token_hash=_hash_token(raw_token1),
        request_ip=None,
        user_agent="",
        get_response_callback=_make_callback(seller),
    )
    _, raw_token2 = generate_invitation(seller=seller)
    activate_session(
        token_hash=_hash_token(raw_token2),
        request_ip=None,
        user_agent="",
        get_response_callback=_make_callback(seller),
    )

    assert SellerSession.objects.filter(seller=seller, revoked_at__isnull=True).count() == 2

    count = revoke_all_sessions(seller=seller)

    assert count == 2
    assert SellerSession.objects.filter(seller=seller, revoked_at__isnull=True).count() == 0
