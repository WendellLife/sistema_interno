# Sistema Interno Life Laboral

Chamados/tarefas · horas por tipo de trabalho · documentação obrigatória · almoxarifado setorial · portfólio de projetos de TI.

**Stack:** Python 3.12 · Django 5.1 · DRF · PostgreSQL 16 · Celery + Redis · `uv` · `ruff` · `pytest-django`.
Leia `CLAUDE.md` (regras do repositório) e `docs/` (handoff completo) antes de contribuir.

## Estado atual — backend (F1–F6) e front-end completos

| App | Entregue |
| --- | --- |
| `core` | `User` custom, `Setor`, `CentroCusto`, `Feriado`, `Auditoria` (append-only), `PermissaoModulo` (matriz editável), calendário de horas úteis, permissões em duas camadas, sequência PostgreSQL para numeração, `/auth/*`, `seed_demo` |
| `chamados` | Modelos, máquina de estados em `services.py`, SLA em horas úteis (recalculado ao mudar prioridade), bloqueio de entrega por documentação, comentários (internos só TI), anexos (≤ 20 MB), histórico, task `verificar_sla`, API `/chamados/*`, `/categorias/`, `/regras-sla/` |
| `documentacao` | 6 seções criadas na abertura do chamado (`obrigatorio` por categoria), versões append-only (rascunho → publicar), `status` Publicado/Rascunho/Falta, cobertura do painel, "Documentação pendente", API `/documentos/*` |
| `almoxarifado` | `Item`, `Estoque` materializado (`saldo >= 0` no banco), `Movimento` imutável (sem PUT/PATCH/DELETE, admin somente leitura, `sinal` ±1), `registrar_movimento()` como ponto único com `select_for_update`, transferência atômica com `fura_minimo_origem`, solicitação aberta → aprovada → atendida (parcial ok), NF gerando entradas e atualizando custo, inventário com snapshot + ajustes + impacto R$, cotação com proposta única escolhida, QR, fila de reposição, alerta de mínimo (task via `on_commit`), reconciliação `Estoque.saldo == Σ movimentos` |
| `almoxarifado` | `Estoque` materializado com `saldo >= 0` no banco, `registrar_movimento` como único ponto de escrita (`select_for_update`), movimento imutável (405 na API, somente leitura no admin), saída exige referência, transferência atômica com `fura_minimo_origem`, solicitação → aprovação → atendimento parcial, NF gerando entradas e atualizando custo, inventário com snapshot e fechamento gerando ajustes, cotação com proposta única escolhida, QR, fila de reposição (`AlertaReposicao` via task idempotente), `reconciliar()` |
| `web` | Front-end server-rendered (Django templates + HTMX + Alpine, sem build): login, shell (sidebar 250 / header 58 / conteúdo 28, menu vindo de `montar_me`, badges, ponto pulsante do cronômetro, busca global com `/`), **Central de tarefas** (grid de 8 colunas, chips de status, filtros via partial, modal Novo chamado com aviso de documentação e SLA por prioridade) e **Tarefa em andamento** (meta, card de apontamento com cronômetro sincronizado pelo servidor, bloco de retrabalho não fechável, lançamento manual com avisos ao vivo de conflito/capacidade, documentação com editor versionado, comentários internos, histórico, transições e **modal de bloqueio de entrega com atalho por seção**) |
| `integracoes` | Camada genérica para **qualquer** sistema externo: chave por sistema (`Api-Key`, só hash no banco, escopos, IPs), `Idempotency-Key` com replay da resposta, outbox de eventos derivada da auditoria (`chamado.*`, `estoque.saida`…) entregue por webhook com HMAC-SHA256 e backoff, polling `/eventos/?desde=`, endpoints de entrada (solicitação, chamado, sync de itens, NF, estoque). OpenAPI em `/api/docs/` |
| `busca` | `/busca/?q=` — full-text `portuguese` + trigram (índices GIN em `chamado.titulo` e `projeto.nome`), escopo por papel, 5 por tipo (chamado, projeto, item, solicitação), throttle 60/min |
| `projetos` | Kanban de 8 fases (avança uma, volta livre, cancela de qualquer, conclui só de implantação), encerramento exige data + situação (serviço e `CheckConstraint`), marcos, alocação com teto de 100% por pessoa, horas realizadas e risco de prazo anotados, aviso de documentação ao implantar, API `/projetos/*` |
| `apontamentos` | Cronômetro único por usuário (`UniqueConstraint` parcial + fechamento automático do anterior), não sobreposição (`ExclusionConstraint` gist + mensagem legível), retrabalho com causa (`CheckConstraint` sobre campo denormalizado), lançamento manual com pendência por capacidade/retroativo, aprovação escopada, API `/cronometro/*`, `/apontamentos/*` |
| `relatorios` | `/painel/` (4 KPIs + 7 cards em uma chamada), `/horas/`, `/retrabalho/`, `/consumo/`, `/sla/`, `/auditoria/`; todos com `?formato=json\|csv\|xlsx\|pdf`, e acima de 5.000 linhas `202 {job_id}` + arquivo por e-mail (`relatorios.gerar_export`) |

