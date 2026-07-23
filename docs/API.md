# API Reference — Vidalys Pay

## Visão Geral

A API do Vidalys Pay segue REST com autenticação via sessão de vendedor ou API Key. Todas as respostas são JSON.

O contrato legível por ferramentas está em [`openapi.json`](openapi.json). Toda
resposta, inclusive de erro, contém `X-Request-ID`; informe esse valor ao suporte
para localizar a requisição nos logs.

## Autenticação

### Sessão do Vendedor

```http
Cookie: vidalys_seller_session=<session_key>
```

### API Key

```http
Authorization: Bearer vly_live_xxxxx
```

### Webhook Pagar.me

```http
Authorization: Basic base64(PAGARME_WEBHOOK_BASIC_AUTH_USER:PAGARME_WEBHOOK_BASIC_AUTH_PASSWORD)
```

### Matriz de acesso

| Recurso | Sessão vendedor | Sessão admin | API Key / escopo |
|---|---:|---:|---|
| Criar link | Sim | Não | `payment_links:write` + `seller_id` |
| Listar/detalhar link | Sim | Não | `payment_links:read` + `seller_id` |
| Reenviar WhatsApp | Sim | Não | `notifications:write` + `seller_id` |
| Consultar CNPJ | Sim | Superusuário | Não |
| CEP e cálculo de frete | Sim | Não | Não |
| Webhook Pagar.me | Não | Não | HTTP Basic próprio |

A API Key representa uma integração, não um vendedor. Por isso `seller_id` é
obrigatório no body da criação e na query string das leituras/reenvio.

## Endpoints

### Criar Link de Pagamento

**POST** `/api/v1/payment-links/`

#### Headers

```http
Content-Type: application/json
Authorization: Bearer vly_live_xxxxx
Idempotency-Key: 9c38991e-8bf4-4d19-89bc-f91f22bfef16
```

#### Body

```json
{
  "reference": "PED-45892",
  "amount_cents": 35000,
  "installments": 3,
  "customer_name": "Maria Silva",
  "customer_phone": "+5531999999999",
  "description": "Pedido da loja",
  "expires_in_minutes": 1440
}
```

#### Campos

| Campo | Tipo | Obrigatório | Descrição |
|-------|------|-------------|-----------|
| `reference` | string | Sim | Referência do pedido (máx. 80 chars) |
| `amount_cents` | integer | Sim | Valor em centavos (> 0) |
| `installments` | integer | Sim | Parcelas (1, 2 ou 3) |
| `customer_name` | string | Não | Nome do cliente |
| `customer_phone` | string | Não | Telefone E.164 ou brasileiro com DDD; armazenado em E.164 |
| `description` | string | Não | Descrição |
| `expires_in_minutes` | integer | Não | Expiração em minutos (10-43200) |

#### Resposta 201

```json
{
  "data": {
    "id": "019-...",
    "reference": "PED-45892",
    "amount_cents": 35000,
    "amount_formatted": "R$ 350,00",
    "installments": 3,
    "status": "ACTIVE",
    "payment_url": "https://checkout.pagar.me/...",
    "expires_at": "2026-07-22T14:00:00Z",
    "whatsapp": {
      "seller": {
        "status": "queued",
        "message": "Envio para seu WhatsApp agendado."
      },
      "customer": {
        "status": "queued",
        "message": "Envio para o cliente agendado."
      }
    },
    "created_at": "2026-07-21T14:00:00Z"
  }
}
```

#### Resposta 202 (Resultado Incerto)

```json
{
  "data": {
    "id": "019-...",
    "status": "CREATING",
    "payment_url": null
  }
}
```

#### Resposta 400 (Validação)

```json
{
  "error": {
    "code": "validation_error",
    "message": "Referência é obrigatória.",
    "field_errors": {
      "reference": ["Campo obrigatório."]
    }
  }
}
```

#### Resposta 409 (Conflito Idempotência)

```json
{
  "error": {
    "code": "idempotency_conflict",
    "message": "Chave de idempotência reutilizada com dados diferentes."
  }
}
```

### Listar Links

**GET** `/api/v1/payment-links/`

#### Query Parameters

| Param | Tipo | Descrição |
|-------|------|-----------|
| `status` | string | Filtrar por status |
| `cursor` | string | Cursor para paginação |
| `limit` | integer | Itens por página (máx. 100) |

#### Resposta 200

```json
{
  "data": [
    {
      "id": "019-...",
      "reference": "PED-45892",
      "customer_name": "Maria Silva",
      "amount_cents": 35000,
      "installments": 3,
      "status": "ACTIVE",
      "last_attempt_status": "FAILED",
      "created_at": "2026-07-21T14:00:00Z"
    }
  ],
  "pagination": {
    "next_cursor": "2026-07-21T13:00:00Z",
    "has_next": true
  }
}
```

### Detalhar Link

**GET** `/api/v1/payment-links/{id}/`

#### Resposta 200

```json
{
  "data": {
    "id": "019-...",
    "reference": "PED-45892",
    "customer_name": "Maria Silva",
    "customer_phone": "+5531999999999",
    "amount_cents": 35000,
    "amount_formatted": "R$ 350,00",
    "installments": 3,
    "status": "ACTIVE",
    "payment_url": "https://checkout.pagar.me/...",
    "provider_link_id": "pl_...",
    "expires_at": "2026-07-22T14:00:00Z",
    "paid_at": null,
    "created_at": "2026-07-21T14:00:00Z",
    "updated_at": "2026-07-21T14:00:00Z",
    "attempts": [
      {
        "id": "019-...",
        "provider_order_id": "or_...",
        "status": "FAILED",
        "amount_cents": 35000,
        "created_at": "2026-07-21T14:30:00Z"
      }
    ],
    "timeline": [
      {
        "event": "link_created",
        "timestamp": "2026-07-21T14:00:00Z",
        "details": "Link criado com valor R$ 350,00"
      },
      {
        "event": "payment_confirmed",
        "timestamp": "2026-07-21T15:00:00Z",
        "details": "Pagamento confirmado"
      }
    ]
  }
}
```

