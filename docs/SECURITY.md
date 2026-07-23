# Segurança — Vidalys Pay

## Princípios

1. **Defesa em Profundidade** — Múltiplas camadas de proteção
2. **Privilégio Mínimo** — Cada componente tem apenas as permissões necessárias
3. **Fail-Secure** — Em caso de falha, o sistema rejeita而非 aceita
4. **Segredo Nunca em Código** — Chaves apenas em variáveis de ambiente

## Autenticação

### Vendedor (Passwordless)

O vendedor não possui senha. O acesso é via:

1. **Convite de Uso Único**
   - Token com pelo menos 256 bits
   - Armazenado apenas como SHA-256 + pepper
   - Validade padrão: 24 horas
   - Consumido atomicamente

2. **Sessão no Aparelho**
   - Cookie HttpOnly
   - Cookie Secure (produção)
   - SameSite=Lax
   - Validade: 30 dias
   - Armazenada no banco de dados

### API Key (Integrações)

```python
# Geração
raw_key = "vly_live_" + secrets.token_urlsafe(32)
key_hash = sha256(raw_key + pepper).hexdigest()

# Autenticação
Authorization: Bearer vly_live_xxxxx
```

- Chaves mostradas apenas uma vez
- Hash armazenado no banco
- Scopes: `payment_links:read`, `payment_links:write`, `notifications:write`

### Webhook Pagar.me

```python
# Autenticação
Authorization: Basic base64(PAGARME_WEBHOOK_BASIC_AUTH_USER:PAGARME_WEBHOOK_BASIC_AUTH_PASSWORD)
```

- Username: segredo configurado no painel Pagar.me
- Password: segredo forte e independente
- Eventos autenticados sem correlação são descartados sem copiar o payload para
  logs; eventos próprios permanecem para auditoria.

## Autorização

### Vendedor

```python
# Toda query filtra por seller_id da sessão
links = PaymentLink.objects.filter(seller=request.seller)
```

- Vendedor só acessa seus próprios recursos
- Vendedor só acessa os próprios boletos e nunca recebe o payload técnico
- IDs UUID não substituem autorização
- Vendedor não acessa Django Admin

### API Key

```python
# Scopes verificados por endpoint
permission_classes = [HasScope("payment_links:read")]
```

### Django Admin

- Apenas para administradores
- Senha forte obrigatória
- MFA recomendado

## Proteções HTTP

```python
# Configurações de segurança
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
REFERRER_POLICY = "strict-origin-when-cross-origin"
CSRF_COOKIE_HTTPONLY = True

# HTTPS (produção)
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
```

## Rate Limiting

```python
# Configuração
@rate_limit(max_requests=60, window_seconds=60)
def my_view(request):
    ...
```

- Chave por seller, API key ou IP
- Headers de resposta:
  - `X-RateLimit-Limit`
  - `X-RateLimit-Remaining`
  - `X-RateLimit-Reset`

## Criptografia

### Senhas e Tokens

```python
# Hash de tokens
import hashlib
stored_hash = hashlib.sha256((token + pepper).encode()).hexdigest()

# Verificação em tempo constante
import hmac
hmac.compare_digest(stored_hash, computed_hash)
```

### Dados em Trânsito

- HTTPS obrigatório em produção
- TLS 1.2+ recomendado

### Dados em Repouso

- Banco de dados com acesso restrito
- Backups criptografados
- Logs não contêm dados sensíveis

## Dados Sensíveis

### Nunca Armazenar

- Dados completos de cartão (PAN)
- CVV
- Chaves secretas em código ou logs

### Minimizar

- Telefone do cliente (opcional)
- Nome do cliente (opcional)
- IPs (retenção mínima)

### Mascarar no Admin

```python
@admin.register(Seller)
class SellerAdmin(admin.ModelAdmin):
    readonly_fields = ("whatsapp_phone",)  # Mascarado
```

## Webhook Seguro

### Autenticação

```python
def _validate_basic_auth(request) -> bool:
    auth_header = request.META.get("HTTP_AUTHORIZATION", "")
    if not auth_header.startswith("Basic "):
        return False
    
    encoded = auth_header[6:]
    decoded = base64.b64decode(encoded).decode("utf-8")
    username, password = decoded.split(":", 1)
    
    return username == expected_user and password == ""
```

### Idempotência

```python
# Verificar duplicidade
existing = WebhookEvent.objects.filter(
    provider_event_id=event_id
).first()

if existing:
    return JsonResponse({"duplicate": True})
```

A deduplicação persistente se aplica aos eventos correlacionados. Eventos
externos sem vínculo são excluídos e, em caso de reenvio, passam novamente pela
autenticação e pelo descarte. Veja [`WEBHOOKS.md`](WEBHOOKS.md).

### Validação de Payload

```python
# Verificar tamanho
if len(body) > MAX_BODY_SIZE:
    return JsonResponse({"error": "Payload too large"}, status=400)

# Verificar JSON válido
try:
    payload = json.loads(body)
except json.JSONDecodeError:
    return JsonResponse({"error": "Invalid JSON"}, status=400)
```

## Segredos

### Variáveis de Ambiente

| Segredo | Descrição |
|---------|-----------|
| `SECRET_KEY` | Chave secreta Django |
| `PAGARME_SECRET_KEY` | Chave da API Pagar.me |
| `EVOLUTION_API_KEY` | Chave da Evolution API |
| `INVITATION_TOKEN_PEPPER` | Pepper para hash de convites |
| `API_KEY_PEPPER` | Pepper para hash de API keys |

### Rotação

- `PAGARME_SECRET_KEY`: a cada 90 dias
- `EVOLUTION_API_KEY`: conforme política
- `INVITATION_TOKEN_PEPPER`: nunca rotacionar (quebra hashes)
- `API_KEY_PEPPER`: nunca rotacionar

## Auditoria

```python
# Logs de ações administrativas
class AuditLog(UUIDModel):
    actor = ForeignKey(User)
    action = CharField()
    entity_type = CharField()
    entity_id = CharField()
    previous_values = JSONField()
    new_values = JSONField()
    ip_address = GenericIPAddressField()
    created_at = DateTimeField(auto_now_add=True)
```

## LGPD

- Telefone do cliente opcional
- Nome do cliente opcional
- Informar finalidade no campo
- Não reutilizar contato para marketing
- Permitir exclusão/anonimização
- Auditar exportações

## Checklist de Segurança

- [ ] HTTPS obrigatório
- [ ] DEBUG=false em produção
- [ ] SECRET_KEY forte e única
- [ ] CSRF configurado
- [ ] Rate limiting ativo
- [ ] Logs não contêm dados sensíveis
- [ ] Webhook com autenticação
- [ ] API keys com scopes
- [ ] Sessões com HttpOnly/Secure
- [ ] Backups criptografados
- [ ] Rotação de chaves documentada