Próximas fases (`docs/07-PLANO-DE-IMPLEMENTACAO.md`): F5 projetos/painel/exportações → F6 integrações.

## Front-end

`web/` renderiza no servidor e chama os `services`/`selectors` diretamente (mesmo escopo da API). HTMX troca partials (`_tabela`, `_apontamento`, `_comentarios`); Alpine cuida de modais e do relógio. Erros de regra viram **modal com causa e correção** (`_modal_erro`, `_modal_bloqueio`) — nunca toast. Cronômetro: `/cronometro/estado/` devolve `inicio` + hora do servidor; o cliente só conta.

Telas prontas: `/entrar/`, `/tarefas/`, `/tarefas/<id>/`, `/tarefa/` (cronômetro ativo ou chamado mais urgente), `/painel/` (4 KPIs + 7 cards; mesmo payload de `/relatorios/painel/`, montado em `relatorios.selectors.painel`; modal Exportar comum). `/almoxarifado/` (KPIs, estoque do setor com situação, movimentos de hoje, solicitações com aprovar/negar/atender por papel, modais Solicitar/Transferência/NF/Inventário, `/almoxarifado/qr/` com câmera via `BarcodeDetector` + código manual e alvos de 44px). `/projetos/` (kanban de 8 colunas com KPIs, cards com horas P/R e risco, mover por select, modal Novo projeto, modal de encerramento exigindo data + situação) e `/projetos/historico/` (3 KPIs, desvio colorido, filtros ano/setor/situação), `/compras/` (4 KPIs, consumo e ruptura por setor com ação Comprar hoje/Cotar/Normal, fila de reposição, consumo sem OS, cotações com propostas e Escolher), `/config/` (SLA por prioridade com **simulação ao vivo** "N dos M abertos estariam no prazo", matriz de permissões clicável ver → editar → sem acesso, tipos de trabalho, motivos, categorias, setores/centros de custo) e `/historico/` (auditoria filtrável). **Todas as 7 telas do handoff + as transversais estão prontas.**

HTMX e Alpine vêm por CDN (unpkg) — para ambiente sem internet, copie os dois arquivos para `static/js/` e troque os `<script>` em `base.html`.

## Subindo local

```bash
cp .env.example .env
docker compose up -d db redis
uv sync
uv run python manage.py makemigrations core projetos chamados documentacao apontamentos almoxarifado   # gera os *_initial
uv run python manage.py migrate
uv run python manage.py seed_demo          # admin / admin, usuários com senha "senha123"
uv run python manage.py runserver
```

> As migrations `core/0001_extensoes` (btree_gist, pg_trgm) e `core/0002_funcao_proximo_numero`
> (função `proximo_numero(prefixo, ano)`) são escritas à mão e não dependem de tabelas; o
> `makemigrations` gera as demais. Depois de gerar, **commite as migrations** — o CI roda
> `makemigrations --check`.

## Primeira execução — checklist

1. `make install && make migrations` — gera os `*_initial`; se o `makemigrations` reclamar de algo, quase sempre é um `related_name` ou o `ExclusionConstraint` de `apontamentos` (ajuste ali, não nas outras apps).
2. `make migrate` — as três migrations manuais de `core` (extensões, função `proximo_numero`) rodam antes das geradas.
3. `make test` — se falhar em bloco, rode por app na ordem `core → chamados → apontamentos → documentacao → almoxarifado → projetos → relatorios → integracoes → web`: as apps posteriores dependem das anteriores.
4. `make format` uma vez para normalizar o estilo (o código foi escrito sem passar pelo `ruff format`).
5. `make seed && make run` → `http://localhost:8000/entrar/` com `admin / admin`.

## Testes

```bash
uv run pytest --cov            # precisa do Postgres do docker-compose (constraints e sequences são reais)
```

