# Pacote de documentação

> Vidalys Pay — Documentação final v1.0 — 21 de julho de 2026

## Objetivo deste pacote

Este diretório contém a especificação final para construir o **Vidalys Pay** — nome provisório e configurável —, uma aplicação interna da Vidalys para criação de links de pagamento do Pagar.me, envio automático ao vendedor pelo WhatsApp e acompanhamento do pagamento por webhooks.

O pacote foi escrito para permitir que o projeto seja iniciado por uma pessoa desenvolvedora ou por um agente de programação sem precisar reconstruir as decisões de produto.

## Decisões fechadas

- Backend em **Django 5.2 LTS** com Django REST Framework.
- PostgreSQL hospedado em container junto da aplicação.
- Deploy pelo Coolify usando Docker Compose.
- Evolution API já existente e consumida externamente.
- n8n já existente, externo e opcional.
- Aplicação mobile-first e instalável como PWA.
- Vendedor sem usuário e senha: convite único pelo WhatsApp que vira uma sessão revogável no aparelho.
- Administrador com autenticação padrão do Django Admin.
- Telefone do cliente opcional.
- Parcelamento permitido: 1x, 2x ou 3x sem juros.
- MVP focado em cartão de crédito via checkout hospedado do Pagar.me.
- Dados de cartão nunca passam pela aplicação.
- Calculadora de fretes apenas preparada arquiteturalmente; não implementada no MVP.

## Ordem de leitura

1. `01_PRD.md`
2. `02_ARQUITETURA.md`
3. `03_FLUXOS_E_ESTADOS.md`
4. `04_MODELO_DE_DADOS.md`
5. `05_SEGURANCA_E_ACESSO.md`
6. `06_CONTRATOS_API.md`
7. `07_INTEGRACOES.md`
8. `08_UI_UX_E_PWA.md`
9. `09_DEPLOY_COOLIFY.md`
10. `10_TESTES_E_ACEITE.md`
11. `11_ROADMAP.md`
12. `12_ADRS.md`
13. `13_PROMPT_MESTRE.md`
14. `openapi.yaml`
15. `docker-compose.example.yml`
16. `.env.example`

## Nome do produto

**Vidalys Pay** é um nome de trabalho. O nome visual e o `APP_NAME` devem ser configuráveis. A documentação não depende da aprovação definitiva do nome.

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
