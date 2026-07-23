# Vidalys Pay — Documentação Completa

## Visão Geral do Projeto

O **Vidalys Pay** é uma aplicação interna da Vidalys para criação de links de pagamento. O sistema permite que vendedores criem links de pagamento via API do Pagar.me, recebam os links no WhatsApp via Evolution API e acompanhem os pagamentos por webhooks.

Documentos operacionais principais:

- [`API.md`](API.md): contratos HTTP;
- [`BOLETOS.md`](BOLETOS.md): emissão e reconciliação de boletos;
- [`WEBHOOKS.md`](WEBHOOKS.md): autenticação, correlação, retenção e diagnóstico;
- [`DEPLOYMENT.md`](DEPLOYMENT.md): configuração e publicação;
- [`TESTING.md`](TESTING.md): validações automatizadas.

### Objetivo

Resolver os problemas de:
- Demora no atendimento para gerar cobranças
- Erros de valor, parcela ou destinatário
- Dificuldade para identificar qual vendedor criou a cobrança
- Ausência de histórico centralizado
- Dependência de conferência manual do pagamento

### Fluxo Principal

```
Vendedor → Cria link → Pagar.me gera checkout → Link enviado via WhatsApp → Cliente paga → Webhook atualiza status
```

## Arquitetura

### Stack Tecnológica

| Camada | Tecnologia | Versão |
|--------|------------|--------|
| Backend | Django | 5.2 LTS |
| API | Django REST Framework | 3.15+ |
| Banco | PostgreSQL | 17+ (externo) |
| Frontend | Django Templates + HTMX | - |
| PWA | Manifest + Service Worker | - |
| Container | Docker Compose | - |
| Deploy | Coolify | - |

### Diagrama de Componentes

```
┌─────────────────────────────────────────────────────────────┐
│                      Coolify / Docker                        │
│  ┌─────────────────┐           ┌─────────────────┐          │
│  │   web (Gunicorn)│           │  worker (outbox) │          │
│  │   porta 8000    │           │  processamento   │          │
│  └────────┬────────┘           └────────┬────────┘          │
│           │                             │                    │
│           └──────────┬──────────────────┘                    │
└──────────────────────┼──────────────────────────────────────┘
                       │
                       ▼
            ┌─────────────────────┐
            │    PostgreSQL       │
            │  (banco externo)    │
            └─────────────────────┘
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
    ┌──────────┐ ┌──────────┐ ┌──────────┐
    │ Pagar.me │ │Evolution │ │   n8n    │
    │(checkout)│ │(WhatsApp)│ │(futuro)  │
    └──────────┘ └──────────┘ └──────────┘
```

### Módulos Django

```
apps/
├── core/                 # Configurações comuns, health, logging
├── sellers/              # Vendedores, convites e sessões
├── payment_links/        # Links e tentativas de pagamento
├── webhooks/             # Entrada e processamento de webhooks
├── notifications/        # Mensagens, templates e outbox
├── integrations/
│   ├── pagarme/          # Cliente HTTP Pagar.me
│   ├── evolution/        # Cliente HTTP Evolution
│   └── n8n/              # API keys para integrações
├── audit/                # Trilha de auditoria
└── shipping/             # Reservado (sem funcionalidade)
```

## Modelo de Dados

### Entidades Principais

#### Seller (Vendedor)
```python
class Seller(UUIDModel, TimeStampedModel):
    name = CharField(max_length=120)
    whatsapp_phone = CharField(max_length=20)  # E.164
    is_active = BooleanField(default=True)
    max_payment_amount_cents = BigIntegerField()
```

#### SellerInvitation (Convite)
```python
class SellerInvitation(UUIDModel, TimeStampedModel):
    seller = ForeignKey(Seller)
    token_hash = CharField(max_length=64)  # SHA-256
    expires_at = DateTimeField()
    used_at = DateTimeField(null=True)
    revoked_at = DateTimeField(null=True)
```

#### SellerSession (Sessão)
```python
class SellerSession(UUIDModel, TimeStampedModel):
    seller = ForeignKey(Seller)
    django_session_key = CharField(max_length=40)
    device_label = CharField(max_length=120)
    expires_at = DateTimeField()
    revoked_at = DateTimeField(null=True)
```

#### PaymentLink (Link de Pagamento)
```python
class PaymentLink(UUIDModel, TimeStampedModel):
    seller = ForeignKey(Seller)
    reference = CharField(max_length=80)
    amount_cents = BigIntegerField()
    installments = SmallIntegerField()  # 1-3
    status = CharField()  # CREATING, ACTIVE, PAID, etc.
    provider_link_id = CharField(unique=True)
    payment_url = TextField()
    idempotency_key = CharField(max_length=100)
```

#### PaymentAttempt (Tentativa)
```python
class PaymentAttempt(UUIDModel, TimeStampedModel):
    payment_link = ForeignKey(PaymentLink)
    provider_order_id = CharField()
    provider_charge_id = CharField()
    status = CharField()  # PENDING, PAID, FAILED, etc.
    amount_cents = BigIntegerField()
```

### Estados do PaymentLink

```
CREATING → ACTIVE → PAID
    ↓         ↓
CREATION_  CANCELED
ERROR      EXPIRED
    ↓
CREATION_
UNKNOWN
```

### Estados do PaymentAttempt

