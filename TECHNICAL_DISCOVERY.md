# Fase 0 — Descoberta técnica

> Vidalys Pay — 21 de julho de 2026

## 1. Pagar.me — Validações pendentes

| # | Item | Status | Observação |
|---|------|--------|------------|
| 1 | Confirmar conta/ambiente sandbox | PENDENTE | `sk_test_...` — verificar se conta está ativa |
| 2 | Payload real de criação de link (type=order) | PENDENTE | Validar schema exato em POST /paymentlinks com conta ativa |
| 3 | Parcelamento 1–3 sem juros | PENDENTE | Confirmar `interest_rate: 0` e `max_installments: 3` no payload vigente |
| 4 | `max_paid_sessions=1` | PENDENTE | Confirmar suporte no schema atual |
| 5 | Mecanismo de assinatura de webhook | PENDENTE | Validar header/exact mechanism da versão ativa da conta |
| 6 | Campos de metadata suportados | PENDENTE | Confirmar se metadata aceita `internal_payment_link_id`, `seller_id`, `reference` |
| 7 | Cancelamento de link | PENDENTE | Confirmar endpoint e semântica |
| 8 | Base URL sandbox vs produção | PENDENTE | `sdx-api.pagar.me/core/v5` — validar |

**Ação necessária:** Acessar painel Pagar.me, criar sandbox, testar criação de link com curl, capturar response real e fixtures sanitizadas.

## 2. Evolution API — Validações pendentes

| # | Item | Status | Observação |
|---|------|--------|------------|
| 1 | Versão instalada | PENDENTE | v2 — confirmar build |
| 2 | Endpoint exato de sendText | PENDENTE | `POST /message/sendText/{instance}` |
| 3 | Autenticação | PENDENTE | Header `apikey` — confirmar |
| 4 | Resposta de sucesso | PENDENTE | Confirmar status code e body |
| 5 | Rate limits | PENDENTE | Verificar limites da instância |

**Ação necessária:** Confirmar instância Evolution ativa, testar envio de texto com curl, capturar response.

## 3. Domínio e deploy

| # | Item | Status | Observação |
|---|------|--------|------------|
| 1 | Nome definitivo do produto | PENDENTE | "Vidalys Pay" é provisório |
| 2 | Domínio | PENDENTE | `pay.vidalys.com.br` sugerido |
| 3 | Coolify configurado | PENDENTE | Verificar acesso e capacidade |
| 4 | SSL/TLS | PENDENTE | Confirmar automação no Coolify |

## 4. Ícones PWA

| # | Item | Status | Observação |
|---|------|--------|------------|
| 1 | SVG/logo base | PENDENTE | Obter da equipe de design |
| 2 | Ícones 192x192 e 512x512 | PENDENTE | Gerar a partir do logo |
| 3 | Maskable icon | PENDENTE | Gerar versão maskable |

## 5. Decisões congeladas (após esta fase)

- [ ] Confirmar fixtures reais do Pagar.me
- [ ] Confirmar mecanismo de webhook
- [ ] Confirmar endpoint Evolution
- [ ] Aprovar nome e domínio
- [ ] Criar ícones PWA

## 6. Fixture sanitizada mínima para Fase 4

```json
{
  "id": "hook_XXXX",
  "event": "order.paid",
  "data": {
    "id": "order_XXXX",
    "status": "paid",
    "amount": 35000,
    "installments": 3,
    "checkout": {
      "id": "chk_XXXX",
      "payment_url": "https://checkout.pagar.me/XXXX"
    }
  },
  "created_at": "2026-07-21T14:00:00Z"
}
```

> Esta fixture será substituída por dados reais do sandbox após validação técnica.
