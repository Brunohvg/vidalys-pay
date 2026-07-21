# PROMPT PRINCIPAL — CORREÇÃO COMPLETA DO APP VIDALYS PAY

Você atuará como **designer de produto, especialista em UI/UX mobile-first e desenvolvedor frontend sênior** para revisar e corrigir visualmente uma aplicação já existente chamada **Vidalys Pay**.

O Vidalys Pay é um sistema interno para vendedores criarem links de pagamento através da API do Pagar.me. Após a criação, o link é enviado ao vendedor pelo WhatsApp usando uma Evolution API externa. O sistema recebe webhooks do Pagar.me para atualizar pagamentos aprovados, pendentes, recusados, cancelados, expirados e reembolsados.

## REGRA PRINCIPAL

A aplicação já existe e possui regras de negócio, banco de dados, integrações, rotas, formulários e processamento de webhooks.

**Não reconstrua o backend e não substitua a arquitetura existente.**

Seu trabalho é:

1. analisar a interface atual;
2. corrigir problemas visuais e de usabilidade;
3. implementar a identidade Vidalys Pay;
4. organizar os componentes visuais;
5. melhorar a responsividade;
6. padronizar a tipografia;
7. aplicar os ativos de marca nos lugares corretos;
8. preservar integralmente as funcionalidades existentes.

Não remova, renomeie ou altere rotas, campos, IDs, nomes enviados ao backend, ações de formulário, endpoints, requisições, integrações ou regras de negócio sem necessidade técnica comprovada.

---

# 1. ARQUIVOS VISUAIS DE REFERÊNCIA

Utilize os seguintes arquivos como referência obrigatória:

- `01_identidade_visual_vidalys_pay.png`
- `02_icones_favicon_exportacao_vidalys_pay.png`
- `03_design_system_vidalys_pay.png`
- `04_guia_implementacao_handoff_vidalys_pay.png`

Esses arquivos definem:

- identidade da marca;
- logotipo;
- ícone reduzido;
- favicon;
- cores;
- estilo dos componentes;
- comportamento visual esperado;
- aplicação dos ativos na interface.

Não copie textos fictícios, valores demonstrativos ou funcionalidades que aparecem apenas como exemplos nos guias. Use os dados e funcionalidades reais da aplicação existente.

---

# 2. OBJETIVO VISUAL

Transformar a interface atual em um produto com aparência profissional, clara, confiável e pronta para produção.

O resultado deve transmitir:

- segurança;
- tecnologia;
- rapidez;
- controle;
- simplicidade;
- confiança;
- identidade própria da Vidalys.

O aplicativo não pode parecer:

- painel administrativo genérico;
- template Bootstrap sem personalização;
- formulário antigo;
- projeto escolar;
- cópia visual de banco ou fintech existente;
- interface carregada de efeitos e cores.

---

# 3. TIPOGRAFIA OBRIGATÓRIA

Utilize **Inter** como fonte principal de toda a aplicação.

Não misture fontes diferentes sem justificativa.

Configuração recomendada:

```css
:root {
  --font-sans: "Inter", ui-sans-serif, system-ui, -apple-system,
    BlinkMacSystemFont, "Segoe UI", sans-serif;
}

html,
body,
button,
input,
select,
textarea {
  font-family: var(--font-sans);
}
```

## Pesos permitidos

- 400 — texto comum;
- 500 — labels, navegação e textos de apoio importantes;
- 600 — botões, subtítulos e títulos de cards;
- 700 — títulos principais e valores de destaque.

Evite usar peso 700 em excesso.

## Escala tipográfica

```css
:root {
  --text-xs: 0.75rem;       /* 12px */
  --text-sm: 0.875rem;      /* 14px */
  --text-base: 1rem;        /* 16px */
  --text-lg: 1.125rem;      /* 18px */
  --text-xl: 1.25rem;       /* 20px */
  --text-2xl: 1.5rem;       /* 24px */
  --text-3xl: 1.875rem;     /* 30px */
}
```

## Aplicação da tipografia

### Título principal da página

- tamanho: 24px no mobile;
- tamanho: 30px no desktop;
- peso: 700;
- line-height: 1.2;
- cor: azul profundo.

### Subtítulo ou descrição da página

- tamanho: 14px ou 16px;
- peso: 400;
- line-height: 1.5;
- cor: cinza médio.

### Títulos de cards

- tamanho: 14px a 16px;
- peso: 600;
- cor: azul profundo.

### Valores financeiros

- usar números tabulares quando disponível;
- peso: 700;
- tamanho adequado ao espaço;
- nunca quebrar valor monetário em duas linhas.

