# 02 — Modelo de dados

Todas as tabelas herdam:

```python
class TimeStampedModel(models.Model):
    criado_em = models.DateTimeField(auto_now_add=True, db_index=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    criado_por = models.ForeignKey("core.User", null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name="+")
    class Meta:
        abstract = True
```

Convenções: nomes de campo em português; `TextChoices` para enums; `on_delete=PROTECT` em cadastros, `CASCADE` só em filhos de agregado (comentário, item de nota, versão de documento).

---

## 1. core

```python
class Setor(TimeStampedModel):
    nome = models.CharField(max_length=60, unique=True)
    sigla = models.CharField(max_length=6, unique=True)
    responsavel = models.ForeignKey("core.User", null=True, on_delete=models.SET_NULL, related_name="setores_responsavel")
    ativo = models.BooleanField(default=True)
```

11 registros iniciais: Manutenção (MAN), Produção (PRD), Expedição (EXP), Qualidade (QLD), Cobrança (COB), Financeiro (FIN), Marketing (MKT), Comercial (COM), RH (RH), Compras (CMP), TI (TI).

```python
class CentroCusto(TimeStampedModel):
    codigo = models.CharField(max_length=10, unique=True)   # ex.: "2001", "3102"
    descricao = models.CharField(max_length=120)
    setor = models.ForeignKey(Setor, on_delete=models.PROTECT, related_name="centros_custo")
    projeto = models.ForeignKey("projetos.Projeto", null=True, blank=True, on_delete=models.SET_NULL)
    ativo = models.BooleanField(default=True)

class Auditoria(models.Model):
    """Append-only. Escrita por mixin nas views e pelos serviços."""
    quando = models.DateTimeField(auto_now_add=True, db_index=True)
    usuario = models.ForeignKey("core.User", null=True, on_delete=models.SET_NULL)
    acao = models.CharField(max_length=60)                  # "chamado.entregar"
    objeto_tipo = models.CharField(max_length=60)
    objeto_id = models.CharField(max_length=40)
    antes = models.JSONField(null=True, blank=True)
    depois = models.JSONField(null=True, blank=True)
    class Meta:
        indexes = [models.Index(fields=["objeto_tipo", "objeto_id", "-quando"])]
```

---

## 2. chamados

```python
class Categoria(models.Model):
    nome = models.CharField(max_length=60, unique=True)
    exige_documentacao = models.BooleanField(default=False)   # True: desenvolvimento, regra de negócio
    slug = models.SlugField(unique=True)
```

Categorias iniciais: `desenvolvimento` (exige), `regra_negocio` (exige), `suporte`, `acesso`, `infraestrutura`, `relatorio`, `integracao`, `melhoria`.

```python
class Chamado(TimeStampedModel):
    class Prioridade(models.TextChoices):
        CRITICA = "critica", "Crítica"; ALTA = "alta", "Alta"
        MEDIA = "media", "Média";       BAIXA = "baixa", "Baixa"

    class Status(models.TextChoices):
        NOVO = "novo", "Novo"
        TRIAGEM = "triagem", "Em triagem"
        FILA = "fila", "Na fila"
        EXECUCAO = "execucao", "Em execução"
        TESTES = "testes", "Em testes"
        AGUARDA_SOLICITANTE = "aguarda", "Aguardando solicitante"
        ENTREGUE = "entregue", "Entregue"
        CANCELADO = "cancelado", "Cancelado"

    numero = models.CharField(max_length=12, unique=True)      # "TI-2026-0341"
    titulo = models.CharField(max_length=180)
    descricao = models.TextField()
    setor_origem = models.ForeignKey("core.Setor", on_delete=models.PROTECT, related_name="chamados_abertos")
    solicitante = models.ForeignKey("core.User", on_delete=models.PROTECT, related_name="chamados_solicitados")
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT)
    prioridade = models.CharField(max_length=10, choices=Prioridade.choices)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.NOVO)
    responsavel = models.ForeignKey("core.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="chamados_atribuidos")
    projeto = models.ForeignKey("projetos.Projeto", null=True, blank=True, on_delete=models.SET_NULL, related_name="chamados")
    horas_previstas_min = models.PositiveIntegerField(default=0)
    sla_previsto = models.DateTimeField(null=True, blank=True)
    sla_cumprido = models.BooleanField(null=True, blank=True)  # null = ainda aberto
    entregue_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["status", "responsavel"]),
                   models.Index(fields=["setor_origem", "status"]),
                   models.Index(fields=["sla_previsto"])]

class RegraSLA(models.Model):
    categoria = models.ForeignKey(Categoria, on_delete=models.CASCADE)
    prioridade = models.CharField(max_length=10, choices=Chamado.Prioridade.choices)
    horas_uteis = models.PositiveIntegerField()
    class Meta:
        constraints = [models.UniqueConstraint(fields=["categoria", "prioridade"], name="uniq_sla_cat_prio")]
```