Testes obrigatórios do CLAUDE.md cobertos nesta fase: entrega de desenvolvimento sem documentação é recusada (serviço e API); cada papel só enxerga o próprio escopo (parametrizado); numeração concorrente sem duplicata/lacuna; SLA de Crítica aberta sexta 16:00 vence segunda 11:00; auditoria com `antes`/`depois` na entrega.

### Apontamentos (F2)

| Endpoint | Notas |
| --- | --- |
| `GET cronometro/` | cronômetro aberto do usuário ou `null` |
| `POST cronometro/iniciar/` | `{tipo, chamado\|projeto, motivo_retrabalho?, detalhe_retrabalho?}` → `201 {apontamento, pausado}` |
| `POST cronometro/parar/` | fecha e devolve os minutos |
| `GET/POST apontamentos/` | POST = lançamento manual (`inicio`, `fim`); acima da capacidade ou > 7 dias retroativo fica `pendente_aprovacao` |
| `POST apontamentos/{id}/aprovar/`, `GET apontamentos/pendentes/` | Gerente do setor (só seu setor) / Gerente de TI / Admin |
| `tipos-trabalho/`, `motivos-retrabalho/` | cadastros |
| `relatorios/horas/?de=&ate=&setor=&tipo=`, `relatorios/retrabalho/?de=&ate=` | só apontamentos fechados e não pendentes |

### Documentação e busca (F3)

| Endpoint | Notas |
| --- | --- |
| `GET documentos/?chamado=` | as 6 seções com `status`, `resumo`, `obrigatorio`, `versao_atual`, `ultima_versao` |
| `POST documentos/` | `{chamado\|projeto, secao}` — idempotente (devolve a existente) |
| `GET/POST documentos/{id}/versoes/` | POST `{conteudo, publicar?}` cria rascunho (append-only) |
| `POST documentos/{id}/versoes/{n}/publicar/` | vira `versao_atual`; 409 se já publicada |
| `GET documentos/cobertura/?setor=&de=&ate=` | % do painel |
| `GET documentos/pendentes/` | chamados em testes travados por documentação, com `faltando` |
| `GET busca/?q=` | `{resultados: [{tipo, id, titulo, subtitulo, url}]}` |

### Almoxarifado (F4)

Prefixo `almoxarifado/`. Erro de saldo: `409 {"erro": "saldo_insuficiente", "item", "saldo", "pedido", "mensagem"}`.

| Endpoint | Notas |
| --- | --- |
| `GET/POST/PATCH itens/` | filtros `setor`, `abaixo_minimo`, `busca`; lista anota `saldo` no setor do usuário (ou `?setor=` para Compras) |
| `GET estoque/?setor=` | saldo por item/setor |
| `GET/POST movimentos/` | POST = entrada/saída/ajuste (ajuste exige `sinal` e `justificativa`); Responsável+; `?sem_os=true` |
| `GET/POST solicitacoes/` + `aprovar/`, `negar/`, `atender/` | itens no mesmo payload; atender aceita `{quantidades: {item_solicitacao_id: qtd}}` (parcial) |
| `GET/POST notas-fiscais/` | Compras; gera entradas e atualiza `custo_unitario` |
| `GET/POST transferencias/` | dois movimentos atômicos; `fura_minimo_origem` no retorno |
| `GET/POST inventarios/` + `PATCH contagens/`, `POST fechar/` | abre com snapshot; fechar devolve `detalhe_divergencias` |
| `GET/POST cotacoes/` + `POST cotacoes/{id}/propostas/`, `POST propostas/{id}/escolher/` | módulo `compras` da matriz |
| `GET qrcode/{codigo}/` (`?formato=png`) | item + saldo(s) |
| `GET reposicao/` | fila de Compras (no mínimo ou abaixo) |
| `GET relatorios/consumo/?de=&ate=&setor=&sem_os=` | por setor, por centro de custo, movimentos |

### Almoxarifado (F4)

Prefixo `almoxarifado/`. Escopo: Colaborador/Responsável/Gerente veem o próprio setor; Gerente de TI lê tudo; Compras e Admin escrevem em todos. NF, inventário e cotação: escrita só Compras/Admin (Responsável no próprio setor para NF e inventário).

