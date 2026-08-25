# 04 — API e permissões

Prefixo `/api/v1/`. JWT (`Authorization: Bearer <token>`), paginação por cursor, filtros `django-filter`, ordenação por `?ordering=`. Erros seguem `{"detail": "..."}` ou `{"campo": ["mensagem"]}`; conflitos de regra usam **409** com corpo estruturado.

## 1. Autenticação

| Endpoint | Método | Retorno |
| --- | --- | --- |
| `/auth/token/` | POST | `{access, refresh}` |
| `/auth/token/refresh/` | POST | `{access}` |
| `/auth/me/` | GET | usuário, setor, papéis, permissões efetivas e itens de menu visíveis |

`/auth/me/` é o que monta a navegação do front — o menu **não** deve ser decidido no cliente:

```json
{
  "id": 41, "nome": "Diego Martins", "matricula": "0417",
  "setor": {"id": 11, "nome": "TI", "sigla": "TI"},
  "papeis": ["GerenteTI"],
  "permissoes": {"ver_painel": true, "ver_projetos": true, "ver_compras": false,
                 "ver_config": false, "todos_setores": true, "aprovar_horas": true},
  "menu": ["painel", "tarefas", "tarefa", "projetos", "almoxarifado"]
}
```

## 2. Chamados

| Endpoint | Métodos | Notas |
| --- | --- | --- |
| `/chamados/` | GET, POST | filtros: `setor`, `status`, `prioridade`, `categoria`, `responsavel`, `sla_vencido`, `busca` |
| `/chamados/{id}/` | GET, PATCH | PATCH só campos editáveis pelo papel |
| `/chamados/{id}/transicoes/` | POST | `{"status": "entregue", "comentario": "..."}` — máquina de estados |
| `/chamados/{id}/comentarios/` | GET, POST | `interno` só para TI |
| `/chamados/{id}/anexos/` | GET, POST | multipart, máx. 20 MB |
| `/chamados/{id}/historico/` | GET | timeline |
| `/categorias/`, `/regras-sla/` | GET; PUT (Admin) | tela de configuração |

Máquina de estados (transições válidas):

```
novo → triagem → fila → execucao → testes → entregue
                    ↑         ↓
                    └── aguarda ──┘
qualquer → cancelado (Responsável+, com justificativa)
```

`entregue` valida documentação (regra §5). Resposta de bloqueio:

```json
409 {"erro": "documentacao_incompleta",
     "faltando": ["Regra de negócio", "Como foi testado"],
     "mensagem": "Publique as seções obrigatórias antes de entregar."}
```

## 3. Apontamentos e cronômetro

| Endpoint | Métodos | Notas |
| --- | --- | --- |
| `/apontamentos/` | GET, POST | POST = lançamento manual (`inicio`, `fim` obrigatórios) |
| `/apontamentos/{id}/aprovar/` | POST | Gerente do setor / Gerente de TI |
| `/apontamentos/pendentes/` | GET | fila de aprovação |
| `/cronometro/` | GET | cronômetro aberto do usuário (ou `null`) |
| `/cronometro/iniciar/` | POST | `{tipo, chamado|projeto, motivo_retrabalho?, detalhe_retrabalho?}` |
| `/cronometro/parar/` | POST | fecha e devolve os minutos |
| `/tipos-trabalho/`, `/motivos-retrabalho/` | GET | cadastros |

Resposta de `iniciar` quando havia outro rodando:

```json
201 {"apontamento": {...},
     "pausado": {"tipo": "Desenvolvimento", "minutos": 72, "fim": "2026-08-24T14:32:00-03:00"}}
```

## 4. Documentação

| Endpoint | Métodos | Notas |
| --- | --- | --- |
| `/documentos/?chamado=` | GET, POST | uma linha por seção |
| `/documentos/{id}/versoes/` | GET, POST | append-only; POST cria rascunho |
| `/documentos/{id}/versoes/{n}/publicar/` | POST | passa a ser `versao_atual` |
| `/documentos/cobertura/?setor=&periodo=` | GET | percentual do painel |

## 5. Almoxarifado

