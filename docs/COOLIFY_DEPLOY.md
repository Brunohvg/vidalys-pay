# Deploy no Coolify — Vidalys Pay

## Informações do Projeto

- **URL:** https://pay.vidalys.com.br
- **Repositório:** https://github.com/Brunohvg/vidalys-pay
- **Branch:** main

## Variáveis de Ambiente para o Coolify

Copie e cole cada variável no painel do Coolify.

### Grupo 1: Aplicação

| Variável | Valor |
|----------|-------|
| `SECRET_KEY` | `[GERE_UMA_CHAVE_FORTE_AQUI]` |
| `DEBUG` | `false` |
| `ALLOWED_HOSTS` | `pay.vidalys.com.br` |
| `CSRF_TRUSTED_ORIGINS` | `https://pay.vidalys.com.br` |
| `APP_BASE_URL` | `https://pay.vidalys.com.br` |
| `APP_NAME` | `Vidalys Pay` |

### Grupo 2: PostgreSQL (Banco Externo)

| Variável | Valor |
|----------|-------|
| `DATABASE_URL` | `postgresql://USUARIO:SENHA@HOST:5432/vidalys_pay` |

> **IMPORTANTE:** Substitua USUARIO, SENHA e HOST pelas credenciais do seu banco PostgreSQL externo.

### Grupo 3: Pagar.me

| Variável | Valor |
|----------|-------|
| `PAGARME_BASE_URL` | `https://api.pagar.me/core/v5` |
| `PAGARME_SECRET_KEY` | `sk_test_xxx` (sua chave) |
| `PAGARME_WEBHOOK_AUTH_MODE` | `basic` |
| `PAGARME_WEBHOOK_BASIC_AUTH_USER` | `[GERE_UMA_CHAVE_FORTE]` |
| `PAGARME_WEBHOOK_BASIC_AUTH_PASSWORD` | `[GERE_OUTRA_CHAVE_FORTE]` |

### Grupo 4: Evolution API

| Variável | Valor |
|----------|-------|
| `EVOLUTION_API_URL` | `https://api.lojabibelo.com.br` |
| `EVOLUTION_API_KEY` | `[SUA_CHAVE_EVOLUTION]` |
| `EVOLUTION_INSTANCE` | `[NOME_DA_INSTANCIA]` |

### Grupo 5: Acesso e API

| Variável | Valor |
|----------|-------|
| `INVITATION_EXPIRATION_HOURS` | `24` |
| `SELLER_SESSION_DAYS` | `30` |
| `INVITATION_TOKEN_PEPPER` | `[GERE_UMA_CHAVE_FORTE]` |
| `API_KEY_PEPPER` | `[GERE_OUTRA_CHAVE_FORTE]` |

### Grupo 6: Operação

| Variável | Valor |
|----------|-------|
| `LOG_LEVEL` | `INFO` |
| `GUNICORN_WORKERS` | `3` |
| `WORKER_POLL_SECONDS` | `3` |
| `MAX_NOTIFICATION_ATTEMPTS` | `5` |
| `WEBPUSH_VAPID_PUBLIC_KEY` | `[CHAVE_PUBLICA_VAPID]` |
| `WEBPUSH_VAPID_PRIVATE_KEY` | `[CHAVE_PRIVADA_VAPID]` (secret) |
| `WEBPUSH_VAPID_SUBJECT` | `mailto:contato@vidalys.com.br` |

## Passos para Deploy no Coolify

### 1. Criar Projeto

1. Acesse o Coolify
2. Crie um novo projeto
3. Nome: `vidalys-pay`

### 2. Conectar Repositório

1. Selecione "Docker Compose"
2. Conecte o repositório GitHub:
   - URL: `https://github.com/Brunohvg/vidalys-pay`
   - Branch: `main`

### 3. Configurar Serviços

O Coolify detectará automaticamente dois serviços:

1. **web** — Servidor principal (Gunicorn)
2. **worker** — Worker de notificações

### Rede validada neste ambiente

Tanto `docker-compose.yml` quanto `docker-compose.production.yml` conectam
`web` e `worker` à rede externa `coolify`. Essa configuração foi mantida porque
é a que permite resolver a Internal URL do PostgreSQL nesta instalação.