### Reenviar Link

**POST** `/api/v1/payment-links/{id}/resend/`

#### Headers

```http
Idempotency-Key: 9c38991e-8bf4-4d19-89bc-f91f22bfef16
```

#### Resposta 202

```json
{
  "data": {
    "whatsapp": {
      "seller": {"status": "queued", "message": "Envio para seu WhatsApp agendado."},
      "customer": {"status": "not_requested", "message": "Cliente sem telefone informado."}
    }
  }
}
```

A mesma `Idempotency-Key` nunca enfileira o mesmo reenvio duas vezes, mesmo se a
primeira mensagem já tiver sido processada. Uma nova tentativa intencional deve
usar uma chave nova. Na criação, a mesma chave só reutiliza o resultado quando
todos os campos do payload são idênticos; qualquer diferença retorna `409`.

### Consultar CNPJ

**GET** `/api/v1/boletos/cnpj/{cnpj}/`

Aceita CNPJ com ou sem máscara. Exige sessão ativa de vendedor ou sessão Django
de superusuário. Retorna `400` para CNPJ inválido, `404` quando não encontrado,
`503` quando o provedor está indisponível e `504` em timeout. Limite: 20/minuto.

### Consultar CEP

**POST** `/api/v1/freight/cep/`

```json
{"zip_code": "30140-071"}
```

Exige sessão de vendedor. A resposta contém `zip_code`, `street`,
`neighborhood`, `city`, `state` e `source`. Limite: 30/minuto.

### Calcular frete

**POST** `/api/v1/freight/calculate/`

```json
{
  "destination_zip_code": "30140-071",
  "weight_grams": 500,
  "length_cm": 20,
  "width_cm": 15,
  "height_cm": 10,
  "declared_value_cents": 10000
}
```

Exige sessão de vendedor. Retorna destino, pacote normalizado e opções com preço
em centavos, prazo do provedor, dias adicionais e prazo final. Limite: 20/minuto.

### Webhook Pagar.me

**POST** `/api/v1/webhooks/pagarme/`

Recebe eventos de links e boletos. Eventos autenticados sem correlação com
recursos da Vidalys Pay respondem `200`, mas são descartados e não permanecem
em `WebhookEvent`. Eventos próprios processados, ignorados ou falhos permanecem
para auditoria. Detalhes: [`WEBHOOKS.md`](WEBHOOKS.md).

#### Headers

```http
Content-Type: application/json
Authorization: Basic base64(PAGARME_WEBHOOK_BASIC_AUTH_USER:PAGARME_WEBHOOK_BASIC_AUTH_PASSWORD)
```

#### Body (Evento order.paid)

```json
{
  "id": "hook_RyEKQO789TRpZjv5",
  "type": "order.paid",
  "data": {
    "id": "or_ZdnB5BBCmYhk534R",
    "code": "PED-45892",
    "amount": 35000,
    "status": "paid",
    "metadata": {
      "internal_payment_link_id": "uuid-do-link"
    }
  }
}
```

#### Resposta 200

```json
{
  "received": true,
  "event_id": "hook_RyEKQO789TRpZjv5",
  "duplicate": false
}
```

`duplicate` só será `true` quando a primeira entrega tiver sido retida. Um
evento externo descartado será avaliado e descartado novamente se for reenviado.

### Encargos dos boletos emitidos

A emissão empresarial feita pelas telas do Vidalys Pay envia por padrão:

```json
{
  "instructions": "Após o vencimento: multa de 2% e juros de mora de 1% ao mês.",
  "interest": {"days": 1, "type": "percentage", "amount": 1},
  "fine": {"days": 1, "type": "percentage", "amount": 2}
}
```

Esses campos pertencem a `payments[].boleto` na criação de order do Pagar.me.
A funcionalidade requer conta Pagar.me na modalidade PSP.

### Health Check

**GET** `/health/`

```json
{"status": "ok"}
```

### Readiness Check

**GET** `/health/ready/`

```json
{
  "status": "ready",
  "database": "ok",
  "migrations": "ok"
}
```

## Status Codes

| Código | Descrição |
|--------|-----------|
| 200 | Sucesso |
| 201 | Criado |
| 202 | Aceito (processamento pendente) |
| 400 | Requisição inválida |
| 401 | Não autenticado |
| 403 | Não autorizado |
| 404 | Não encontrado |
| 409 | Conflito (idempotência) |
| 422 | Erro de regra de negócio |
| 429 | Rate limit excedido |

## Erros

```json
{
  "error": {
    "code": "error_code",
    "message": "Mensagem amigável",
    "field_errors": {
      "campo": ["Erro específico"]
    }
  }
}
```

O identificador de rastreio fica no header `X-Request-ID`, não no corpo.

## Rate Limiting

Headers de resposta:

```http
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 45
X-RateLimit-Reset: 1721568000
```

## Paginação

Use cursor para paginação:

```
GET /api/v1/payment-links/?cursor=2026-07-21T13:00:00Z&limit=20
```

O `next_cursor` na resposta indica o próximo item.
