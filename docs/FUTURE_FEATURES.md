# Próximas features — Vidalys Pay

Este documento registra as evoluções posteriores à entrega de push e lembretes
de boletos. A ordem considera redução de risco financeiro e ganho operacional.

## 1. API completa de boletos

Criar endpoints autenticados para emissão, listagem, detalhe, cancelamento,
reenvio e consulta de situação. Reutilizar os serviços de domínio existentes,
exigir `Idempotency-Key` nas mutações e manter escopo por vendedor.

Critérios de aceite:

- contrato OpenAPI e exemplos atualizados;
- API Key com escopos específicos de boletos;
- nenhuma possibilidade de acessar boleto de outro vendedor;
- respostas e erros no padrão da API atual;
- testes de autorização, idempotência e isolamento.

## 2. Cancelamento e segunda via

Permitir cancelamento apenas nos estados aceitos pelo Pagar.me. A segunda via
deve criar um novo boleto ligado ao anterior, preservando a trilha histórica e
usando nova idempotência.

Critérios de aceite:

- confirmação explícita antes de cancelar;
- status local alterado somente após confirmação do provedor ou webhook;
- relação entre boleto original e substituto;
- notificações deduplicadas;
- auditoria do ator, data e resposta do provedor.

## 3. Conciliação automática com Pagar.me

Adicionar rotina periódica para consultar boletos em `CREATION_UNKNOWN`,
`CREATING` antigo e `PENDING` sem webhook recente. A fonte externa pode avançar
o estado local, mas nunca regredir um estado final.

Critérios de aceite:

- lotes pequenos, timeout e backoff;
- lock seguro para múltiplos workers;
- métricas de reconciliados, divergentes e falhos;
- dry-run operacional;
- testes para eventos atrasados e estados fora de ordem.

## 4. Exportação administrativa

Disponibilizar CSV e, se necessário, XLSX com filtros por período, vendedor,
empresa e status. A exportação é exclusiva de gestores e não adiciona métricas
à interface simples do vendedor.

Critérios de aceite:

- autorização administrativa;
- processamento em streaming para não consumir memória excessiva;
- datas e valores formatados sem perder precisão;
- proteção contra CSV injection;
- registro de auditoria da exportação.

## 5. Central de notificações

Criar uma visão administrativa de WhatsApp e push por boleto/link, exibindo
canal, destinatário mascarado, estado, tentativas e último erro sanitizado.

Critérios de aceite:

- filtros por agregado, canal, status e período;
- reenvio controlado com nova chave idempotente;
- sem exposição de credenciais ou payload técnico ao vendedor;
- identificação clara de `PENDING`, `PROCESSING`, `DONE` e `DEAD`.

## 6. Observabilidade e alertas

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