| Endpoint | Notas |
| --- | --- |
| `itens/?setor=&abaixo_minimo=&busca=` | saldo anotado para o setor (padrão: do usuário); POST/PATCH cadastro |
| `estoque/?setor=` | saldos do setor |
| `movimentos/` | GET, POST (`entrada`, `saida`, `ajuste` c/ `sinal` e `justificativa`); **405** em PUT/PATCH/DELETE |
| `solicitacoes/` + `{id}/aprovar\|negar\|atender/` | itens no payload; `atender` aceita `{quantidades: {item_id: qtd}}` (parcial) |
| `notas-fiscais/` | POST gera uma entrada por item e atualiza `custo_unitario` |
| `transferencias/` | dois movimentos atômicos; `fura_minimo_origem` + alerta |
| `inventarios/` + `{id}/contagens/` (PATCH) + `{id}/fechar/` | snapshot na abertura; fechamento devolve `itens_divergentes`, `divergencias`, `impacto_valor` |
| `cotacoes/` + `{id}/propostas/` + `propostas/{id}/escolher/` | uma escolhida por cotação (constraint) |
| `qrcode/{codigo}/` | item + saldo do setor |
| `alertas/` | fila de reposição aberta |
| `relatorios/consumo/?sem_os=true` | consumo geral (desperdício) |

### Projetos, painel e exportações (F5)

| Endpoint | Notas |
| --- | --- |
| `GET projetos/` | `{kpis, colunas: {fase: [...]}}`; `?historico=true` → concluídos/cancelados |
| `POST/PATCH projetos/` | escrita só Gerente de TI / Admin (matriz) |
| `POST projetos/{id}/fase/` | `{fase, encerrado_em?, situacao_final?}` — concluir/cancelar sem data → 400 `encerramento_sem_data` |
| `projetos/{id}/marcos/`, `marcos/{m}/concluir/`, `alocacoes/`, `projetos/capacidade/` | |
| `GET relatorios/painel/?de=&ate=&setor=` | mês corrente por padrão; `kpis`, `horas_por_tipo`, `mini`, `risco_sla`, `retrabalho_por_motivo`, `consumo_por_setor`, `documentacao_pendente` |
| `GET relatorios/sla/`, `relatorios/auditoria/?objeto=tipo:id&acao=&usuario=` | |
| `POST apontamentos/{id}/recusar/`, `POST apontamentos/decidir-lote/` | `{ids, aprovar, motivo?}` — tudo ou nada |

### Integrações (F6)

Autenticação: `Authorization: Api-Key li_...` (criada por Admin em `POST integracoes/sistemas/`, exibida uma única vez; `rotacionar-chave/` para trocar). Escopos: `chamados:ler|escrever`, `almoxarifado:ler|escrever`, `eventos:ler`. Throttle 600/min.

| Endpoint | Notas |
| --- | --- |
| `POST integracoes/solicitacoes/` | `{solicitante: {matricula\|email\|username}, itens: [{codigo\|codigo_sankhya, quantidade}], centro_custo?, os_ref?, urgente?, origem?}` |
| `POST integracoes/chamados/` | `{solicitante, titulo, descricao, categoria (slug), prioridade?}` |
| `POST integracoes/itens/sync/` | lista para upsert por `codigo_sankhya`/`codigo` (cadastro mestre de ERP) |
| `POST integracoes/notas-fiscais/` | mesmo payload da NF interna → gera entradas |
| `GET integracoes/estoque/?setor=SIGLA` | itens com saldo |
| `GET integracoes/eventos/?desde=<id>` | polling dos eventos do próprio sistema |
| `integracoes/webhooks/` (Admin) | `{sistema, url, segredo, eventos: ["chamado.*", "solicitacao.aprovar"]}` — corpo assinado em `X-Assinatura` (HMAC-SHA256), `X-Evento`, `X-Evento-Id`; 8 tentativas com backoff 2^n min |
| `/api/schema/`, `/api/docs/`, `/api/redoc/` | OpenAPI 3 (drf-spectacular) |
| `/health/` | banco + cache para o balanceador |

Todo POST das rotas `integracoes/*` aceita `Idempotency-Key`: repetir devolve a resposta original com `Idempotent-Replayed: true`.

Como conectar um sistema (ex.: bot de WhatsApp): Admin cria o sistema com escopo `almoxarifado:escrever`, o bot chama `POST integracoes/solicitacoes/` com `origem: "whatsapp"` e `Idempotency-Key = id da mensagem`, e assina o webhook `solicitacao.*` para responder ao usuário quando aprovarem/atenderem.

## API (resumo)

Prefixo `/api/v1/`, JWT em `Authorization: Bearer`. Erros de regra retornam `409 {"erro": "...", "mensagem": "...", ...}`.

