from rest_framework import serializers

from core.serializers import SetorSerializer, UsuarioResumoSerializer

from .models import Alocacao, Marco, Projeto


class MarcoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Marco
        fields = ["id", "nome", "previsto", "concluido_em"]
        read_only_fields = ["id", "concluido_em"]


class AlocacaoSerializer(serializers.ModelSerializer):
    usuario = UsuarioResumoSerializer(read_only=True)

    class Meta:
        model = Alocacao
        fields = ["id", "usuario", "percentual"]


class ProjetoSerializer(serializers.ModelSerializer):
    setor_solicitante = SetorSerializer(read_only=True)
    patrocinador = UsuarioResumoSerializer(read_only=True)
    responsavel = UsuarioResumoSerializer(read_only=True)
    fase_label = serializers.CharField(source="get_fase_display", read_only=True)
    minutos_realizados = serializers.IntegerField(read_only=True, default=0)
    em_risco = serializers.BooleanField(read_only=True, default=False)
    desvio_horas = serializers.SerializerMethodField()
    marcos = MarcoSerializer(many=True, read_only=True)
    alocacoes = AlocacaoSerializer(many=True, read_only=True)

    class Meta:
        model = Projeto
        fields = ["id", "nome", "setor_solicitante", "patrocinador", "responsavel", "fase", "fase_label",
                  "horas_estimadas", "minutos_realizados", "desvio_horas", "inicio_previsto", "fim_previsto",
                  "em_risco", "encerrado_em", "situacao_final", "marcos", "alocacoes", "criado_em"]  # fmt: skip
        read_only_fields = fields

    def get_desvio_horas(self, obj) -> float:
        return round(getattr(obj, "minutos_realizados", 0) / 60 - obj.horas_estimadas, 1)


class ProjetoEntradaSerializer(serializers.Serializer):
    nome = serializers.CharField(max_length=180)
    setor_solicitante = serializers.PrimaryKeyRelatedField(queryset=Projeto.objects.none())
    patrocinador = serializers.PrimaryKeyRelatedField(queryset=Projeto.objects.none())
    responsavel = serializers.PrimaryKeyRelatedField(queryset=Projeto.objects.none(), required=False, allow_null=True)
    horas_estimadas = serializers.IntegerField(min_value=0, required=False, default=0)
    inicio_previsto = serializers.DateField(required=False, allow_null=True)
    fim_previsto = serializers.DateField(required=False, allow_null=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from core.models import Setor, User

        self.fields["setor_solicitante"].queryset = Setor.objects.filter(ativo=True)
        self.fields["patrocinador"].queryset = User.objects.filter(is_active=True)
        self.fields["responsavel"].queryset = User.objects.filter(is_active=True)


class MoverFaseSerializer(serializers.Serializer):
    fase = serializers.ChoiceField(choices=Projeto.Fase.choices)
    encerrado_em = serializers.DateField(required=False, allow_null=True)
    situacao_final = serializers.CharField(max_length=180, required=False, allow_blank=True, default="")


class AlocacaoEntradaSerializer(serializers.Serializer):
    usuario = serializers.PrimaryKeyRelatedField(queryset=Projeto.objects.none())
    percentual = serializers.IntegerField(min_value=1, max_value=100)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from core.models import User

        self.fields["usuario"].queryset = User.objects.filter(is_active=True)
