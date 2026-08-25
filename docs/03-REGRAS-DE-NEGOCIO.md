# 03 — Regras de negócio

Cada regra tem: **onde vive**, **como se comporta** e **o teste que a comprova**. Estas regras são o produto — se uma delas puder ser burlada pela API, a implementação está errada.

---

## 1. Retrabalho exige causa

**Onde:** `apontamentos/services.py::criar_apontamento()` + `CheckConstraint` no banco.

Se `tipo.exige_causa` é `True`, `motivo_retrabalho` é obrigatório e `detalhe_retrabalho` precisa de no mínimo 15 caracteres. Recusar com `400 {"motivo_retrabalho": "Obrigatório para retrabalho."}`.

```python
# constraint (Meta.constraints de Apontamento) — depende de campo denormalizado
# tipo_exige_causa, preenchido no save() a partir do TipoTrabalho:
models.CheckConstraint(
    check=Q(tipo_exige_causa=False) | Q(motivo_retrabalho__isnull=False),
    name="ap_retrabalho_tem_causa")
```

**Teste:** POST de apontamento tipo Retrabalho sem motivo → 400; com motivo → 201 e `Apontamento.motivo_retrabalho_id` preenchido. Tentativa de `UPDATE` direto no banco limpando o motivo → `IntegrityError`.

---

## 2. Cronômetro exclusivo por usuário

**Onde:** `apontamentos/services.py::iniciar_cronometro()`.

Ao iniciar um cronômetro, o cronômetro aberto do mesmo usuário é **fechado automaticamente na mesma transação** e retornado na resposta (o front mostra "Desenvolvimento pausado às 14:32 — 1h12 registradas").

```python
@transaction.atomic
def iniciar_cronometro(*, usuario, tipo, chamado=None, projeto=None, **causa):
    anterior = (Apontamento.objects.select_for_update()
                .filter(usuario=usuario, fim__isnull=True).first())
    if anterior:
        fechar_apontamento(anterior, fim=timezone.now())
    if tipo.exige_causa and not causa.get("motivo_retrabalho"):
        raise CausaObrigatoria(tipo)
    return Apontamento.objects.create(usuario=usuario, tipo=tipo, chamado=chamado,
                                      projeto=projeto, inicio=timezone.now(), **causa)
```

Garantia estrutural: `UniqueConstraint(fields=["usuario"], condition=Q(fim__isnull=True))`.

**Teste:** dois `iniciar_cronometro` seguidos → só um apontamento com `fim=None`; o primeiro tem `minutos > 0`. Duas requisições concorrentes → uma vence, a outra não cria segundo registro aberto.

---

## 3. Horas não se sobrepõem

**Onde:** constraint no banco (`RunSQL`) + validação no serviço para dar mensagem legível.

```sql
ALTER TABLE apontamentos_apontamento
ADD CONSTRAINT ap_sem_sobreposicao
EXCLUDE USING gist (
  usuario_id WITH =,
  tstzrange(inicio, COALESCE(fim, 'infinity'::timestamptz)) WITH &&
);
```

**Teste:** lançamento manual 08:00–12:00 e depois 11:00–13:00 para o mesmo usuário → 400 com a mensagem "Conflita com apontamento de Análise (08:00–12:00)".

---

## 4. Lançamento manual acima da capacidade exige aprovação

**Onde:** `apontamentos/services.py::criar_apontamento(lancamento_manual=True)`.

Se a soma do dia (após inclusão) passar de `usuario.capacidade_diaria_min` (480 por padrão), o apontamento é criado com `aprovado_por=None` e status pendente; **não entra nos indicadores** até ser aprovado por Gerente do setor ou Gerente de TI. Lançamento retroativo com mais de 7 dias sempre exige aprovação, independente da carga.

**Teste:** 9h no mesmo dia → apontamento pendente e ausente do relatório de horas; após `aprovar_apontamento()` → aparece.

---

## 5. Documentação bloqueia a entrega

**Onde:** `chamados/services.py::entregar_chamado()` e `Chamado.pode_entregar()`.

Se `chamado.categoria.exige_documentacao` (desenvolvimento e mudança de regra de negócio), a transição para `ENTREGUE` só ocorre com **todas** as seções obrigatórias (Contexto, Regra de negócio, Solução, Como foi testado) tendo uma `VersaoDocumento` com `publicada_em` preenchido.

```python
def pode_entregar(chamado) -> tuple[bool, list[str]]:
    if not chamado.categoria.exige_documentacao:
        return True, []
    faltando = [s for s in SECOES_OBRIGATORIAS
                if not chamado.documentos.filter(secao=s, versao_atual__publicada_em__isnull=False).exists()]
    return not faltando, faltando
```

Nas outras categorias, a ausência **não bloqueia**: apenas reduz o percentual de cobertura exibido no painel (`documentos publicados / seções aplicáveis`).

**Teste:** chamado de categoria `desenvolvimento` sem seção "Como foi testado" → `POST /transicoes/ {status: entregue}` retorna 409 com a lista das seções faltantes. Chamado de `suporte` sem documento nenhum → entrega permitida, cobertura do painel cai.

---

## 6. SLA em horas úteis

**Onde:** `core/calendario.py` + `chamados/services.py::abrir_chamado()`.

`sla_previsto = calendario.somar_horas_uteis(criado_em, RegraSLA(categoria, prioridade).horas_uteis)`, jornada 08:00–17:00 com 1h de almoço, seg–sex, feriados nacionais + municipais (tabela editável), fuso `America/Sao_Paulo`.