```css
.amount,
.currency-value {
  font-variant-numeric: tabular-nums;
}
```

### Labels de campos

- tamanho: 14px;
- peso: 500;
- cor: cinza escuro;
- espaçamento inferior consistente.

### Texto de ajuda e validação

- tamanho: 12px ou 14px;
- peso: 400;
- line-height: 1.4;

### Botões

- tamanho: 14px ou 16px;
- peso: 600;
- não usar texto totalmente em maiúsculas;
- não reduzir o espaçamento entre letras artificialmente.

## Regras de legibilidade

- não usar textos menores que 12px;
- corpo de texto principal deve ter no mínimo 14px;
- campos e botões principais devem utilizar 16px no mobile;
- manter contraste suficiente;
- evitar cinza muito claro em informações importantes;
- não centralizar textos longos;
- limitar largura de parágrafos quando necessário.

---

# 4. PALETA DE CORES

Utilize os seguintes tokens:

```css
:root {
  --color-navy-950: #07152f;
  --color-navy-900: #0a1b3d;
  --color-navy-800: #112b59;

  --color-blue-600: #2563ff;
  --color-blue-500: #3180ff;
  --color-cyan-500: #00d4ff;
  --color-teal-500: #00c896;

  --color-gray-950: #111827;
  --color-gray-700: #374151;
  --color-gray-600: #4b5563;
  --color-gray-500: #6b7280;
  --color-gray-400: #9ca3af;
  --color-gray-300: #d1d5db;
  --color-gray-200: #e5e7eb;
  --color-gray-100: #f3f4f6;
  --color-gray-50: #f8fafc;
  --color-white: #ffffff;

  --color-success: #00a878;
  --color-warning: #f59e0b;
  --color-danger: #ef4444;
  --color-info: #2563ff;
  --color-refund: #7c3aed;
}
```

Gradiente principal:

```css
background: linear-gradient(135deg, #2563ff 0%, #00d4ff 100%);
```

Use gradientes apenas em:

- logo e ícone de marca;
- botão primário principal;
- pequenos destaques;
- splash screen;
- cards especiais quando fizer sentido.

Não use gradiente em todos os elementos.

---

# 5. ESPAÇAMENTO E LAYOUT

Utilize escala baseada em múltiplos de 4px:

```css
:root {
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 20px;
  --space-6: 24px;
  --space-8: 32px;
  --space-10: 40px;
  --space-12: 48px;
  --space-16: 64px;
}
```

Regras:

- não usar espaçamentos aleatórios;
- manter 16px de margem lateral mínima no mobile;
- utilizar 24px a 32px entre blocos principais;
- manter cards visualmente respirados;
- agrupar campos relacionados;
- evitar páginas excessivamente largas;
- limitar o conteúdo principal no desktop;
- manter ações importantes próximas do contexto.

Container sugerido:

```css
.app-container {
  width: min(100% - 32px, 1120px);
  margin-inline: auto;
}
```

---

# 6. BORDAS, RAIOS E SOMBRAS

```css
:root {
  --radius-sm: 8px;
  --radius-md: 12px;
  --radius-lg: 16px;
  --radius-xl: 24px;

  --shadow-sm: 0 1px 2px rgba(10, 27, 61, 0.06);
  --shadow-md: 0 8px 24px rgba(10, 27, 61, 0.08);
  --shadow-lg: 0 16px 40px rgba(10, 27, 61, 0.12);
}
```

Regras:

- inputs: raio de 10px a 12px;
- botões: raio de 10px a 12px;
- cards: raio de 16px;
- modais: raio de 20px a 24px;
- usar bordas claras e sombras discretas;
- não adicionar sombras pesadas em todos os elementos.

---

# 7. CABEÇALHO E IDENTIDADE

## Desktop

- usar o logo horizontal Vidalys Pay no cabeçalho;
- logo alinhado à esquerda;
- manter altura compacta;
- exibir informações do vendedor ou botão de perfil à direita;
- manter o cabeçalho fixo apenas se isso melhorar o fluxo;
- evitar cabeçalho alto e vazio.

## Mobile

- usar versão compacta do logo;
- manter botão de menu ou navegação clara;
- garantir área de toque mínima de 44x44px;
- não cortar o logo;
- não reduzir excessivamente o nome da marca.

---

# 8. NAVEGAÇÃO

A navegação do vendedor deve ser simples.

Priorize:

- Novo link;
- Histórico;
- Perfil.

Caso exista uma quarta área necessária, mantenha somente se já fizer parte da aplicação real.

No mobile:

- utilizar navegação inferior fixa quando apropriado;
- destacar claramente o item ativo;
- manter rótulos curtos;
- usar ícones consistentes;
- respeitar safe area do aparelho.