Padrão de SLA do protótipo (horas úteis): Crítica 4 · Alta 24 · Média 48 · Baixa 72 — editável na tela de configuração (Admin).

```python
class Comentario(TimeStampedModel):
    chamado = models.ForeignKey(Chamado, on_delete=models.CASCADE, related_name="comentarios")
    autor = models.ForeignKey("core.User", on_delete=models.PROTECT)
    texto = models.TextField()
    interno = models.BooleanField(default=False)   # invisível ao solicitante

class Anexo(TimeStampedModel):
    chamado = models.ForeignKey(Chamado, on_delete=models.CASCADE, related_name="anexos")
    arquivo = models.FileField(upload_to="chamados/%Y/%m/")
    nome_original = models.CharField(max_length=180)
    tamanho_bytes = models.PositiveIntegerField()

class HistoricoChamado(models.Model):
    """Timeline exibida na tela de tarefa. Append-only."""
    chamado = models.ForeignKey(Chamado, on_delete=models.CASCADE, related_name="historico")
    quando = models.DateTimeField(auto_now_add=True)
    usuario = models.ForeignKey("core.User", null=True, on_delete=models.SET_NULL)
    texto = models.CharField(max_length=240)
```

---

## 3. apontamentos

```python
class TipoTrabalho(models.Model):
    nome = models.CharField(max_length=40, unique=True)
    exige_causa = models.BooleanField(default=False)
    contabiliza_capacidade = models.BooleanField(default=True)
    ordem = models.PositiveSmallIntegerField(default=0)
```

8 tipos iniciais (ordem da tela): Análise, Desenvolvimento, Testes, Reunião, Atendimento, Documentação, Espera de terceiro (`contabiliza_capacidade=False`), **Retrabalho** (`exige_causa=True`).

```python
class MotivoRetrabalho(models.Model):
    nome = models.CharField(max_length=60, unique=True)
```

5 motivos iniciais: Requisito incompleto · Erro de análise · Mudança de escopo · Falha em teste · Dado incorreto na origem.

```python
class Apontamento(TimeStampedModel):
    usuario = models.ForeignKey("core.User", on_delete=models.PROTECT, related_name="apontamentos")
    tipo = models.ForeignKey(TipoTrabalho, on_delete=models.PROTECT)
    chamado = models.ForeignKey("chamados.Chamado", null=True, blank=True, on_delete=models.PROTECT, related_name="apontamentos")
    projeto = models.ForeignKey("projetos.Projeto", null=True, blank=True, on_delete=models.PROTECT, related_name="apontamentos")
    inicio = models.DateTimeField()
    fim = models.DateTimeField(null=True, blank=True)          # null = cronômetro rodando
    minutos = models.PositiveIntegerField(default=0)           # calculado no fechamento
    observacao = models.CharField(max_length=240, blank=True)
    motivo_retrabalho = models.ForeignKey(MotivoRetrabalho, null=True, blank=True, on_delete=models.PROTECT)
    detalhe_retrabalho = models.CharField(max_length=240, blank=True)
    lancamento_manual = models.BooleanField(default=False)
    aprovado_por = models.ForeignKey("core.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="apontamentos_aprovados")
    aprovado_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(check=Q(fim__isnull=True) | Q(fim__gt=F("inicio")), name="ap_fim_maior_inicio"),
            models.CheckConstraint(check=Q(chamado__isnull=False) | Q(projeto__isnull=False), name="ap_tem_destino"),
            # cronômetro único por usuário
            models.UniqueConstraint(fields=["usuario"], condition=Q(fim__isnull=True), name="ap_um_cronometro_aberto"),
        ]
        indexes = [models.Index(fields=["usuario", "-inicio"]), models.Index(fields=["tipo"])]
```

Causa obrigatória para retrabalho e **não sobreposição de intervalos** do mesmo usuário: ver `03-REGRAS-DE-NEGOCIO.md` §1 e §2 (constraint `EXCLUDE USING gist` via `RunSQL` — precisa de `btree_gist`).

---

## 4. documentacao

