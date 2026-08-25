# CLAUDE.md — Sistema Interno Life Laboral

Instruções permanentes para este repositório. Ler junto com `01`…`07` do pacote de handoff.

## Contexto

Sistema interno da Life Laboral que unifica chamados/tarefas, apontamento de horas por tipo de trabalho, documentação obrigatória, almoxarifado setorial e portfólio de projetos de TI. 11 setores, 6 papéis. O valor do sistema está nas **regras** (retrabalho visível, entrega bloqueada sem documentação, saldo confiável por centro de custo) — não na UI.

## Stack

Python 3.12 · Django 5.1 · DRF · PostgreSQL 16 · Celery + Redis · HTMX/Alpine (ou React nos kanbans, se decidido). Gerenciador: `uv`. Lint: `ruff`. Testes: `pytest-django` + `factory_boy`.

## Regras de código

- **Regra de negócio vive em `services.py`.** Views, serializers, tasks e admin apenas chamam serviços. Nunca escrever regra em `save()`, em signal ou na view.
- **Toda regra de integridade também é constraint no banco.** Se a regra pode ser burlada por `Model.objects.update()`, falta constraint.
- **`Estoque.saldo` só é escrito por `almoxarifado.services.registrar_movimento()`**, com `select_for_update()` dentro de `transaction.atomic()`. `Movimento` é imutável — correção é ajuste novo.
- **Um cronômetro aberto por usuário**, garantido por `UniqueConstraint` parcial; apontamentos do mesmo usuário não podem se sobrepor (`EXCLUDE USING gist`).
- **Retrabalho sem motivo não existe** — validação no serviço e `CheckConstraint`.
- Consultas de leitura/agregação em `selectors.py`. Nada de agregação dentro de `@property` usada em listagem (N+1).
- Toda listagem usa `select_related`/`prefetch_related` explícitos.
- Toda escrita de estado grava `core.Auditoria` com `antes`/`depois`.
- Permissão em duas camadas: classe DRF (pode a ação?) + queryset escopado por setor (vê o quê?). Nunca só uma.
- Números de documento (`TI-2026-0341`, `SOL-2026-0912`) vêm de sequência do PostgreSQL, nunca de `count() + 1`.
- Dinheiro e quantidade em `Decimal`; duração sempre em **minutos inteiros**, nunca float de horas.
- `pt-BR`, `America/Sao_Paulo`, `USE_TZ = True`. Nomes de campos e modelos em português; código, docstrings e commits em português.

## Testes

Todo serviço tem teste do caminho feliz e do caminho de recusa. Obrigatórios (não remover):

- concorrência de saída de estoque não gera saldo negativo;
- reconciliação `Estoque.saldo == Σ movimentos` sobre o seed;
- entrega de chamado de desenvolvimento sem documentação é recusada;
- retrabalho sem motivo é recusado pela API e pelo banco;
- apontamentos sobrepostos são recusados;
- cada papel só enxerga o próprio escopo em todos os endpoints de listagem.

Cobertura mínima: 80% no app tocado, com foco em `services.py`.

## Front-end

Importar os tokens de `static/css/tokens/` (cópia de `referencias/_ds/tokens/`) e usar **aliases semânticos** (`--color-primary`, `--text-body`, `--border-subtle`) — nunca hex literal nem token cru de marca. Fonte Manrope; números, códigos e horas em IBM Plex Mono. Card: raio 16px, padding 22px 24px, `--shadow-sm`, borda `--border-subtle`. Menu montado a partir de `/auth/me/`, não decidido no cliente.

Erros de regra (saldo insuficiente, documentação incompleta, conflito de horas) aparecem como **modal com causa e caminho de correção**, nunca toast genérico.

## O que não fazer

- Não permitir `UPDATE`/`DELETE` de `Movimento`, `VersaoDocumento` ou `Auditoria` (admin inclusive).
- Não recalcular saldo varrendo movimentos em requisição de usuário.
- Não exigir mais de dois campos para apontar hora — adoção depende disso.
- Não bloquear entrega por documentação em categorias que não a exigem.
- Não criar chamado ou solicitação a partir de mensagem de WhatsApp/IA sem revisão humana.
- Não introduzir dependência nova sem justificar no PR.
