# 06 — Design tokens

Fonte: `referencias/_ds/tokens/`. **Copiar os arquivos CSS para `static/css/tokens/` e importar** — não redigitar valores no código do produto. Em componentes, usar sempre os aliases semânticos (`--color-primary`, `--text-body`), nunca os tokens crus (`--ll-teal`).

## 1. Cores

### Marca
| Token | Hex | Uso |
| --- | --- | --- |
| `--ll-teal` | `#43B5B6` | assinatura; ações primárias |
| `--ll-teal-600` | `#34999a` | hover de ação primária |
| `--ll-teal-700` | `#2b8283` | active; texto sobre fundo teal claro |
| `--ll-teal-300` | `#7fcecf` | bordas de destaque |
| `--ll-teal-100` | `#d8f0f0` | seleção de texto |
| `--ll-teal-050` | `#eef9f9` | fundo de chip/estado ativo |
| `--ll-blue` | `#0086C4` | institucional; links |
| `--ll-blue-600` | `#0a6fa3` | hover de link |
| `--ll-blue-700` | `#0d5b85` | códigos e IDs monoespaçados |
| `--ll-blue-300` | `#62b8de` | — |
| `--ll-blue-100` | `#cfe8f4` | borda de chip azul |
| `--ll-blue-050` | `#eaf5fb` | fundo de badge de contagem |
| `--ll-navy` | `#0D4B86` | superfícies escuras |
| `--ll-navy-800` | `#0a3a6b` | — |
| `--ll-navy-900` | `#082c52` | fundo hero/escuro |

### Neutros
| Token | Hex | Uso |
| --- | --- | --- |
| `--ll-ink` | `#12232e` | texto forte (títulos) |
| `--ll-slate-700` | `#33454f` | corpo de texto |
| `--ll-slate-500` | `#5b6b74` | texto secundário |
| `--ll-slate-400` | `#84949c` | placeholder, borda forte |
| `--ll-slate-300` | `#b7c1c7` | borda padrão, scrollbar |
| `--ll-slate-200` | `#d9e0e4` | borda sutil (cards, tabelas) |
| `--ll-slate-100` | `#eceff1` | superfície rebaixada, divisória de linha |
| `--ll-slate-050` | `#f5f7f8` | fundo da página |
| `--ll-white` | `#ffffff` | superfície de card |

### Status
| Token | Hex | Fundo | Texto sobre fundo |
| --- | --- | --- | --- |
| `--ll-success` | `#2f9e6b` | `#e4f4ec` | `#2f9e6b` |
| `--ll-warning` | `#d9922b` | `#fbf0dc` | `#8a5a14` ⚠ hex fixo, não é token |
| `--ll-danger` | `#d24b46` | `#fbe7e6` | `#d24b46` |
| `--ll-info` | = `--ll-blue` | `#eaf5fb` | `--ll-blue-700` |

> `#8a5a14` é usado no protótipo como texto sobre fundo âmbar (o token `--ll-warning` não tem contraste suficiente ali). **Criar um token novo** no projeto: `--ll-warning-fg: #8a5a14`.

### Aliases semânticos (usar estes)
`--color-primary` · `--color-primary-hover` · `--color-primary-active` · `--color-primary-soft` · `--color-secondary` · `--color-secondary-hover` · `--color-secondary-soft` · `--text-strong` · `--text-body` · `--text-muted` · `--text-on-brand` · `--text-link` · `--surface-page` · `--surface-card` · `--surface-sunken` · `--surface-brand` · `--surface-brand-deep` · `--border-subtle` · `--border-default` · `--border-strong` · `--focus-ring`

Gradientes: `--gradient-brand` (blue→teal 120°), `--gradient-hero`, `--gradient-soft`. No sistema interno **só o brand aparece**, e apenas em barras de progresso e cabeçalho de login.

## 2. Tipografia

Família única: **Manrope** (stand-in de Codec Pro, a fonte de marca comercial). Mono: **IBM Plex Mono** — obrigatória em números de chamado, códigos de item, horas e timestamps (alinhamento tabular é requisito).

| Token | Valor |
| --- | --- |
| `--font-display` / `--font-body` | `'Manrope', system-ui, sans-serif` |
| `--font-mono` | `'IBM Plex Mono', ui-monospace, Menlo, monospace` |

