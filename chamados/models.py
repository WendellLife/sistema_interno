from django.contrib.postgres.indexes import GinIndex
from django.db import models

from core.models import TimeStampedModel


class Categoria(models.Model):
    nome = models.CharField(max_length=60, unique=True)
    slug = models.SlugField(unique=True)
    exige_documentacao = models.BooleanField(default=False)

    class Meta:
        ordering = ["nome"]

    def __str__(self) -> str:
        return self.nome


class Chamado(TimeStampedModel):
    class Prioridade(models.TextChoices):
        CRITICA = "critica", "Crítica"
        ALTA = "alta", "Alta"
        MEDIA = "media", "Média"
        BAIXA = "baixa", "Baixa"

    class Status(models.TextChoices):
        NOVO = "novo", "Novo"
        TRIAGEM = "triagem", "Em triagem"
        FILA = "fila", "Na fila"
        EXECUCAO = "execucao", "Em execução"
        TESTES = "testes", "Em testes"
        AGUARDA_SOLICITANTE = "aguarda", "Aguardando solicitante"
        ENTREGUE = "entregue", "Entregue"
        CANCELADO = "cancelado", "Cancelado"

    numero = models.CharField(max_length=12, unique=True)
    titulo = models.CharField(max_length=180)
    descricao = models.TextField()
    setor_origem = models.ForeignKey(
        "core.Setor", on_delete=models.PROTECT, related_name="chamados_abertos"
    )
    solicitante = models.ForeignKey(
        "core.User", on_delete=models.PROTECT, related_name="chamados_solicitados"
    )
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT)
    prioridade = models.CharField(max_length=10, choices=Prioridade.choices)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.NOVO)
    responsavel = models.ForeignKey(
        "core.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="chamados_atribuidos"
    )
    projeto = models.ForeignKey(
        "projetos.Projeto", null=True, blank=True, on_delete=models.SET_NULL, related_name="chamados"
    )
    horas_previstas_min = models.PositiveIntegerField(default=0)
    sla_previsto = models.DateTimeField(null=True, blank=True)
    sla_cumprido = models.BooleanField(null=True, blank=True)  # null = ainda aberto
    entregue_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-criado_em"]
        indexes = [
            models.Index(fields=["status", "responsavel"]),
            models.Index(fields=["setor_origem", "status"]),
            models.Index(fields=["sla_previsto"]),
            GinIndex(fields=["titulo"], name="chamado_titulo_trgm", opclasses=["gin_trgm_ops"]),
        ]

    def __str__(self) -> str:
        return f"{self.numero} — {self.titulo}"

    @property
    def aberto(self) -> bool:
        return self.status not in (self.Status.ENTREGUE, self.Status.CANCELADO)


STATUS_ABERTOS = [
    s for s in Chamado.Status if s not in (Chamado.Status.ENTREGUE, Chamado.Status.CANCELADO)
]


class RegraSLA(models.Model):
    categoria = models.ForeignKey(Categoria, on_delete=models.CASCADE, related_name="regras_sla")
    prioridade = models.CharField(max_length=10, choices=Chamado.Prioridade.choices)
    horas_uteis = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["categoria", "prioridade"], name="uniq_sla_cat_prio")
        ]
        verbose_name = "regra de SLA"
        verbose_name_plural = "regras de SLA"

    def __str__(self) -> str:
        return f"{self.categoria} / {self.get_prioridade_display()}: {self.horas_uteis}h úteis"


# Padrão do protótipo quando não há RegraSLA para (categoria, prioridade)
SLA_PADRAO_HORAS = {
    Chamado.Prioridade.CRITICA: 4,
    Chamado.Prioridade.ALTA: 24,
    Chamado.Prioridade.MEDIA: 48,
    Chamado.Prioridade.BAIXA: 72,
}


class Comentario(TimeStampedModel):
    chamado = models.ForeignKey(Chamado, on_delete=models.CASCADE, related_name="comentarios")
    autor = models.ForeignKey("core.User", on_delete=models.PROTECT)
    texto = models.TextField()
    interno = models.BooleanField(default=False)  # invisível ao solicitante

    class Meta:
        ordering = ["criado_em"]


class Anexo(TimeStampedModel):
    chamado = models.ForeignKey(Chamado, on_delete=models.CASCADE, related_name="anexos")
    arquivo = models.FileField(upload_to="chamados/%Y/%m/")
    nome_original = models.CharField(max_length=180)
    tamanho_bytes = models.PositiveIntegerField()

    class Meta:
        ordering = ["criado_em"]


class HistoricoChamado(models.Model):
    """Timeline exibida na tela de tarefa. Append-only."""

    chamado = models.ForeignKey(Chamado, on_delete=models.CASCADE, related_name="historico")
    quando = models.DateTimeField(auto_now_add=True)
    usuario = models.ForeignKey("core.User", null=True, on_delete=models.SET_NULL)
    texto = models.CharField(max_length=240)

    class Meta:
        ordering = ["quando"]

    def __str__(self) -> str:
        return f"{self.chamado_id} · {self.texto[:40]}"
