# Prompt — Posicionamento dos ativos visuais no sistema Vidalys Pay

Quero que você implemente e posicione corretamente todos os ativos visuais da aplicação **Vidalys Pay** usando os arquivos deste pacote como referência.

Arquivos de referência:
- `01_identidade_visual_vidalys_pay.png`
- `02_icones_favicon_exportacao_vidalys_pay.png`
- `03_design_system_vidalys_pay.png`
- `04_guia_implementacao_handoff_vidalys_pay.png`

## Objetivo
Aplicar corretamente logo, ícones, favicon, tokens visuais e componentes do design system no sistema web/mobile do Vidalys Pay.

## Onde cada ativo deve ser usado

### 1. Favicon
Usar o ícone reduzido da marca nos arquivos:
- `favicon-16x16`
- `favicon-32x32`
- `favicon-48x48`

Aplicar no HTML via:
- `<link rel="icon" ...>`
- também considerar `apple-touch-icon` e ícones de manifest PWA

### 2. Logo principal
Usar o logo horizontal `Vidalys Pay`:
- no cabeçalho da aplicação web
- na tela inicial autenticada
- em e-mails/transacionais, quando fizer sentido
- em splash/header institucional

### 3. Ícone reduzido
Usar o símbolo reduzido:
- sidebar recolhida
- botões compactos
- navegação inferior mobile
- atalhos da aplicação
- loading splash

### 4. Manifest PWA
Configurar ícones do manifest com os tamanhos recomendados:
- 180x180
- 192x192
- 512x512
- 1024x1024, se necessário

### 5. Social preview / compartilhamento
Usar a imagem de compartilhamento como:
- `og:image`
- preview de links
- metadados de WhatsApp / redes

### 6. Design system
Aplicar o guia visual nos componentes:
- botões
- inputs
- cards
- badges
- toasts
- navegação
- ícones de ação
- estados vazios
- estados de carregamento

## Estrutura esperada no frontend
Quero que você organize algo parecido com:
- `assets/brand/`
- `assets/icons/`
- `assets/favicons/`
- `assets/social/`
- `components/ui/`
- `components/layout/`
- `styles/tokens/`

## Tokens visuais
Criar variáveis reutilizáveis para:
- cores
- tipografia
- raios de borda
- sombras
- espaçamentos
- estados de feedback

## Regras de consistência
- não trocar a paleta principal
- não usar ícones aleatórios fora do padrão
- não misturar estilos de borda e sombra
- manter consistência entre desktop e mobile
- priorizar clareza e usabilidade

## Entrega esperada
Quero que você:
1. liste cada ativo
2. diga onde ele deve ficar no projeto
3. descreva onde ele entra na interface
4. mostre a estrutura de pastas
5. gere o código ou instruções para aplicar cada ativo
6. entregue a aplicação visualmente consistente com o kit Vidalys Pay
