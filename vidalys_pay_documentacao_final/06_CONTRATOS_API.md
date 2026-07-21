# Contratos da API

> Vidalys Pay — Documentação final v1.0 — 21 de julho de 2026

## 1. Convenções

Base: `/api/v1`  
Formato: JSON  
Datas: ISO 8601 UTC  
Dinheiro: centavos inteiros  
Telefone: E.164  
Idempotência: header `Idempotency-Key` em operações de criação e reenvio.

## 2. Autenticação

### PWA do vendedor

Cookie de sessão + CSRF.

### n8n e integrações

```http
Authorization: Bearer vly_live_xxxxx
```

A chave é mostrada apenas uma vez ao criar e armazenada como hash.

## 3. Erro padrão

```json
{
  "error": {
    "code": "seller_amount_limit_exceeded",
    "message": "O valor ultrapassa o limite permitido para este vendedor.",
    "field_errors": {
      "amount_cents": ["Valor máximo: 500000"]
    },
    "request_id": "req_01..."
  }
}
```

## 4. Criar link

`POST /api/v1/payment-links`

Headers:

```http
Idempotency-Key: 9c38991e-8bf4-4d19-89bc-f91f22bfef16
```

Request:

```json
{
  "reference": "PED-45892",
  "amount_cents": 35000,
  "installments": 3,
  "customer_name": "Maria Silva",
  "customer_phone": null,
  "description": "Pedido da loja",
  "expires_in_minutes": 1440
}
```

Response `201`:

```json
{
  "data": {
    "id": "019...",
    "reference": "PED-45892",
    "amount_cents": 35000,
    "amount_formatted": "R$ 350,00",
    "installments": 3,
    "status": "ACTIVE",
    "payment_url": "https://checkout.pagar.me/...",
    "expires_at": "2026-07-22T14:00:00Z",
    "whatsapp_delivery": {
      "status": "QUEUED"
    },
    "created_at": "2026-07-21T14:00:00Z"
  }
}
```

Possíveis respostas:

- `400` validação;
- `401` sessão/API Key inválida;
- `403` vendedor inativo ou scope ausente;
- `409` chave reutilizada com payload diferente;
- `422` regra de negócio;
- `502` falha confirmada do Pagar.me;
- `202` resultado incerto e reconciliação em andamento, se adotado.

## 5. Listar links

`GET /api/v1/payment-links?status=ACTIVE&cursor=...&limit=20`

Para sessão de vendedor, retorna apenas próprios links. Para API Key, exige escopo e pode aceitar `seller_id`.

Response:

```json
{
  "data": [
    {
      "id": "019...",
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
    "next_cursor": null
  }
}
```

## 6. Detalhar link

`GET /api/v1/payment-links/{id}`

Inclui tentativas, entregas de WhatsApp e timeline sanitizada, respeitando autorização.

## 7. Reenviar WhatsApp

`POST /api/v1/payment-links/{id}/resend`

Requer `Idempotency-Key`. Cria outbox, não chama Evolution dentro da transação da request.

Response `202`:

```json
{
  "data": {
    "message_id": "019...",
    "status": "QUEUED"
  }
}
```

## 8. Cancelar link

`POST /api/v1/payment-links/{id}/cancel`

Disponível somente se `PAYMENT_LINK_CANCEL_ENABLED=true` e o ator tiver permissão.

```json
{
  "reason": "Pedido cancelado pelo cliente"
}
```

## 9. Perfil do vendedor

- `GET /api/v1/me`
- `POST /api/v1/me/logout`
- `GET /api/v1/me/sessions`
- `DELETE /api/v1/me/sessions/{id}` apenas sessão atual ou política permitida.

## 10. Webhook Pagar.me

`POST /api/v1/webhooks/pagarme/{endpoint_secret}`

O endpoint:

- aceita JSON;
- preserva body bruto;
- retorna `200` para evento processado ou duplicado;
- retorna `202` se persistido para processamento posterior;
- usa `400` para payload inválido;
- usa `401/403` para autenticidade inválida;
- evita `500` repetitivo em evento permanentemente inválido depois de registrado.

Response:

```json
{
  "received": true,
  "event_id": "hook_...",
  "duplicate": false
}
```

## 11. Health

### `GET /health`

```json
{"status":"ok"}
```

### `GET /ready`

```json
{
  "status": "ready",
  "database": "ok",
  "migrations": "ok"
}
```

## 12. API administrativa

Não expor CRUD administrativo público no MVP. Usar Django Admin. Qualquer API de administração futura deve possuir autenticação separada e auditoria.

## 13. OpenAPI

O arquivo `openapi.yaml` deste pacote serve como contrato inicial. A implementação deve gerar schema automaticamente pelo DRF e compará-lo no CI com o contrato aprovado.

---

## Referências oficiais consultadas

Documentação consultada em 21/07/2026. Durante a implementação, validar novamente os contratos ativos da conta Pagar.me e a versão instalada da Evolution API.

1. Pagar.me — Criar link de pagamento: https://docs.pagar.me/reference/criar-link
2. Pagar.me — Checkout para cobrança pontual: https://docs.pagar.me/docs/checkout_pagarme_skill_order
3. Pagar.me — Visão geral sobre webhooks: https://docs.pagar.me/reference/vis%C3%A3o-geral-sobre-webhooks
4. Pagar.me — Eventos de webhook: https://docs.pagar.me/reference/eventos-de-webhook-1
5. Evolution API v2 — Send Plain Text: https://doc.evolution-api.com/v2/api-reference/message-controller/send-text
6. Coolify — Docker Compose: https://coolify.io/docs/knowledge-base/docker/compose
7. Coolify — Health checks: https://coolify.io/docs/knowledge-base/health-checks
8. Django — versões suportadas: https://www.djangoproject.com/download/
