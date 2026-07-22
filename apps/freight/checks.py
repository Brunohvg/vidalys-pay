"""Django system checks for freight configuration."""
from django.core.checks import CheckMessage, Warning, register

from .config import get_correios_config

PLACEHOLDER_PATTERNS = ("configure-no", "troque", "seu-", "gere-um")


@register()
def check_freight_config(app_configs, **kwargs) -> list[CheckMessage]:
    messages: list[CheckMessage] = []

    from django.conf import settings

    enabled = getattr(settings, "CORREIOS_ENABLED", False)
    if not enabled:
        return messages

    usuario = (getattr(settings, "CORREIOS_USUARIO", "") or "").strip()
    codigo_acesso = (getattr(settings, "CORREIOS_CODIGO_ACESSO", "") or "").strip()
    cep_origem = (getattr(settings, "CORREIOS_CEP_ORIGEM", "") or "").strip()
    pac_code = (getattr(settings, "CORREIOS_PAC_PRODUCT_CODE", "03298") or "").strip()
    sedex_code = (getattr(settings, "CORREIOS_SEDEX_PRODUCT_CODE", "03220") or "").strip()
    connect_timeout = float(getattr(settings, "CORREIOS_CONNECT_TIMEOUT_SECONDS", 5))
    read_timeout = float(getattr(settings, "CORREIOS_READ_TIMEOUT_SECONDS", 15))
    allow_fallback = bool(getattr(settings, "CORREIOS_ALLOW_ESTIMATE_FALLBACK", False))

    hint = "Configure CORREIOS_ENABLED=false ou forneca as credenciais reais."

    if not usuario:
        messages.append(
            Warning(
                "CORREIOS_ENABLED=true mas CORREIOS_USUARIO nao esta configurado.",
                hint=hint,
                id="freight.W001",
            )
        )

    if not codigo_acesso:
        messages.append(
            Warning(
                "CORREIOS_ENABLED=true mas CORREIOS_CODIGO_ACESSO nao esta configurado.",
                hint=hint,
                id="freight.W002",
            )
        )

    if not cep_origem or len(cep_origem) != 8 or not cep_origem.isdigit():
        messages.append(
            Warning(
                "CORREIOS_CEP_ORIGEM invalido ou nao configurado. "
                "Precisa ter exatamente 8 digitos.",
                hint=hint,
                id="freight.W003",
            )
        )

    if not pac_code:
        messages.append(
            Warning(
                "CORREIOS_ENABLED=true mas CORREIOS_PAC_PRODUCT_CODE nao esta configurado.",
                hint=hint,
                id="freight.W004",
            )
        )

    if not sedex_code:
        messages.append(
            Warning(
                "CORREIOS_ENABLED=true mas CORREIOS_SEDEX_PRODUCT_CODE nao esta configurado.",
                hint=hint,
                id="freight.W005",
            )
        )

    if connect_timeout <= 0:
        messages.append(
            Warning(
                "CORREIOS_CONNECT_TIMEOUT_SECONDS deve ser positivo.",
                hint="Defina um valor > 0.",
                id="freight.W006",
            )
        )

    if read_timeout <= 0:
        messages.append(
            Warning(
                "CORREIOS_READ_TIMEOUT_SECONDS deve ser positivo.",
                hint="Defina um valor > 0.",
                id="freight.W007",
            )
        )

    for field_name, value in [
        ("CORREIOS_USUARIO", usuario),
        ("CORREIOS_CODIGO_ACESSO", codigo_acesso),
    ]:
        lower = value.lower()
        for pattern in PLACEHOLDER_PATTERNS:
            if pattern in lower:
                messages.append(
                    Warning(
                        f"{field_name} parece conter um placeholder. "
                        "Configure a credencial real dos Correios.",
                        hint=hint,
                        id="freight.W008",
                    )
                )
                break

    if allow_fallback:
        messages.append(
            Warning(
                "CORREIOS_ALLOW_ESTIMATE_FALLBACK esta habilitado. "
                "Os valores exibidos serao estimativas e nao precos oficiais.",
                hint="Para producao, mantenha CORREIOS_ALLOW_ESTIMATE_FALLBACK=false.",
                id="freight.W009",
            )
        )

    return messages
