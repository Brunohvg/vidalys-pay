# Roadmap e plano de implementação

> Vidalys Pay — Documentação final v1.0 — 21 de julho de 2026

## Princípio

Entregar fatias verticais pequenas, cada uma com migrations, testes e documentação. Não gerar todo o projeto em um único salto.

## Fase 0 — Descoberta técnica

- confirmar conta/ambiente Pagar.me;
- validar payload real de cartão e parcelamento 1–3 sem juros;
- validar mecanismo exato de assinatura de webhook;
- confirmar versão/endpoint da Evolution;
- aprovar nome provisório e domínio;
- obter SVG/logo e criar ícones PWA.

Saída: fixtures reais sanitizadas e decisões congeladas.

## Fase 1 — Fundação

- projeto Django 5.2 LTS;
- settings por ambiente;
- PostgreSQL;
- Docker/Compose;
- health/readiness;
- CI com Ruff/Pytest;
- logs estruturados;
- Admin básico.

## Fase 2 — Vendedores e acesso

- Seller;
- convites;
- sessão do aparelho;
- middleware/decorators;
- ações do Admin;
- template de convite;
- testes de concorrência e revogação.

## Fase 3 — PWA e interface base

- design tokens Vidalys;
- layout mobile;
- manifest/service worker;
- navegação;
- formulário sem integração real;
- histórico vazio/perfil.

## Fase 4 — Pagar.me

- cliente HTTP;
- caso de uso de criação;
- idempotência;
- PaymentLink;
- estados incertos/reconciliação;
- UI de sucesso e erro;
- sandbox.

## Fase 5 — Evolution e outbox

- WhatsAppMessage;
- NotificationOutbox;
- worker;
- templates;
- retries;
- ações de reenviar;
- status na UI.

## Fase 6 — Webhooks e tentativas

- WebhookEvent;
- PaymentAttempt;
- autenticidade;
- idempotência;
- mapeamentos;
- notificações de aprovação/falha/estorno;
- reprocessamento administrativo.

## Fase 7 — Histórico e API

- filtros e cursor;
- detalhes/timeline;
- API Key e scopes;
- OpenAPI;
- endpoints para n8n;
- rate limits.

## Fase 8 — Produção

- hardening;
- backup;
- alertas;
- testes E2E;
- deploy Coolify;
- runbook;
- homologação e go-live controlado.

## Pós-MVP

### 1. Frete

- CEP;
- fornecedores de cotação;
- soma no link;
- prazo e modalidade.

### 2. Notificação direta ao cliente

Opt-in, finalidade clara e LGPD.

### 3. PIX

Configuração por feature flag e UX específica.

### 4. Relatórios

Dashboard de conversão, tempo de pagamento e desempenho por vendedor.

### 5. Provedor de WhatsApp

Interface pronta para substituir Evolution pela API oficial sem alterar domínio.

## Definition of Done

Uma fase está pronta somente quando:

- código e migration revisados;
- testes passando;
- erros tratados;
- logs úteis;
- documentação atualizada;
- deploy em ambiente de teste;
- fluxo manual validado.

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
