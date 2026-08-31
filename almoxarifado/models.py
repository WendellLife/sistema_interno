from decimal import Decimal

from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.db.models import F, Q

from core.models import TimeStampedModel

D0 = Decimal("0")


class Item(TimeStampedModel):
    codigo = models.CharField(max_length=20, unique=True)  # "MRO-4471"
    descricao = models.CharField(max_length=180)
    unidade = models.CharField(max_length=8)  # UN, PC, CX, KG, M
    setor_dono = models.ForeignKey("core.Setor", on_delete=models.PROTECT, related_name="itens")
    estoque_minimo = models.DecimalField(max_digits=12, decimal_places=3, default=D0)
    custo_unitario = models.DecimalField(max_digits=12, decimal_places=2, default=D0)
    codigo_sankhya = models.CharField(max_length=30, blank=True, db_index=True)
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ["codigo"]
        indexes = [GinIndex(fields=["descricao"], name="item_descricao_trgm", opclasses=["gin_trgm_ops"])]

    def __str__(self) -> str:
        return f"{self.codigo} — {self.descricao}"


class Estoque(models.Model):
    """Saldo materializado — 1:1 com Item por setor. Nunca editar fora de services."""

    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="estoques")
    setor = models.ForeignKey("core.Setor", on_delete=models.PROTECT, related_name="estoques")
    saldo = models.DecimalField(max_digits=14, decimal_places=3, default=D0)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["item", "setor"], name="uniq_estoque_item_setor"),
            models.CheckConstraint(condition=Q(saldo__gte=0), name="estoque_nao_negativo"),
        ]

    def __str__(self) -> str:
        return f"{self.item.codigo}@{self.setor.sigla}: {self.saldo}"


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
    # Ajuste de inventário pode ser para menos: sinal separado da quantidade (que é sempre > 0)
    sinal = models.SmallIntegerField(default=1)
    saldo_apos = models.DecimalField(max_digits=14, decimal_places=3)
    centro_custo = models.ForeignKey("core.CentroCusto", null=True, blank=True, on_delete=models.PROTECT)
    chamado = models.ForeignKey("chamados.Chamado", null=True, blank=True, on_delete=models.SET_NULL)
    projeto = models.ForeignKey("projetos.Projeto", null=True, blank=True, on_delete=models.SET_NULL)
    os_ref = models.CharField(max_length=30, blank=True)  # ordem de serviço externa
    nota_fiscal = models.ForeignKey(
        "almoxarifado.NotaFiscal", null=True, blank=True, on_delete=models.PROTECT
    )
    solicitacao = models.ForeignKey(
        "almoxarifado.Solicitacao", null=True, blank=True, on_delete=models.SET_NULL
    )
    inventario = models.ForeignKey(
        "almoxarifado.Inventario", null=True, blank=True, on_delete=models.SET_NULL
    )
    transferencia = models.ForeignKey(
        "almoxarifado.Transferencia", null=True, blank=True, on_delete=models.SET_NULL
    )
    usuario = models.ForeignKey("core.User", on_delete=models.PROTECT)
    justificativa = models.CharField(max_length=240, blank=True)

    class Meta:
        ordering = ["-criado_em"]
        constraints = [
            models.CheckConstraint(condition=Q(quantidade__gt=0), name="mov_qtd_positiva"),
            models.CheckConstraint(condition=Q(sinal__in=[1, -1]), name="mov_sinal_valido"),
        ]
        indexes = [
            models.Index(fields=["item", "-criado_em"]),
            models.Index(fields=["setor", "tipo", "-criado_em"]),
            models.Index(fields=["centro_custo"]),
        ]

    @property
    def delta(self) -> Decimal:
        return self.quantidade * self.sinal

    @property
    def consumo_geral(self) -> bool:
        """Saída sem OS, chamado ou projeto — relatório de desperdício de Compras (regra §8)."""
        return self.tipo == self.Tipo.SAIDA and not (self.os_ref or self.chamado_id or self.projeto_id)


ENTRADAS = {Movimento.Tipo.ENTRADA, Movimento.Tipo.TRANSF_ENTRADA}
SAIDAS = {Movimento.Tipo.SAIDA, Movimento.Tipo.TRANSF_SAIDA}


