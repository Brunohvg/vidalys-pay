# Runbook — Vidalys Pay

## Arquitetura

```
┌─────────────────────────────────────────────────────────┐
│                    Coolify / Docker                      │
│  ┌──────────────┐    ┌──────────────┐                   │
│  │     web      │    │    worker    │                   │
│  │  (Gunicorn)  │    │  (outbox)    │                   │
│  └──────┬───────┘    └──────┬───────┘                   │
│         │                   │                           │
│         └─────────┬─────────┘                           │
│                   │                                     │
└───────────────────┼─────────────────────────────────────┘
                    │
                    ▼
         ┌──────────────────┐
         │   PostgreSQL     │  (banco externo)
         │   (host:5432)    │
         └──────────────────┘
```

## Serviços

| Serviço | Comando | Porta | Descrição |
|---------|---------|-------|-----------|
| web | gunicorn | 8000 | API, admin, webhooks |
| worker | run_outbox_worker | - | Processa WhatsApp/push e agenda lembretes de boletos |

## Variáveis de Ambiente

### Obrigatórias

| Variável | Descrição |
|----------|-----------|
| SECRET_KEY | Chave secreta Django (mín. 50 chars) |
| DATABASE_URL | URL do PostgreSQL externo |
| ALLOWED_HOSTS | Domínios permitidos |
| CSRF_TRUSTED_ORIGINS | Origens CSRF |
| APP_BASE_URL | URL base da aplicação |
| PAGARME_SECRET_KEY | Chave Pagar.me |
| PAGARME_WEBHOOK_BASIC_AUTH_USER | Usuário Basic Auth webhook |
| PAGARME_WEBHOOK_BASIC_AUTH_PASSWORD | Senha forte do webhook |
| EVOLUTION_API_URL | URL da Evolution API |
| EVOLUTION_API_KEY | Chave da Evolution API |
| EVOLUTION_INSTANCE | Nome da instância Evolution |
| INVITATION_TOKEN_PEPPER | Pepper para hash de convites |
| API_KEY_PEPPER | Pepper para hash de API keys |

### Opcionais

| Variável | Default | Descrição |
|----------|---------|-----------|
| DEBUG | false | Modo debug |
| APP_NAME | Vidalys Pay | Nome da aplicação |
| LOG_LEVEL | INFO | Nível de log |
| GUNICORN_WORKERS | 3 | Workers do Gunicorn |
| WORKER_POLL_SECONDS | 3 | Intervalo do worker |
| MAX_NOTIFICATION_ATTEMPTS | 5 | Máximo de tentativas |
| WEBPUSH_VAPID_PUBLIC_KEY | vazio | Chave pública Web Push |
| WEBPUSH_VAPID_PRIVATE_KEY | vazio | Chave privada Web Push (secret) |
| WEBPUSH_VAPID_SUBJECT | mailto:contato@vidalys.com.br | Contato VAPID |
| INVITATION_EXPIRATION_HOURS | 24 | Validade do convite |
| SELLER_SESSION_DAYS | 30 | Validade da sessão |
| CNPJ_LOOKUP_BASE_URL | BrasilAPI | Endpoint HTTPS de consulta de CNPJ |
| BOLETO_MANAGER_WHATSAPP_PHONES | vazio | Telefones de gestores separados por vírgula |
| BOLETO_NOTIFY_CUSTOMER_ON_PAID | false | Confirma pagamento ao cliente |
| BOLETO_NOTIFY_CUSTOMER_ON_CANCELED | false | Informa cancelamento ao cliente |
| BOLETO_REMINDERS_ENABLED | true | Habilita a varredura de vencimentos |
| BOLETO_REMINDER_DAYS | 3,0,-1 | Marcos: antes, no dia e depois do vencimento |
| BOLETO_REMINDER_SCAN_SECONDS | 3600 | Intervalo mínimo entre varreduras |
| BOLETO_REMINDER_TIME_ZONE | America/Sao_Paulo | Fuso usado para comparar datas |
| BOLETO_REMINDER_WHATSAPP_ENABLED | true | Envia lembrete ao vendedor por WhatsApp |
| BOLETO_REMINDER_NOTIFY_CUSTOMER | false | Envia lembrete ao cliente; requer autorização |

## Comandos

### Migrations

```bash
docker compose exec web python manage.py migrate
```

### Superusuário

```bash
docker compose exec web python manage.py createsuperuser
```

### Collectstatic

```bash
docker compose exec web python manage.py collectstatic --noinput
```

### Logs

```bash
# Web
docker compose logs -f web

# Worker
docker compose logs -f worker

# Todos
docker compose logs -f
```

### Shell Django

```bash
docker compose exec web python manage.py shell
```

## Problemas Comuns

### "No available server"

**Causa:** Gunicorn não está respondendo.

**Solução:**
```bash
docker compose restart web
docker compose logs web --tail=50
```

