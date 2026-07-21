# Segurança e acesso único

> Vidalys Pay — Documentação final v1.0 — 21 de julho de 2026

## 1. Modelo de autenticação

### Administrador

Usa usuário e senha do Django Admin. Exigir senha forte e preferencialmente MFA no provedor de acesso/rede ou solução administrativa futura.

### Vendedor

Não possui login e senha. O acesso combina:

1. convite secreto de uso único entregue ao WhatsApp cadastrado;
2. sessão persistente no banco e cookie seguro no dispositivo;
3. capacidade de revogação pelo administrador.

Isso é **passwordless**, não acesso público.

## 2. Geração do convite

Pseudocódigo:

```python
raw_token = secrets.token_urlsafe(32)  # pelo menos 256 bits antes da codificação
stored_hash = sha256(raw_token.encode()).hexdigest()
```

O banco recebe somente `stored_hash`. A mensagem recebe a URL com `raw_token`.

### Validade

- padrão: 24 horas;
- configurável por `INVITATION_EXPIRATION_HOURS`;
- usado uma vez;
- revogado ao gerar novo convite;
- inválido se o vendedor estiver inativo.

## 3. Consumo atômico

O backend abre transação, seleciona o convite com bloqueio, verifica hash em tempo constante, confirma validade e marca `used_at`. Duas requisições simultâneas não podem criar duas sessões.

Depois, redireciona com status 303 para `/app`, evitando manter o token na barra de endereço. Aplicar `Referrer-Policy: no-referrer` na rota de ativação.

## 4. Cookie e sessão

Configuração recomendada:

```text
SESSION_COOKIE_NAME=vidalys_seller_session
SESSION_COOKIE_HTTPONLY=true
SESSION_COOKIE_SECURE=true
SESSION_COOKIE_SAMESITE=Lax
SESSION_COOKIE_AGE=2592000
CSRF_COOKIE_SECURE=true
```

A sessão identifica `seller_id` e `seller_session_id`, nunca a chave do Pagar.me.

## 5. Perda ou troca do aparelho

O administrador executa “Revogar acessos e enviar novo convite”. O sistema:

1. revoga todas as `SellerSession` ativas;
2. apaga sessões Django correspondentes;
3. revoga convites anteriores;
4. gera convite novo;
5. enfileira WhatsApp.

## 6. Riscos do modelo

### Link encaminhado antes do primeiro uso

Quem abrir primeiro pode ativar a sessão. Mitigações:

- validade curta;
- envio apenas ao WhatsApp cadastrado;
- mensagem “não encaminhe”;
- mostrar nome do vendedor na ativação;
- notificar o vendedor após ativação;
- botão administrativo de revogação rápida.

Como evolução, pode-se exigir código curto enviado em uma segunda mensagem, sem criar senha permanente.

### Celular desbloqueado

A sessão segue acessível. O app deve esconder dados desnecessários e oferecer “Sair deste aparelho”. A política interna deve orientar bloqueio de tela.

## 7. Autorização

- toda query de vendedor filtra por `seller_id` da sessão;
- IDs UUID não substituem autorização;
- vendedor não acessa Django Admin;
- API Key possui scopes: `payment_links:read`, `payment_links:write`, `notifications:write`;
- cancelamento pode ser limitado ao Admin por configuração.

## 8. Proteções HTTP

- HTTPS obrigatório;
- HSTS após validação do domínio;
- CSP restritiva;
- `X-Content-Type-Options: nosniff`;
- `Referrer-Policy: strict-origin-when-cross-origin`, e `no-referrer` na ativação;
- frame ancestors `none`;
- CSRF nas views;
- CORS fechado por padrão;
- limite de body;
- rate limit por IP, sessão e API client.

## 9. Webhook seguro

Não inventar nome de header ou algoritmo. Implementar exatamente o mecanismo de assinatura/documentação disponível na conta e versão Pagar.me durante a fase de integração.

Defesa em profundidade:

- HTTPS;
- rota não previsível opcional;
- assinatura oficial quando disponível;
- persistência do body bruto;
- idempotência;
- validação de esquema;
- consulta ao Pagar.me para reconciliar eventos críticos ou duvidosos;
- nenhum efeito financeiro baseado apenas em campos não verificados.

## 10. Segredos

Segredos apenas no Coolify:

- `SECRET_KEY`;
- `PAGARME_SECRET_KEY`;
- `EVOLUTION_API_KEY`;
- `API_KEY_PEPPER`;
- `INVITATION_TOKEN_PEPPER` opcional.

Nunca imprimir headers de autenticação. Rotacionar chaves com procedimento documentado.

## 11. LGPD e minimização

- telefone do cliente opcional;
- nome do cliente opcional;
- informar finalidade no campo;
- não reutilizar contato para marketing sem base legal;
- permitir exclusão/anonymização conforme política;
- limitar visualização no Admin;
- auditar exportações e alterações críticas.

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