class Solicitacao(TimeStampedModel):
    class Status(models.TextChoices):
        ABERTA = "aberta", "Aberta"
        APROVADA = "aprovada", "Aprovada"
        ATENDIDA = "atendida", "Atendida"
        NEGADA = "negada", "Negada"

    class Origem(models.TextChoices):
        SISTEMA = "sistema", "Sistema"
        WHATSAPP = "whatsapp", "WhatsApp"

    numero = models.CharField(max_length=14, unique=True)  # "SOL-2026-0912"
    setor = models.ForeignKey("core.Setor", on_delete=models.PROTECT, related_name="solicitacoes")
    solicitante = models.ForeignKey("core.User", on_delete=models.PROTECT, related_name="solicitacoes")
    centro_custo = models.ForeignKey("core.CentroCusto", on_delete=models.PROTECT)
    os_ref = models.CharField(max_length=30, blank=True)
    urgente = models.BooleanField(default=False)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ABERTA)
    aprovada_por = models.ForeignKey(
        "core.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    aprovada_em = models.DateTimeField(null=True, blank=True)
    motivo_negacao = models.CharField(max_length=240, blank=True)
    origem = models.CharField(max_length=12, choices=Origem.choices, default=Origem.SISTEMA)

    class Meta:
        ordering = ["-criado_em"]
        verbose_name = "solicitação"
        verbose_name_plural = "solicitações"

    def __str__(self) -> str:
        return self.numero


class ItemSolicitacao(models.Model):
    solicitacao = models.ForeignKey(Solicitacao, on_delete=models.CASCADE, related_name="itens")
    item = models.ForeignKey(Item, on_delete=models.PROTECT)
    quantidade = models.DecimalField(max_digits=12, decimal_places=3)
    quantidade_atendida = models.DecimalField(max_digits=12, decimal_places=3, default=D0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["solicitacao", "item"], name="uniq_item_solicitacao"),
            models.CheckConstraint(condition=Q(quantidade__gt=0), name="itemsol_qtd_positiva"),
            models.CheckConstraint(
                condition=Q(quantidade_atendida__lte=F("quantidade")), name="itemsol_atendida_lte_pedida"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.solicitacao_id} · {self.item_id} × {self.quantidade}"

    @property
    def pendente(self) -> Decimal:
        return self.quantidade - self.quantidade_atendida

class NotaFiscal(TimeStampedModel):
    numero = models.CharField(max_length=20)
    serie = models.CharField(max_length=6, blank=True)
    fornecedor = models.CharField(max_length=140)
    cnpj = models.CharField(max_length=18, blank=True)
    emissao = models.DateField()
    valor_total = models.DecimalField(max_digits=14, decimal_places=2)
    setor = models.ForeignKey("core.Setor", on_delete=models.PROTECT)  # onde entra
    arquivo = models.FileField(upload_to="notas/%Y/%m/", null=True, blank=True)
    conferida_por = models.ForeignKey(
        "core.User", null=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["-emissao"]
        constraints = [models.UniqueConstraint(fields=["numero", "serie", "cnpj"], name="uniq_nf")]
        verbose_name = "nota fiscal"
        verbose_name_plural = "notas fiscais"

    def __str__(self) -> str:
        return f"NF {self.numero}/{self.serie} — {self.fornecedor}"


class ItemNotaFiscal(models.Model):
    nota = models.ForeignKey(NotaFiscal, on_delete=models.CASCADE, related_name="itens")
    item = models.ForeignKey(Item, on_delete=models.PROTECT)
    quantidade_pedida = models.DecimalField(max_digits=12, decimal_places=3)
    quantidade_recebida = models.DecimalField(max_digits=12, decimal_places=3)
    custo_unitario = models.DecimalField(max_digits=12, decimal_places=2)
    divergencia = models.CharField(max_length=140, blank=True)

    def __str__(self) -> str:
        return f"{self.nota_id} · {self.item_id}"

class Transferencia(TimeStampedModel):
    item = models.ForeignKey(Item, on_delete=models.PROTECT)
    setor_origem = models.ForeignKey("core.Setor", on_delete=models.PROTECT, related_name="transf_saidas")
    setor_destino = models.ForeignKey("core.Setor", on_delete=models.PROTECT, related_name="transf_entradas")
    quantidade = models.DecimalField(max_digits=12, decimal_places=3)
    motivo = models.CharField(max_length=180)
    fura_minimo_origem = models.BooleanField(default=False)  # calculado, exibido como alerta

    class Meta:
        ordering = ["-criado_em"]
        constraints = [
            models.CheckConstraint(
                condition=~Q(setor_origem=F("setor_destino")), name="transf_setores_diferentes"
            ),
            models.CheckConstraint(condition=Q(quantidade__gt=0), name="transf_qtd_positiva"),
        ]
        verbose_name = "transferência"
        verbose_name_plural = "transferências"


class Inventario(TimeStampedModel):
    class Status(models.TextChoices):
        ABERTO = "aberto", "Aberto"
        FECHADO = "fechado", "Fechado"

    setor = models.ForeignKey("core.Setor", on_delete=models.PROTECT)
    responsavel = models.ForeignKey("core.User", on_delete=models.PROTECT)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.ABERTO)
    fechado_em = models.DateTimeField(null=True, blank=True)
    divergencias = models.PositiveIntegerField(default=0)
    impacto_valor = models.DecimalField(max_digits=14, decimal_places=2, default=D0)

    class Meta:
        ordering = ["-criado_em"]
        constraints = [
            # um inventário aberto por setor
            models.UniqueConstraint(
                fields=["setor"], condition=Q(status="aberto"), name="inv_um_aberto_por_setor"
            )
        ]
        verbose_name = "inventário"


class ContagemInventario(models.Model):
    inventario = models.ForeignKey(Inventario, on_delete=models.CASCADE, related_name="contagens")
    item = models.ForeignKey(Item, on_delete=models.PROTECT)
    saldo_sistema = models.DecimalField(max_digits=14, decimal_places=3)
    saldo_contado = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["inventario", "item"], name="uniq_contagem_item"),
            models.CheckConstraint(
                condition=Q(saldo_contado__isnull=True) | Q(saldo_contado__gte=0), name="contagem_nao_negativa"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.inventario_id} · {self.item_id}"

    @property
    def divergencia(self) -> Decimal | None:
        if self.saldo_contado is None:
            return None
        return self.saldo_contado - self.saldo_sistema

