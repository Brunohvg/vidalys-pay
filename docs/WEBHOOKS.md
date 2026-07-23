# Webhooks Pagar.me

Este documento é a referência operacional para recebimento, correlação,
retenção e diagnóstico dos webhooks do Pagar.me.

## Endpoint e autenticação

- Endpoint: `POST /api/v1/webhooks/pagarme/`
- `Content-Type`: `application/json`
- Autenticação: Basic Auth
- Limite padrão do corpo: 1 MiB (`PAGARME_WEBHOOK_MAX_BODY_BYTES`)

Credenciais:

```http
Authorization: Basic base64(PAGARME_WEBHOOK_BASIC_AUTH_USER:PAGARME_WEBHOOK_BASIC_AUTH_PASSWORD)
```

Em produção, `PAGARME_WEBHOOK_AUTH_MODE` deve permanecer como `basic`. O modo
`none` serve apenas para desenvolvimento controlado.

## Política de correlação e retenção

O endpoint autentica e normaliza o evento antes de encaminhá-lo ao processador.
O processador procura, nesta ordem:

1. boleto por metadado interno e identificadores do Pagar.me;
2. link por `internal_payment_link_id`;
3. link pelos IDs de payment link, checkout ou order;
4. link pela referência do pedido, somente quando a correspondência é única.

O resultado determina a retenção:

| Situação | Resultado no banco |
|---|---|
| Evento vinculado a boleto ou link e processado | Mantido como `PROCESSED` |
| Evento vinculado, mas redundante, fora de ordem ou desconhecido | Mantido como `IGNORED` |
| Evento vinculado com erro recuperável | Mantido como `FAILED` |
| Metadado interno aponta para recurso ainda ausente | Mantido para auditoria/reprocessamento |
| Nenhum boleto, link ou metadado interno da Vidalys Pay | Excluído; não permanece salvo |

Um evento externo descartado recebe HTTP 200 normalmente. Isso confirma o
recebimento ao Pagar.me e evita retries inúteis. Como não existe tombstone no
banco para eventos externos, uma nova entrega do mesmo evento será novamente
autenticada, verificada e descartada.

## Logs para diagnóstico

O logger é `apps.webhooks`. Pesquise por:

```text
Webhook externo descartado
Webhook correlacionado ignorado
Webhook persistido
Evento duplicado
Erro ao processar evento
```

O descarte registra apenas ID do evento, tipo e motivo. O payload externo não é
copiado para os logs.

Motivos atuais:

- `unknown_event_type`: tipo sem mapeamento;
- `configured_ignore`: evento configurado para não alterar estado;
- `payment_link_not_found`: nenhum link encontrado.

Exemplo no Coolify:

```bash
docker compose logs web | grep "Webhook externo descartado"
docker compose logs web | grep "Webhook correlacionado ignorado"
```

No Django Admin, eventos `IGNORED` sem boleto devem existir apenas quando houver
correlação com link ou referência interna. Eventos antigos, criados antes desta
política, não são removidos automaticamente.

## Respostas do endpoint

- `200`: evento aceito, inclusive duplicado ou externo descartado;
- `400`: JSON, tipo, tamanho ou `Content-Type` inválido;
- `401`: Basic Auth inválido;
- `405`: método diferente de POST.

Resposta normal:

```json
{
  "received": true,
  "event_id": "hook_xxx",
  "duplicate": false
}
```

O campo `duplicate` só pode ser `true` para eventos retidos. Eventos externos
descartados não permanecem no banco para deduplicação.

## Teste de produção

1. Configure a URL e o Basic Auth no painel Pagar.me.
2. Emita um link e um boleto de valor baixo, com referências identificáveis.
3. Confirme no Admin que os eventos próprios foram vinculados e processados.
4. Envie um payload autenticado com `order_id` inexistente.
5. Confirme HTTP 200 e o log `Webhook externo descartado`.
6. Confirme que o ID externo não aparece em `WebhookEvent`.
7. Reenvie um evento próprio e confirme idempotência/`duplicate`.

Nunca teste pagamento real sem alinhar previamente valor, destinatário,
cancelamento e conciliação financeira.

## Código relacionado

- Entrada e autenticação: `apps/webhooks/views.py`
- Normalização: `apps/webhooks/pagarme_payload.py`
- Correlação e retenção: `apps/webhooks/processor.py`
- Boletos: `apps/boletos/services/webhook_processing.py`
- Mapeamento de eventos: `apps/webhooks/event_mapping.py`
- Auditoria persistida: `apps/webhooks/models.py`
