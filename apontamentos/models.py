from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateTimeRangeField, RangeBoundary, RangeOperators
from django.db import models
from django.db.models import F, Func, Q

from core.models import TimeStampedModel


class TsTzRange(Func):
    function = "TSTZRANGE"
    output_field = DateTimeRangeField()


class TipoTrabalho(models.Model):
    nome = models.CharField(max_length=40, unique=True)
    slug = models.SlugField(unique=True)
    exige_causa = models.BooleanField(default=False)
    contabiliza_capacidade = models.BooleanField(default=True)
    ordem = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["ordem", "nome"]
        verbose_name = "tipo de trabalho"
        verbose_name_plural = "tipos de trabalho"

    def __str__(self) -> str:
        return self.nome


class MotivoRetrabalho(models.Model):
    nome = models.CharField(max_length=60, unique=True)

    class Meta:
        ordering = ["nome"]
        verbose_name = "motivo de retrabalho"
        verbose_name_plural = "motivos de retrabalho"

    def __str__(self) -> str:
        return self.nome


class Apontamento(TimeStampedModel):
    usuario = models.ForeignKey("core.User", on_delete=models.PROTECT, related_name="apontamentos")
    tipo = models.ForeignKey(TipoTrabalho, on_delete=models.PROTECT)
    # Denormalizado do tipo para a CheckConstraint de causa (regra §1)
    tipo_exige_causa = models.BooleanField(default=False, editable=False)
    chamado = models.ForeignKey(
        "chamados.Chamado", null=True, blank=True, on_delete=models.PROTECT, related_name="apontamentos"
    )
    projeto = models.ForeignKey(
        "projetos.Projeto", null=True, blank=True, on_delete=models.PROTECT, related_name="apontamentos"
    )
    inicio = models.DateTimeField()
    fim = models.DateTimeField(null=True, blank=True)  # null = cronômetro rodando
    minutos = models.PositiveIntegerField(default=0)  # calculado no fechamento
    observacao = models.CharField(max_length=240, blank=True)
    motivo_retrabalho = models.ForeignKey(
        MotivoRetrabalho, null=True, blank=True, on_delete=models.PROTECT
    )
    detalhe_retrabalho = models.CharField(max_length=240, blank=True)
    lancamento_manual = models.BooleanField(default=False)
    pendente_aprovacao = models.BooleanField(default=False, db_index=True)
    aprovado_por = models.ForeignKey(
        "core.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="apontamentos_aprovados"
    )
    aprovado_em = models.DateTimeField(null=True, blank=True)
    recusado_em = models.DateTimeField(null=True, blank=True)
    motivo_recusa = models.CharField(max_length=240, blank=True)

    class Meta:
        ordering = ["-inicio"]
        constraints = [
            models.CheckConstraint(
                condition=Q(fim__isnull=True) | Q(fim__gt=F("inicio")), name="ap_fim_maior_inicio"
            ),
            models.CheckConstraint(
                condition=Q(chamado__isnull=False) | Q(projeto__isnull=False), name="ap_tem_destino"
            ),
            models.CheckConstraint(
                condition=Q(tipo_exige_causa=False) | Q(motivo_retrabalho__isnull=False),
                name="ap_retrabalho_tem_causa",
            ),
            # Um cronômetro aberto por usuário (regra §2)
            models.UniqueConstraint(
                fields=["usuario"], condition=Q(fim__isnull=True), name="ap_um_cronometro_aberto"
            ),
            # Intervalos do mesmo usuário não se sobrepõem (regra §3). fim NULL = aberto até o infinito.
            ExclusionConstraint(
                name="ap_sem_sobreposicao",
                expressions=[
                    (TsTzRange("inicio", "fim", RangeBoundary()), RangeOperators.OVERLAPS),
                    ("usuario", RangeOperators.EQUAL),
                ],
            ),
        ]
        indexes = [models.Index(fields=["usuario", "-inicio"]), models.Index(fields=["tipo"])]

    def __str__(self) -> str:
        return f"{self.usuario} · {self.tipo} · {self.inicio:%d/%m %H:%M}"

    @property
    def aberto(self) -> bool:
        return self.fim is None

    def save(self, *args, **kwargs):
        # Denormalização (não é regra de fluxo): mantém a CheckConstraint verdadeira.
        self.tipo_exige_causa = self.tipo.exige_causa
        super().save(*args, **kwargs)


# Tipos iniciais (ordem da tela)
TIPOS_INICIAIS = [
    ("Análise", "analise", False, True),
    ("Desenvolvimento", "desenvolvimento", False, True),
    ("Testes", "testes", False, True),
    ("Reunião", "reuniao", False, True),
    ("Atendimento", "atendimento", False, True),
    ("Documentação", "documentacao", False, True),
    ("Espera de terceiro", "espera_terceiro", False, False),
    ("Retrabalho", "retrabalho", True, True),
]
MOTIVOS_INICIAIS = [
    "Requisito incompleto", "Erro de análise", "Mudança de escopo", "Falha em teste",
    "Dado incorreto na origem",
]  # fmt: skip
