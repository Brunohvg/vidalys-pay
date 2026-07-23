# Arquitetura — Vidalys Pay

## Visão Geral

O Vidalys Pay segue uma arquitetura modular com separação clara de responsabilidades. Cada módulo Django encapsula uma área de domínio específica.

## Princípios de Design

1. **Separação de Responsabilidades** — Cada módulo tem uma função bem definida
2. **Adaptadores Isolados** — Integrações externas (Pagar.me, Evolution) são isoladas
3. **Outbox Pattern** — Notificações são garantidas via outbox no PostgreSQL
4. **Idempotência** — Operações podem ser repetidas sem efeitos colaterais
5. **Fail-Safe** — Falhas em integrações não bloqueiam o fluxo principal

## Módulos

### Core (`apps/core`)

Responsável por:
- Configurações comuns
- Health endpoints
- Rate limiting
- Middleware de request ID
- Exception handling

### Sellers (`apps/sellers`)

Responsável por:
- Cadastro de vendedores
- Geração e consumo de convites
- Sessões do aparelho
- Middleware de autenticação

### Payment Links (`apps/payment_links`)

Responsável por:
- Criação de links de pagamento
- Tentativas de pagamento
- Estados e transições
- API REST

### Webhooks (`apps/webhooks`)

Responsável por:
- Recebimento de eventos
- Validação de autenticidade
- Processamento e mapeamento
- Atualização de estados

### Notifications (`apps.notifications`)

Responsável por:
- Templates de mensagens
- Outbox de notificações
- Worker de envio (WhatsApp e Web Push)
- Status de entrega

O Web Push usa VAPID e mantém uma assinatura por perfil de navegador. Eventos de
pagamento entram no mesmo outbox das demais notificações; no retry, o worker
preserva os aparelhos que já receberam para não duplicar a entrega.

### Integrations (`apps.integrations`)

- **pagarme**: Cliente HTTP para API Pagar.me
- **evolution**: Cliente HTTP para Evolution API
- **n8n**: Chaves de API para integrações externas

### Audit (`apps.audit`)

Responsável por:
- Trilha de auditoria
- Logs de ações administrativas

### Shipping (`apps.shipping`)

Módulo reservado para futura implementação de calculadora de frete.

## Fluxos

### Fluxo de Criação de Link

```
1. Vendedor preenche formulário
2. POST /api/v1/payment-links/
3. Validação de dados
4. Verificação de idempotência
5. Criação local (status: CREATING)
6. Chamada HTTP para Pagar.me
7. Atualização com resposta
8. Inserção no outbox (WhatsApp)
9. Resposta ao vendedor
10. Worker envia WhatsApp
```

### Fluxo de Webhook

```
1. POST /api/v1/webhooks/pagarme/
2. Validação de Basic Auth
3. Persistência do evento bruto
4. Verificação de duplicidade
5. Mapeamento do evento
6. Atualização de PaymentLink/PaymentAttempt
7. Inserção de notificações no outbox
8. Resposta 200
```

### Fluxo de Autenticação

```
1. Admin cria vendedor
2. Admin gera convite
3. Convite enviado via WhatsApp
4. Vendedor abre link
5. Token validado atomicamente
6. Sessão criada (cookie HttpOnly)
7. Redirect para /app/
```

## Estado das Entidades

### PaymentLink

```python
class PaymentLinkStatus(models.TextChoices):
    CREATING = "CREATING"           # Criando no Pagar.me
    CREATION_UNKNOWN = "CREATION_UNKNOWN"  # Resultado incerto
    CREATION_ERROR = "CREATION_ERROR"      # Erro na criação
    ACTIVE = "ACTIVE"               # Link ativo
    PAID = "PAID"                   # Pago
    CANCELED = "CANCELED"           # Cancelado
    EXPIRED = "EXPIRED"             # Expirado
    REFUNDED = "REFUNDED"           # Reembolsado
```

### PaymentAttempt

```python
class PaymentAttemptStatus(models.TextChoices):
    PENDING = "PENDING"         # Aguardando
    PROCESSING = "PROCESSING"   # Processando
    PAID = "PAID"               # Pago
    FAILED = "FAILED"           # Falhou
    REFUNDED = "REFUNDED"       # Reembolsado
    CHARGEDBACK = "CHARGEDBACK" # Chargeback
```

## Padrões de Projeto

### Outbox Pattern

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Transação  │────▶│   Outbox    │────▶│   Worker    │
│   Principal │     │  (PostgreSQL)│     │  (Envio)    │
└─────────────┘     └─────────────┘     └─────────────┘
```

- Mensagens são inseridas na mesma transação que a mudança de estado
- Worker processa com `SELECT ... FOR UPDATE SKIP LOCKED`
- Backoff exponencial: 0s, 60s, 300s, 900s, 3600s
- Máximo de 5 tentativas antes de marcar como DEAD

### Idempotência

- Chave de idempotência no header `Idempotency-Key`
- Restrição unique por `(seller, idempotency_key)`
- Reutilização com mesmo payload retorna resposta existente
- Reutilização com payload diferente retorna 409

### Adaptadores de Integração

```python
# Pagar.me
class PagarmeClient:
    def create_payment_link(self, payload) -> dict
    def get_payment_link(self, link_id) -> dict
    def cancel_payment_link(self, link_id) -> dict

# Evolution
class EvolutionClient:
    def send_text(self, phone, text) -> dict
```

## Segurança

### Autenticação

- **Vendedor**: Sessão via cookie HttpOnly/Secure/SameSite
- **API Key**: Bearer token com hash SHA-256
- **Webhook**: Basic Auth com username do segredo

### Autorização

- Vendedor só acessa seus próprios recursos
- API Key tem scopes específicos
- Django Admin para operações administrativas

### Proteções HTTP

- HTTPS obrigatório
- HSTS após validação
- CSP restritiva
- X-Content-Type-Options: nosniff
- X-Frame-Options: DENY
- CSRF em todas as mutações

### Dados Sensíveis

- Nenhum dado de cartão armazenado
- Telefone do cliente opcional
- Logs não contêm chaves ou dados sensíveis
- Payloads sanitizados antes de armazenar

## Observabilidade

### Logs

```json
{
  "timestamp": "2026-07-21T14:00:00Z",
  "level": "INFO",
  "logger": "apps.payment_links",
  "message": "Link criado com sucesso",
  "request_id": "req_01...",
  "seller_id": "uuid",
  "payment_link_id": "uuid"
}
```

### Métricas

- Tempo de resposta das telas (< 800ms p95)
- Taxa de criação de links
- Taxa de entrega WhatsApp
- Eventos de webhook com erro
- Itens DEAD no outbox

## Escalabilidade

### Horizontal

- Web: múltiplos workers Gunicorn
- Worker: múltiplas instâncias com SKIP LOCKED

### Vertical

- Aumentar workers do Gunicorn
- Aumentar conexões do PostgreSQL

### Limitações

- Worker é single-threaded por instância
- Rate limiting é in-memory (não compartilhado)
- Sessões são armazenadas no banco
