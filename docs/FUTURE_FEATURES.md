# Próximas features — Vidalys Pay

Este documento registra as evoluções posteriores à entrega de push, lembretes,
API completa, cancelamento e segunda via de boletos. A ordem considera redução
de risco financeiro e ganho operacional.

## Entregas concluídas

- API autenticada para emissão, listagem, detalhe, situação, cancelamento,
  reenvio e segunda via.
- Escopos `boletos:read` e `boletos:write`, além de
  `notifications:write` para reenvio.
- Cancelamento restrito a boletos não pagos.
- Segunda via como nova cobrança ligada ao boleto original.

## 1. Conciliação automática com Pagar.me

Adicionar rotina periódica para consultar boletos em `CREATION_UNKNOWN`,
`CREATING` antigo e `PENDING` sem webhook recente. A fonte externa pode avançar
o estado local, mas nunca regredir um estado final.

Critérios de aceite:

- lotes pequenos, timeout e backoff;
- lock seguro para múltiplos workers;
- métricas de reconciliados, divergentes e falhos;
- dry-run operacional;
- testes para eventos atrasados e estados fora de ordem.

## 2. Exportação administrativa

Disponibilizar CSV e, se necessário, XLSX com filtros por período, vendedor,
empresa e status. A exportação é exclusiva de gestores e não adiciona métricas
à interface simples do vendedor.

Critérios de aceite:

- autorização administrativa;
- processamento em streaming para não consumir memória excessiva;
- datas e valores formatados sem perder precisão;
- proteção contra CSV injection;
- registro de auditoria da exportação.

## 3. Central de notificações

Criar uma visão administrativa de WhatsApp e push por boleto/link, exibindo
canal, destinatário mascarado, estado, tentativas e último erro sanitizado.

Critérios de aceite:

- filtros por agregado, canal, status e período;
- reenvio controlado com nova chave idempotente;
- sem exposição de credenciais ou payload técnico ao vendedor;
- identificação clara de `PENDING`, `PROCESSING`, `DONE` e `DEAD`.

## 4. Observabilidade e alertas

Monitorar worker parado, fila acumulada, itens `DEAD`, falhas de webhook,
indisponibilidade do Pagar.me/Evolution e boletos presos em estados incertos.

Critérios de aceite:

- health/readiness sem chamadas externas lentas;
- métricas e logs estruturados com `request_id`/aggregate id;
- limites e janelas configuráveis;
- alerta com procedimento correspondente no `RUNBOOK.md`;
- ausência de CNPJ, telefone, linha digitável e credenciais nos alertas.

## Regras gerais

- Toda mutação financeira precisa de idempotência.
- Estado final não pode regredir por evento atrasado.
- Chamadas externas não devem ocorrer dentro de locks de banco.
- Notificações devem usar `NotificationOutbox`.
- Features administrativas não devem poluir a experiência do vendedor.
- Cada fase exige documentação, testes e roteiro de homologação em produção.
