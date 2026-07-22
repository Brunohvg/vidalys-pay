"""Tests for dual WhatsApp delivery — seller + customer."""
from unittest.mock import patch

import pytest

from apps.notifications.models import NotificationOutbox, RecipientType, WhatsAppMessage, WhatsAppMessageStatus
from apps.notifications.whatsapp_service import queue_payment_link_created
from apps.sellers.models import Seller


@pytest.fixture
def seller(db):
    return Seller.objects.create(
        name="Seller Test",
        whatsapp_phone="+5531999999999",
        max_payment_amount_cents=1000000,
        is_active=True,
    )


@pytest.fixture
def seller_no_phone(db):
    return Seller.objects.create(
        name="Seller No Phone",
        whatsapp_phone="",
        max_payment_amount_cents=1000000,
        is_active=True,
    )


@pytest.fixture
def payment_link(seller):
    from apps.payment_links.models import PaymentLink, PaymentLinkStatus

    return PaymentLink.objects.create(
        seller=seller,
        reference="PED-001",
        amount_cents=10000,
        installments=1,
        status=PaymentLinkStatus.ACTIVE,
        idempotency_key="test-key-001",
        customer_name="Cliente Teste",
        customer_phone="+5531888888888",
        payment_url="https://pagar.me/link/test123",
    )


@pytest.fixture
def payment_link_no_customer(seller):
    from apps.payment_links.models import PaymentLink, PaymentLinkStatus

    return PaymentLink.objects.create(
        seller=seller,
        reference="PED-002",
        amount_cents=5000,
        installments=1,
        status=PaymentLinkStatus.ACTIVE,
        idempotency_key="test-key-002",
        payment_url="https://pagar.me/link/test456",
    )


@pytest.mark.django_db
class TestDualDelivery:
    """Test that both seller and customer receive WhatsApp messages."""

    def test_with_customer_phone_creates_two_messages(self, seller, payment_link):
        """With customer_phone: creates message for seller AND customer."""
        results = queue_payment_link_created(seller=seller, payment_link=payment_link)

        assert len(results) == 2

        seller_result = next(r for r in results if r.recipient_type == "seller")
        customer_result = next(r for r in results if r.recipient_type == "customer")

        assert seller_result.status == "queued"
        assert seller_result.recipient_phone == seller.whatsapp_phone
        assert customer_result.status == "queued"
        assert customer_result.recipient_phone == payment_link.customer_phone

        # Verify DB records
        messages = WhatsAppMessage.objects.filter(payment_link=payment_link)
        assert messages.count() == 2
        assert messages.filter(recipient_type="seller").count() == 1
        assert messages.filter(recipient_type="customer").count() == 1

    def test_without_customer_phone_creates_one_message(self, seller, payment_link_no_customer):
        """Without customer_phone: creates message for seller only."""
        results = queue_payment_link_created(seller=seller, payment_link=payment_link_no_customer)

        assert len(results) == 2

        seller_result = next(r for r in results if r.recipient_type == "seller")
        customer_result = next(r for r in results if r.recipient_type == "customer")

        assert seller_result.status == "queued"
        assert customer_result.status == "not_requested"

        messages = WhatsAppMessage.objects.filter(payment_link=payment_link_no_customer)
        assert messages.count() == 1
        assert messages.first().recipient_type == "seller"

    def test_seller_receives_when_customer_different(self, seller, payment_link):
        """Seller continues receiving even when customer has different phone."""
        results = queue_payment_link_created(seller=seller, payment_link=payment_link)

        seller_result = next(r for r in results if r.recipient_type == "seller")
        customer_result = next(r for r in results if r.recipient_type == "customer")

        assert seller_result.recipient_phone == "+5531999999999"
        assert customer_result.recipient_phone == "+5531888888888"
        assert seller_result.status == "queued"
        assert customer_result.status == "queued"

    def test_customer_failure_does_not_block_seller(self, seller, payment_link):
        """If customer phone is invalid, seller still gets queued."""
        payment_link.customer_phone = "invalid"
        results = queue_payment_link_created(seller=seller, payment_link=payment_link)

        seller_result = next(r for r in results if r.recipient_type == "seller")
        customer_result = next(r for r in results if r.recipient_type == "customer")

        assert seller_result.status == "queued"
        # Customer phone is still valid format for queuing (validation happens at send time)
        assert customer_result.status == "queued"

    def test_seller_no_phone_marks_failed(self, seller_no_phone, payment_link_no_customer):
        """Seller without phone: marks as failed, no message created."""
        results = queue_payment_link_created(seller=seller_no_phone, payment_link=payment_link_no_customer)

        seller_result = next(r for r in results if r.recipient_type == "seller")
        assert seller_result.status == "failed"
        assert seller_result.recipient_phone == ""

        messages = WhatsAppMessage.objects.filter(payment_link=payment_link_no_customer)
        assert messages.count() == 0


