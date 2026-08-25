# 07 — Plano de implementação

6 fases, ~17 semanas. Cada fase entrega algo usável e tem critério de aceite verificável. **Não pular a ordem F1 → F2 → F3** (chamado → horas → documentação são dependentes).

---

## F1 — Fundação e chamados (3 semanas)

1. Projeto Django + settings por ambiente + docker-compose + CI.
2. `core`: `User` custom, `Setor` (11), `CentroCusto`, `Auditoria`, grupos/papéis, calendário de horas úteis, extensões `btree_gist` e `pg_trgm`.
3. `chamados`: modelos, máquina de estados, `RegraSLA`, cálculo de SLA, histórico, comentários, anexos.
4. API `/auth/*`, `/chamados/*` + permissões e queryset escopado.
5. Telas: Central de tarefas, Tarefa (só meta + histórico + comentários), modal Novo chamado.
6. `seed_demo` com os números do protótipo.

**Aceite:** abrir chamado como Colaborador de Produção, triar e atribuir como Gerente de TI, entregar; SLA de Crítica aberta sexta 16:00 cai na segunda 11:00; Colaborador não vê chamado de outro setor pela API.

---

## F2 — Horas, cronômetro e retrabalho (3 semanas)

1. `apontamentos`: modelos, constraint de cronômetro único, `EXCLUDE` de não sobreposição, tipos e motivos.
2. Serviços: `iniciar_cronometro`, `parar`, `criar_apontamento` (manual), `aprovar_apontamento`.
3. API `/cronometro/*`, `/apontamentos/*`, `/apontamentos/pendentes/`.
4. Telas: card de apontamento na Tarefa, modal de lançamento manual (com avisos de conflito e capacidade), modal de aprovação.
5. Relatório `/relatorios/horas/` + `/relatorios/retrabalho/`.

**Aceite:** iniciar Desenvolvimento e depois Testes → o primeiro fecha sozinho e o total do dia fecha sem sobreposição; retrabalho sem motivo é recusado pela API e pelo banco; 9h manuais ficam pendentes e só entram no relatório após aprovação.

---

## F3 — Documentação e bloqueio de entrega (2 semanas)

1. `documentacao`: `Documento`, `VersaoDocumento` append-only, requisitos por categoria.
2. `pode_entregar()` integrado a `entregar_chamado()`; resposta 409 estruturada.
3. Cobertura documental (`selectors`) para o painel.
4. Telas: card de documentação, editor por seção com versões, modal de bloqueio de entrega.

**Aceite:** chamado de desenvolvimento sem "Como foi testado" não é entregável por nenhuma via (API, admin, tela); chamado de suporte sem documento entrega normalmente e a cobertura do painel cai.

---

## F4 — Almoxarifado (4 semanas)

1. Modelos completos + `Estoque` materializado + constraints.
2. `registrar_movimento()` como ponto único de escrita, com `select_for_update`; movimento imutável.
3. Serviços: `atender_solicitacao`, `entrada_por_nota`, `transferir`, `abrir/fechar_inventario`, `cotacao`.
4. API `/almoxarifado/*` (sem PUT/DELETE em movimentos) + QR Code.
5. Telas: Almoxarifado completo e os 4 modais (solicitar, nota fiscal, transferência, inventário) + leitura de QR.
6. Alertas de mínimo (signal + task) e resumo diário.

**Aceite:** teste de concorrência não gera saldo negativo; reconciliação `Estoque.saldo == Σ movimentos` passa sobre todo o seed; saída sem centro de custo/OS/projeto é recusada; inventário com 2 divergências gera 2 ajustes e o impacto em R$ confere.

---

## F5 — Projetos, painel e exportações (2 semanas)

1. `projetos`: modelos, 8 fases no kanban, histórico, marcos, alocação.
2. `relatorios`: `/painel/`, `/consumo/`, `/sla/`, `/auditoria/`; export CSV/XLSX/PDF + job assíncrono acima de 5.000 linhas.
3. Telas: Projetos, Histórico, Painel de indicadores, Compras, busca global, modal Exportar, tela de Histórico de mudanças.
4. Tela SLA e permissões (Admin) com recálculo ao vivo e matriz editável.

**Aceite:** todo KPIs do painel confere com consulta bruta no banco; mover projeto para Concluído sem data é recusado; matriz de permissões alterada muda o menu no próximo `/auth/me/`.

---

## F6 — Integrações (3 semanas)

**Depende das 4 decisões abertas — confirmar com o time de TI antes de começar.**

1. Sankhya: client, mapeamento de itens (`codigo_sankhya`), sync noturno idempotente por `hash_payload`, log em `SincronizacaoSankhya`, tela de conflitos.
2. WhatsApp: webhook, `MensagemWhatsApp` com payload cru em JSONB, identificação do remetente por telefone, fila de triagem.
3. IA: `classificar_mensagem` sugerindo categoria/prioridade/setor/itens com nível de confiança — **sempre** com revisão humana antes de criar chamado ou solicitação.

**Aceite:** reenviar o mesmo payload não duplica nada; nenhuma mensagem se transforma em chamado sem `revisada_por` preenchido; falha de rede na Sankhya não perde movimento (retry com backoff e log).

---

## Riscos e cuidados

| Risco | Mitigação |
| --- | --- |
| Saldo divergente por escrita fora do serviço | Escrita de `Estoque` só em `registrar_movimento`; teste de reconciliação no CI; admin somente leitura |
| Rejeição do apontamento pelos técnicos | Cronômetro com 1 clique, pausa automática, lançamento manual como exceção; nunca exigir mais de 2 campos |
| Documentação virar burocracia | Só 4 seções obrigatórias e só em 2 categorias; texto curto aceito |
| Retrabalho virar punição | Relatório por **motivo**, não por pessoa; expor "requisito incompleto" como causa dominante |
| Sankhya como fonte dupla de verdade | Definir direção única por entidade antes da F6; até lá, sistema é a verdade do consumo interno |
| Migrations com constraint em base já populada | Aplicar `EXCLUDE`/`CHECK` com `RunSQL` + limpeza prévia dos dados do seed |

## Definição de pronto (toda tarefa)

- Regra implementada em `services.py`, não na view.
- Constraint equivalente no banco quando a regra for de integridade.
- Teste que falha sem a regra (`pytest`), incluindo o caminho de erro.
- Auditoria gravada nas ações de escrita.
- Tela conferida contra o protótipo (tokens, copy, estados vazio/carregando/erro).
- `ruff` e `mypy` limpos; cobertura ≥ 80% no app tocado.
