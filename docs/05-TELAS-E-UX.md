# 05 — Telas e UX

Referência visual: `referencias/Sistema Interno TI.dc.html` (abrir no navegador; o seletor de perfil no topo da sidebar troca o papel e recalcula o menu). Medidas e cores em `06-DESIGN-TOKENS.md`.

**Shell comum a todas as telas:** sidebar 250px + header sticky 58px + conteúdo com padding 28px. Header contém: breadcrumb (`Life Laboral / <módulo>`), busca global (botão que abre overlay), chip de alerta âmbar contextual, seletor de setor (só para papéis com `todos_setores`), avatar com papel.

Menu (ordem fixa, filtrado por permissão):

| Grupo | Item | Badge | Visível para |
| --- | --- | --- | --- |
| Gestão | Painel de indicadores | — | ≠ Colaborador |
| — | Central de tarefas | contagem de abertos (34) | todos |
| — | Tarefa em andamento | ponto pulsante se cronômetro ativo | todos |
| Portfólio | Projetos de TI | 17 | ≠ Colaborador |
| Materiais | Almoxarifado | rupturas (6), âmbar | todos |
| — | Compras | 9, âmbar | Compras, Admin |
| Administração | SLA e permissões | — | Admin |

---

## 1. Painel de indicadores

**Objetivo:** o gestor entende em 10 segundos se as horas estão sendo bem gastas e o que está em risco.

**Layout:** header da tela (título + subtítulo + botão "Exportar") → 4 KPIs (`auto-fit minmax(200px,1fr)`) → 2 cards grandes (`minmax(360px,1fr)`) → 3 cards menores (`minmax(300px,1fr)`).

**KPIs (copy exata):**
1. `551,5h` — "Horas apontadas no mês · previsto 512h"
2. `87%` — "Cumprimento de SLA · meta 90%"
3. `14%` — "Horas em retrabalho · meta ≤ 8%" (vermelho quando acima da meta)
4. `19` — "Itens abaixo do mínimo · 11 setores"

**Card "Horas por tipo de trabalho":** 8 linhas em grid `130px 1fr 62px` — nome, barra de progresso (9px, trilha `--surface-sunken`, preenchimento teal; **retrabalho em vermelho**), horas à direita em mono. Rodapé com 3 mini-indicadores (`auto-fit minmax(140px,1fr)`): Documentação (% de cobertura), Retrabalho (h), Espera de terceiro (h).

**Card "Risco de SLA":** lista de chamados com vencimento < 8h úteis, ordenada por urgência; chip de prioridade + tempo restante em mono; clique abre a tarefa.

**Outros cards:** "Retrabalho por motivo" (5 barras), "Consumo por setor" (top 5), "Documentação pendente" (chamados entregáveis travados).

**Estados:** sem dados no período → card com texto neutro "Nada apontado neste período" (não esconder o card). Carregando → skeleton com as mesmas alturas.

---

## 2. Central de tarefas

**Objetivo:** fila de trabalho do time; triagem e priorização.

**Layout:** header com título, subtítulo ("34 chamados abertos · 6 em risco de SLA"), botões `Novo chamado` (primário teal) e `Exportar` (secundário) → filtros em linha (chips de status + select de setor/prioridade/responsável) → tabela em card.

**Tabela** (`min-width: 1120px`, `overflow-x: auto`, grid de 8 colunas `92px 2.2fr 130px 96px 132px 116px 156px 104px`):

| Coluna | Conteúdo |
| --- | --- |
| Chamado | `TI-2026-0341` mono azul |
| Assunto | título (1 linha, ellipsis) + categoria em 11px muted |
| Solicitante | nome + setor |
| Prioridade | chip colorido |
| Responsável | nome ou "—" |
| Horas P/R | `12 / 15,5` mono; vermelho se realizado > previsto |
| SLA | barra fina + texto ("em 6h", "atrasado 2h") |
| Documento | chip "OK", "Pendente" (âmbar) ou "N/A" |

Linha inteira clicável (`cursor: pointer`, hover `--ll-slate-050`) → abre "Tarefa em andamento". Ordenação por qualquer coluna. Sem resultado → estado vazio com botão de limpar filtros.

**Modal "Novo chamado":** campos Título, Descrição, Categoria (select — mostra aviso "esta categoria exige documentação para entrega" quando aplicável), Prioridade (4 chips com exemplo do SLA resultante: "Crítica · resposta em 4h úteis"), Setor de origem (pré-preenchido), Anexos (drag-and-drop). Rodapé: "O SLA será calculado em horas úteis a partir da abertura." Ações: Cancelar / Abrir chamado.

---

## 3. Tarefa em andamento

**Objetivo:** onde o técnico trabalha — aponta horas, documenta, comenta.

