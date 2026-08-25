from django.contrib.auth.models import AbstractUser
from django.db import models


class TimeStampedModel(models.Model):
    criado_em = models.DateTimeField(auto_now_add=True, db_index=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    criado_por = models.ForeignKey(
        "core.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        abstract = True


class Setor(TimeStampedModel):
    nome = models.CharField(max_length=60, unique=True)
    sigla = models.CharField(max_length=6, unique=True)
    responsavel = models.ForeignKey(
        "core.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="setores_responsavel",
    )
    ativo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "setor"
        verbose_name_plural = "setores"
        ordering = ["nome"]

    def __str__(self) -> str:
        return self.nome


class User(AbstractUser):
    setor = models.ForeignKey(Setor, on_delete=models.PROTECT, related_name="usuarios")
    matricula = models.CharField(max_length=20, unique=True)
    capacidade_diaria_min = models.PositiveIntegerField(default=480)  # 8h
    ativo_para_apontamento = models.BooleanField(default=True)

    REQUIRED_FIELDS = ["email", "matricula", "setor"]

    class Meta:
        verbose_name = "usuário"
        verbose_name_plural = "usuários"

    def __str__(self) -> str:
        return self.get_full_name() or self.username

    @property
    def nome(self) -> str:
        return self.get_full_name() or self.username

    def papeis(self) -> set[str]:
        """Nomes dos grupos. Use `core.permissions.papeis_de()` em código quente (cacheado)."""
        return set(self.groups.values_list("name", flat=True))


class CentroCusto(TimeStampedModel):
    codigo = models.CharField(max_length=10, unique=True)
    descricao = models.CharField(max_length=120)
    setor = models.ForeignKey(Setor, on_delete=models.PROTECT, related_name="centros_custo")
    projeto = models.ForeignKey(
        "projetos.Projeto", null=True, blank=True, on_delete=models.SET_NULL
    )
    ativo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "centro de custo"
        verbose_name_plural = "centros de custo"
        ordering = ["codigo"]

    def __str__(self) -> str:
        return f"{self.codigo} — {self.descricao}"


class Feriado(models.Model):
    """Feriados municipais/estaduais editáveis. Os nacionais vêm do workalendar."""

    data = models.DateField(unique=True)
    nome = models.CharField(max_length=80)

    class Meta:
        ordering = ["data"]

    def __str__(self) -> str:
        return f"{self.data:%d/%m/%Y} — {self.nome}"


class Auditoria(models.Model):
    """Append-only. Escrita apenas por `core.auditoria.registrar()`."""

    quando = models.DateTimeField(auto_now_add=True, db_index=True)
    usuario = models.ForeignKey("core.User", null=True, on_delete=models.SET_NULL)
    acao = models.CharField(max_length=60)
    objeto_tipo = models.CharField(max_length=60)
    objeto_id = models.CharField(max_length=40)
    antes = models.JSONField(null=True, blank=True)
    depois = models.JSONField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["objeto_tipo", "objeto_id", "-quando"])]
        ordering = ["-quando"]

    def __str__(self) -> str:
        return f"{self.acao} {self.objeto_tipo}#{self.objeto_id}"


class PermissaoModulo(models.Model):
    """Matriz de acesso por papel e módulo. É dado, não código — editável pelo Admin."""

    class Nivel(models.TextChoices):
        SEM_ACESSO = "-", "Sem acesso"
        VER = "V", "Ver"
        EDITAR = "E", "Editar"

    papel = models.CharField(max_length=20)
    modulo = models.CharField(max_length=20)
    nivel = models.CharField(max_length=1, choices=Nivel.choices, default=Nivel.SEM_ACESSO)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["papel", "modulo"], name="uniq_permissao_papel_modulo")
        ]
        verbose_name = "permissão de módulo"
        verbose_name_plural = "permissões de módulo"

    def __str__(self) -> str:
        return f"{self.papel}/{self.modulo}={self.nivel}"
