# Boletos para CNPJ

## Escopo

O Vidalys Pay emite boletos exclusivamente para pessoas jurídicas com CNPJ. CPF
não é aceito. Gestores podem emitir e consultar boletos de qualquer vendedor
ativo; vendedores só operam e visualizam seus próprios boletos.

O Flowlog foi usado como referência funcional. A implementação final segue os
models, autenticação, cliente Pagar.me, endpoint de webhook, outbox e padrões
visuais já existentes no Vidalys Pay.

## Fluxo de emissão

1. O usuário informa um CNPJ.
2. O backend normaliza e valida os dígitos verificadores.
3. O endpoint autenticado consulta a BrasilAPI com timeout e rate limit.
4. O usuário revisa e completa empresa, endereço e cobrança.
5. Uma confirmação assinada impede alteração silenciosa dos dados revisados.
6. O Vidalys Pay cria uma tentativa local antes da chamada ao Pagar.me.
7. A mesma tentativa reutiliza a mesma chave de idempotência.
8. Order, charge, transaction, linha digitável, código de barras e PDF HTTPS
   são normalizados e persistidos.
9. As notificações são inseridas no outbox depois do commit.

Em timeout ou resultado incerto, o boleto fica em `CREATION_UNKNOWN`. Não se
deve emitir outro boleto automaticamente: aguarde o webhook ou faça a
reconciliação operacional.

## Rotas

| Perfil | Rota | Uso |
|---|---|---|
| Gestor | `/painel/boletos/` | Listagem, filtros e métricas globais |
| Gestor | `/painel/boletos/criar/` | Emissão para vendedor ativo |
| Gestor | `/painel/boletos/<uuid>/` | Detalhes e payload técnico |
| Vendedor | `/app/boletos/` | Listagem restrita ao vendedor |
| Vendedor | `/app/boletos/criar/` | Emissão para si próprio |
| Vendedor | `/app/boletos/<uuid>/` | Detalhes sem payload técnico |
| Interna | `/api/v1/boletos/cnpj/<cnpj>/` | Consulta autenticada de CNPJ |
| Pública autenticada | `/api/v1/webhooks/pagarme/` | Endpoint Pagar.me consolidado |

## Webhook e reconciliação

Não existe endpoint separado para boletos. O endpoint Pagar.me existente
persiste o evento bruto, valida Basic Auth e deduplica por `provider_event_id`.
O roteamento identifica o boleto nesta ordem:

1. `metadata.internal_boleto_id`;
2. `provider_charge_id`;
3. `provider_order_id`.

Eventos duplicados não alteram nem notificam novamente. Eventos fora de ordem
passam pela tabela de transições e não regridem estados finais. Eventos que
indicam explicitamente um boleto inexistente ficam como `FAILED` com
`BOLETO_NOT_FOUND` e podem ser reprocessados pelo Django Admin.

Eventos tratados incluem pagamento, falha, pendência, cancelamento,
cancelamento parcial, vencimento e estorno.

## Notificações

As mensagens usam `NotificationOutbox` e o worker existente. Não há chamada
direta do domínio de boletos à Evolution API. A chave de deduplicação contém
boleto, evento, tipo de destinatário e telefone, inclusive depois de uma
entrega concluída.

- Emissão: vendedor e cliente, quando há telefone no snapshot.
- Pagamento: vendedor; cliente e gestores conforme configuração.
- Falha: somente vendedor, sem detalhes técnicos.
- Cancelamento: vendedor; cliente e gestores conforme configuração.
- Vencimento, cancelamento parcial e estorno: vendedor.

## Configuração

```env
CNPJ_LOOKUP_BASE_URL=https://brasilapi.com.br/api/cnpj/v1
CNPJ_LOOKUP_CONNECT_TIMEOUT_SECONDS=5
CNPJ_LOOKUP_READ_TIMEOUT_SECONDS=10
CNPJ_LOOKUP_USER_AGENT=Vidalys-Pay-CNPJ/1.0

PAGARME_CREDENTIAL=sk_...
PAGARME_WEBHOOK_AUTH_MODE=basic
PAGARME_WEBHOOK_BASIC_AUTH_USER=...
PAGARME_WEBHOOK_BASIC_AUTH_PASSWORD=...

BOLETO_MANAGER_WHATSAPP_PHONES=5511999999999,5511888888888
BOLETO_NOTIFY_CUSTOMER_ON_PAID=false
BOLETO_NOTIFY_CUSTOMER_ON_CANCELED=false
```

Em produção, `CNPJ_LOOKUP_BASE_URL` e `APP_BASE_URL` devem usar HTTPS.

## Operação

### Boleto preso em confirmação pendente

1. Localize o boleto pelo UUID, order ou charge no Django Admin.
2. Consulte os eventos associados em **Webhooks**.
3. Confirme no Pagar.me se a order foi criada.
4. Reprocesse o evento correspondente no Admin.
5. Não crie outra tentativa com nova chave sem confirmar a inexistência da
   cobrança anterior.

### Webhook sem boleto

1. Filtre `WebhookEvent` por `BOLETO_NOT_FOUND`.
2. Confira `internal_boleto_id`, order e charge no payload técnico.
3. Corrija apenas a causa da correlação.
4. Use a ação **Reprocessar evento selecionado**.

### Notificação não entregue

1. Consulte `WhatsAppMessage` ligado ao boleto.
2. Consulte o item `NotificationOutbox` pela chave `boleto:<uuid>:...`.
3. Verifique o worker e as variáveis `EVOLUTION_*`.
4. Itens `DEAD` exigem análise da causa antes de novo envio.

## Segurança e dados

- Autorização e escopo são aplicados no backend.
- Somente gestor visualiza payload técnico do webhook.
- CNPJ e snapshot da empresa são persistidos para histórico.
- Credenciais, cabeçalhos de autenticação e linha digitável não são gravados
  em logs gerais.
- Apenas URLs HTTPS válidas retornadas pelo provedor são expostas como PDF.
- IDs, linha digitável e código de barras têm tipo e tamanho limitados.

## Verificação

```bash
python manage.py migrate --plan
python manage.py check
python manage.py makemigrations --check --dry-run
ruff check apps/boletos apps/webhooks apps/notifications
pytest -q
```
