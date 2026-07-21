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
- Envio automático via WhatsApp
- Acompanhamento em tempo real via webhooks
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
| `EVOLUTION_API_URL` | URL da Evolution API | Sim |
| `EVOLUTION_API_KEY` | Chave da Evolution API | Sim |
| `EVOLUTION_INSTANCE` | Nome da instância | Sim |
| `INVITATION_TOKEN_PEPPER` | Pepper para hash de convites | Sim |
| `API_KEY_PEPPER` | Pepper para hash de API keys | Sim |

Veja `.env.example` para todas as variáveis.

## Estrutura do Projeto

```
vidalys-pay/
├── apps/
│   ├── core/                 # Configurações comuns, health, logging
│   ├── sellers/              # Vendedores, convites e sessões
│   ├── payment_links/        # Links e tentativas de pagamento
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
| GET | `/health/` | Health check |
| GET | `/health/ready/` | Readiness check |

### Autenticação

- **Sessão do vendedor:** Cookie HttpOnly
- **API Key:** `Authorization: Bearer vly_live_xxxxx`

## Deploy no Coolify

1. Conecte o repositório ao Coolify
2. Selecione Docker Compose
3. Configure o domínio no serviço `web` porta 8000
4. Preencha as variáveis de ambiente
5. Deploy

Veja `RUNBOOK.md` para detalhes completos.

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