@pytest.mark.django_db
class TestIdempotency:
    """Test that duplicate clicks do not create duplicate messages."""

    def test_double_click_no_duplicates(self, seller, payment_link):
        """Clicking twice does not duplicate either recipient."""
        results1 = queue_payment_link_created(seller=seller, payment_link=payment_link)
        results2 = queue_payment_link_created(seller=seller, payment_link=payment_link)

        # First call creates, second returns None (duplicate)
        for r1, r2 in zip(results1, results2):
            if r1.status == "queued":
                assert r2.status == "duplicate"
            else:
                assert r2.status == r1.status

        messages = WhatsAppMessage.objects.filter(payment_link=payment_link)
        assert messages.count() == 2  # One for seller, one for customer

    def test_retry_does_not_create_new_if_pending(self, seller, payment_link):
        """Retry does not create new notification if one is pending."""
        queue_payment_link_created(seller=seller, payment_link=payment_link)

        # Simulate retry
        results = queue_payment_link_created(seller=seller, payment_link=payment_link)

        for r in results:
            if r.status not in ("not_requested", "failed"):
                assert r.status == "duplicate"

    def test_retry_creates_new_if_all_done(self, seller, payment_link):
        """After all messages are SENT, retry creates new ones."""
        queue_payment_link_created(seller=seller, payment_link=payment_link)

        # Mark all messages as SENT
        WhatsAppMessage.objects.filter(payment_link=payment_link).update(status="SENT")
        NotificationOutbox.objects.filter(
            aggregate_type="payment_link",
            aggregate_id=str(payment_link.id),
        ).update(status="DONE")

        # Now retry should create new messages
        results = queue_payment_link_created(seller=seller, payment_link=payment_link)

        for r in results:
            if r.status not in ("not_requested", "failed"):
                assert r.status == "queued"

        messages = WhatsAppMessage.objects.filter(payment_link=payment_link)
        assert messages.count() == 4  # 2 original + 2 new


@pytest.mark.django_db
class TestOutboxDeduplication:
    """Test outbox deduplication key includes recipient_type."""

    def test_different_recipients_have_different_keys(self, seller, payment_link):
        """Seller and customer have different deduplication keys."""
        queue_payment_link_created(seller=seller, payment_link=payment_link)

        outbox_entries = NotificationOutbox.objects.filter(
            aggregate_type="payment_link",
            aggregate_id=str(payment_link.id),
        )

        assert outbox_entries.count() == 2

        keys = set(outbox_entries.values_list("deduplication_key", flat=True))
        assert len(keys) == 2
        assert any("seller" in k for k in keys)
        assert any("customer" in k for k in keys)


@pytest.mark.django_db
class TestStatusValues:
    """Test that all expected status values work."""

    def test_queued_status(self, seller, payment_link):
        results = queue_payment_link_created(seller=seller, payment_link=payment_link)
        for r in results:
            if r.status not in ("not_requested", "failed"):
                assert r.status == "queued"

    def test_not_requested_when_no_customer(self, seller, payment_link_no_customer):
        results = queue_payment_link_created(seller=seller, payment_link=payment_link_no_customer)
        customer_result = next(r for r in results if r.recipient_type == "customer")
        assert customer_result.status == "not_requested"

    def test_duplicate_on_retry(self, seller, payment_link):
        queue_payment_link_created(seller=seller, payment_link=payment_link)
        results = queue_payment_link_created(seller=seller, payment_link=payment_link)
        for r in results:
            if r.status not in ("not_requested", "failed", "duplicate"):
                assert False, f"Unexpected status: {r.status}"