```python
class Documento(TimeStampedModel):
    class Secao(models.TextChoices):
        CONTEXTO = "contexto", "Contexto e problema"
        REGRA = "regra", "Regra de negócio"
        SOLUCAO = "solucao", "Solução aplicada"
        IMPACTO = "impacto", "Impacto em outros setores"
        TESTE = "teste", "Como foi testado"
        ROLLBACK = "rollback", "Plano de rollback"

    chamado = models.ForeignKey("chamados.Chamado", null=True, blank=True, on_delete=models.CASCADE, related_name="documentos")
    projeto = models.ForeignKey("projetos.Projeto", null=True, blank=True, on_delete=models.CASCADE, related_name="documentos")
    secao = models.CharField(max_length=12, choices=Secao.choices)
    obrigatorio = models.BooleanField(default=False)
    versao_atual = models.ForeignKey("documentacao.VersaoDocumento", null=True, blank=True,
                                     on_delete=models.SET_NULL, related_name="+")
    class Meta:
        constraints = [models.UniqueConstraint(fields=["chamado", "secao"], name="uniq_doc_chamado_secao")]

class VersaoDocumento(TimeStampedModel):
    """Append-only: nunca editar, sempre nova versão."""
    documento = models.ForeignKey(Documento, on_delete=models.CASCADE, related_name="versoes")
    numero = models.PositiveIntegerField()
    conteudo = models.TextField()
    autor = models.ForeignKey("core.User", on_delete=models.PROTECT)
    publicada_em = models.DateTimeField(null=True, blank=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["documento", "numero"], name="uniq_versao_num")]
```

Seções obrigatórias por categoria (`exige_documentacao=True`): Contexto, Regra de negócio, Solução, Como foi testado. Impacto e Rollback são recomendadas — entram no percentual de cobertura, não no bloqueio.

---

## 5. almoxarifado