Mudança de prioridade **recalcula** o SLA a partir da abertura original (não da mudança) e registra no histórico. `sla_cumprido` é gravado na entrega (`entregue_em <= sla_previsto`). A task `chamados.verificar_sla` roda a cada 15 min e marca vencidos (`sla_cumprido=False`) sem fechar o chamado.

**Teste:** chamado Crítica (4h úteis) aberto sexta 16:00 → SLA na segunda 11:00 (considerando jornada e fim de semana).

---

## 7. Saldo de estoque nunca fica negativo

**Onde:** `almoxarifado/services.py::registrar_movimento()` — **ponto único de escrita de saldo**.

```python
@transaction.atomic
def registrar_movimento(*, item, setor, tipo, quantidade, usuario, centro_custo=None, **ref):
    if quantidade <= 0:
        raise QuantidadeInvalida()
    estoque, _ = Estoque.objects.select_for_update().get_or_create(item=item, setor=setor)
    delta = quantidade if tipo in ENTRADAS else -quantidade
    novo = estoque.saldo + delta
    if novo < 0:
        raise SaldoInsuficiente(item=item, saldo=estoque.saldo, pedido=quantidade)
    estoque.saldo = novo
    estoque.save(update_fields=["saldo", "atualizado_em"])
    mov = Movimento.objects.create(item=item, setor=setor, tipo=tipo, quantidade=quantidade,
                                   saldo_apos=novo, centro_custo=centro_custo,
                                   usuario=usuario, **ref)
    if novo <= item.estoque_minimo:
        alertar_estoque_minimo.delay(item.id, setor.id)   # signal/task, fora da transação lógica
    return mov
```

Movimento é **imutável**: sem `update`/`delete` na API nem no admin (`has_change_permission = has_delete_permission = False`). Correção = novo movimento de `AJUSTE` com justificativa.

**Teste:** duas saídas concorrentes de 6 unidades com saldo 10 → uma passa, a outra recebe `SaldoInsuficiente`; saldo final 4. `Estoque.saldo` sempre igual à soma dos movimentos (teste de reconciliação sobre o seed).

---

## 8. Consumo exige centro de custo

**Onde:** `registrar_movimento()` para `tipo=SAIDA`.

Toda saída precisa de **pelo menos um** entre: `centro_custo`, `chamado`, `projeto` ou `os_ref`. Quando vem de solicitação, herda o centro de custo dela. Saída sem OS e sem projeto é classificada como **consumo geral do setor** e alimenta o relatório de desperdício que Compras acompanha.

**Teste:** saída sem nenhuma referência → 400. Relatório `/relatorios/consumo/?sem_os=true` traz exatamente os movimentos de consumo geral.

---

## 9. Transferência entre setores

**Onde:** `almoxarifado/services.py::transferir()` — dois movimentos (`TRANSF_SAIDA` + `TRANSF_ENTRADA`) na mesma transação, mesmo `quantidade`, setores diferentes.

Se o saldo da origem ficar abaixo do mínimo, a operação **não é bloqueada** — é marcada (`fura_minimo_origem=True`), o front exibe o alerta amarelo e Compras recebe o item na fila de reposição.

**Teste:** transferência de 8 com saldo 10 e mínimo 5 → executa, `fura_minimo_origem=True`, alerta enfileirado; saldo destino +8.

---

## 10. Inventário cíclico

**Onde:** `almoxarifado/services.py::fechar_inventario()`.

Ao fechar, cada `ContagemInventario` com `saldo_contado != saldo_sistema` gera um movimento `AJUSTE` com `justificativa="Inventário #<id>"`, e o inventário grava `divergencias` (contagem de itens divergentes) e `impacto_valor` (Σ |divergência| × custo unitário). Itens sem contagem informada são ignorados, não zerados.

**Teste:** inventário com 5 itens, 2 divergentes → 2 movimentos de ajuste, `divergencias=2`, `impacto_valor` conferindo com o cálculo manual, saldos iguais ao contado.

---

## 11. Numeração sequencial

`Chamado.numero` = `TI-{ano}-{seq:04d}`, `Solicitacao.numero` = `SOL-{ano}-{seq:04d}`. Gerar com sequência do PostgreSQL por ano (`SELECT nextval`), nunca com `count()+1`.

**Teste:** 50 criações concorrentes → 50 números distintos e sem lacuna dentro do ano.

---

## 12. Escopo de dados por papel

**Onde:** `core/mixins.py::SetorScopedQuerysetMixin` — aplicado em **todo** viewset.

| Papel | Chamados | Apontamentos | Almoxarifado | Projetos |
| --- | --- | --- | --- | --- |
| Colaborador | os que abriu ou é responsável | só os seus | itens/solicitações do seu setor | — |
| Responsável do setor | do seu setor | do seu setor (leitura) | movimenta o seu setor | leitura |
| Gerente do setor | do seu setor | do seu setor + aprova | leitura do seu setor | leitura |
| Gerente de TI | todos | todos + aprova | leitura | escrita |
| Compras | leitura | — | todos os setores, NF/cotação/inventário | leitura |
| Administrador | todos | todos | todos | todos |

**Teste:** cada papel em um teste parametrizado consultando `/api/v1/chamados/` — nenhum ID fora do escopo aparece; tentativa de `PATCH` fora do escopo → 403/404 (nunca 200).

---

## 13. Auditoria

Toda transição de status, aprovação, movimento de estoque e mudança de SLA/permissão grava `core.Auditoria` com `antes`/`depois`. A tela "Histórico de mudanças" lê essa tabela.

**Teste:** entregar um chamado gera exatamente um registro com `acao="chamado.entregar"`, `antes.status="testes"`, `depois.status="entregue"`.
