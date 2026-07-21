# ADRs — Decisões arquiteturais

> Vidalys Pay — Documentação final v1.0 — 21 de julho de 2026

## ADR-001 — Django em vez de Go

**Status:** aceito.  
**Decisão:** Django 5.2 LTS.  
**Motivo:** velocidade, conhecimento existente, Admin, segurança e ecossistema.  
**Consequência:** desempenho suficiente para o escopo; otimizar apenas com dados reais.

## ADR-002 — PostgreSQL próprio

**Status:** aceito.  
**Decisão:** PostgreSQL em container/serviço persistente no Coolify, sem Supabase.  
**Consequência:** controle total e responsabilidade por backup/restore.

## ADR-003 — Acesso passwordless por convite

**Status:** aceito.  
**Decisão:** convite único via WhatsApp que vira sessão revogável.  
**Alternativa rejeitada:** link permanente por vendedor, por risco de vazamento.  
**Risco:** primeiro uso por terceiro se mensagem for encaminhada; mitigado por validade e revogação.

## ADR-004 — Telefone do cliente opcional

**Status:** aceito.  
**Motivo:** reduzir atrito; o checkout coleta dados necessários.  
**Consequência:** notificações diretas ao cliente só quando o telefone existir e houver finalidade adequada.

## ADR-005 — Evolution externa

**Status:** aceito.  
**Decisão:** consumir HTTP; não incluir na stack.  
**Consequência:** integração isolada e tolerância a indisponibilidade.

## ADR-006 — n8n externo e não crítico

**Status:** aceito.  
**Decisão:** API pronta para futuro; fluxo principal independente.

## ADR-007 — Outbox no PostgreSQL

**Status:** aceito.  
**Motivo:** confiabilidade sem Redis/Celery.  
**Consequência:** worker da mesma imagem e consultas cuidadosas com locks.

## ADR-008 — Checkout hospedado

**Status:** aceito.  
**Decisão:** cartão é preenchido no Pagar.me.  
**Consequência:** menor escopo PCI e nenhum dado de cartão no Vidalys Pay.

## ADR-009 — Link e tentativa são entidades separadas

**Status:** aceito.  
**Motivo:** uma tentativa pode falhar e o link continuar ativo.  
**Consequência:** status comercial correto e melhor auditoria.

## ADR-010 — UI server-rendered com HTMX

**Status:** aceito.  
**Motivo:** simplicidade e velocidade sem SPA JavaScript pesada.  
**Consequência:** endpoints JSON continuam disponíveis para integrações.

## ADR-011 — Identidade Vidalys

**Status:** aceito.  
**Tokens:** Graphite #0B1120, Electric Blue #1263FF, Cyan #00D1E6, White #FFFFFF e Light Gray #F3F5F9.  
**Tipografia:** Manrope/Inter.  
**Símbolo:** V tecnológico/pulso.

## ADR-012 — Calculadora de fretes fora do MVP

**Status:** aceito.  
**Decisão:** reservar módulo e interface, sem implementar fornecedor.

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
