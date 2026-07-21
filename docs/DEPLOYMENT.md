# Deploy — Vidalys Pay

## Pré-requisitos

- Servidor com Docker instalado
- Domínio configurado
- PostgreSQL externo acessível
- Conta Pagar.me (sandbox ou produção)
- Evolution API externa

## Estrutura de Deploy

```
┌─────────────────────────────────────────────────────────┐
│                    Coolify / Docker                      │
│  ┌──────────────┐    ┌──────────────┐                   │
│  │     web      │    │    worker    │                   │
│  │  (Gunicorn)  │    │  (outbox)    │                   │
│  │  porta 8000  │    │              │                   │
│  └──────┬───────┘    └──────┬───────┘                   │
│         └─────────┬─────────┘                           │
└───────────────────┼─────────────────────────────────────┘
                    │
                    ▼
         ┌──────────────────┐
         │   PostgreSQL     │  (banco externo)
         └──────────────────┘
```

## Variáveis de Ambiente

### Django

```bash
SECRET_KEY=sua-chave-secreta-minimo-50-caracteres
DEBUG=false
ALLOWED_HOSTS=pay.vidalys.com.br
CSRF_TRUSTED_ORIGINS=https://pay.vidalys.com.br
APP_BASE_URL=https://pay.vidalys.com.br
APP_NAME=Vidalys Pay
DATABASE_URL=postgresql://usuario:senha@host:5432/vidalys_pay
```

### Pagar.me

```bash
PAGARME_BASE_URL=https://api.pagar.me/core/v5  # produção
# ou
PAGARME_BASE_URL=https://sdx-api.pagar.me/core/v5  # sandbox

PAGARME_SECRET_KEY=sk_test_xxx  # ou sk_live_xxx
PAGARME_WEBHOOK_BASIC_AUTH_USER=segredo-do-webhook
```

### Evolution API

```bash
EVOLUTION_API_URL=https://evolution.seudominio.com
EVOLUTION_API_KEY=sua-chave
EVOLUTION_INSTANCE=nome-da-instancia
```

### Acesso

```bash
INVITATION_EXPIRATION_HOURS=24
SELLER_SESSION_DAYS=30
INVITATION_TOKEN_PEPPER=segredo-forte
API_KEY_PEPPER=outro-segredo-forte
```

### Operação

```bash
LOG_LEVEL=INFO
GUNICORN_WORKERS=3
WORKER_POLL_SECONDS=3
MAX_NOTIFICATION_ATTEMPTS=5
```

## Docker Compose

```yaml
services:
  web:
    build: .
    command: gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3
    environment:
      SECRET_KEY: ${SECRET_KEY}
      DATABASE_URL: ${DATABASE_URL}
      # ... outras variáveis
    ports:
      - "8000:8000"
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://localhost:8000/health"]
      interval: 30s
      timeout: 5s
      retries: 5

  worker:
    build: .
    command: python manage.py run_outbox_worker
    environment:
      # ... mesmas variáveis do web
```

## Deploy no Coolify

### 1. Conectar Repositório

1. Acesse o Coolify
2. Crie um novo projeto
3. Conecte o repositório Git (GitHub)
4. Selecione a branch `main`

### 2. Configurar Serviços

1. Selecione "Docker Compose"
2. O Coolify detectará automaticamente o `docker-compose.yml`
3. Configure o serviço `web` na porta 8000

### 3. Configurar Domínio

1. No serviço `web`, vá em "Networking"
2. Adicione o domínio (ex: `pay.vidalys.com.br`)
3. Ative HTTPS automático

### 4. Variáveis de Ambiente

1. Vá em "Environment Variables"
2. Adicione todas as variáveis listadas acima
3. Marque as sensíveis como "Secret"

### 5. Deploy

1. Clique em "Deploy"
2. Aguarde o build completo
3. Verifique os logs

### 6. Pós-Deploy

```bash
# Criar superusuário
docker compose exec web python manage.py createsuperuser

# Verificar health
curl https://pay.vidalys.com.br/health/
curl https://pay.vidalys.com.br/health/ready/
```

## Backup

### Banco de Dados

```bash
# Backup manual
pg_dump -h HOST -U USER -d DATABASE -F c -f backup_$(date +%Y%m%d).dump

# Restauração
pg_restore -h HOST -U USER -d DATABASE -c backup.dump
```

### Configuração Automática

Configure backup automático no provedor do PostgreSQL:
- Retenção: 7 diários + 4 semanais
- Cópia fora do mesmo servidor
- Teste mensal de restauração

## Monitoramento

### Health Checks

```bash
# Liveness
curl https://pay.vidalys.com.br/health/
# {"status": "ok"}

# Readiness
curl https://pay.vidalys.com.br/health/ready/
# {"status": "ready", "database": "ok", "migrations": "ok"}
```

### Logs

```bash
# Ver logs do web
docker compose logs -f web

# Ver logs do worker
docker compose logs -f worker
```

## Rollback

1. No Coolify, selecione a tag/imagem anterior
2. Clique em "Deploy"
3. Verifique se o serviço está funcionando

## Troubleshooting

### Erro 502

- Verificar se o Gunicorn está rodando
- Verificar logs do container

### Erro de Conexão com Banco

- Verificar `DATABASE_URL`
- Verificar se o PostgreSQL está acessível
- Verificar firewall

### Webhook não funciona

- Verificar `PAGARME_WEBHOOK_BASIC_AUTH_USER`
- Verificar logs do web
- Testar com curl

### WhatsApp não envia

- Verificar `EVOLUTION_API_URL`, `EVOLUTION_API_KEY`, `EVOLUTION_INSTANCE`
- Verificar outbox: `SELECT * FROM notifications_notificationoutbox WHERE status='DEAD'`
