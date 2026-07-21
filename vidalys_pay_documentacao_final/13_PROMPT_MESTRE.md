# Prompt mestre para agente de desenvolvimento

> Vidalys Pay — Documentação final v1.0 — 21 de julho de 2026

Você é o engenheiro responsável por implementar o **Vidalys Pay**, uma aplicação interna mobile-first para vendedores criarem links de pagamento do Pagar.me, receberem o link no próprio WhatsApp via Evolution API e acompanharem o pagamento por webhooks.

## Regras de trabalho

1. Leia todos os arquivos deste pacote antes de alterar código.
2. Trate `01_PRD.md` como fonte de requisitos e `12_ADRS.md` como decisões fechadas.
3. Não implemente toda a aplicação de uma vez.
4. Trabalhe uma fase por vez conforme `11_ROADMAP.md`.
5. Antes de cada fase, apresente objetivo, arquivos e critérios de aceite.
6. Ao terminar, rode lint, testes e mostre resultados.
7. Não altere decisões fechadas sem criar novo ADR.
8. Não invente campos do Pagar.me. Consulte o contrato vigente e isole o payload no adapter.
9. Nunca armazene ou registre dados completos de cartão, CVV ou chaves secretas.
10. Não inclua Evolution API, n8n ou Supabase no Docker Compose.

## Stack obrigatória

- Django 5.2 LTS;
- Django REST Framework;
- PostgreSQL;
- Django Templates;
- HTMX e JavaScript mínimo;
- PWA;
- Docker Compose;
- deploy no Coolify.

## Arquitetura obrigatória

- `web`, `worker` da mesma imagem e `db` PostgreSQL;
- outbox no PostgreSQL;
- adapters isolados para Pagar.me e Evolution;
- n8n apenas por API externa futura;
- módulos separados para sellers, payment_links, webhooks, notifications, integrations e audit;
- módulo shipping reservado, sem funcionalidade.

## Acesso

Administrador usa Django Admin. Vendedor não possui senha. O Admin gera convite de uso único enviado ao WhatsApp. O token tem pelo menos 256 bits, é armazenado em hash, expira, é consumido atomicamente e vira sessão HttpOnly/Secure revogável.

## Formulário

Obrigatórios: valor, parcelas de 1 a 3 e referência.  
Opcionais: nome, telefone do cliente, descrição e validade.

Telefone do cliente nunca deve ser exigido pelo domínio do MVP.

## Pagamentos

- cobrança pontual `type=order`;
- checkout hospedado;
- cartão de crédito no MVP;
- até 3x sem juros;
- valores em centavos;
- limite por vendedor;
- idempotência;
- no máximo uma sessão paga por link;
- timeout de criação tratado como resultado incerto, sem retry cego.

## Estados

PaymentLink: CREATING, CREATION_UNKNOWN, CREATION_ERROR, ACTIVE, PAID, CANCELED, EXPIRED, REFUNDED.

PaymentAttempt: PENDING, PROCESSING, PAID, FAILED, REFUNDED, CHARGEDBACK.

Uma tentativa falha não deve fechar o link automaticamente.

## WhatsApp

Após criar o link, salvar outbox. O worker chama:

`POST {EVOLUTION_API_URL}/message/sendText/{EVOLUTION_INSTANCE}`

com header `apikey`. Falha no WhatsApp não remove o link. Sempre permitir copiar e compartilhar.

## Webhooks

Persistir body bruto antes de processar. Implementar autenticidade exatamente conforme documentação/conta ativa, sem inventar headers. Garantir idempotência e não regredir estados por eventos fora de ordem.

## UI

Use a identidade Vidalys:

- #0B1120;
- #1263FF;
- #00D1E6;
- #FFFFFF;
- #F3F5F9;
- Manrope ou Inter;
- V/pulso tecnológico.

Mobile-first, botões grandes, valor destacado, navegação inferior e acessibilidade AA.

## Entrega inicial

Comece somente pela **Fase 0 e Fase 1** do roadmap:

1. registre as validações técnicas pendentes;
2. proponha estrutura de pastas;
3. crie projeto, configuração, Docker, PostgreSQL, health endpoints, lint, testes e CI;
4. não implemente ainda integração real com Pagar.me ou Evolution;
5. finalize com comandos de execução e evidência dos testes.

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
