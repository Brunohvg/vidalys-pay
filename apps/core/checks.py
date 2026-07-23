"""Production-readiness checks for mandatory security and integration settings."""
from urllib.parse import urlparse

from django.conf import settings
from django.core.checks import Error, register
from django.core.checks import Warning as CheckWarning

_PLACEHOLDERS = ("change_me", "configure", "troque", "gere-", "example", "changeme")


def _missing_or_placeholder(value: str, *, minimum: int = 1) -> bool:
    cleaned = (value or "").strip()
    lowered = cleaned.lower()
    return len(cleaned) < minimum or any(marker in lowered for marker in _PLACEHOLDERS)


@register(deploy=True)
def check_production_configuration(app_configs, **kwargs):
    if settings.DEBUG:
        return []

    messages = []

    for name in ("INVITATION_TOKEN_PEPPER", "API_KEY_PEPPER"):
        if _missing_or_placeholder(getattr(settings, name, ""), minimum=32):
            messages.append(Error(f"{name} deve ter pelo menos 32 caracteres aleatórios.", id="core.E001"))

    credential = getattr(settings, "PAGARME_CREDENTIAL", "") or getattr(settings, "PAGARME_SECRET_KEY", "")
    if _missing_or_placeholder(credential, minimum=16):
        messages.append(Error("Credencial da Pagar.me ausente ou com placeholder.", id="core.E002"))

    auth_mode = getattr(settings, "PAGARME_WEBHOOK_AUTH_MODE", "basic")
    if auth_mode != "basic":
        messages.append(Error("PAGARME_WEBHOOK_AUTH_MODE deve ser 'basic' em produção.", id="core.E003"))
    webhook_user = getattr(settings, "PAGARME_WEBHOOK_BASIC_AUTH_USER", "")
    if _missing_or_placeholder(webhook_user, minimum=1):
        messages.append(Error("PAGARME_WEBHOOK_BASIC_AUTH_USER é obrigatório e não pode ser placeholder.", id="core.E004"))
    webhook_password = getattr(settings, "PAGARME_WEBHOOK_BASIC_AUTH_PASSWORD", "")
    if _missing_or_placeholder(webhook_password, minimum=16):
        messages.append(Error("PAGARME_WEBHOOK_BASIC_AUTH_PASSWORD deve conter um segredo forte.", id="core.E004"))

    for name in ("EVOLUTION_API_URL", "EVOLUTION_API_KEY", "EVOLUTION_INSTANCE"):
        if _missing_or_placeholder(getattr(settings, name, ""), minimum=3):
            messages.append(Error(f"{name} é obrigatório para os envios de WhatsApp.", id="core.E005"))

    app_url = getattr(settings, "APP_BASE_URL", "")
    parsed_url = urlparse(app_url)
    if parsed_url.scheme != "https" or not parsed_url.netloc:
        messages.append(Error("APP_BASE_URL deve ser uma URL HTTPS válida em produção.", id="core.E006"))

    cnpj_url = getattr(settings, "CNPJ_LOOKUP_BASE_URL", "")
    parsed_cnpj_url = urlparse(cnpj_url)
    if parsed_cnpj_url.scheme != "https" or not parsed_cnpj_url.netloc:
        messages.append(
            Error(
                "CNPJ_LOOKUP_BASE_URL deve ser uma URL HTTPS válida em produção.",
                id="core.E011",
            )
        )

    if "*" in settings.ALLOWED_HOSTS or not settings.ALLOWED_HOSTS:
        messages.append(Error("ALLOWED_HOSTS deve listar somente hosts explícitos em produção.", id="core.E007"))
    if not settings.CSRF_TRUSTED_ORIGINS:
        messages.append(Error("CSRF_TRUSTED_ORIGINS deve ser configurado em produção.", id="core.E008"))

    vapid_public = getattr(settings, "WEBPUSH_VAPID_PUBLIC_KEY", "")
    vapid_private = getattr(settings, "WEBPUSH_VAPID_PRIVATE_KEY", "")
    if bool(vapid_public) != bool(vapid_private):
        messages.append(Error("As duas chaves VAPID devem ser configuradas juntas.", id="core.E009"))
    elif not vapid_public:
        messages.append(CheckWarning("Web Push está desabilitado porque as chaves VAPID não foram configuradas.", id="core.W001"))

    for name in ("CORREIOS_USUARIO", "CORREIOS_CODIGO_ACESSO", "CORREIOS_CEP_ORIGEM"):
        if _missing_or_placeholder(getattr(settings, name, ""), minimum=8):
            messages.append(Error(f"{name} é obrigatório para o cálculo de frete.", id="core.E010"))

    return messages
