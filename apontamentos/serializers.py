from rest_framework import serializers

from core.serializers import UsuarioResumoSerializer

from .models import Apontamento, MotivoRetrabalho, TipoTrabalho


class TipoTrabalhoSerializer(serializers.ModelSerializer):
    class Meta:
        model = TipoTrabalho
        fields = ["id", "nome", "slug", "exige_causa", "contabiliza_capacidade", "ordem"]


class MotivoRetrabalhoSerializer(serializers.ModelSerializer):
    class Meta:
        model = MotivoRetrabalho
        fields = ["id", "nome"]


class ApontamentoSerializer(serializers.ModelSerializer):
    usuario = UsuarioResumoSerializer(read_only=True)
    tipo = TipoTrabalhoSerializer(read_only=True)
    motivo_retrabalho = MotivoRetrabalhoSerializer(read_only=True)
    chamado_numero = serializers.CharField(source="chamado.numero", read_only=True, default=None)
    projeto_nome = serializers.CharField(source="projeto.nome", read_only=True, default=None)
    aprovado_por = UsuarioResumoSerializer(read_only=True)

    class Meta:
        model = Apontamento
        fields = [
            "id", "usuario", "tipo", "chamado", "chamado_numero", "projeto", "projeto_nome",
            "inicio", "fim", "minutos", "observacao", "motivo_retrabalho", "detalhe_retrabalho",
            "lancamento_manual", "pendente_aprovacao", "aprovado_por", "aprovado_em", "recusado_em",
            "motivo_recusa", "criado_em",
        ]  # fmt: skip
        read_only_fields = fields


class _EntradaBase(serializers.Serializer):
    """Nunca mais de dois campos obrigatórios (tipo + destino) — adoção depende disso."""

    tipo = serializers.PrimaryKeyRelatedField(queryset=TipoTrabalho.objects.all())
    chamado = serializers.PrimaryKeyRelatedField(queryset=TipoTrabalho.objects.none(), required=False, allow_null=True)
    projeto = serializers.PrimaryKeyRelatedField(queryset=TipoTrabalho.objects.none(), required=False, allow_null=True)
    motivo_retrabalho = serializers.PrimaryKeyRelatedField(
        queryset=MotivoRetrabalho.objects.all(), required=False, allow_null=True
    )
    detalhe_retrabalho = serializers.CharField(max_length=240, required=False, allow_blank=True, default="")
    observacao = serializers.CharField(max_length=240, required=False, allow_blank=True, default="")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from chamados.models import Chamado
        from projetos.models import Projeto

        self.fields["chamado"].queryset = Chamado.objects.all()
        self.fields["projeto"].queryset = Projeto.objects.all()


class IniciarCronometroSerializer(_EntradaBase):
    pass


class LancamentoManualSerializer(_EntradaBase):
    inicio = serializers.DateTimeField()
    fim = serializers.DateTimeField()


class CronometroRespostaSerializer(serializers.Serializer):
    apontamento = ApontamentoSerializer()
    pausado = serializers.SerializerMethodField()

    def get_pausado(self, obj):
        p = obj.get("pausado")
        if not p:
            return None
        return {"id": p.pk, "tipo": p.tipo.nome, "minutos": p.minutos, "fim": p.fim}


class DecisaoLoteSerializer(serializers.Serializer):
    ids = serializers.ListField(child=serializers.IntegerField(), allow_empty=False)
    aprovar = serializers.BooleanField()
    motivo = serializers.CharField(max_length=240, required=False, allow_blank=True, default="")


class RecusaSerializer(serializers.Serializer):
    motivo = serializers.CharField(max_length=240)
