# Testes e critérios de aceite

> Vidalys Pay — Documentação final v1.0 — 21 de julho de 2026

## 1. Estratégia

- testes unitários para regras;
- integração para banco e casos de uso;
- contrato para clientes externos com mocks realistas;
- API para autenticação/autorização;
- E2E mobile para jornada principal;
- smoke test após deploy.

## 2. Casos obrigatórios

### Acesso

- convite é aleatório e hash é armazenado;
- convite válido cria sessão;
- convite usado falha;
- convite expirado falha;
- dois acessos simultâneos geram uma sessão;
- novo convite revoga anterior;
- vendedor inativo não ativa;
- sessão revogada perde acesso;
- outro vendedor não acessa recurso alheio.

### Criação

- 1x, 2x e 3x aceitos;
- 0x, 4x e valores inválidos rejeitados;
- valor acima do limite rejeitado;
- telefone do cliente ausente é aceito;
- telefone informado é normalizado;
- resposta do Pagar.me salva ID e URL;
- erro confirmado não cria link ativo;
- timeout cria estado incerto e não duplica;
- mesma Idempotency-Key retorna mesma resposta;
- mesma chave com payload diferente retorna 409.

### WhatsApp

- link criado gera outbox;
- Evolution 201 marca enviado;
- timeout agenda retry;
- falha definitiva vira DEAD;
- falha não apaga link;
- reenvio deduplicado.

### Webhooks

- evento pago altera link para PAID;
- evento duplicado não notifica duas vezes;
- falha de tentativa mantém link ativo;
- estorno integral altera para REFUNDED;
- evento desconhecido é guardado como IGNORED;
- payload inválido não quebra worker;
- evento não autenticado não altera estado;
- ordem de eventos fora de sequência não regride estado final.

### PWA/UI

- formulário usável em 360 px;
- teclado numérico no valor;
- botão não duplica submit;
- link pode ser copiado sem WhatsApp;
- offline não enfileira cobrança;
- contraste e foco visível;
- instalação PWA válida.

## 3. Critérios de aceite por história

### CA-01 — Vendedor cadastrado

Dado um administrador autenticado, quando cria um vendedor e envia o convite, então existe um convite válido no banco e uma mensagem enfileirada para o WhatsApp correto.

### CA-02 — Acesso único

Dado um convite válido, quando aberto pela primeira vez, então o vendedor entra no app e o mesmo convite não funciona novamente.

### CA-03 — Link de 3x

Dado vendedor ativo e dentro do limite, quando cria R$ 300 em 3 parcelas, então o sistema cria checkout no Pagar.me, salva URL e mostra “3x sem juros”.

### CA-04 — Telefone opcional

Dado formulário sem telefone do cliente, quando enviado, então a criação segue normalmente.

### CA-05 — Falha de WhatsApp

Dado link criado e Evolution indisponível, então a tela mostra o link e oferece copiar/compartilhar, enquanto a mensagem fica para retry.

### CA-06 — Confirmação

Dado webhook válido de pagamento aprovado, então o link passa para pago uma única vez e o vendedor recebe uma notificação.

### CA-07 — Isolamento

Dado vendedor A, quando tenta consultar ID do vendedor B, então recebe 404 ou 403 sem revelar dados.

## 4. Qualidade mínima para produção

- cobertura mínima: 85% nos módulos de domínio e aplicação;
- zero falhas críticas do linter;
- migrations testadas em banco vazio e cópia recente anonimizada;
- OpenAPI validado;
- teste de restauração de backup;
- secrets scan no CI;
- dependências com vulnerabilidades críticas bloqueiam release;
- smoke test após deploy.

## 5. Checklist de homologação

- conta Pagar.me sandbox configurada;
- payload de 1x/2x/3x validado;
- link aceita somente uma venda paga;
- webhooks reais capturados e adicionados como fixtures sanitizadas;
- Evolution envia para número de teste;
- PWA instala em Android e iPhone;
- acesso revogado testado;
- Admin revisado com permissões;
- logs não contêm chaves ou dados de cartão;
- domínio e TLS válidos.

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
