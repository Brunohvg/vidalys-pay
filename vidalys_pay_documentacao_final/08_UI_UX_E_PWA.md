# UI, UX, identidade Vidalys e PWA

> Vidalys Pay — Documentação final v1.0 — 21 de julho de 2026

## 1. Direção visual

A aplicação deve parecer um produto SaaS da Vidalys, não uma tela genérica de formulário.

### Identidade já definida

- Graphite: `#0B1120`;
- Electric Blue: `#1263FF`;
- Cyan: `#00D1E6`;
- White: `#FFFFFF`;
- Light Gray: `#F3F5F9`;
- tipografia geométrica/limpa: preferência por Manrope ou Inter na web;
- símbolo: monograma V tecnológico associado a pulso, fluxo e conexão.

### Tokens

```css
:root {
  --vly-graphite: #0B1120;
  --vly-blue: #1263FF;
  --vly-cyan: #00D1E6;
  --vly-white: #FFFFFF;
  --vly-gray-50: #F3F5F9;
  --vly-gray-200: #D8DEE9;
  --vly-gray-600: #526071;
  --vly-success: #16A36A;
  --vly-warning: #D97706;
  --vly-danger: #D92D20;
  --vly-radius-sm: 10px;
  --vly-radius-md: 16px;
  --vly-radius-lg: 24px;
  --vly-shadow-card: 0 12px 30px rgba(11, 17, 32, .10);
}
```

Azul é a ação principal; ciano é acento, foco e detalhes do pulso. Evitar grandes áreas em ciano por contraste.

## 2. Princípios de experiência

- uso com uma mão;
- ação principal sempre visível;
- mínimo de digitação;
- valor em destaque;
- feedback imediato;
- nenhum bloqueio por falha do WhatsApp após o link existir;
- estados escritos em linguagem comercial, não termos técnicos;
- botões com pelo menos 44x44 px;
- contraste AA.

## 3. Navegação

Barra inferior:

- Novo link;
- Histórico;
- Perfil.

## 4. Wireframe — novo link

```text
┌─────────────────────────────────┐
│ VIDALYS PAY              ● online│
│ Olá, Bruno                      │
│                                 │
│ Novo link de pagamento          │
│                                 │
│ Valor                           │
│ ┌─────────────────────────────┐ │
│ │ R$ 350,00                   │ │
│ └─────────────────────────────┘ │
│                                 │
│ Parcelamento                    │
│ [ 1x ]   [ 2x ]   [ 3x ]       │
│                                 │
│ Pedido / referência *           │
│ [ PED-45892                  ]   │
│                                 │
│ Cliente (opcional)              │
│ [ Maria Silva                ]   │
│                                 │
│ Telefone (opcional)             │
│ [ (31) 99999-9999           ]   │
│ Usado somente para notificações │
│                                 │
│ [ Gerar link de pagamento ]     │
│                                 │
│  + Novo    Histórico    Perfil  │
└─────────────────────────────────┘
```

## 5. Tela de sucesso

- animação curta de pulso/V;
- valor e parcelas;
- URL não precisa aparecer inteira;
- botão primário “Compartilhar link”;
- botão secundário “Copiar”;
- status do WhatsApp: enviando, enviado ou falhou;
- “Criar outro link”.

## 6. Histórico

Cards com:

- referência;
- cliente quando houver;
- valor;
- parcelas;
- data;
- badge de status;
- menu para copiar, compartilhar e reenviar.

Filtros horizontais: Todos, Aguardando, Pagos, Expirados.

Falha recente de tentativa aparece como informação secundária, sem classificar o link ativo como permanentemente falho.

## 7. Perfil

- nome;
- WhatsApp cadastrado mascarado parcialmente;
- instalar aplicativo;
- sessões/aparelhos;
- sair deste aparelho;
- versão.

Não permitir editar número ou limite no perfil.

## 8. Estados e mensagens

### Carregando

Usar skeleton nos cards e spinner apenas em ações curtas.

### Vazio

“Você ainda não criou nenhum link.” + botão Novo link.

### Offline

- mostrar banner “Sem conexão”;
- histórico já carregado pode ser exibido do cache de shell, sem dados financeiros persistidos indevidamente;
- criação fica desabilitada;
- não enfileirar criação offline para evitar duplicidade financeira.

### Erro Pagar.me

“Não foi possível criar o link agora. Nenhuma cobrança foi confirmada. Tente novamente.”

### Resultado incerto

“Estamos confirmando se o link foi criado. Não tente novamente até a atualização desta tela.”

## 9. PWA

`manifest.webmanifest`:

```json
{
  "name": "Vidalys Pay",
  "short_name": "Vidalys Pay",
  "start_url": "/app/",
  "scope": "/app/",
  "display": "standalone",
  "background_color": "#F3F5F9",
  "theme_color": "#1263FF",
  "icons": [
    {"src":"/static/icons/icon-192.png","sizes":"192x192","type":"image/png"},
    {"src":"/static/icons/icon-512.png","sizes":"512x512","type":"image/png"},
    {"src":"/static/icons/icon-maskable-512.png","sizes":"512x512","type":"image/png","purpose":"maskable"}
  ]
}
```

Service worker deve cachear somente app shell, fontes, CSS, JS e página offline. Não cachear respostas autenticadas da API nem payloads de pagamento.

## 10. Componentes

- `AppHeader`;
- `MoneyInput`;
- `InstallmentsSelector`;
- `TextField`;
- `PrimaryButton`;
- `PaymentStatusBadge`;
- `PaymentLinkCard`;
- `InlineAlert`;
- `BottomNavigation`;
- `InstallPwaBanner`;
- `WhatsappDeliveryStatus`.

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
