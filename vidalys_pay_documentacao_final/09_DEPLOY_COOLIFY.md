# Deploy no Coolify

> Vidalys Pay — Documentação final v1.0 — 21 de julho de 2026

## 1. Topologia

No mesmo projeto/stack:

- web Django;
- worker da mesma imagem;
- PostgreSQL.

Externos:

- Pagar.me;
- Evolution API;
- n8n.

## 2. Arquivos obrigatórios

- `Dockerfile`;
- `docker-compose.yml`;
- `.dockerignore`;
- `.env.example`;
- `docker/entrypoint.sh`;
- healthcheck;
- volume persistente do PostgreSQL.

## 3. Estratégia do Compose

O Compose é a fonte de verdade do deploy. O banco não publica porta no host. Apenas o serviço web recebe domínio pelo proxy do Coolify.

O arquivo `docker-compose.example.yml` acompanha este pacote.

## 4. Imagem

Requisitos:

- imagem Python slim;
- usuário não-root;
- dependências travadas;
- `collectstatic` no release/entrypoint;
- migrations controladas antes de iniciar web;
- Gunicorn ouvindo em `0.0.0.0:8000`;
- `curl` instalado para healthcheck;
- `PYTHONDONTWRITEBYTECODE=1`;
- `PYTHONUNBUFFERED=1`.

## 5. Migrations

Para um único web replica no MVP, o entrypoint pode aplicar migrations com lock consultivo no PostgreSQL. Em escala maior, migrar para comando de pré-deploy exclusivo.

Nunca executar várias migrations concorrentes sem lock.

## 6. Variáveis no Coolify

Marcar segredos/obrigatórias. O Compose pode usar `${VAR:?}` para impedir deploy incompleto.

Grupos:

### Django

- `SECRET_KEY`;
- `DEBUG=false`;
- `ALLOWED_HOSTS`;
- `CSRF_TRUSTED_ORIGINS`;
- `APP_BASE_URL`;
- `APP_NAME`;
- `DATABASE_URL`.

### Pagar.me

- `PAGARME_BASE_URL`;
- `PAGARME_SECRET_KEY`;
- `PAGARME_WEBHOOK_ENDPOINT_SECRET`;
- variável de assinatura, se exigida pelo mecanismo oficial.

### Evolution

- `EVOLUTION_API_URL`;
- `EVOLUTION_API_KEY`;
- `EVOLUTION_INSTANCE`.

### Acesso

- `INVITATION_EXPIRATION_HOURS=24`;
- `SELLER_SESSION_DAYS=30`;
- `INVITATION_TOKEN_PEPPER`;
- `API_KEY_PEPPER`.

### Operação

- `LOG_LEVEL=INFO`;
- `WORKER_POLL_SECONDS=3`;
- `MAX_NOTIFICATION_ATTEMPTS=5`.

## 7. Domínio e TLS

Sugestão:

`pay.vidalys.com.br` ou nome aprovado.

Configurar HTTPS automático, redirecionamento HTTP → HTTPS e, após validação, HSTS.

## 8. Healthchecks

Web:

```yaml
healthcheck:
  test: ["CMD", "curl", "-fsS", "http://localhost:8000/health"]
  interval: 30s
  timeout: 5s
  retries: 5
  start_period: 30s
```

PostgreSQL: `pg_isready`.

Worker: pode atualizar heartbeat no banco; o monitor operacional alerta se ficar antigo.

## 9. Backup

- backup automático diário;
- retenção mínima inicial de 7 diários + 4 semanais;
- cópia fora do mesmo disco/servidor;
- teste mensal de restauração;
- documentar RPO inicial de 24 h e RTO de 4 h.

## 10. Deploy

1. Conectar repositório Git ao Coolify.
2. Selecionar Docker Compose.
3. Configurar domínio no serviço `web` porta 8000.
4. Preencher variáveis.
5. Criar storage persistente do PostgreSQL.
6. Fazer deploy em sandbox.
7. Criar superusuário por comando no terminal.
8. Cadastrar vendedor de teste.
9. Testar convite, link, WhatsApp e webhook.
10. Só depois trocar Pagar.me para produção.

## 11. Rollback

- manter imagens/tag anterior;
- migrations devem ser backward-compatible quando possível;
- deploy em duas etapas para mudanças destrutivas;
- rollback de código não deve depender de rollback automático de banco.

## 12. Runbook rápido

### Link cria, WhatsApp não chega

Consultar outbox, WhatsAppMessage, conectividade e instância Evolution. Não recriar cobrança.

### Webhook não atualiza

Consultar WebhookEvent, autenticidade, mapeamento, ID externo e fila. Reprocessar evento pelo Admin com auditoria.

### “No available server”

Verificar `/health`, porta do Gunicorn e configuração de healthcheck/proxy no Coolify.

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