**Layout:** título do chamado (H1 800/27px, max 720px) + 3 chips (prioridade, categoria, status) + ações à direita (`Enviar entrega`, `Comentar`) → grid `auto-fit minmax(380px,1fr)`, coluna esquerda com 3 cards empilhados, direita com 2.

**Card meta:** grid de 4 blocos (Solicitante, Aberto em, SLA, Responsável) — label overline 9px + valor 13px.

**Card "Apontamento de horas" (o coração da tela):** 8 linhas em grid `150px 1fr 88px 96px`:
- ponto de status (pulsa quando ativo) + nome do tipo;
- barra proporcional ao maior valor;
- total em mono;
- botão `Iniciar` / `Parar` (teal quando ativo).

Ao iniciar um tipo com outro rodando: toast "Desenvolvimento pausado — 1h12 registradas". Linha ativa ganha borda e fundo teal claro. Botão secundário `Lançamento manual`.

**Card "Motivo de retrabalho"** (aparece só quando Retrabalho está selecionado/ativo): select de motivo + campo de detalhe (mín. 15 caracteres) + aviso âmbar explicando por que a causa é obrigatória. Bloco não é fechável — sem causa não grava.

**Card "Documentação":** 6 linhas em grid `180px 1fr 96px` — seção, resumo do conteúdo, chip de status (Publicado / Rascunho / Falta). Seções obrigatórias marcadas. Botão `Editar documentação` abre editor por seção com versionamento.

**Card "Histórico":** timeline em grid `78px 1fr` — hora em mono + texto.

**Modal "Lançamento manual de horas":** Tipo, Data, Início, Fim (calcula duração ao vivo), Chamado/Projeto, Observação, Motivo de retrabalho quando aplicável. Avisos em tempo real: conflito de horário ("conflita com Análise 08:00–12:00") e estouro de capacidade ("total do dia: 9h05 — exigirá aprovação do gerente").

**Modal "Aprovação de gerente":** lista de lançamentos pendentes com pessoa, dia, total, tipo e justificativa; ações Aprovar / Recusar (com motivo) em lote.

**Bloqueio de entrega:** clicar `Enviar entrega` sem documentação → modal de bloqueio listando as seções faltantes, com atalho para cada uma. Nunca só um toast.

---

## 4. Projetos de TI

**Objetivo:** portfólio e capacidade.

**Layout:** header (título, `Novo projeto`, `Projetos concluídos/cancelados`) → 4 KPIs → kanban horizontal de **8 colunas** (`overflow-x: auto`, coluna ~280px): Ideia · Em análise · Aprovado · Na fila · Em desenvolvimento · Em testes · Homologação · Implantação.

**Card de projeto:** nome (2 linhas máx.), setor solicitante, responsável (avatar + nome), `horas previstas / realizadas` em mono com desvio colorido, barra de progresso, chip de risco quando `fim_previsto` estourado. Drag entre colunas (opcional na F5; clique + select serve).

**Modal "Novo projeto":** Nome, Setor solicitante, Patrocinador, Descrição do problema, Horas estimadas, Início/Fim previstos, Responsável de TI. Aviso: "Projetos com mudança de regra de negócio exigem documentação antes da implantação."

---

## 5. Projetos concluídos e cancelados (histórico)

Header + 3 KPIs (`23` concluídos em 2026, `+11%` desvio médio de horas, `4` cancelados) → tabela `min-width 1040px`, colunas `2fr 130px 120px 132px 96px 1.3fr`: Projeto · Setor · Encerrado em · Horas P/R · Desvio (verde/vermelho) · Situação final (texto livre, ex.: "Entregue com escopo reduzido"). Filtros: ano, setor, situação. Botão `Exportar`.

---

## 6. Almoxarifado

**Objetivo:** o setor enxerga e movimenta o próprio estoque.

**Layout:** header (título, subtítulo com nome do setor e centro de custo, botões `Solicitar material`, `Entrada por nota fiscal`, `Transferência`, `Inventário cíclico`, `Leitura de QR Code`) → 4 KPIs em cards próprios → grid `auto-fit minmax(340px,1fr)`.

**Card "Estoque do setor"** (`min-width 660px`, grid `76px 2fr 80px 76px 92px 128px`): Código (mono azul) · Item (descrição + unidade) · Saldo · Mínimo · Unitário · Situação (chip: OK verde / Abaixo do mínimo âmbar / Ruptura vermelho). Cabeçalho do card mostra `CC 3102` à direita em mono.

**Card "Movimentos de hoje":** grid `52px 1fr auto` — hora mono, texto ("Saída 4 UN Disco de corte · OS 88213"), quantidade com sinal colorido.

**Card "Solicitações do setor":** status, solicitante, itens, ação (aprovar/atender conforme papel).