```python
class Item(TimeStampedModel):
    codigo = models.CharField(max_length=20, unique=True)      # "MRO-4471"
    descricao = models.CharField(max_length=180)
    unidade = models.CharField(max_length=8)                    # UN, PC, CX, KG, M
    setor_dono = models.ForeignKey("core.Setor", on_delete=models.PROTECT, related_name="itens")
    estoque_minimo = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    custo_unitario = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    codigo_sankhya = models.CharField(max_length=30, blank=True, db_index=True)
    ativo = models.BooleanField(default=True)

class Estoque(models.Model):
    """Saldo materializado — 1:1 com Item por setor. Nunca editar fora de services."""
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="estoques")
    setor = models.ForeignKey("core.Setor", on_delete=models.PROTECT)
    saldo = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["item", "setor"], name="uniq_estoque_item_setor"),
                       models.CheckConstraint(check=Q(saldo__gte=0), name="estoque_nao_negativo")]

class Movimento(TimeStampedModel):
    """Imutável. Correção é ajuste novo, nunca update/delete."""
    class Tipo(models.TextChoices):
        ENTRADA = "entrada", "Entrada"
        SAIDA = "saida", "Saída"
        TRANSF_SAIDA = "transf_saida", "Transferência (saída)"
        TRANSF_ENTRADA = "transf_entrada", "Transferência (entrada)"
        AJUSTE = "ajuste", "Ajuste de inventário"

    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="movimentos")
    setor = models.ForeignKey("core.Setor", on_delete=models.PROTECT)
    tipo = models.CharField(max_length=14, choices=Tipo.choices)
    quantidade = models.DecimalField(max_digits=12, decimal_places=3)
    saldo_apos = models.DecimalField(max_digits=14, decimal_places=3)
    centro_custo = models.ForeignKey("core.CentroCusto", null=True, blank=True, on_delete=models.PROTECT)
    chamado = models.ForeignKey("chamados.Chamado", null=True, blank=True, on_delete=models.SET_NULL)
    projeto = models.ForeignKey("projetos.Projeto", null=True, blank=True, on_delete=models.SET_NULL)
    os_ref = models.CharField(max_length=30, blank=True)        # ordem de serviço externa
    nota_fiscal = models.ForeignKey("almoxarifado.NotaFiscal", null=True, blank=True, on_delete=models.PROTECT)
    solicitacao = models.ForeignKey("almoxarifado.Solicitacao", null=True, blank=True, on_delete=models.SET_NULL)
    inventario = models.ForeignKey("almoxarifado.Inventario", null=True, blank=True, on_delete=models.SET_NULL)
    usuario = models.ForeignKey("core.User", on_delete=models.PROTECT)
    justificativa = models.CharField(max_length=240, blank=True)

    class Meta:
        constraints = [models.CheckConstraint(check=Q(quantidade__gt=0), name="mov_qtd_positiva")]
        indexes = [models.Index(fields=["item", "-criado_em"]),
                   models.Index(fields=["setor", "tipo", "-criado_em"]),
                   models.Index(fields=["centro_custo"])]

class Solicitacao(TimeStampedModel):
    class Status(models.TextChoices):
        ABERTA = "aberta", "Aberta"; APROVADA = "aprovada", "Aprovada"
        ATENDIDA = "atendida", "Atendida"; NEGADA = "negada", "Negada"
    numero = models.CharField(max_length=14, unique=True)       # "SOL-2026-0912"
    setor = models.ForeignKey("core.Setor", on_delete=models.PROTECT)
    solicitante = models.ForeignKey("core.User", on_delete=models.PROTECT)
    centro_custo = models.ForeignKey("core.CentroCusto", on_delete=models.PROTECT)
    os_ref = models.CharField(max_length=30, blank=True)
    urgente = models.BooleanField(default=False)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ABERTA)
    aprovada_por = models.ForeignKey("core.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    origem = models.CharField(max_length=12, default="sistema")  # sistema | whatsapp

class ItemSolicitacao(models.Model):
    solicitacao = models.ForeignKey(Solicitacao, on_delete=models.CASCADE, related_name="itens")
    item = models.ForeignKey(Item, on_delete=models.PROTECT)
    quantidade = models.DecimalField(max_digits=12, decimal_places=3)
    quantidade_atendida = models.DecimalField(max_digits=12, decimal_places=3, default=0)

class NotaFiscal(TimeStampedModel):
    numero = models.CharField(max_length=20)
    serie = models.CharField(max_length=6, blank=True)
    fornecedor = models.CharField(max_length=140)
    cnpj = models.CharField(max_length=18, blank=True)
    emissao = models.DateField()
    valor_total = models.DecimalField(max_digits=14, decimal_places=2)
    arquivo = models.FileField(upload_to="notas/%Y/%m/", null=True, blank=True)
    conferida_por = models.ForeignKey("core.User", null=True, on_delete=models.SET_NULL, related_name="+")
    class Meta:
        constraints = [models.UniqueConstraint(fields=["numero", "serie", "cnpj"], name="uniq_nf")]

class ItemNotaFiscal(models.Model):
    nota = models.ForeignKey(NotaFiscal, on_delete=models.CASCADE, related_name="itens")
    item = models.ForeignKey(Item, on_delete=models.PROTECT)
    quantidade_pedida = models.DecimalField(max_digits=12, decimal_places=3)
    quantidade_recebida = models.DecimalField(max_digits=12, decimal_places=3)
    custo_unitario = models.DecimalField(max_digits=12, decimal_places=2)
    divergencia = models.CharField(max_length=140, blank=True)

class Transferencia(TimeStampedModel):
    item = models.ForeignKey(Item, on_delete=models.PROTECT)
    setor_origem = models.ForeignKey("core.Setor", on_delete=models.PROTECT, related_name="transf_saidas")
    setor_destino = models.ForeignKey("core.Setor", on_delete=models.PROTECT, related_name="transf_entradas")
    quantidade = models.DecimalField(max_digits=12, decimal_places=3)
    motivo = models.CharField(max_length=180)
    fura_minimo_origem = models.BooleanField(default=False)     # calculado, exibido como alerta
    class Meta:
        constraints = [models.CheckConstraint(check=~Q(setor_origem=F("setor_destino")), name="transf_setores_diferentes")]

class Inventario(TimeStampedModel):
    class Status(models.TextChoices):
        ABERTO = "aberto", "Aberto"; FECHADO = "fechado", "Fechado"
    setor = models.ForeignKey("core.Setor", on_delete=models.PROTECT)
    responsavel = models.ForeignKey("core.User", on_delete=models.PROTECT)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.ABERTO)
    fechado_em = models.DateTimeField(null=True, blank=True)
    divergencias = models.PositiveIntegerField(default=0)
    impacto_valor = models.DecimalField(max_digits=14, decimal_places=2, default=0)

class ContagemInventario(models.Model):
    inventario = models.ForeignKey(Inventario, on_delete=models.CASCADE, related_name="contagens")
    item = models.ForeignKey(Item, on_delete=models.PROTECT)
    saldo_sistema = models.DecimalField(max_digits=14, decimal_places=3)
    saldo_contado = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    @property
    def divergencia(self): ...   # contado - sistema

class Cotacao(TimeStampedModel):
    class Status(models.TextChoices):
        ABERTA = "aberta", "Aberta"; RESPONDIDA = "respondida", "Respondida"
        FECHADA = "fechada", "Fechada"
    item = models.ForeignKey(Item, on_delete=models.PROTECT)
    quantidade = models.DecimalField(max_digits=12, decimal_places=3)
    prazo_resposta = models.DateField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ABERTA)

class PropostaCotacao(models.Model):
    cotacao = models.ForeignKey(Cotacao, on_delete=models.CASCADE, related_name="propostas")
    fornecedor = models.CharField(max_length=140)
    valor_unitario = models.DecimalField(max_digits=12, decimal_places=2)
    prazo_entrega_dias = models.PositiveSmallIntegerField()
    escolhida = models.BooleanField(default=False)
```

