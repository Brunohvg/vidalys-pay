"""Read-side queries for boleto panels."""

from datetime import timedelta
from uuid import UUID

from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.dateparse import parse_date

from .models import Boleto, BoletoStatus
from .permissions import scope_boletos

PENDING_STATUSES = {
    BoletoStatus.CREATING,
    BoletoStatus.CREATION_UNKNOWN,
    BoletoStatus.PENDING,
}
ORDERING = {
    "recent": "-created_at",
    "oldest": "created_at",
    "due": "due_date",
    "amount_desc": "-amount_cents",
    "amount_asc": "amount_cents",
}


def boleto_list_page(*, actor, params):
    queryset = scope_boletos(
        Boleto.objects.select_related("company", "seller"),
        actor=actor,
    )
    filtered = _apply_filters(queryset, params)
    ordering = params.get("ordering", "recent")
    page = Paginator(filtered.order_by(ORDERING.get(ordering, "-created_at")), 20).get_page(
        params.get("page", "1")
    )
    query = params.copy()
    query.pop("page", None)
    return page, query.urlencode()


def boleto_metrics(*, actor) -> dict:
    queryset = scope_boletos(Boleto.objects.all(), actor=actor)
    today = timezone.localdate()
    due_limit = today + timedelta(days=7)
    values = queryset.aggregate(
        issued_today=Count("id", filter=Q(created_at__date=today)),
        pending=Count("id", filter=Q(status__in=PENDING_STATUSES)),
        paid=Count("id", filter=Q(status=BoletoStatus.PAID)),
        expired=Count("id", filter=Q(status=BoletoStatus.EXPIRED)),
        issued_amount=Coalesce(
            Sum(
                "amount_cents",
                filter=~Q(status=BoletoStatus.CREATION_ERROR),
            ),
            0,
        ),
        received_amount=Coalesce(
            Sum("amount_cents", filter=Q(status=BoletoStatus.PAID)),
            0,
        ),
        due_soon=Count(
            "id",
            filter=Q(status__in=PENDING_STATUSES, due_date__range=(today, due_limit)),
        ),
    )
    return values


def _apply_filters(queryset, params):
    query = params.get("q", "").strip()
    if query:
        search = (
            Q(company__legal_name__icontains=query)
            | Q(company__trade_name__icontains=query)
            | Q(internal_reference__icontains=query)
        )
        digits = _digits(query)
        if digits:
            search |= Q(company__cnpj__icontains=digits)
        queryset = queryset.filter(search)

    status = params.get("status", "").strip()
    if status in BoletoStatus.values:
        queryset = queryset.filter(status=status)

    seller = params.get("seller", "").strip()
    try:
        seller_id = UUID(seller) if seller else None
    except ValueError:
        seller_id = None
    if seller_id:
        queryset = queryset.filter(seller_id=seller_id)

    created_from = parse_date(params.get("created_from", "").strip())
    if created_from:
        queryset = queryset.filter(created_at__date__gte=created_from)
    created_to = parse_date(params.get("created_to", "").strip())
    if created_to:
        queryset = queryset.filter(created_at__date__lte=created_to)
    due_date = parse_date(params.get("due_date", "").strip())
    if due_date:
        queryset = queryset.filter(due_date=due_date)
    return queryset


def _digits(value: str) -> str:
    return "".join(character for character in value if character.isdigit())
