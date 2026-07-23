"""Diagnostic command to verify Pagar.me API connectivity."""
import httpx
from django.core.management.base import BaseCommand, CommandError

from apps.integrations.pagarme.credentials import (
    PagarMeConfigurationError,
    build_basic_auth_header,
    get_pagarme_api_key,
)


class Command(BaseCommand):
    help = "Verifica a conectividade com a API Pagar.me e a validade da credencial."

    def handle(self, *args, **options):
        try:
            api_key = get_pagarme_api_key()
        except PagarMeConfigurationError as e:
            raise CommandError(f"Credencial invalida: {e}") from e

        from django.conf import settings

        auth_header = build_basic_auth_header(api_key)

        self.stdout.write("Credencial configurada:        sim")
        self.stdout.write(f"Formato de entrada detectado:  {_detect_input_format_from_settings()}")
        self.stdout.write(f"Ambiente detectado:            {'production' if not api_key.startswith('sk_test_') else 'test'}")
        self.stdout.write("Authorization presente:         sim")
        self.stdout.write("Authorization schema:           Basic")
        self.stdout.write(f"Endpoint:                       {settings.PAGARME_BASE_URL.rstrip('/')}/paymentlinks")
        self.stdout.write("")

        try:
            response = httpx.get(
                f"{settings.PAGARME_BASE_URL.rstrip('/')}/paymentlinks",
                headers={"Authorization": auth_header, "Accept": "application/json"},
                timeout=httpx.Timeout(connect=5, read=10),
            )
        except httpx.ConnectError as exc:
            raise CommandError("Falha de conexao: nao foi possivel alcancar a API Pagar.me.") from exc
        except httpx.TimeoutException as exc:
            raise CommandError("Timeout: a API Pagar.me nao respondeu a tempo.") from exc

        if response.status_code == 401:
            raise CommandError(
                "HTTP 401: autenticacao recusada. Verifique se a credencial representa "
                "uma Secret Key valida e se nao houve dupla conversao para Basic Auth."
            )
        elif response.status_code == 403:
            raise CommandError("HTTP 403: acesso negado. Verifique permissoes da conta.")
        elif response.status_code >= 400:
            raise CommandError(f"HTTP {response.status_code}: erro ao acessar a API.")

        self.stdout.write(self.style.SUCCESS("API Pagar.me acessivel. Autenticacao OK."))


def _detect_input_format_from_settings() -> str:
    from django.conf import settings

    from apps.integrations.pagarme.credentials import _detect_input_format

    credential = getattr(settings, "PAGARME_CREDENTIAL", "") or ""
    if credential:
        return _detect_input_format(credential)

    legacy_key = getattr(settings, "PAGARME_SECRET_KEY", "") or ""
    return _detect_input_format(legacy_key)