```
PENDING → PROCESSING → PAID
    ↓           ↓
FAILED      REFUNDED
            CHARGEDBACK
```

## Autenticação

### Vendedor (Sessão)

1. Admin cria vendedor no Django Admin
2. Admin gera convite (token SHA-256 com pepper)
3. Convite enviado via WhatsApp
4. Vendedor abre link → sessão criada (cookie HttpOnly)
5. Sessão válida por 30 dias

### API Key (Integrações)

```http
Authorization: Bearer vly_live_xxxxx
```

- Chaves geradas no Django Admin
- Scopes: `payment_links:read`, `payment_links:write`, `notifications:write`
- Hash SHA-256 com pepper

### Webhook Pagar.me

```http
Authorization: Basic base64(PAGARME_WEBHOOK_BASIC_AUTH_USER:PAGARME_WEBHOOK_BASIC_AUTH_PASSWORD)
```

Eventos sem vínculo com boleto, link ou referência interna da Vidalys Pay não
permanecem armazenados. Consulte [`WEBHOOKS.md`](WEBHOOKS.md).

## API

### Endpoints

| Método | Endpoint | Auth | Descrição |
|--------|----------|------|-----------|
| POST | `/api/v1/payment-links/` | Seller/API Key | Criar link |
| GET | `/api/v1/payment-links/` | Seller/API Key | Listar links |
| GET | `/api/v1/payment-links/{id}/` | Seller/API Key | Detalhar link |
| POST | `/api/v1/payment-links/{id}/resend/` | Seller/API Key | Reenviar link |
| POST | `/api/v1/webhooks/pagarme/` | Basic Auth | Webhook Pagar.me |
| GET | `/health/` | - | Health check |
| GET | `/health/ready/` | - | Readiness check |

### Criar Link

```bash
curl -X POST http://localhost:8000/api/v1/payment-links/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer vly_live_xxxxx" \
  -H "Idempotency-Key: $(uuidgen)" \
  -d '{
    "reference": "PED-001",
    "amount_cents": 35000,
    "installments": 3,
    "customer_name": "João Silva"
  }'
```

### Resposta

```json
{
  "data": {
    "id": "uuid",
    "reference": "PED-001",
    "amount_cents": 35000,
    "amount_formatted": "R$ 350,00",
    "installments": 3,
    "status": "ACTIVE",
    "payment_url": "https://checkout.pagar.me/...",
    "created_at": "2026-07-21T14:00:00Z"
  }
}
```

## Integrações

### Pagar.me

- **Endpoint:** `POST https://api.pagar.me/core/v5/paymentlinks`
- **Auth:** Basic Auth (sk_test_* ou sk_*)
- **Checkout hospedado** (dados de cartão não passam pelo sistema)
- **Webhook:** Eventos order.paid, order.payment_failed, charge.*, checkout.*

### Evolution API

- **Endpoint:** `POST {EVOLUTION_API_URL}/message/sendText/{EVOLUTION_INSTANCE}`
- **Auth:** Header `apikey`
- **Envio de mensagens de texto**
- **Retry via outbox**

## Segurança

- Senhas nunca armazenadas (vendedor é passwordless)
- Tokens com pelo menos 256 bits
- Hash SHA-256 com pepper
- Cookie HttpOnly/Secure/SameSite
- Rate limiting por seller/API key/IP
- Webhook com autenticação Basic Auth
- Nenhum dado de cartão armazenado

## Deploy

### Docker Compose

```yaml
services:
  web:
    command: gunicorn config.wsgi:application --bind 0.0.0.0:8000
    ports:
      - "8000:8000"
  
  worker:
    command: python manage.py run_outbox_worker
```

### Coolify

1. Conectar repositório Git
2. Selecionar Docker Compose
3. Configurar domínio
4. Preencher variáveis de ambiente
5. Deploy

## Testes

```bash
# Rodar todos os testes
pytest

# Com cobertura
pytest --cov=apps

# Testes específicos
pytest tests/test_sellers_services.py -v
```

## Comandos Úteis

```bash
# Migrations
python manage.py migrate

# Superusuário
python manage.py createsuperuser

# Shell Django
python manage.py shell

# Worker outbox
python manage.py run_outbox_worker

# Collectstatic
python manage.py collectstatic

# Lint
ruff check .
```

## Variáveis de Ambiente

| Variável | Descrição | Obrigatória |
|----------|-----------|-------------|
| `SECRET_KEY` | Chave secreta Django | Sim |
| `DATABASE_URL` | URL do PostgreSQL | Sim |
| `PAGARME_SECRET_KEY` | Chave Pagar.me | Sim |
| `PAGARME_WEBHOOK_BASIC_AUTH_USER` | Usuário Basic Auth webhook | Sim |
| `PAGARME_WEBHOOK_BASIC_AUTH_PASSWORD` | Senha Basic Auth webhook | Sim |
| `EVOLUTION_API_URL` | URL da Evolution API | Sim |
| `EVOLUTION_API_KEY` | Chave da Evolution API | Sim |
| `EVOLUTION_INSTANCE` | Nome da instância | Sim |
| `INVITATION_TOKEN_PEPPER` | Pepper para hash de convites | Sim |
| `API_KEY_PEPPER` | Pepper para hash de API keys | Sim |

## Licença

MIT License
