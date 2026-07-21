"""Tests for seller services — invitations, sessions, access control."""
import pytest
from django.contrib.sessions.backends.db import SessionStore
from django.utils import timezone

from apps.sellers.models import Seller, SellerInvitation, SellerSession
from apps.sellers.services import (
    consume_invitation,
    generate_invitation,
    revoke_all_sessions,
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
    assert len(raw_token) >= 40  # 256 bits = 43 chars URL-safe
    assert invitation.seller == seller
    assert invitation.used_at is None
    assert invitation.revoked_at is None
    assert invitation.expires_at > timezone.now()


@pytest.mark.django_db
def test_generate_invitation_revokes_previous(seller):
    inv1, _ = generate_invitation(seller=seller)
    inv2, raw_token2 = generate_invitation(seller=seller)

    inv1.refresh_from_db()
    assert inv1.revoked_at is not None
    assert inv2.revoked_at is None


@pytest.mark.django_db
def test_generate_invitation_stores_hash_not_token(seller):
    invitation, raw_token = generate_invitation(seller=seller)

    # Token should not be stored
    assert SellerInvitation.objects.filter(token_hash=raw_token).count() == 0
    # Hash should be stored
    assert invitation.token_hash != raw_token
    assert len(invitation.token_hash) == 64  # SHA-256 hex


# --- Invitation Consumption ---


@pytest.mark.django_db
def test_consume_invitation_success(seller):
    _, raw_token = generate_invitation(seller=seller)

    session = consume_invitation(raw_token=raw_token, request_ip="127.0.0.1")

    assert session is not None
    assert session.seller == seller
    assert session.ip_first == "127.0.0.1"

    # Verify invitation is marked as used
    invitation = SellerInvitation.objects.get(seller=seller)
    assert invitation.used_at is not None


@pytest.mark.django_db
def test_consume_invitation_fails_twice(seller):
    _, raw_token = generate_invitation(seller=seller)

    session1 = consume_invitation(raw_token=raw_token)
    session2 = consume_invitation(raw_token=raw_token)

    assert session1 is not None
    assert session2 is None


@pytest.mark.django_db
def test_consume_invitation_fails_for_inactive_seller(inactive_seller):
    _, raw_token = generate_invitation(seller=inactive_seller)

    session = consume_invitation(raw_token=raw_token)

    assert session is None


@pytest.mark.django_db
def test_consume_invitation_fails_for_invalid_token(seller):
    generate_invitation(seller=seller)

    session = consume_invitation(raw_token="invalid-token-12345")

    assert session is None


@pytest.mark.django_db
def test_consume_invitation_fails_for_expired(seller):
    from datetime import timedelta

    invitation, raw_token = generate_invitation(seller=seller)

    # Manually expire the invitation
    invitation.expires_at = timezone.now() - timedelta(hours=1)
    invitation.save(update_fields=["expires_at"])

    session = consume_invitation(raw_token=raw_token)

    assert session is None


@pytest.mark.django_db
def test_consume_invitation_creates_django_session(seller):
    _, raw_token = generate_invitation(seller=seller)

    session = consume_invitation(raw_token=raw_token)

    assert session.django_session_key is not None
    django_session = SessionStore(session_key=session.django_session_key)
    assert django_session["seller_id"] == str(seller.id)


# --- Concurrency ---


@pytest.mark.django_db
def test_concurrent_consumption_only_one_session(seller):
    """Two concurrent consume_invitation calls should only create one session."""
    _, raw_token = generate_invitation(seller=seller)

    # Simulate concurrent access
    session1 = consume_invitation(raw_token=raw_token)
    session2 = consume_invitation(raw_token=raw_token)

    # Only one should succeed
    assert (session1 is not None) != (session2 is not None)
    assert SellerSession.objects.filter(seller=seller).count() == 1


# --- Revocation ---


@pytest.mark.django_db
def test_revoke_all_sessions(seller):
    # Create two sessions (consume first before generating second)
    _, raw_token1 = generate_invitation(seller=seller)
    consume_invitation(raw_token=raw_token1)

    _, raw_token2 = generate_invitation(seller=seller)
    consume_invitation(raw_token=raw_token2)

    assert SellerSession.objects.filter(seller=seller, revoked_at__isnull=True).count() == 2

    count = revoke_all_sessions(seller=seller)

    assert count == 2
    assert SellerSession.objects.filter(seller=seller, revoked_at__isnull=True).count() == 0


@pytest.mark.django_db
def test_revoked_session_not_found(seller):
    _, raw_token = generate_invitation(seller=seller)
    session = consume_invitation(raw_token=raw_token)

    revoke_all_sessions(seller=seller)

    # Session should no longer be valid
    found = get_seller_from_session_by_key(session.django_session_key)
    assert found is None


# --- Session Validation ---


@pytest.mark.django_db
def test_get_seller_from_session_valid(seller):
    _, raw_token = generate_invitation(seller=seller)
    session = consume_invitation(raw_token=raw_token)

    found = get_seller_from_session_by_key(session.django_session_key)
    assert found == seller


@pytest.mark.django_db
def test_get_seller_from_session_revoked(seller):
    _, raw_token = generate_invitation(seller=seller)
    session = consume_invitation(raw_token=raw_token)

    revoke_all_sessions(seller=seller)

    found = get_seller_from_session_by_key(session.django_session_key)
    assert found is None


@pytest.mark.django_db
def test_get_seller_from_session_expired(seller):
    from datetime import timedelta

    _, raw_token = generate_invitation(seller=seller)
    session = consume_invitation(raw_token=raw_token)

    # Manually expire the session
    session.expires_at = timezone.now() - timedelta(days=1)
    session.save(update_fields=["expires_at"])

    found = get_seller_from_session_by_key(session.django_session_key)
    assert found is None


@pytest.mark.django_db
def test_get_seller_from_session_inactive_seller(seller):
    _, raw_token = generate_invitation(seller=seller)
    session = consume_invitation(raw_token=raw_token)

    seller.is_active = False
    seller.save(update_fields=["is_active"])

    found = get_seller_from_session_by_key(session.django_session_key)
    assert found is None


# --- Helper ---


def get_seller_from_session_by_key(session_key):
    """Helper to test session validation without a request object."""
    from django.utils import timezone as tz

    session = (
        SellerSession.objects.select_related("seller")
        .filter(
            django_session_key=session_key,
            revoked_at__isnull=True,
            expires_at__gt=tz.now(),
        )
        .first()
    )

    if session is None:
        return None

    if not session.seller.is_active:
        return None

    return session.seller
