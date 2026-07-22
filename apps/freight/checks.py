"""Django system checks for freight configuration."""
from django.core.checks import CheckMessage, Warning, register

from .config import get_correios_config, is_correios_configured

_PLACEHOLDER_PATTERNS = ("configure-no", "troque", "seu-", "gere-um")


@register()
def check_freight_config(app_configs, **kwargs) -> list[CheckMessage]:
    """Warn when mandatory Correios fields are missing."""
    messages: list[CheckMessage] = []

    config = get_correios_config()

    if is_correios_configured(config):
        return messages

    hint = "Configure as variáveis CORREIOS_USUARIO, CORREIOS_CODIGO_ACESSO e CORREIOS_CEP_ORIGEM."

    if not config.usuario:
        messages.append(
            Warning(
                "CORREIOS_USUARIO nao esta configurado.",
                hint=hint,
                id="freight.W001",
            )
        )

    if not config.codigo_acesso:
        messages.append(
            Warning(
                "CORREIOS_CODIGO_ACESSO nao esta configurado.",
                hint=hint,
                id="freight.W002",
            )
        )

    if not config.cep_origem or len(config.cep_origem) != 8:
        messages.append(
            Warning(
                "CORREIOS_CEP_ORIGEM invalido. Precisa ter exatamente 8 digitos.",
                hint=hint,
                id="freight.W003",
            )
        )

    return messages
