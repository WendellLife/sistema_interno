from django.db import models

from core.models import TimeStampedModel


class Documento(TimeStampedModel):
    class Secao(models.TextChoices):
        CONTEXTO = "contexto", "Contexto e problema"
        REGRA = "regra", "Regra de negócio"
        SOLUCAO = "solucao", "Solução aplicada"
        IMPACTO = "impacto", "Impacto em outros setores"
        TESTE = "teste", "Como foi testado"
        ROLLBACK = "rollback", "Plano de rollback"

    chamado = models.ForeignKey(
        "chamados.Chamado", null=True, blank=True, on_delete=models.CASCADE, related_name="documentos"
    )
    projeto = models.ForeignKey(
        "projetos.Projeto", null=True, blank=True, on_delete=models.CASCADE, related_name="documentos"
    )
    secao = models.CharField(max_length=12, choices=Secao.choices)
    obrigatorio = models.BooleanField(default=False)
    versao_atual = models.ForeignKey(
        "documentacao.VersaoDocumento", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["chamado", "secao"], name="uniq_doc_chamado_secao"),
            models.UniqueConstraint(fields=["projeto", "secao"], name="uniq_doc_projeto_secao"),
        ]

    def __str__(self) -> str:
        return f"{self.get_secao_display()} ({self.chamado or self.projeto})"


# Seções que bloqueiam a entrega em categorias com exige_documentacao=True (regra §5)
SECOES_OBRIGATORIAS = [
    Documento.Secao.CONTEXTO,
    Documento.Secao.REGRA,
    Documento.Secao.SOLUCAO,
    Documento.Secao.TESTE,
]


class VersaoDocumento(TimeStampedModel):
    """Append-only: nunca editar, sempre nova versão."""

    documento = models.ForeignKey(Documento, on_delete=models.CASCADE, related_name="versoes")
    numero = models.PositiveIntegerField()
    conteudo = models.TextField()
    autor = models.ForeignKey("core.User", on_delete=models.PROTECT)
    publicada_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["documento", "numero"], name="uniq_versao_num")
        ]
        ordering = ["-numero"]