---

## 6. projetos

```python
class Projeto(TimeStampedModel):
    class Fase(models.TextChoices):
        IDEIA = "ideia", "Ideia"
        ANALISE = "analise", "Em análise"
        APROVADO = "aprovado", "Aprovado"
        FILA = "fila", "Na fila"
        DESENVOLVIMENTO = "desenvolvimento", "Em desenvolvimento"
        TESTES = "testes", "Em testes"
        HOMOLOGACAO = "homologacao", "Homologação"
        IMPLANTACAO = "implantacao", "Implantação"
        CONCLUIDO = "concluido", "Concluído"     # só no histórico
        CANCELADO = "cancelado", "Cancelado"     # só no histórico

    nome = models.CharField(max_length=180)
    setor_solicitante = models.ForeignKey("core.Setor", on_delete=models.PROTECT, related_name="projetos")
    patrocinador = models.ForeignKey("core.User", on_delete=models.PROTECT, related_name="projetos_patrocinados")
    responsavel = models.ForeignKey("core.User", null=True, on_delete=models.SET_NULL, related_name="projetos_responsavel")
    fase = models.CharField(max_length=16, choices=Fase.choices, default=Fase.IDEIA)
    horas_estimadas = models.PositiveIntegerField(default=0)
    inicio_previsto = models.DateField(null=True, blank=True)
    fim_previsto = models.DateField(null=True, blank=True)
    encerrado_em = models.DateField(null=True, blank=True)
    situacao_final = models.CharField(max_length=180, blank=True)

    class Meta:
        constraints = [models.CheckConstraint(
            check=~Q(fase__in=["concluido", "cancelado"]) | Q(encerrado_em__isnull=False),
            name="proj_encerrado_tem_data")]

    @property
    def horas_realizadas_min(self): ...   # soma via selector, não em property N+1
```

O kanban da tela usa as **8 primeiras fases**; `concluido` e `cancelado` aparecem só na tela de histórico (`?historico=true`).

```python
class Marco(models.Model):
    projeto = models.ForeignKey(Projeto, on_delete=models.CASCADE, related_name="marcos")
    nome = models.CharField(max_length=140)
    previsto = models.DateField()
    concluido_em = models.DateField(null=True, blank=True)

class Alocacao(models.Model):
    projeto = models.ForeignKey(Projeto, on_delete=models.CASCADE, related_name="alocacoes")
    usuario = models.ForeignKey("core.User", on_delete=models.PROTECT)
    percentual = models.PositiveSmallIntegerField()  # 0-100
```

---

## 7. integracoes

```python
class MensagemWhatsApp(TimeStampedModel):
    """Payload cru antes de virar solicitação/chamado. Nunca apagar."""
    provider_id = models.CharField(max_length=80, unique=True)
    telefone = models.CharField(max_length=20)
    texto = models.TextField()
    payload = models.JSONField()
    usuario_identificado = models.ForeignKey("core.User", null=True, on_delete=models.SET_NULL)
    sugestao_ia = models.JSONField(null=True, blank=True)  # {categoria, prioridade, setor, itens, confianca}
    revisada_por = models.ForeignKey("core.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    chamado = models.ForeignKey("chamados.Chamado", null=True, blank=True, on_delete=models.SET_NULL)
    solicitacao = models.ForeignKey("almoxarifado.Solicitacao", null=True, blank=True, on_delete=models.SET_NULL)

class SincronizacaoSankhya(TimeStampedModel):
    entidade = models.CharField(max_length=40)      # "item", "movimento"
    direcao = models.CharField(max_length=8)         # "in" | "out"
    hash_payload = models.CharField(max_length=64, db_index=True)  # idempotência
    payload = models.JSONField()
    sucesso = models.BooleanField(default=False)
    erro = models.TextField(blank=True)
```

---

## 8. Extensões PostgreSQL necessárias

```python
# core/migrations/0002_extensoes.py
operations = [
    BtreeGistExtension(),   # constraint de não sobreposição de apontamentos
    TrigramExtension(),     # busca global por item/chamado
]
```

Busca global (header do sistema): `SearchVector` em `Chamado.titulo/descricao` e `Item.codigo/descricao` com `config='portuguese'`, mais `trigram_similar` como fallback para código digitado parcialmente.