Não remova `networks: [coolify]` nem o bloco `external: true` sem uma migração
de rede planejada. Alternar o arquivo Compose é seguro somente enquanto essa
configuração permanecer idêntica nos dois arquivos.

### 4. Configurar Domínio

1. No serviço **web**, vá em "Networking"
2. Adicione o domínio: `pay.vidalys.com.br`
3. Ative HTTPS automático (Let's Encrypt)

### 5. Inserir Variáveis de Ambiente

1. No serviço **web**, vá em "Environment Variables"
2. Insira TODAS as variáveis listadas acima
3. Marque as seguintes como **Secret**:
   - `SECRET_KEY`
   - `DATABASE_URL`
   - `PAGARME_SECRET_KEY`
   - `PAGARME_WEBHOOK_BASIC_AUTH_USER`
   - `EVOLUTION_API_KEY`
   - `INVITATION_TOKEN_PEPPER`
   - `API_KEY_PEPPER`

### 6. Configurar Healthcheck

O `docker-compose.production.yml` já inclui healthcheck. Verifique se está configurado:

```yaml
healthcheck:
  test: ["CMD", "curl", "-fsS", "http://localhost:8000/health"]
  interval: 30s
  timeout: 5s
  retries: 5
  start_period: 30s
```

### 7. Deploy

1. Clique em "Deploy"
2. Aguarde o build completo (2-5 minutos)
3. Verifique os logs em "Logs"

### 8. Pós-Deploy

#### Criar Superusuário

```bash
# No terminal do Coolify ou via SSH
docker compose exec web python manage.py createsuperuser
```

#### Verificar Health

```bash
curl https://pay.vidalys.com.br/health/
# Resposta esperada: {"status": "ok"}

curl https://pay.vidalys.com.br/health/ready/
# Resposta esperada: {"status": "ready", "database": "ok", "migrations": "ok"}
```

#### Acessar Admin

- URL: https://pay.vidalys.com.br/admin/
- Login: superusuário criado acima

## Configurar Webhook no Pagar.me

1. Acesse o painel do Pagar.me
2. Vá em Desenvolvimento > Webhooks
3. Adicione um novo webhook:
   - **URL:** `https://pay.vidalys.com.br/api/v1/webhooks/pagarme/`
   - **Eventos:** `order.paid`, `order.payment_failed`, `charge.paid`, `charge.payment_failed`, `charge.refunded`
4. O **Basic Auth Username** deve ser o mesmo valor de `PAGARME_WEBHOOK_BASIC_AUTH_USER`

## Variáveis que Você Precisa Preencher

Antes do deploy, você precisa:

1. **Gerar SECRET_KEY forte:**
   ```bash
   python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
   ```

2. **Obter credenciais do PostgreSQL externo**

3. **Obter chave da API Pagar.me:**
   - Acesse https://id.pagar.me
   - Vá em Desenvolvimento > Chaves
   - Copie a **Chave Secreta** (sk_test_* ou sk_*)

4. **Obter chave da Evolution API:**
   - Acesse o painel da Evolution API
   - Copie a chave de API

5. **Obter nome da instância Evolution:**
   - Acesse o painel da Evolution API
   - Copie o nome da instância

6. **Gerar peppers:**
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

## Troubleshooting

### Erro 502 Bad Gateway

- Verificar se o Gunicorn está rodando
- Verificar logs do container web
- Verificar se as variáveis estão corretas

### Erro de Conexão com Banco

- Verificar se `DATABASE_URL` ainda é a Internal URL atual do PostgreSQL
- Confirmar que `web`, `worker` e PostgreSQL estão conectados à rede `coolify`
- Confirmar que o Compose selecionado contém `external: true`
- Verificar se o PostgreSQL está acessível e se não houve recriação do recurso

### Webhook não funciona

- Verificar `PAGARME_WEBHOOK_BASIC_AUTH_USER`
- Verificar logs do web
- Testar com curl

### WhatsApp não envia

- Verificar `EVOLUTION_API_URL`, `EVOLUTION_API_KEY`, `EVOLUTION_INSTANCE`
- Verificar outbox: `SELECT * FROM notifications_notificationoutbox WHERE status='DEAD'`
