# PRD — Product Requirements Document

> Vidalys Pay — Documentação final v1.0 — 21 de julho de 2026

## 1. Visão do produto

O Vidalys Pay reduz o tempo e os erros na criação manual de cobranças. O vendedor abre o aplicativo instalado no celular, informa o valor, as parcelas e uma referência, gera o link e o recebe imediatamente no próprio WhatsApp. O sistema acompanha os eventos do Pagar.me e mantém o histórico atualizado.

### Proposta de valor

> Criar, enviar e acompanhar um link de pagamento em poucos toques, sem login diário, sem copiar dados entre sistemas e sem expor dados de cartão.

## 2. Problema

O processo manual de geração e compartilhamento de links tende a criar:

- demora no atendimento;
- erros de valor, parcela ou destinatário;
- dificuldade para identificar qual vendedor criou a cobrança;
- ausência de histórico centralizado;
- dependência de conferência manual do pagamento;
- mensagens inconsistentes no WhatsApp.

## 3. Público

### Vendedor

Usa principalmente celular. Precisa gerar cobranças rapidamente, copiar/compartilhar o link e consultar o status.

### Administrador

Cadastra vendedores, controla acessos, consulta links, webhooks e erros de integração pelo Django Admin.

### Integrações futuras

O n8n poderá consultar ou criar recursos por API Key, mas não participa do caminho crítico do pagamento.

## 4. Objetivos do MVP

1. Cadastrar vendedores pelo Django Admin.
2. Enviar um convite de acesso único ao WhatsApp do vendedor.
3. Transformar o convite em sessão persistente e revogável no aparelho.
4. Criar links de cobrança pontual no Pagar.me.
5. Permitir 1x, 2x ou 3x sem juros.
6. Enviar o link criado ao WhatsApp do vendedor pela Evolution API.
7. Permitir copiar e compartilhar o link mesmo se o WhatsApp falhar.
8. Registrar e processar webhooks de pagamento.
9. Exibir histórico por vendedor.
10. Expor API REST autenticada para integrações futuras.
11. Implantar facilmente no Coolify.

## 5. Fora do escopo do MVP

- estoque e catálogo;
- ERP ou CRM;
- emissão de nota fiscal;
- split de pagamento;
- assinatura ou recorrência;
- captura de cartão dentro do sistema;
- cadastro público de vendedores;
- login e recuperação de senha para vendedores;
- envio obrigatório ao telefone do cliente;
- calculadora de fretes;
- dependência de n8n para operações essenciais;
- Evolution API dentro da stack.

## 6. Requisitos funcionais

### RF-01 — Cadastro de vendedor

O administrador deve cadastrar nome, WhatsApp, status e limite máximo por link.

### RF-02 — Convite de acesso

Ao salvar o vendedor ou executar uma ação administrativa, o sistema deve gerar um convite único, expirar convites anteriores e enviá-lo pelo WhatsApp.

### RF-03 — Primeiro acesso

Ao abrir um convite válido, o sistema deve consumi-lo atomicamente, criar sessão no aparelho e redirecionar para uma URL sem token.

### RF-04 — Revogação

O administrador deve revogar uma sessão específica ou todas as sessões de um vendedor.

### RF-05 — Criação do link

Campos obrigatórios:

- valor;
- parcelas;
- referência/pedido.

Campos opcionais:

- nome do cliente;
- telefone do cliente;
- descrição;
- validade do link.

### RF-06 — Parcelamento

Somente 1x, 2x ou 3x. O sistema deve configurar o checkout para que o custo não seja repassado ao comprador dentro das regras comerciais da conta Pagar.me.

### RF-07 — Envio ao vendedor

Depois da criação, o link deve ser enviado ao WhatsApp cadastrado do vendedor. Falha no WhatsApp não invalida o link.

### RF-08 — Histórico

O vendedor só vê links próprios, com filtros por status e ações de copiar, compartilhar e reenviar.

### RF-09 — Webhooks

O sistema deve registrar todos os eventos recebidos antes de processá-los, garantir idempotência e manter o payload bruto para auditoria.

### RF-10 — Administração

O Django Admin deve permitir vendedores, convites, sessões, links, tentativas, webhooks, mensagens, outbox e auditoria.

### RF-11 — API externa

A API para n8n usa API Key própria, escopos e idempotência. Sessão de vendedor nunca é usada como credencial de integração.

### RF-12 — PWA

Deve possuir manifest, service worker, ícones, modo standalone e experiência segura com conexão intermitente.

## 7. Requisitos não funcionais

- p95 de resposta das telas internas menor que 800 ms, excluindo terceiros;
- criação completa do link com retorno visual em até 8 segundos em condições normais;
- endpoint de webhook responde em até 2 segundos após persistir o evento;
- nenhuma chave secreta em código ou logs;
- valores financeiros em centavos inteiros;
- logs estruturados com `request_id` e `correlation_id`;
- disponibilidade alvo inicial de 99,5%;
- backups diários do PostgreSQL;
- acessibilidade mínima WCAG 2.1 AA nas telas principais;
- suporte aos navegadores móveis atuais de Android e iOS.

## 8. Regras de negócio

- RN-01: vendedor inativo não cria link e não inicia nova sessão.
- RN-02: link pertence permanentemente ao vendedor que o criou.
- RN-03: valor deve ser maior que zero e menor ou igual ao limite do vendedor.
- RN-04: telefone do cliente é opcional.
- RN-05: telefone do vendedor é obrigatório e normalizado em E.164.
- RN-06: uma referência é obrigatória e pode se repetir apenas quando houver intenção explícita; duplicidades rápidas devem ser bloqueadas por idempotência.
- RN-07: uma falha de tentativa de pagamento não significa que o link inteiro expirou. O link pode continuar ativo para nova tentativa.
- RN-08: link usa cobrança pontual, não assinatura.
- RN-09: o link deve aceitar no máximo uma sessão paga (`max_paid_sessions=1`), sujeito à confirmação final no contrato ativo do Pagar.me.
- RN-10: status interno nunca é substituído cegamente por texto externo; o evento é mapeado por regras versionadas.
- RN-11: a aplicação não armazena PAN, CVV ou dados completos do cartão.
- RN-12: o n8n não executa transições financeiras críticas.

## 9. Indicadores

- tempo mediano da abertura até o link criado;
- taxa de criação bem-sucedida no Pagar.me;
- taxa de entrega do WhatsApp;
- pagamentos aprovados por vendedor;
- links expirados sem pagamento;
- eventos de webhook com erro;
- reenvios manuais;
- convites expirados ou reutilizados.

## 10. Critério de sucesso do MVP

O MVP será considerado pronto quando um vendedor cadastrado conseguir ativar o acesso, instalar o PWA, criar uma cobrança em até 3 parcelas, receber o link no WhatsApp, observar o pagamento aprovado no histórico e o administrador conseguir auditar toda a sequência.

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