**Modal "Solicitar material":** busca de item (autocomplete por código/descrição), quantidade, **centro de custo (obrigatório)**, OS/projeto, urgência, observação. Mostra saldo atual do item e alerta se a quantidade pedida ultrapassa o saldo. Vários itens por solicitação.

**Modal "Entrada por nota fiscal":** dados da NF (número, série, fornecedor, CNPJ, emissão, valor) + tabela de itens com `pedido` × `recebido` e campo de divergência por linha; total conferido no rodapé; anexo do PDF. Ao confirmar: uma entrada por item.

**Modal "Transferência entre setores":** item, saldo atual, quantidade, setor destino (lista os outros 10), motivo. Se sobrar abaixo do mínimo: alerta âmbar "A origem ficará abaixo do mínimo (5 UN) — Compras será notificada". Não bloqueia.

**Modal "Inventário cíclico":** 5 itens por rodada com `saldo sistema` (readonly) e `saldo contado` (input); calcula divergência e impacto em R$ ao vivo; rodapé mostra "2 divergências · impacto R$ 412,80"; confirmar gera os ajustes.

**Tela "Leitura de QR Code":** área de câmera simulada + campo de código manual; ao ler, mostra o item, saldo do setor e atalhos para saída rápida e solicitação.

---

## 7. Compras

**Objetivo:** visão dos 11 setores, ruptura e reposição.

**Layout:** header (`Abrir cotação`, `Exportar`) → 4 KPIs (`19` itens em ruptura, `17` solicitações abertas, `R$ 148.320` consumo do mês, `6` cotações abertas) → tabela "Consumo e ruptura por setor" (`min-width 960px`, grid `1.4fr 96px 130px 130px 1fr 128px`): Setor · C. custo (mono) · Consumo/mês · Abaixo do mínimo · Mais consumido · Ação (chip `Comprar hoje` vermelho / `Cotar` âmbar / `Normal` verde) → dois cards: "Fila de reposição" (item, saldo, ação) e "Consumo sem OS" (o relatório de desperdício).

**Tela "Abrir cotação":** item, quantidade, prazo de resposta, fornecedores convidados; ao receber propostas, comparativo com valor unitário, prazo e botão `Escolher` (a escolhida vira sugestão de pedido).

---

## 8. SLA e permissões (Admin)

**Layout:** grid `auto-fit minmax(380px,1fr)`.

**Card "SLA por prioridade":** 4 linhas em grid `1fr 140px 96px` — ponto colorido + prioridade + exemplo ("linha parada", "setor bloqueado", "melhoria pedida", "ajuste cosmético"), input de horas úteis, efeito simulado. Rodapé recalcula ao vivo: "Com estas regras, 31 dos 34 chamados abertos estariam no prazo (91%)". Esse recálculo ao vivo é requisito — mostra a consequência antes de salvar.

**Card "Matriz de permissões":** grid `180px repeat(5, 1fr)` — linha por módulo, coluna por papel; célula clicável alterna **ver → editar → sem acesso**, com cor e rótulo. Salvar grava em `core.PermissaoModulo`.

**Outros cards:** Tipos de trabalho (ativar/desativar, marcar `exige_causa`), Motivos de retrabalho, Categorias e exigência de documentação, Setores e centros de custo.

---

## 9. Telas transversais

- **Busca global (overlay):** atalho `/` ou clique no campo do header; resultados agrupados por tipo (chamado, projeto, item, solicitação), navegação por teclado, "Enter" abre.
- **Histórico de mudanças:** tabela lida de `core.Auditoria` — quando, quem, ação, antes → depois; filtro por objeto e por usuário.
- **Exportar:** modal comum a todas as telas — formato (CSV/XLSX/PDF), período, escopo ("tela atual" ou "todos os setores"), e aviso de envio por e-mail acima de 5.000 linhas.
- **Estados de erro:** saldo insuficiente, documentação incompleta e conflito de horas sempre aparecem como **modal com a causa e o caminho de correção**, nunca como toast genérico.

## 10. Comportamento e responsividade

- Alvo é desktop (1440px+). Abaixo de 1200px a sidebar colapsa em ícones; abaixo de 900px as tabelas rolam horizontalmente e os grids caem para 1 coluna. Não há versão mobile prioritária — o operador de almoxarifado usa tablet, então **os modais de solicitação e QR Code precisam funcionar em 768px** com alvos de 44px.
- Transições: 150ms ease para hover, 200ms para abrir modal (fade + translateY 8px). Nada acima de 250ms.
- Cronômetro atualiza a cada segundo no cliente, mas a verdade é do servidor (`inicio` + hora atual do servidor); ao reabrir a tela, recalcular a partir de `/cronometro/`.
- Toda ação de escrita mostra feedback em ≤ 300ms (otimista) e reverte com mensagem se a API recusar.
