"""Diagnostic command to verify Pagar.me API connectivity."""
import httpx
from django.core.management.base import BaseCommand, CommandError

from apps.integrations.pagarme.credentials import CredentialError, get_credential


class Command(BaseCommand):
    help = "Verifica a conectividade com a API Pagar.me e a validade da credencial."

    def handle(self, *args, **options):
        try:
            cred = get_credential()
        except CredentialError as e:
            raise CommandError(f"Credencial inválida: {e}") from e

        from django.conf import settings

        self.stdout.write(f"Credencial configurada:        sim")
        self.stdout.write(f"Formato de entrada detectado:  {cred.source_format}")
        self.stdout.write(f"Ambiente detectado:            {cred.environment}")
        self.stdout.write(f"Base URL:                      {settings.PAGARME_BASE_URL}")
        self.stdout.write("")

        try:
            response = httpx.get(
                f"{settings.PAGARME_BASE_URL.rstrip('/')}/paymentlinks",
                headers={"Authorization": cred.authorization_header, "Accept": "application/json"},
                timeout=httpx.Timeout(connect=5, read=10),
            )
        except httpx.ConnectError:
            raise CommandError("Falha de conexão: não foi possível alcançar a API Pagar.me.")
        except httpx.TimeoutException:
            raise CommandError("Timeout: a API Pagar.me não respondeu a tempo.")

        if response.status_code == 401:
            raise CommandError(
                "HTTP 401: autenticação recusada. Verifique se a credencial representa "
                "uma Secret Key válida e se não houve dupla conversão para Basic Auth."
            )
        elif response.status_code == 403:
            raise CommandError("HTTP 403: acesso negado. Verifique permissões da conta.")
        elif response.status_code >= 400:
            raise CommandError(f"HTTP {response.status_code}: erro ao acessar a API.")

        self.stdout.write(self.style.SUCCESS("API Pagar.me acessível. Autenticação OK."))