No desktop:

- utilizar cabeçalho ou sidebar compacta;
- não criar um menu administrativo complexo para vendedores.

---

# 9. TELA “CRIAR LINK”

Essa é a tela principal do produto e deve receber a maior atenção.

## Campos obrigatórios reais

- valor;
- parcelas;
- referência ou número do pedido, quando existir na implementação atual.

## Campos opcionais

- nome do cliente;
- telefone do cliente;
- descrição.

O telefone do cliente não deve parecer obrigatório quando não for.

Utilizar texto de apoio:

> Opcional — utilizado somente quando necessário para identificação ou comunicação.

## Campo de valor

- deve ser o elemento visual principal do formulário;
- teclado numérico no mobile;
- máscara monetária brasileira;
- prefixo R$ claro;
- fonte de 20px a 24px quando houver espaço;
- validação visível sem quebrar layout;
- não alterar o valor ou o binding usado pelo backend.

## Parcelas

Exibir as opções permitidas pelo sistema, atualmente:

- 1x sem juros;
- 2x sem juros;
- 3x sem juros.

Preferir botões segmentados ou cards selecionáveis.

O estado selecionado deve ser muito claro.

## Botão principal

Texto sugerido:

> Criar link de pagamento

Regras:

- largura total no mobile;
- altura mínima de 48px;
- loading com spinner e texto adequado;
- impedir clique duplo;
- não remover atributos, handlers ou bindings existentes.

---

# 10. RESULTADO DA CRIAÇÃO DO LINK

Após o link ser criado, mostrar uma área de sucesso clara contendo:

- ícone de sucesso;
- texto “Link criado com sucesso”;
- valor;
- parcelas;
- referência;
- URL do pagamento;
- botão “Copiar link”;
- botão “Compartilhar” quando suportado;
- botão “Reenviar via WhatsApp”;
- opção “Criar outro link”.

A falha no envio pelo WhatsApp não deve visualmente parecer falha na criação do link quando o Pagar.me já criou o link corretamente.

Exibir mensagens distintas:

- link criado e WhatsApp enviado;
- link criado, mas WhatsApp não enviado;
- link não criado.

---

# 11. HISTÓRICO

A tela de histórico deve funcionar bem no celular.

Cada item deve apresentar:

- referência;
- cliente, quando informado;
- valor;
- parcelas;
- data;
- status;
- ação para copiar ou abrir detalhes.

No mobile, não utilizar tabelas largas que exijam rolagem horizontal.

Utilizar cards ou lista responsiva.

Filtros devem ser compactos:

- Todos;
- Aguardando;
- Pagos;
- Falharam;
- Expirados.

Use somente filtros compatíveis com os status reais do sistema.

---

# 12. BADGES DE STATUS

Padronizar os status:

- Criado: azul;
- Aguardando pagamento: amarelo;
- Pago: verde;
- Falhou: vermelho;
- Cancelado: cinza;
- Expirado: laranja;
- Reembolsado: roxo.

Regras:

- texto legível;
- fundo claro com cor forte no texto e no ícone;
- evitar fundo completamente saturado em badges pequenos;
- não depender apenas da cor: usar texto e ícone.

---

# 13. TOASTS E FEEDBACK

Criar padrões para:

- sucesso;
- informação;
- aviso;
- erro.

Cada toast deve possuir:

- ícone;
- título curto;
- mensagem objetiva;
- opção de fechar quando necessário;
- duração adequada;
- acessibilidade com `role="status"` ou `role="alert"`.

Não utilizar alertas nativos do navegador como solução final.

---

# 14. ESTADOS DA INTERFACE

Implementar visual consistente para:

## Carregamento

- spinner discreto;
- skeleton quando apropriado;
- bloquear apenas a ação em processamento;
- não congelar toda a tela sem necessidade.

## Estado vazio

- ilustração simples;
- mensagem direta;
- ação principal;
- não mostrar cards vazios ou tabelas quebradas.

## Erro

- explicar o que ocorreu sem exibir detalhes técnicos ao vendedor;
- oferecer nova tentativa quando fizer sentido;
- manter detalhes técnicos somente nos logs.

## Desabilitado

- estado visual claro;
- preservar contraste mínimo;
- cursor e comportamento corretos.

---

# 15. ÍCONES

Utilize uma única biblioteca de ícones consistente ou os ícones fornecidos no kit.

Regras:

- espessura visual uniforme;
- tamanhos principais de 18px, 20px e 24px;
- não misturar ícones preenchidos e outline aleatoriamente;
- botões somente com ícone precisam de `aria-label`;
- não substituir ícones da marca por emojis.

