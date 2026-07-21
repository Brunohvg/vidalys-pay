# Testes — Vidalys Pay

## Estratégia

O projeto utiliza uma combinação de:

- **Testes Unitários** — Regras de negócio isoladas
- **Testes de Integração** — Interação com banco de dados
- **Testes de API** — Endpoints REST
- **Testes de UI** — Formulários e fluxos

## Configuração

### Pytest

```ini
[tool.pytest.ini_options]
DJANGO_SETTINGS_MODULE = "config.settings.development"
pythonpath = ["."]
addopts = "--strict-markers -v"
markers = [
    "slow: marks tests as slow",
    "integration: marks tests requiring database",
]
```

### Cobertura

```ini
[tool.coverage.run]
source = ["apps", "config"]
omit = ["*/tests/*", "*/migrations/*"]

[tool.coverage.report]
fail_under = 80
show_missing = true
```

## Executando Testes

```bash
# Todos os testes
pytest

# Com verbose
pytest -v

# Com cobertura
pytest --cov=apps --cov-report=html

# Testes específicos
pytest tests/test_sellers_services.py -v

# Apenas testes marcados
pytest -m "integration"
```

## Estrutura de Testes

```
tests/
├── __init__.py
├── conftest.py              # Fixtures compartilhadas
├── test_health.py           # Health endpoints
├── test_sellers_models.py   # Modelos de vendedores
├── test_sellers_services.py # Serviços de vendedores
└── test_payment_links_models.py  # Modelos de links
```

## Fixtures

### conftest.py

```python
import pytest
from django.test import RequestFactory

@pytest.fixture
def request_factory():
    return RequestFactory()
```

### Fixtures de Banco

```python
@pytest.fixture
def seller(db):
    return Seller.objects.create(
        name="Bruno Vendas",
        whatsapp_phone="+5531999999999",
        max_payment_amount_cents=1000000,
        is_active=True,
    )
```

## Testes de Vendedores

### Geração de Convite

```python
def test_generate_invitation_creates_token(seller):
    invitation, raw_token = generate_invitation(seller=seller)
    
    assert invitation.pk is not None
    assert len(raw_token) >= 40  # 256 bits
    assert invitation.seller == seller
    assert invitation.used_at is None
```

### Consumo de Convite

```python
def test_consume_invitation_success(seller):
    _, raw_token = generate_invitation(seller=seller)
    
    session = consume_invitation(raw_token=raw_token)
    
    assert session is not None
    assert session.seller == seller
```

### Concorrência

```python
def test_concurrent_consumption_only_one_session(seller):
    _, raw_token = generate_invitation(seller=seller)
    
    session1 = consume_invitation(raw_token=raw_token)
    session2 = consume_invitation(raw_token=raw_token)
    
    # Apenas uma deve ter sucesso
    assert (session1 is not None) != (session2 is not None)
    assert SellerSession.objects.filter(seller=seller).count() == 1
```

### Revogação

```python
def test_revoke_all_sessions(seller):
    # Criar duas sessões
    _, raw_token1 = generate_invitation(seller=seller)
    consume_invitation(raw_token=raw_token1)
    
    _, raw_token2 = generate_invitation(seller=seller)
    consume_invitation(raw_token=raw_token2)
    
    count = revoke_all_sessions(seller=seller)
    
    assert count == 2
    assert SellerSession.objects.filter(
        seller=seller, revoked_at__isnull=True
    ).count() == 0
```

## Testes de Health

```python
def test_health_returns_ok():
    client = Client()
    response = client.get("/health/")
    
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_ready_returns_ok():
    client = Client()
    response = client.get("/health/ready/")
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["database"] == "ok"
```

## Testes de Modelos

### PaymentLink

```python
def test_payment_link_creation():
    seller = Seller.objects.create(
        name="Test Seller",
        whatsapp_phone="+5531999999999",
        max_payment_amount_cents=1000000,
    )
    link = PaymentLink.objects.create(
        seller=seller,
        reference="PED-001",
        amount_cents=35000,
        installments=3,
        idempotency_key="test-key-001",
    )
    
    assert link.pk is not None
    assert link.status == PaymentLinkStatus.CREATING
    assert link.installments == 3
```

## Rodando com Docker

```bash
# Executar testes no container
docker compose exec web pytest -v

# Com cobertura
docker compose exec web pytest --cov=apps
```

## CI/CD

### GitHub Actions

```yaml
test:
  runs-on: ubuntu-latest
  services:
    postgres:
      image: postgres:17-alpine
      env:
        POSTGRES_DB: vidalys_pay_test
        POSTGRES_USER: vidalys_pay_test
        POSTGRES_PASSWORD: test_password
      ports:
        - 5432:5432
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with:
        python-version: "3.12"
    - run: pip install -r requirements-dev.txt
    - run: pytest --cov=apps --cov-report=xml -v
```

## Qualidade Mínima

- Cobertura mínima: 85% nos módulos de domínio
- Zero falhas críticas do linter
- Migrations testadas em banco vazio
- OpenAPI validado
- Secrets scan no CI
- Dependências com vulnerabilidades críticas bloqueiam release
