"""Integration tests for invitation activation flow — full HTTP cycle."""
import pytest
from django.conf import settings
from django.test import Client
from django.urls import reverse

from apps.sellers.models import Seller, SellerInvitation, SellerSession
from apps.sellers.services import generate_invitation


@pytest.fixture
def seller(db):
    return Seller.objects.create(
        name="Bruno Test",
        whatsapp_phone="+5531999999999",
        max_payment_amount_cents=1000000,
        is_active=True,
    )


@pytest.fixture
def invitation_url(seller):
    _, raw_token = generate_invitation(seller=seller)
    return reverse("sellers:activate", kwargs={"token": raw_token})


@pytest.mark.django_db
def test_get_activation_page_does_not_consume(client, seller, invitation_url):
    """GET /acesso/<token>/ shows confirm page, does NOT consume invitation."""
    response = client.get(invitation_url)

    assert response.status_code == 200
    assert "Olá" in response.content.decode()
    assert seller.name in response.content.decode()

    invitation = SellerInvitation.objects.get(seller=seller)
    assert invitation.used_at is None


@pytest.mark.django_db
def test_post_activation_creates_session_and_consumes(client, seller, invitation_url):
    """POST confirmation creates session, consumes invitation, redirects to /app/."""
    get_response = client.get(invitation_url)
    assert get_response.status_code == 200

    confirm_url = reverse("sellers:confirm_activation", kwargs={
        "token": invitation_url.rsplit("/", 2)[-2],
    })

    response = client.post(confirm_url, follow=False)

    assert response.status_code == 302
    assert response.url == reverse("sellers:app_new_link")

    invitation = SellerInvitation.objects.get(seller=seller)
    assert invitation.used_at is not None

    session = client.session
    assert session["seller_id"] == str(seller.id)

    assert SellerSession.objects.filter(
        seller=seller,
        django_session_key=session.session_key,
        revoked_at__isnull=True,
    ).exists()


@pytest.mark.django_db
def test_session_cookie_is_set(client, seller, invitation_url):
    """Response should set the session cookie."""
    client.get(invitation_url)
    confirm_url = reverse("sellers:confirm_activation", kwargs={
        "token": invitation_url.rsplit("/", 2)[-2],
    })
    response = client.post(confirm_url, follow=False)

    cookie_name = settings.SESSION_COOKIE_NAME
    assert cookie_name in response.cookies
    cookie = response.cookies[cookie_name]
    assert cookie["httponly"] is True
    assert cookie["samesite"] == "Lax"
    assert cookie["path"] == "/"


@pytest.mark.django_db
def test_app_page_accessible_after_activation(client, seller, invitation_url):
    """After successful activation, /app/ returns 200."""
    client.get(invitation_url)
    confirm_url = reverse("sellers:confirm_activation", kwargs={
        "token": invitation_url.rsplit("/", 2)[-2],
    })
    client.post(confirm_url, follow=False)

    response = client.get(reverse("sellers:app_new_link"))
    assert response.status_code == 200
    assert seller.name in response.content.decode()


@pytest.mark.django_db
def test_get_does_not_consume_on_double_access(client, seller, invitation_url):
    """Two GET requests should both show confirm page, not consume."""
    response1 = client.get(invitation_url)
    assert response1.status_code == 200

    response2 = client.get(invitation_url)
    assert response2.status_code == 200

    invitation = SellerInvitation.objects.get(seller=seller)
    assert invitation.used_at is None


@pytest.mark.django_db
def test_post_twice_second_fails(client, seller, invitation_url):
    """Second POST should fail because invitation is already used."""
    client.get(invitation_url)
    confirm_url = reverse("sellers:confirm_activation", kwargs={
        "token": invitation_url.rsplit("/", 2)[-2],
    })

    response1 = client.post(confirm_url)
    assert response1.status_code == 302

    response2 = client.post(confirm_url)
    assert response2.status_code == 400
    assert "já foi utilizado" in response2.content.decode()


@pytest.mark.django_db
def test_app_page_requires_auth(client):
    """Without session, /app/ redirects to session_invalid page for HTML requests."""
    response = client.get(reverse("sellers:app_new_link"), HTTP_ACCEPT="text/html")
    assert response.status_code == 302
    assert response.url == reverse("sellers:session_invalid")


@pytest.mark.django_db
def test_session_cookie_sent_on_next_request(client, seller, invitation_url):
    """Cookie from activation is sent on subsequent request."""
    client.get(invitation_url)
    confirm_url = reverse("sellers:confirm_activation", kwargs={
        "token": invitation_url.rsplit("/", 2)[-2],
    })
    response = client.post(confirm_url, follow=False)

    # Extract session key from cookie
    cookie = response.cookies[settings.SESSION_COOKIE_NAME]
    session_key = cookie.value

    assert SellerSession.objects.filter(django_session_key=session_key).exists()

    # Now access /app/ with the same client (cookie is persistent)
    app_response = client.get(reverse("sellers:app_new_link"))
    assert app_response.status_code == 200