---

# 16. FAVICON, MANIFEST E PWA

Aplicar corretamente:

- favicon 16x16;
- favicon 32x32;
- favicon 48x48;
- `apple-touch-icon` 180x180;
- PWA 192x192;
- PWA 512x512;
- versão maskable 512x512;
- ícone reduzido para atalho do celular;
- cor do tema alinhada ao azul profundo da marca.

Exemplo de manifest:

```json
{
  "name": "Vidalys Pay",
  "short_name": "Vidalys Pay",
  "display": "standalone",
  "background_color": "#F8FAFC",
  "theme_color": "#0A1B3D",
  "icons": [
    {
      "src": "/static/brand/icons/icon-192.png",
      "sizes": "192x192",
      "type": "image/png"
    },
    {
      "src": "/static/brand/icons/icon-512.png",
      "sizes": "512x512",
      "type": "image/png"
    },
    {
      "src": "/static/brand/icons/icon-maskable-512.png",
      "sizes": "512x512",
      "type": "image/png",
      "purpose": "maskable"
    }
  ]
}
```

Adapte os caminhos à estrutura real do projeto.

---

# 17. RESPONSIVIDADE

Teste e corrija pelo menos nestas larguras:

- 320px;
- 360px;
- 390px;
- 430px;
- 768px;
- 1024px;
- 1440px.

Verificar:

- campos não cortados;
- botões não espremidos;
- textos sem sobreposição;
- cards sem estouro;
- navegação acessível;
- valores monetários completos;
- modais dentro da viewport;
- teclado virtual no mobile;
- safe areas;
- rolagem vertical natural.

---

# 18. ACESSIBILIDADE

Aplicar:

- contraste adequado;
- foco visível;
- labels associados aos inputs;
- `aria-label` em botões com ícones;
- mensagens de erro associadas aos campos;
- navegação por teclado;
- ordem de foco lógica;
- área de toque mínima de 44x44px;
- `prefers-reduced-motion` para reduzir animações.

---

# 19. REGRAS PARA ALTERAÇÃO DO CÓDIGO

Antes de alterar qualquer arquivo:

1. identifique a stack visual utilizada;
2. mapeie templates, componentes e arquivos CSS;
3. localize os assets existentes;
4. identifique o comportamento dos formulários;
5. preserve CSRF, ações, URLs, handlers, IDs e nomes de campos;
6. preserve chamadas ao Pagar.me, Evolution API e endpoints internos;
7. preserve webhooks e código backend;
8. faça mudanças incrementais.

Não faça:

- reescrita completa sem necessidade;
- troca de framework;
- alteração do banco;
- alteração da API;
- remoção de validações;
- substituição de formulários reais por mockups;
- inclusão de dados fictícios no sistema final;
- instalação de bibliotecas pesadas sem justificativa.

---

# 20. PROCESSO DE TRABALHO OBRIGATÓRIO

Siga esta ordem:

## Etapa 1 — Auditoria

Apresente:

- problemas encontrados;
- inconsistências visuais;
- problemas de tipografia;
- problemas de responsividade;
- componentes duplicados;
- riscos de quebrar funcionalidades.

## Etapa 2 — Plano de correção

Liste:

- arquivos que serão alterados;
- componentes que serão criados ou padronizados;
- tokens visuais;
- estratégia mobile-first;
- ativos que serão posicionados.

## Etapa 3 — Implementação

Implemente por grupos:

1. tokens e tipografia;
2. layout base;
3. cabeçalho e navegação;
4. formulário de criação;
5. resultado do link;
6. histórico;
7. perfil;
8. feedbacks e estados;
9. favicon e PWA;
10. responsividade e acessibilidade.

## Etapa 4 — Validação

Confirme:

- backend preservado;
- rotas preservadas;
- integrações preservadas;
- formulários funcionando;
- CSRF funcionando;
- criação de link funcionando;
- envio via WhatsApp funcionando;
- histórico funcionando;
- layout funcionando nas larguras definidas;
- favicon e manifest carregando;
- ausência de erros no console.

---

# 21. ENTREGA FINAL

Ao terminar, forneça:

1. resumo das correções;
2. lista de arquivos alterados;
3. componentes criados;
4. tokens visuais adotados;
5. explicação de onde cada logo e ícone foi aplicado;
6. pontos que ainda dependem de decisão;
7. checklist de testes manuais;
8. comandos necessários para executar e validar o projeto.

O resultado deve ser uma evolução visual real da aplicação existente, mantendo toda a lógica já implementada.

**Não entregue apenas uma sugestão ou um mockup. Corrija o código real da aplicação de maneira incremental, segura e consistente.**
