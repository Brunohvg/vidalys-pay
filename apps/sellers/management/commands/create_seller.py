"""Management command to create a seller with an access invitation."""
import getpass

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from apps.sellers.models import Seller
from apps.sellers.services import generate_invitation


class Command(BaseCommand):
    help = "Cria um vendedor e gera um link de convite de acesso."

    def add_arguments(self, parser):
        parser.add_argument("--name", type=str, help="Nome do vendedor")
        parser.add_argument("--whatsapp", type=str, help="Telefone WhatsApp (formato E.164: +5511999999999)")
        parser.add_argument("--max-amount", type=int, default=50000, help="Limite máximo por link em centavos (padrão: 50000 = R$500,00)")

    def handle(self, *args, **options):
        name = options["name"] or input("Nome do vendedor: ").strip()
        if not name:
            raise CommandError("Nome do vendedor é obrigatório.")

        whatsapp = options["whatsapp"] or input("WhatsApp (+5511999999999): ").strip()
        if not whatsapp:
            raise CommandError("WhatsApp é obrigatório.")

        max_amount = options["max_amount"]

        if not User.objects.filter(is_superuser=True).exists():
            self.stdout.write("\nNenhum superusuário encontrado. Crie um para acessar o Admin (/admin/):")
            username = input("Usuário admin: ").strip()
            email = input("Email admin: ").strip()
            password = getpass.getpass("Senha admin: ").strip()
            if not username or not password:
                raise CommandError("Usuário e senha são obrigatórios.")
            User.objects.create_superuser(username=username, email=email, password=password)
            self.stdout.write(self.style.SUCCESS(f"Superusuário '{username}' criado."))

        seller, created = Seller.objects.get_or_create(
            whatsapp_phone=whatsapp,
            defaults={
                "name": name,
                "max_payment_amount_cents": max_amount,
                "is_active": True,
            },
        )

        if not created:
            seller.name = name
            seller.max_payment_amount_cents = max_amount
            seller.is_active = True
            seller.save()

        invitation, raw_token = generate_invitation(seller=seller)

        base_url = getattr(__import__("django.conf", fromlist=["settings"]).settings, "APP_BASE_URL", "http://localhost:8000")
        access_url = f"{base_url.rstrip('/')}/acesso/{raw_token}/"

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Vendedor '{seller.name}' criado com sucesso."))
        self.stdout.write(f"  Link de acesso: {access_url}")
        self.stdout.write(f"  Expira em:      {invitation.expires_at.strftime('%d/%m/%Y %H:%M')} UTC")
        self.stdout.write(f"  Admin:          {base_url.rstrip('/')}/admin/")
        self.stdout.write("")
