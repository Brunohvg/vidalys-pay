# Coolify Quick Start — Vidalys Pay

## Resumo Rápido

```
URL: https://pay.vidalys.com.br
Repo: https://github.com/Brunohvg/vidalys-pay
Branch: main
```

## Variáveis Obrigatórias (Copie e Cole)

```
SECRET_KEY=[GERE_AQUI]
DEBUG=false
ALLOWED_HOSTS=pay.vidalys.com.br
CSRF_TRUSTED_ORIGINS=https://pay.vidalys.com.br
APP_BASE_URL=https://pay.vidalys.com.br
APP_NAME=Vidalys Pay
DATABASE_URL=[SEU_BANCO_POSTGRESQL]
PAGARME_BASE_URL=https://api.pagar.me/core/v5
PAGARME_SECRET_KEY=[SUA_CHAVE_PAGARME]
PAGARME_WEBHOOK_AUTH_MODE=basic
PAGARME_WEBHOOK_BASIC_AUTH_USER=[GERE_AQUI]
PAGARME_WEBHOOK_BASIC_AUTH_PASSWORD=[GERE_OUTRO_SEGREDO]
EVOLUTION_API_URL=https://api.lojabibelo.com.br
EVOLUTION_API_KEY=[SUA_CHAVE_EVOLUTION]
EVOLUTION_INSTANCE=[NOME_INSTANCIA]
INVITATION_EXPIRATION_HOURS=24
SELLER_SESSION_DAYS=30
INVITATION_TOKEN_PEPPER=[GERE_AQUI]
API_KEY_PEPPER=[GERE_AQUI]
LOG_LEVEL=INFO
GUNICORN_WORKERS=3
WORKER_POLL_SECONDS=3
MAX_NOTIFICATION_ATTEMPTS=5
WEBPUSH_VAPID_PUBLIC_KEY=[CHAVE_PUBLICA_VAPID]
WEBPUSH_VAPID_PRIVATE_KEY=[CHAVE_PRIVADA_VAPID]
WEBPUSH_VAPID_SUBJECT=mailto:contato@vidalys.com.br
```

## Gerar Chaves

```bash
# SECRET_KEY
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

# Peppers
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

## Passos

1. Criar projeto no Coolify
2. Conectar repositório GitHub
3. Copiar a **Internal URL** atual do PostgreSQL para `DATABASE_URL`
4. Ativar **Connect to Predefined Network** se o banco for outro recurso
5. Configurar domínio `pay.vidalys.com.br`
6. Inserir variáveis
7. Deploy
8. Criar superusuário
9. Testar `https://pay.vidalys.com.br/health/`

## Links Úteis

- Admin: https://pay.vidalys.com.br/admin/
- Health: https://pay.vidalys.com.br/health/
- API Docs: https://github.com/Brunohvg/vidalys-pay/tree/main/docs