class Cotacao(TimeStampedModel):
    class Status(models.TextChoices):
        ABERTA = "aberta", "Aberta"
        RESPONDIDA = "respondida", "Respondida"
        FECHADA = "fechada", "Fechada"

    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="cotacoes")
    quantidade = models.DecimalField(max_digits=12, decimal_places=3)
    prazo_resposta = models.DateField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ABERTA)

    class Meta:
        ordering = ["-criado_em"]
        verbose_name = "cotação"
        verbose_name_plural = "cotações"


class PropostaCotacao(models.Model):
    cotacao = models.ForeignKey(Cotacao, on_delete=models.CASCADE, related_name="propostas")
    fornecedor = models.CharField(max_length=140)
    valor_unitario = models.DecimalField(max_digits=12, decimal_places=2)
    prazo_entrega_dias = models.PositiveSmallIntegerField()
    escolhida = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["cotacao"], condition=Q(escolhida=True), name="uniq_proposta_escolhida"
            )
        ]

    def __str__(self) -> str:
        return f"{self.fornecedor} — {self.valor_unitario}"

class AlertaReposicao(models.Model):
    """Fila de reposição que Compras acompanha. Um alerta aberto por (item, setor)."""

    class Origem(models.TextChoices):
        MINIMO = "minimo", "Saldo no mínimo"
        TRANSFERENCIA = "transferencia", "Transferência furou mínimo"

    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="alertas")
    setor = models.ForeignKey("core.Setor", on_delete=models.CASCADE)
    saldo = models.DecimalField(max_digits=14, decimal_places=3)
    minimo = models.DecimalField(max_digits=12, decimal_places=3)
    origem = models.CharField(max_length=14, choices=Origem.choices)
    criado_em = models.DateTimeField(auto_now_add=True)
    resolvido_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-criado_em"]
        constraints = [
            models.UniqueConstraint(
                fields=["item", "setor"], condition=Q(resolvido_em__isnull=True), name="uniq_alerta_aberto"
            )
        ]

    def __str__(self) -> str:
        return f"{self.item_id} em {self.setor_id}"
