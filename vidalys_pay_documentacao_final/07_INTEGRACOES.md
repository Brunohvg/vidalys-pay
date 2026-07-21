# Integrações externas

> Vidalys Pay — Documentação final v1.0 — 21 de julho de 2026

## 1. Pagar.me

### Papel

Cria checkout hospedado e envia eventos de pagamento. O sistema não recebe dados de cartão.

### Ambiente

- teste: base URL sandbox e chave `sk_test_...`;
- produção: base URL de produção e chave `sk_live_...`.

A autenticação oficial da API V5 usa Basic Auth com a secret key como usuário e senha vazia.

### Payload conceitual do MVP

```json
{
  "type": "order",
  "max_paid_sessions": 1,
  "expires_in": 1440,
  "payment_settings": {
    "accepted_payment_methods": ["credit_card"],
    "credit_card_settings": {
      "operation_type": "auth_and_capture",
      "installments_setup": {
        "interest_type": "simple",
        "interest_rate": 0,
        "max_installments": 3
      }
    }
  },
  "cart_settings": {
    "items": [
      {
        "name": "Pedido PED-45892",
        "amount": 35000,
        "description": "Pedido da loja",
        "default_quantity": 1
      }
    ]
  }
}
```

**Nota obrigatória:** nomes exatos de objetos de parcelamento e campos opcionais devem ser confirmados no schema vigente da conta Pagar.me antes de codificar. O cliente HTTP deve isolar essas diferenças para não espalhá-las pelo domínio.

### Timeout

- conexão: 3 s;
- leitura: 10 s;
- sem retry automático cego em `POST /paymentlinks`;
- em timeout, consultar/reconciliar usando metadados ou identificadores antes de repetir.

### Metadata

Quando suportado, enviar:

- `internal_payment_link_id`;
- `seller_id`;
- `reference`.

Nunca enviar segredo ou telefone desnecessário em metadata.

### Webhooks

Assinar eventos mínimos de pedido, cobrança e checkout. Mapear por uma tabela versionada, guardar evento desconhecido e testar payloads reais do sandbox.

## 2. Evolution API

### Endpoint

`POST {EVOLUTION_API_URL}/message/sendText/{EVOLUTION_INSTANCE}`

Headers:

```http
Content-Type: application/json
apikey: <EVOLUTION_API_KEY>
```

Body mínimo:

```json
{
  "number": "5531999999999",
  "text": "Link de pagamento...",
  "linkPreview": true
}
```

### Regras

- número com DDI e DDD;
- timeout 10 s;
- resposta 201 considerada aceita;
- guardar ID e status retornados;
- não expor API Key;
- circuit breaker simples por falhas consecutivas;
- retry pela outbox;
- templates versionados.

### Templates

#### Convite

```text
Olá, {seller_name}.

Seu acesso ao {app_name} foi liberado:
{activation_url}

O link é pessoal, expira em {expiration_hours} horas e funciona uma única vez. Não encaminhe esta mensagem.
```

#### Link criado

```text
Link de pagamento criado

Pedido: {reference}
Cliente: {customer_name_or_not_informed}
Valor: {amount}
Parcelamento: {installments_label}

{payment_url}
```

#### Pagamento aprovado

```text
Pagamento confirmado

Pedido: {reference}
Valor: {amount}
Cliente: {customer_name_or_not_informed}
```

#### Falha de tentativa

```text
Uma tentativa de pagamento não foi aprovada.

Pedido: {reference}
Valor: {amount}

O link continua disponível enquanto estiver ativo.
```

#### Link expirado/cancelado

Mensagens separadas; não chamar cancelamento de expiração.

## 3. n8n

O n8n já existe externamente.

### MVP

Nenhuma dependência. A aplicação funciona sem ele.

### Uso futuro

- consultar pagamentos;
- criar links com API Key;
- gerar relatórios;
- integrar planilhas/ERP;
- acionar fluxos comerciais;
- receber eventos opcionais.

### Eventos de saída opcionais

- `payment_link.created`;
- `payment_link.paid`;
- `payment_link.expired`;
- `payment_attempt.failed`.

Assinar webhooks de saída com HMAC próprio e não bloquear o fluxo principal por falha no n8n.

## 4. Calculadora de frete futura

Criar interface `ShippingQuoteProvider`, sem implementação no MVP:

```python
class ShippingQuoteProvider(Protocol):
    def quote(self, *, origin_zip: str, destination_zip: str, packages: list[Package]) -> list[Quote]: ...
```

O módulo retorna cotação e o caso de uso soma frete ao valor antes de criar o link. O pagamento não deve depender diretamente de uma transportadora específica.

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
