from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.db.models import Q

from core.models import TimeStampedModel

FASES_KANBAN = [
    "ideia", "analise", "aprovado", "fila", "desenvolvimento", "testes", "homologacao", "implantacao",
]  # fmt: skip
FASES_HISTORICO = ["concluido", "cancelado"]


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
        CONCLUIDO = "concluido", "Concluído"
        CANCELADO = "cancelado", "Cancelado"

    nome = models.CharField(max_length=180)
    setor_solicitante = models.ForeignKey(
        "core.Setor", on_delete=models.PROTECT, related_name="projetos"
    )
    patrocinador = models.ForeignKey(
        "core.User", on_delete=models.PROTECT, related_name="projetos_patrocinados"
    )
    responsavel = models.ForeignKey(
        "core.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="projetos_responsavel"
    )
    fase = models.CharField(max_length=16, choices=Fase.choices, default=Fase.IDEIA)
    horas_estimadas = models.PositiveIntegerField(default=0)
    inicio_previsto = models.DateField(null=True, blank=True)
    fim_previsto = models.DateField(null=True, blank=True)
    encerrado_em = models.DateField(null=True, blank=True)
    situacao_final = models.CharField(max_length=180, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=~Q(fase__in=FASES_HISTORICO) | Q(encerrado_em__isnull=False),
                name="proj_encerrado_tem_data",
            )
        ]
        ordering = ["nome"]
        indexes = [GinIndex(fields=["nome"], name="projeto_nome_trgm", opclasses=["gin_trgm_ops"])]

    def __str__(self) -> str:
        return self.nome


class Marco(models.Model):
    projeto = models.ForeignKey(Projeto, on_delete=models.CASCADE, related_name="marcos")
    nome = models.CharField(max_length=140)
    previsto = models.DateField()
    concluido_em = models.DateField(null=True, blank=True)

    def __str__(self) -> str:
        return self.nome


class Alocacao(models.Model):
    projeto = models.ForeignKey(Projeto, on_delete=models.CASCADE, related_name="alocacoes")
    usuario = models.ForeignKey("core.User", on_delete=models.PROTECT)
    percentual = models.PositiveSmallIntegerField()

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(percentual__lte=100), name="aloc_percentual_max_100")
        ]

    def __str__(self) -> str:
        return f"{self.usuario_id} em {self.projeto_id} ({self.percentual}%)"
