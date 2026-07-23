import json
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model

from apps.core.checks import check_production_configuration
from apps.integrations.auth import hash_api_key
from apps.integrations.n8n.models import ApiClient
from apps.payment_links.models import PaymentLink, PaymentLinkStatus
from apps.sellers.models import Seller
from apps.webhooks.models import ProcessingStatus, WebhookEvent


@pytest.fixture
def seller(db):
    return Seller.objects.create(
        name="Seller Audit",
        whatsapp_phone="+5531999999999",
        max_payment_amount_cents=100000,
    )


@pytest.mark.django_db
def test_panel_login_rejects_external_next_url(client):
    get_user_model().objects.create_superuser("admin-audit", "admin@example.com", "strong-test-password")

    response = client.post(
        "/painel/login/?next=https://evil.example/phishing",
        {"username": "admin-audit", "password": "strong-test-password"},
    )

    assert response.status_code == 302
    assert response.url == "/painel/"


@pytest.mark.django_db
def test_panel_delete_seller_with_links_is_handled(client, seller):
    admin = get_user_model().objects.create_superuser("admin-delete", "delete@example.com", "strong-test-password")
    client.force_login(admin)
    PaymentLink.objects.create(
        seller=seller,
        reference="AUDIT-1",
        amount_cents=1000,
        installments=1,
        status=PaymentLinkStatus.ACTIVE,
        idempotency_key="audit-delete",
    )

    response = client.post(f"/painel/{seller.id}/excluir/")

    assert response.status_code == 302
    assert Seller.objects.filter(pk=seller.pk).exists()


@pytest.mark.django_db
def test_api_key_without_write_scope_cannot_create_link(client, seller, settings):
    settings.API_KEY_PEPPER = "audit-pepper"
    raw_key = "vly_live_audit_key_without_write_scope"
    ApiClient.objects.create(
        name="Read only",
        key_prefix=raw_key[:12],
        key_hash=hash_api_key(raw_key),
        scopes=["payment_links:read"],
    )

    response = client.post(
        "/api/v1/payment-links/",
        data={"seller_id": str(seller.id), "reference": "AUDIT", "amount_cents": 1000, "installments": 1},
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {raw_key}",
        HTTP_IDEMPOTENCY_KEY="audit-scope",
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "insufficient_scope"
    assert not PaymentLink.objects.exists()


@pytest.mark.django_db
def test_failed_duplicate_webhook_is_reprocessed(client, settings):
    settings.PAGARME_WEBHOOK_AUTH_MODE = "basic"
    settings.PAGARME_WEBHOOK_BASIC_AUTH_USER = "audit-user"
    settings.PAGARME_WEBHOOK_BASIC_AUTH_PASSWORD = "audit-password"
    payload = {"id": "evt-audit-retry", "type": "order.created", "data": {}}
    event = WebhookEvent.objects.create(
        provider_event_id=payload["id"],
        event_type=payload["type"],
        payload=payload,
        payload_sha256="0" * 64,
        processing_status=ProcessingStatus.FAILED,
    )

    import base64
    auth = base64.b64encode(b"audit-user:audit-password").decode()
    with patch("apps.webhooks.views.process_webhook_event", return_value=True) as process:
        response = client.post(
            "/api/v1/webhooks/pagarme/",
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Basic {auth}",
        )

    assert response.status_code == 200
    assert response.json()["reprocessed"] is True
    process.assert_called_once_with(event)


def test_production_check_requires_https_cnpj_provider(settings):
    settings.DEBUG = False
    settings.CNPJ_LOOKUP_BASE_URL = "http://cnpj.internal/api"

    messages = check_production_configuration(None)

    assert "core.E011" in {message.id for message in messages}

    settings.CNPJ_LOOKUP_BASE_URL = "https://cnpj.internal/api"
    messages = check_production_configuration(None)
    assert "core.E011" not in {message.id for message in messages}