| Endpoint | Métodos | Notas |
| --- | --- | --- |
| `/almoxarifado/itens/` | GET, POST, PATCH | filtros: `setor`, `abaixo_minimo`, `busca` |
| `/almoxarifado/estoque/?setor=` | GET | saldo por item/setor |
| `/almoxarifado/movimentos/` | GET, POST | **sem PUT/PATCH/DELETE**; POST usa `registrar_movimento` |
| `/almoxarifado/solicitacoes/` | GET, POST | itens no mesmo payload |
| `/almoxarifado/solicitacoes/{id}/aprovar/` | POST | Gerente do setor |
| `/almoxarifado/solicitacoes/{id}/atender/` | POST | gera saídas; parcial permitido |
| `/almoxarifado/notas-fiscais/` | GET, POST | POST gera entradas de todos os itens |
| `/almoxarifado/transferencias/` | GET, POST | dois movimentos atômicos |
| `/almoxarifado/inventarios/` | GET, POST | abre com snapshot dos saldos |
| `/almoxarifado/inventarios/{id}/contagens/` | PATCH | grava `saldo_contado` |
| `/almoxarifado/inventarios/{id}/fechar/` | POST | gera ajustes, devolve divergências |
| `/almoxarifado/cotacoes/` | GET, POST | + `/propostas/{id}/escolher/` |
| `/almoxarifado/qrcode/{codigo}/` | GET | leitura por QR → item + saldo do setor |

Erro de saldo:

```json
409 {"erro": "saldo_insuficiente", "item": "MRO-4471",
     "saldo": 4, "pedido": 6, "mensagem": "Saldo insuficiente em Manutenção."}
```

## 6. Projetos

| Endpoint | Métodos | Notas |
| --- | --- | --- |
| `/projetos/` | GET, POST, PATCH | `?historico=true` traz concluídos/cancelados |
| `/projetos/{id}/fase/` | POST | move no kanban; valida encerramento com data |
| `/projetos/{id}/marcos/`, `/alocacoes/` | GET, POST | |

## 7. Relatórios e exportações

| Endpoint | Conteúdo |
| --- | --- |
| `/relatorios/painel/` | todos os KPIs da tela de indicadores em uma chamada |
| `/relatorios/horas/?de=&ate=&setor=&tipo=` | horas por tipo, por pessoa, por chamado |
| `/relatorios/retrabalho/?de=&ate=` | horas e % de retrabalho por motivo e por origem |
| `/relatorios/consumo/?setor=&sem_os=` | consumo por centro de custo; desperdício |
| `/relatorios/sla/?de=&ate=` | cumprimento por categoria e prioridade |
| `/relatorios/auditoria/?objeto=` | histórico de mudanças |

Todos aceitam `?formato=json|csv|xlsx|pdf`. Acima de 5.000 linhas a resposta é `202 {"job_id"}` e o arquivo vai por e-mail (`relatorios.gerar_export`).

## 8. Busca global

`/busca/?q=` — retorna no máximo 5 resultados por tipo (chamado, projeto, item, solicitação), com `tipo`, `titulo`, `subtitulo`, `url`. Usa full-text português + trigram, escopado pelo papel.

## 9. Permissões

Papéis são `Group`. A checagem é em duas camadas: **classe de permissão** (pode chamar a ação?) e **queryset escopado** (vê quais registros?). Nunca só uma.

```python
class PodeAprovarHoras(BasePermission):
    def has_permission(self, request, view):
        return request.user.groups.filter(name__in=["GerenteSetor", "GerenteTI", "Administrador"]).exists()

class SetorScopedQuerysetMixin:
    campo_setor = "setor"
    def get_queryset(self):
        qs = super().get_queryset()
        u = self.request.user
        if u.groups.filter(name__in=["Compras", "Administrador", "GerenteTI"]).exists():
            return qs
        return qs.filter(**{self.campo_setor: u.setor})
```

### Matriz de módulos (tela "SLA e permissões", Admin)

Legenda: **E** = editar · **V** = ver · **—** = sem acesso

| Módulo | Colaborador | Responsável | Gerente setor | Gerente TI | Compras | Admin |
| --- | --- | --- | --- | --- | --- | --- |
| Painel de indicadores | — | V | V | E | V | E |
| Central de tarefas | E (suas) | E (setor) | V (setor) | E | V | E |
| Tarefa em andamento / horas | E (suas) | V | V + aprova | E + aprova | — | E |
| Documentação | E (suas) | E (setor) | V | E | — | E |
| Almoxarifado | E (solicita) | E (setor) | V (setor) | V | E (todos) | E |
| Compras | — | — | V | V | E | E |
| Projetos de TI | — | V | V | E | V | E |
| SLA e permissões | — | — | — | — | — | E |

A matriz é **dado**, não código: tabela `core.PermissaoModulo (papel, modulo, nivel)` editável pelo Admin na tela de configuração, lida pelas classes de permissão com cache de 60s.

## 10. Regras transversais da API

- Toda escrita que muda estado passa por serviço e grava `core.Auditoria`.
- `select_related`/`prefetch_related` obrigatórios nas listagens do protótipo (a tela de tarefas mostra 8 colunas com dados de 4 tabelas).
- Idempotência: POSTs de integração aceitam header `Idempotency-Key`.
- Throttle: 1.000 req/h por usuário; 60/min em `/busca/`.