Escala: `--text-2xs` 11px · `--text-xs` 12px · `--text-sm` 14px · `--text-base` 16px · `--text-md` 18px · `--text-lg` 22px · `--text-xl` 28px · `--text-2xl` 36px · `--text-3xl` 48px.

Pesos: 400 / 500 / 600 / 700 / 800 / 900. Line-height: `1.08` tight · `1.25` snug · `1.55` normal · `1.7` relaxed. Tracking: `-0.02em` tight (títulos) · `0.04em` wide · `0.14em` caps (overlines).

### Papéis de texto no sistema (valores exatos do protótipo)

| Elemento | Especificação |
| --- | --- |
| H1 de tela | `800 27px/1.2` display, `-.02em`, `--text-strong`, `max-width: 720px` |
| H2 de card | `700 16px/1.2` display, `-.01em`, `--text-strong` |
| Overline / label de KPI | `600 9px/1` display, `.14em`, uppercase, `--text-muted` |
| Cabeçalho de tabela | `600 10.5–11px`, `.06em`, uppercase, `--text-muted` |
| Corpo de tabela | `13px/1.3`, `--text-body`; ênfase `600 13px` `--text-strong` |
| Texto auxiliar | `12–12.5px/1.55`, `--text-muted` |
| Chip / badge | `600 11px/1`, padding `5px 10px`, `border-radius: 999px` |
| Código / número | `600 11–11.5px/1` mono, `--ll-blue-700` |
| Timestamp | `500 10.5px/1.4` mono, `--text-muted` |

## 3. Espaçamento e forma

- Grid de 4px. Padding de card: `22px 24px`. Gap entre cards: `16px`. Gap em grades de KPI: `14px`.
- Padding de linha de tabela: `13–14px 22px`; cabeçalho `11–12px 22px`.
- Raios: `999px` chip/pill · `16px` card · `12px` bloco interno / input · `8px` badge pequeno.
- Sombra: `--shadow-sm` em todos os cards (única elevação do sistema); modais usam `--shadow-lg` + overlay `rgba(18,35,46,.45)`.
- Barra de progresso: altura `9px`, `border-radius: 999px`, trilha `--surface-sunken`.
- Ponto de status: `7–8px` círculo; quando ativo, animação `pulseDot` (opacidade 1 → .25 → 1, 1.6s infinite).

## 4. Layout do shell

| Parte | Especificação |
| --- | --- |
| Sidebar | `250px` fixa, `--surface-card`, borda direita `--border-subtle`, `position: sticky; top: 0; height: 100vh; overflow: auto` |
| Logo | `assets/logo-horizontal.png`, altura `44px`, padding `22px 18px 16px`, divisória inferior |
| Grupos de menu | overline `.14em` uppercase 9px; item ativo = fundo `--ll-teal-050` + texto `--ll-teal-700`; badge à direita |
| Header | `position: sticky; top: 0; z-index: 20`, `min-height: 58px`, padding `10px 28px`, `rgba(255,255,255,.9)` + `backdrop-filter: blur(...)`, borda inferior sutil |
| Conteúdo | padding `28px`; `max-width` por tela: 1400px (painel, tarefas, tarefa, histórico, config), 1500px (almoxarifado, compras), 1600px (projetos) |
| Grades responsivas | `repeat(auto-fit, minmax(200px, 1fr))` KPIs · `minmax(340–380px, 1fr)` cards de conteúdo |
| Tabelas largas | `min-width` explícito + `overflow-x: auto` no card (nunca quebrar coluna) |

## 5. Ícones

SVG stroke inline: `viewBox="0 0 24 24"`, `fill: none`, `stroke: currentColor`, `stroke-width: 2.2`, `stroke-linecap: round`, `17×17px`, `flex: none`. Equivalente mais próximo em biblioteca: **Lucide** (usar `strokeWidth={2.2}`).

## 6. Acessibilidade

- Foco visível sempre: `outline: 2px solid var(--focus-ring); outline-offset: 2px`.
- Cor nunca é o único sinal: todo chip de status traz texto ("Comprar hoje", "Atrasado").
- Contraste mínimo AA em texto ≤ 14px — atenção ao par âmbar (`--ll-warning-bg` + `#8a5a14`).
- Alvos clicáveis ≥ 36px de altura em desktop; linhas de tabela clicáveis inteiras com `cursor: pointer`.