| Endpoint | Notas |
| --- | --- |
| `POST auth/token/`, `auth/token/refresh/`, `GET auth/me/` | `me` devolve papéis, permissões efetivas e o **menu** (decidido no servidor) |
| `GET/POST chamados/` | filtros `setor, status (ou "abertos"), prioridade, categoria (slug), responsavel, sla_vencido, busca`; resposta inclui `resumo` |
| `GET/PATCH chamados/{id}/` | prioridade e responsável passam por serviço (recalcula SLA / histórico) |
| `POST chamados/{id}/transicoes/` | `{"status": "...", "comentario": "..."}`; `entregue` valida documentação; `cancelado` exige Responsável+ e justificativa |
| `chamados/{id}/comentarios/`, `anexos/`, `historico/` | comentários `interno` só visíveis a TI |
| `GET chamados/risco-sla/` | vencimento em < 8h úteis |
| `categorias/`, `regras-sla/`, `permissoes/` | leitura para todos; escrita só Administrador |

## Decisões desta fase (registrar no PR)

- Papéis e matriz padrão são garantidos por `post_migrate` idempotente (`core/signals.py`) em vez de data migration numerada, para não depender da ordem do `makemigrations`.
- A matriz do `04-API-E-PERMISSOES.md §9` prevalece sobre o exemplo JSON de `/auth/me/` (que omite Compras para Gerente de TI; a matriz dá "V").
- Categoria sem `RegraSLA` cadastrada usa o padrão Crítica 4 · Alta 24 · Média 48 · Baixa 72.
- Não sobreposição usa `ExclusionConstraint` nativo do Django (gerado pelo `makemigrations`) em vez de `RunSQL`; `tstzrange(inicio, NULL)` já é aberto até o infinito, dispensando o `COALESCE`.
- `Apontamento.tipo_exige_causa` é denormalizado em `save()` — é espelho do cadastro, não regra de fluxo; a regra fica em `services._validar_causa` e na `CheckConstraint`.
- Cobertura = seções obrigatórias publicadas ÷ (4 × chamados entregues no período), para toda categoria. Nas que não exigem documentação isso não bloqueia nada, só puxa o percentual para baixo — é o que a regra §5 descreve.
- Busca cobre chamados e projetos; itens e solicitações entram na F4 (`busca/services.py` já deixa o lugar).
- `Movimento.sinal` (±1) foi adicionado ao modelo do handoff: `quantidade` é sempre positiva (constraint) e AJUSTE precisa de direção. Entradas/saídas têm o sinal travado por `CheckConstraint`.
- `fechar_inventario` mede a divergência contra o saldo **atual**, não o do snapshot: movimentos feitos entre abertura e fechamento não viram ajuste fantasma.
- Cadastro de item é global (não escopado); o que é escopado é o saldo. Colaborador solicita; Responsável/Compras/Admin movimentam; Gerentes leem e aprovam solicitações do setor. **Isso é imposto**, não só documentado: `PodeMovimentar` nas rotas que geram movimento (saída/ajuste, transferência, atender solicitação) e os botões escondidos na tela para quem não movimenta.
- `Movimento` ganhou `sinal` (±1) separado de `quantidade` (> 0): ajuste de inventário para menos continua respeitando `mov_qtd_positiva` e a reconciliação vira `Σ quantidade × sinal`.
- `fechar_inventario` compara o contado com o saldo **atual**, não com o snapshot — se houve movimento entre abertura e fechamento, o ajuste não desfaz esse movimento.
- Alerta de mínimo vai por `transaction.on_commit` → task idempotente (um `AlertaReposicao` aberto por item/setor); task diária resolve os que voltaram acima do mínimo.
- "Horas previstas" do KPI 1 = Σ `capacidade_diaria_min` das pessoas de TI ativas para apontamento × dias úteis do período (o handoff não define; é o único número derivável do que já existe).
- Implantar projeto sem seção "Regra de negócio" publicada **avisa** (registro em auditoria), não bloqueia — o modal do handoff fala em exigência, mas bloquear precisa de decisão de produto.
- Apontamento recusado (`recusado_em` + `motivo_recusa`) sai dos indicadores e permanece visível ao autor.
- Eventos de integração são **derivados da auditoria** (`core.auditoria.registrar` → `integracoes.eventos.publicar`): nenhum serviço precisa saber que existe webhook, e o catálogo de eventos é exatamente o catálogo de ações auditadas.
- Status de chamado é `readonly` no Django admin — transição só pelo serviço, para que o bloqueio por documentação valha "por nenhuma via".
#   s i s t e m a _ i n t e r n o 
 
 