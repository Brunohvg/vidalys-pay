"""Safe, idempotent cancellation of unpaid boleto charges."""

import logging
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from apps.boletos.models import Boleto, BoletoStatus
from apps.integrations.pagarme.client import PagarmeClient, PagarmeError

logger = logging.getLogger("apps.boletos")

CANCELABLE_STATUSES = {BoletoStatus.PENDING, BoletoStatus.FAILED}


@dataclass(frozen=True)
class CancelBoletoResult:
    boleto: Boleto
    success: bool
    error_message: str = ""
    uncertain: bool = False
    idempotent_replay: bool = False


def cancel_boleto(
    *,
    boleto: Boleto,
    idempotency_key: str,
    client: PagarmeClient | None = None,
) -> CancelBoletoResult:
    """Reserve cancellation locally, call Pagar.me, then confirm local state."""
    if not idempotency_key or len(idempotency_key) > 100:
        return CancelBoletoResult(boleto, False, "Chave de idempotência inválida.")

    with transaction.atomic():
        locked = Boleto.objects.select_for_update().get(pk=boleto.pk)
        if locked.status == BoletoStatus.CANCELED:
            return CancelBoletoResult(locked, True, idempotent_replay=True)
        if locked.status == BoletoStatus.CANCELING:
            if locked.cancellation_idempotency_key == idempotency_key:
                return CancelBoletoResult(
                    locked,
                    True,
                    uncertain=True,
                    idempotent_replay=True,
                )
            return CancelBoletoResult(
                locked,
                False,
                "Já existe um cancelamento em processamento.",
            )
        if locked.status not in CANCELABLE_STATUSES:
            return CancelBoletoResult(
                locked,
                False,
                "Somente boletos não pagos e pendentes podem ser cancelados.",
            )
        if not locked.provider_charge_id:
            return CancelBoletoResult(
                locked,
                False,
                "Boleto ainda não possui cobrança confirmada no provedor.",
            )

        previous_status = locked.status
        locked.status = BoletoStatus.CANCELING
        locked.cancellation_idempotency_key = idempotency_key
        locked.cancellation_requested_at = timezone.now()
        locked.save(
            update_fields=[
                "status",
                "cancellation_idempotency_key",
                "cancellation_requested_at",
                "updated_at",
            ]
        )

    provider_client = client or PagarmeClient()
    try:
        response = provider_client.cancel_boleto_charge(
            charge_id=locked.provider_charge_id,
            idempotency_key=idempotency_key,
        )
    except PagarmeError as exc:
        if exc.status_code >= 500:
            logger.warning(
                "boleto_cancellation_unknown=true boleto=%s status=%s",
                locked.id,
                exc.status_code,
            )
            return CancelBoletoResult(
                locked,
                True,
                "Cancelamento enviado; aguardando confirmação do webhook.",
                uncertain=True,
            )
        with transaction.atomic():
            locked = Boleto.objects.select_for_update().get(pk=locked.pk)
            if locked.status == BoletoStatus.CANCELING:
                locked.status = previous_status
                locked.cancellation_response = {
                    "provider_error": True,
                    "status_code": exc.status_code,
                }
                locked.save(
                    update_fields=[
                        "status",
                        "cancellation_response",
                        "updated_at",
                    ]
                )
        return CancelBoletoResult(
            locked,
            False,
            "O Pagar.me recusou o cancelamento deste boleto.",
        )
    except Exception:
        logger.exception("boleto_cancellation_unknown=true boleto=%s", locked.id)
        return CancelBoletoResult(
            locked,
            True,
            "Cancelamento enviado; aguardando confirmação do webhook.",
            uncertain=True,
        )

    with transaction.atomic():
        locked = Boleto.objects.select_for_update().get(pk=locked.pk)
        if locked.status != BoletoStatus.CANCELING:
            logger.warning(
                "boleto_cancellation_state_changed=true boleto=%s status=%s",
                locked.id,
                locked.status,
            )
            return CancelBoletoResult(
                locked,
                locked.status == BoletoStatus.CANCELED,
                "O estado do boleto mudou durante o cancelamento.",
                uncertain=locked.status not in {BoletoStatus.CANCELED, BoletoStatus.PAID},
            )
        locked.status = BoletoStatus.CANCELED
        locked.canceled_at = locked.canceled_at or timezone.now()
        locked.provider_status = str(response.get("status") or "canceled")[:80]
        locked.cancellation_response = {
            "id": str(response.get("id") or "")[:100],
            "status": str(response.get("status") or "")[:80],
        }
        locked.save(
            update_fields=[
                "status",
                "canceled_at",
                "provider_status",
                "cancellation_response",
                "updated_at",
            ]
        )
        transaction.on_commit(
            lambda boleto_id=locked.id: _queue_canceled_notification(boleto_id),
            robust=True,
        )
    return CancelBoletoResult(locked, True)


def _queue_canceled_notification(boleto_id) -> None:
    from apps.boletos.services.webhook_processing import _queue_status_notification

    _queue_status_notification(boleto_id, "boleto_canceled")
