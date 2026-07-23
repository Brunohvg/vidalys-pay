from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.test import Client
from django.urls import reverse

from apps.notifications.models import NotificationOutbox, PushSubscription
from apps.notifications.push_service import (
    DELIVERED_SUBSCRIPTIONS_KEY,
    queue_payment_status_push,
    send_push_outbox_item,
)
from apps.payment_links.models import PaymentLink, PaymentLinkStatus
from apps.sellers.models import Seller
from apps.sellers.services import generate_invitation
from apps.webhooks.processor import _handle_create_attempt


@pytest.fixture
def seller(db):
    return Seller.objects.create(
        name="Seller Push",
        whatsapp_phone="+5531999999999",
        max_payment_amount_cents=1000000,
        is_active=True,
    )


@pytest.fixture
def payment_link(seller):
    return PaymentLink.objects.create(
        seller=seller,
        reference="PED-PUSH-001",
        amount_cents=12345,
        installments=1,
        status=PaymentLinkStatus.ACTIVE,
        idempotency_key="push-test-key",
    )


def _authenticated_client(seller):
    client = Client()
    _, raw_token = generate_invitation(seller=seller)
    client.get(reverse("sellers:activate", kwargs={"token": raw_token}))
    client.post(reverse("sellers:confirm_activation", kwargs={"token": raw_token}))
    return client


@pytest.mark.django_db
def test_queue_push_requires_complete_vapid_configuration(settings, payment_link):
    settings.WEBPUSH_VAPID_PUBLIC_KEY = ""
    settings.WEBPUSH_VAPID_PRIVATE_KEY = "private"

    assert not queue_payment_status_push(
        payment_link=payment_link, event_type="payment_paid"
    )
    assert not NotificationOutbox.objects.exists()


@pytest.mark.django_db
def test_queue_push_is_idempotent_and_formats_payload(settings, payment_link):
    settings.WEBPUSH_VAPID_PUBLIC_KEY = "public"
    settings.WEBPUSH_VAPID_PRIVATE_KEY = "private"

    assert queue_payment_status_push(
        payment_link=payment_link, event_type="payment_paid"
    )
    assert not queue_payment_status_push(
        payment_link=payment_link, event_type="payment_paid"
    )

    item = NotificationOutbox.objects.get()
    assert item.topic == "webpush.send"
    assert item.payload["body"] == "O link PED-PUSH-001 foi pago: R$ 123,45."
    assert item.payload["seller_id"] == str(payment_link.seller_id)


@pytest.mark.django_db
def test_retry_does_not_resend_to_a_device_that_already_received(settings, seller, payment_link):
    settings.WEBPUSH_VAPID_PUBLIC_KEY = "public"
    settings.WEBPUSH_VAPID_PRIVATE_KEY = "private"
    settings.WEBPUSH_VAPID_SUBJECT = "mailto:test@example.com"
    first = PushSubscription.objects.create(
        seller=seller,
        endpoint="https://push.example/first",
        p256dh="first-key",
        auth="first-auth",
    )
    second = PushSubscription.objects.create(
        seller=seller,
        endpoint="https://push.example/second",
        p256dh="second-key",
        auth="second-auth",
    )
    queue_payment_status_push(payment_link=payment_link, event_type="payment_paid")
    item = NotificationOutbox.objects.get()
    calls = []

    def fail_second_once(**kwargs):
        endpoint = kwargs["subscription_info"]["endpoint"]
        calls.append(endpoint)
        if endpoint == second.endpoint:
            raise RuntimeError("temporary push provider failure")

    with patch("pywebpush.webpush", side_effect=fail_second_once):
        assert not send_push_outbox_item(item)

    item.refresh_from_db()
    assert item.payload[DELIVERED_SUBSCRIPTIONS_KEY] == [str(first.id)]

    with patch("pywebpush.webpush") as webpush:
        assert send_push_outbox_item(item)

    assert webpush.call_count == 1
    assert webpush.call_args.kwargs["subscription_info"]["endpoint"] == second.endpoint
    assert calls.count(first.endpoint) == 1


@pytest.mark.django_db
def test_push_subscription_endpoint_rejects_non_https(seller, settings):
    settings.WEBPUSH_VAPID_PUBLIC_KEY = "public"
    settings.WEBPUSH_VAPID_PRIVATE_KEY = "private"
    client = _authenticated_client(seller)

    response = client.post(
        reverse("sellers:push_subscriptions"),
        data={"endpoint": "http://push.example/sub", "keys": {"p256dh": "key", "auth": "auth"}},
        content_type="application/json",
    )

    assert response.status_code == 400
    assert not PushSubscription.objects.exists()


@pytest.mark.django_db
def test_existing_subscription_is_reactivated_and_updated(seller, settings):
    settings.WEBPUSH_VAPID_PUBLIC_KEY = "public"
    settings.WEBPUSH_VAPID_PRIVATE_KEY = "private"
    subscription = PushSubscription.objects.create(
        seller=seller,
        endpoint="https://push.example/sub",
        p256dh="old-key",
        auth="old-auth",
        is_active=False,
        failure_count=4,
    )
    client = _authenticated_client(seller)

    response = client.post(
        reverse("sellers:push_subscriptions"),
        data={"endpoint": subscription.endpoint, "keys": {"p256dh": "new-key", "auth": "new-auth"}},
        content_type="application/json",
    )

    assert response.status_code == 200
    subscription.refresh_from_db()
    assert subscription.is_active
    assert subscription.failure_count == 0
    assert subscription.p256dh == "new-key"


@pytest.mark.django_db
def test_paid_attempt_path_queues_push(payment_link, django_capture_on_commit_callbacks):
    normalized = SimpleNamespace(status="paid")

    with (
        patch("apps.webhooks.processor._create_or_update_attempt"),
        patch("apps.webhooks.processor.queue_payment_approved"),
        patch("apps.webhooks.processor.queue_payment_status_push") as queue_push,
        django_capture_on_commit_callbacks(execute=True),
    ):
        _handle_create_attempt(None, payment_link, {"attempt_status": "PAID"}, normalized)

    queue_push.assert_called_once_with(
        payment_link=payment_link, event_type="payment_paid"
    )
