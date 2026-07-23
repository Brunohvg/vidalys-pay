# Vidalys Pay

> Gerador de links de pagamento para vendedores

![Django](https://img.shields.io/badge/Django-5.2-092E20?style=flat&logo=django&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-17-4169E1?style=flat&logo=postgresql&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-24-2496ED?style=flat&logo=docker&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

## Visão Geral

O **Vidalys Pay** é uma aplicação interna para vendedores criarem links de pagamento via API do Pagar.me. O link é enviado automaticamente ao vendedor pelo WhatsApp usando a Evolution API, e o sistema acompanha os pagamentos via webhooks.

### Funcionalidades

- Criação de links de pagamento (1x, 2x, 3x sem juros)
- Emissão e acompanhamento de boletos empresariais por CNPJ
- Boletos com multa de 2% e juros de mora de 1% ao mês após o vencimento
- Consulta de CNPJ com autopreenchimento e revisão antes da emissão
- Envio automático via WhatsApp
- Acompanhamento em tempo real via webhooks
- Retenção seletiva de webhooks: eventos externos sem vínculo são descartados
- Histórico de transações
- Dashboard mobile-first (PWA)
- API REST para integrações (n8n)

## Arquitetura

```
┌─────────────────────────────────────────────────────────┐
│                    Coolify / Docker                      │
│  ┌──────────────┐    ┌──────────────┐                   │
│  │     web      │    │    worker    │                   │
│  │  (Gunicorn)  │    │  (outbox)    │                   │
│  └──────┬───────┘    └──────┬───────┘                   │
│         └─────────┬─────────┘                           │
└───────────────────┼─────────────────────────────────────┘
                    │
                    ▼
         ┌──────────────────┐
         │   PostgreSQL     │  (banco externo)
         └──────────────────┘
```

## Stack

- **Backend:** Django 5.2 LTS + Django REST Framework
- **Banco:** PostgreSQL 17 (externo)
- **Frontend:** Django Templates + HTMX + JavaScript
- **PWA:** Manifest + Service Worker
- **Containerização:** Docker Compose
- **Deploy:** Coolify

## Pré-requisitos

- Python 3.12+
- PostgreSQL 17+ (externo)
- Docker (opcional)
- Conta Pagar.me (sandbox ou produção)
- Evolution API externa

## Instalação

### 1. Clone o repositório

```bash
git clone https://github.com/SEU_USUARIO/vidalys-pay.git
cd vidalys-pay
```

### 2. Configure as variáveis de ambiente

```bash
cp .env.example .env
# Edite o .env com suas credenciais
```

### 3. Instale as dependências

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 4. Execute as migrations

```bash
python manage.py migrate
```

### 5. Crie um superusuário

```bash
python manage.py createsuperuser
```

### 6. Inicie o servidor

```bash
python manage.py runserver
```

Acesse: http://localhost:8000/admin/

### Com Docker

```bash
docker compose up --build
```

## Variáveis de Ambiente

| Variável | Descrição | Obrigatória |
|----------|-----------|-------------|
| `SECRET_KEY` | Chave secreta Django | Sim |
| `DATABASE_URL` | URL do PostgreSQL | Sim |
| `PAGARME_SECRET_KEY` | Chave Pagar.me | Sim |
| `PAGARME_WEBHOOK_BASIC_AUTH_USER` | Usuário Basic Auth webhook | Sim |
| `PAGARME_WEBHOOK_BASIC_AUTH_PASSWORD` | Senha forte do webhook | Sim |
| `CNPJ_LOOKUP_BASE_URL` | Endpoint HTTPS da consulta de CNPJ | Para boletos |
| `BOLETO_MANAGER_WHATSAPP_PHONES` | Gestores notificados, separados por vírgula | Não |
| `EVOLUTION_API_URL` | URL da Evolution API | Sim |
| `EVOLUTION_API_KEY` | Chave da Evolution API | Sim |
| `EVOLUTION_INSTANCE` | Nome da instância | Sim |
| `INVITATION_TOKEN_PEPPER` | Pepper para hash de convites | Sim |
| `API_KEY_PEPPER` | Pepper para hash de API keys | Sim |
| `WEBPUSH_VAPID_PUBLIC_KEY` | Chave pública VAPID (Web Push) | Para push |
| `WEBPUSH_VAPID_PRIVATE_KEY` | Chave privada VAPID; manter em segredo | Para push |
| `WEBPUSH_VAPID_SUBJECT` | Contato VAPID (`mailto:` ou URL HTTPS) | Não |

Veja `.env.example` para todas as variáveis.

### Webhooks Pagar.me

Eventos autenticados são correlacionados com boletos e links da Vidalys Pay.
Eventos próprios permanecem no banco para processamento e auditoria; eventos
sem boleto, link ou referência interna são descartados e aparecem apenas nos
logs como `Webhook externo descartado`. Consulte
[`docs/WEBHOOKS.md`](docs/WEBHOOKS.md) para retenção, diagnóstico e roteiro de
teste em produção.

## Estrutura do Projeto

```
vidalys-pay/
├── apps/
│   ├── core/                 # Configurações comuns, health, logging
│   ├── sellers/              # Vendedores, convites e sessões
│   ├── payment_links/        # Links e tentativas de pagamento
│   ├── boletos/              # Empresas, emissão, consulta e painel de boletos
│   ├── webhooks/             # Entrada e processamento de webhooks
│   ├── notifications/        # Mensagens, templates e outbox
│   ├── integrations/
│   │   ├── pagarme/          # Cliente HTTP Pagar.me
│   │   ├── evolution/        # Cliente HTTP Evolution
│   │   └── n8n/              # API keys para integrações
│   ├── audit/                # Trilha de auditoria
│   └── shipping/             # Reservado (sem funcionalidade)
├── config/                   # Settings Django
├── templates/                # Templates HTML
├── static/
│   ├── css/                  # Estilos
│   ├── js/                   # JavaScript
│   ├── brand/                # Logos e identidade
│   ├── favicons/             # Favicons
│   ├── pwa/                  # Ícones PWA
│   ├── ui-icons/             # Ícones SVG
│   └── social/               # Imagens OG
├── docker/                   # Docker entrypoint
├── tests/                    # Testes
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## API

### Endpoints

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| POST | `/api/v1/payment-links/` | Criar link |
| GET | `/api/v1/payment-links/` | Listar links |
| GET | `/api/v1/payment-links/{id}/` | Detalhar link |
| POST | `/api/v1/payment-links/{id}/resend/` | Reenviar link |
| POST | `/api/v1/webhooks/pagarme/` | Webhook Pagar.me |
| GET | `/api/v1/boletos/cnpj/{cnpj}/` | Consulta autenticada de CNPJ |
| POST | `/api/v1/freight/cep/` | Consulta autenticada de CEP |
| POST | `/api/v1/freight/calculate/` | Cálculo autenticado de frete |
| GET | `/health/` | Health check |
| GET | `/health/ready/` | Readiness check |

### Autenticação

- **Sessão do vendedor:** Cookie HttpOnly
- **API Key:** `Authorization: Bearer vly_live_xxxxx`

Consulte [`docs/API.md`](docs/API.md) para exemplos, autenticação, escopos,
idempotência e erros. O contrato OpenAPI 3.1 está em
[`docs/openapi.json`](docs/openapi.json).

## Deploy no Coolify

### Pré-requisitos

- PostgreSQL criado ou selecionado no Coolify
- Aplicação e banco na mesma rede interna (`coolify`)

### Passo a passo

1. **Configure o PostgreSQL** no Coolify e copie a URL interna de conexão (formato `postgresql://usuario:senha@host-interno:5432/nome-do-banco`)
2. **Conecte o repositório** ao Coolify e selecione **Docker Compose**
3. **Configure o domínio** no serviço `web`, porta `8000`
4. **Preencha as variáveis de ambiente** (veja tabela abaixo)
5. **Deploy**

Após o primeiro deploy, crie o superusuário:

```bash
docker compose exec web python manage.py createsuperuser
```

### Variáveis obrigatórias

| Variável | Descrição |
|----------|-----------|
| `SECRET_KEY` | Chave secreta Django (mín. 50 caracteres) |
| `DATABASE_URL` | URL interna do PostgreSQL (`postgresql://...`) |
| `ALLOWED_HOSTS` | Domínio da aplicação |
| `CSRF_TRUSTED_ORIGINS` | Origem HTTPS da aplicação |
| `APP_BASE_URL` | URL base da aplicação |
| `PAGARME_SECRET_KEY` | Chave de produção do Pagar.me |
| `PAGARME_WEBHOOK_BASIC_AUTH_USER` | Segredo Basic Auth para webhooks |
| `PAGARME_WEBHOOK_BASIC_AUTH_PASSWORD` | Senha forte e independente do webhook |
| `EVOLUTION_API_URL` | URL da Evolution API |
| `EVOLUTION_API_KEY` | Chave da Evolution API |
| `EVOLUTION_INSTANCE` | Nome da instância Evolution |
| `INVITATION_TOKEN_PEPPER` | Pepper para hash de convites |
| `API_KEY_PEPPER` | Pepper para hash de API keys |

### Variáveis opcionais

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `LOG_LEVEL` | `INFO` | Nível de log |
| `GUNICORN_WORKERS` | `3` | Workers do Gunicorn |
| `GUNICORN_TIMEOUT` | `60` | Timeout do Gunicorn (segundos) |
| `WORKER_POLL_SECONDS` | `3` | Intervalo de polling do worker |
| `MAX_NOTIFICATION_ATTEMPTS` | `5` | Tentativas máximas por notificação |
| `WEBPUSH_VAPID_SUBJECT` | `mailto:contato@vidalys.com.br` | Contato do responsável pelo Web Push |
| `DB_WAIT_MAX_ATTEMPTS` | `60` | Tentativas de espera pelo banco |
| `DB_WAIT_INTERVAL_SECONDS` | `2` | Intervalo entre tentativas |
| `DB_CONNECT_TIMEOUT_SECONDS` | `5` | Timeout de conexão com o banco |

### Verificando o deploy

```bash
# Logs do serviço web
docker compose logs -f web

# Logs do worker
docker compose logs -f worker

# Healthcheck
curl -s https://pay.vidalys.com.br/health/
# {"status":"ok"}

# Readiness (banco + migrations)
curl -s https://pay.vidalys.com.br/health/ready/
# {"status":"ready","database":"ok","migrations":"ok"}
```

### Importante

- **Nunca** use `localhost` como host do banco de dados
- **Nunca** defina `DB_HOST`, `DB_PORT`, `POSTGRES_USER` — use apenas `DATABASE_URL`
- O banco PostgreSQL é externo, gerenciado pelo Coolify
- A rede `coolify` deve ser externa (`external: true`) nos arquivos
  `docker-compose.yml` e `docker-compose.production.yml`
- A configuração de rede foi validada no ambiente atual; não alterne o arquivo
  Compose no Coolify sem confirmar que ambos continuam equivalentes

Veja `RUNBOOK.md` para procedimentos operacionais.
O fluxo completo de boletos está documentado em [`docs/BOLETOS.md`](docs/BOLETOS.md).
O fluxo e a retenção de webhooks estão documentados em
[`docs/WEBHOOKS.md`](docs/WEBHOOKS.md).

## Comandos Úteis

```bash
# Migrations
python manage.py migrate

# Superusuário
python manage.py createsuperuser

# Shell Django
python manage.py shell

# Testes
pytest -v

# Lint
ruff check .

# Worker (outbox)
python manage.py run_outbox_worker
```

## Licença

MIT License

## Contato

- **Admin:** Django Admin em `/admin/`
- **Suporte:** Abrir issue no GitHub