### Link criado, WhatsApp não chega

**Causa:** Evolution API indisponível ou instância errada.

**Verificar:**
1. Status da Evolution API
2. Variáveis EVOLUTION_*
3. Outbox: `SELECT * FROM notifications_notificationoutbox WHERE status='DEAD'`

**Solução:** Reenviar pelo admin ou ajustar configuração.

### Webhook não atualiza status

**Causa:** Autenticação falhou ou evento não mapeado.

**Verificar:**
1. `SELECT * FROM webhooks_webhookevent ORDER BY received_at DESC LIMIT 10`
2. Campo `authenticity_status` e `processing_status`
3. Logs do serviço `web`
4. Mensagens `Webhook correlacionado ignorado` e `Erro ao processar evento`

**Solução:** Reprocessar pelo admin → Webhooks → Selecionar → Reprocessar evento.

Para boletos em `CREATION_UNKNOWN`, eventos com `BOLETO_NOT_FOUND` e histórico
de notificações, consulte o procedimento detalhado em `docs/BOLETOS.md`.

Se o evento não estiver no banco, procure `Webhook externo descartado` nos logs.
Isso indica que não havia boleto, link nem referência interna da Vidalys Pay e,
portanto, o evento foi removido intencionalmente. A política e o roteiro de teste
estão em `docs/WEBHOOKS.md`.

### Erro de migrations

**Causa:** Migrations pendentes ou conflito.

**Solução:**
```bash
docker compose exec web python manage.py showmigrations
docker compose exec web python manage.py migrate --plan
```

### Banco externo inacessível

**Causa:** Firewall, credentials ou URL incorreta.

**Verificar:**
```bash
docker compose exec web python manage.py dbshell
```

## Backup

### Banco externo

O banco PostgreSQL roda externamente. Configure backup automático no provedor:

- **Retenção mínima:** 7 diários + 4 semanais
- **Cópia fora do mesmo disco/servidor**
- **Teste mensal de restauração**
- **RPO:** 24h | **RTO:** 4h

### Comando de backup manual

```bash
pg_dump -h HOST -U USER -d DATABASE -F c -f backup_$(date +%Y%m%d).dump
```

### Restauração

```bash
pg_restore -h HOST -U USER -d DATABASE -c backup_20260721.dump
```

## Monitoramento

### Health check

```bash
curl -s https://pay.vidalys.com.br/health/
# {"status": "ok"}

curl -s https://pay.vidalys.com.br/health/ready/
# {"status": "ready", "database": "ok", "migrations": "ok"}
```

### Métricas

- Tempo de resposta das telas (< 800ms p95)
- Taxa de criação de links
- Taxa de emissão e pagamento de boletos
- Boletos em `CREATION_UNKNOWN`
- Taxa de entrega WhatsApp
- Eventos de webhook com erro
- Itens DEAD no outbox

## Deploy

### Contrato de rede do Coolify

O ambiente atual usa a rede externa `coolify`. Os dois arquivos de produção,
`docker-compose.yml` e `docker-compose.production.yml`, devem manter:

```yaml
services:
  web:
    networks:
      - coolify
  worker:
    networks:
      - coolify

networks:
  coolify:
    external: true
```

Se o deploy parar em `failed to resolve host`, confirme primeiro o arquivo
Compose selecionado e a presença dessa rede. Não troque para rede gerenciada
sem validar previamente a resolução da Internal URL do PostgreSQL.

### Setup inicial (Coolify)

1. Conectar repositório Git
2. Selecionar Docker Compose
3. Configurar domínio no serviço `web` porta 8000
4. Preencher variáveis de ambiente
5. Deploy
6. Criar superusuário
7. Cadastrar vendedor de teste
8. Testar fluxo completo

### Deploy de atualização

```bash
git push origin main
# Coolify detecta e faz deploy automático
```

### Rollback

1. Manter imagem/tag anterior
2. No Coolify, selecionar tag anterior
3. Deploy

## Segurança

### Checklist

- [ ] HTTPS obrigatório
- [ ] SECRET_KEY forte e secreta
- [ ] DEBUG=false em produção
- [ ] CSRF configurado
- [ ] Rate limiting ativo
- [ ] Logs não contêm dados sensíveis
- [ ] Webhook com autenticação
- [ ] API keys com scopes
- [ ] Sessões com HttpOnly/Secure

### Rotação de chaves

1. PAGARME_SECRET_KEY: a cada 90 dias
2. EVOLUTION_API_KEY: conforme política
3. API_KEY_PEPPER: nunca rotacionar (quebra hashes)
4. INVITATION_TOKEN_PEPPER: nunca rotacionar

## Contato

- **Admin:** Django Admin em `/admin/`
- **Logs:** CloudWatch/ Loki (conforme setup)
- **Emergências:** Verificar status dos serviços primeiro
