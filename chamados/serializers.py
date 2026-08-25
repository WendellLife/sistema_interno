from django.conf import settings
from rest_framework import serializers

from core.serializers import SetorSerializer, UsuarioResumoSerializer

from . import selectors
from .models import Anexo, Categoria, Chamado, Comentario, HistoricoChamado, RegraSLA


class CategoriaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Categoria
        fields = ["id", "nome", "slug", "exige_documentacao"]


class RegraSLASerializer(serializers.ModelSerializer):
    class Meta:
        model = RegraSLA
        fields = ["id", "categoria", "prioridade", "horas_uteis"]


class ChamadoListSerializer(serializers.ModelSerializer):
    setor_origem = SetorSerializer(read_only=True)
    solicitante = UsuarioResumoSerializer(read_only=True)
    responsavel = UsuarioResumoSerializer(read_only=True)
    categoria = CategoriaSerializer(read_only=True)
    projeto_nome = serializers.CharField(source="projeto.nome", read_only=True, default=None)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    prioridade_label = serializers.CharField(source="get_prioridade_display", read_only=True)
    minutos_uteis_restantes = serializers.SerializerMethodField()

    class Meta:
        model = Chamado
        fields = [
            "id", "numero", "titulo", "setor_origem", "solicitante", "categoria",
            "prioridade", "prioridade_label", "status", "status_label", "responsavel",
            "projeto", "projeto_nome", "horas_previstas_min", "sla_previsto", "sla_cumprido",
            "minutos_uteis_restantes", "entregue_em", "criado_em", "atualizado_em",
        ]  # fmt: skip
        read_only_fields = fields

    def get_minutos_uteis_restantes(self, obj) -> int | None:
        return selectors.minutos_uteis_restantes(obj)


class ChamadoDetailSerializer(ChamadoListSerializer):
    descricao = serializers.CharField(read_only=True)
    pode_entregar = serializers.SerializerMethodField()

    class Meta(ChamadoListSerializer.Meta):
        fields = [*ChamadoListSerializer.Meta.fields, "descricao", "pode_entregar"]
        read_only_fields = fields

    def get_pode_entregar(self, obj) -> dict:
        from .services import pode_entregar

        ok, faltando = pode_entregar(obj)
        return {"ok": ok, "faltando": faltando}


class ChamadoCreateSerializer(serializers.Serializer):
    titulo = serializers.CharField(max_length=180)
    descricao = serializers.CharField()
    categoria = serializers.PrimaryKeyRelatedField(queryset=Categoria.objects.all())
    prioridade = serializers.ChoiceField(choices=Chamado.Prioridade.choices)
    setor_origem = serializers.PrimaryKeyRelatedField(
        queryset=Categoria.objects.none(), required=False, allow_null=True
    )
    projeto = serializers.PrimaryKeyRelatedField(queryset=Categoria.objects.none(), required=False, allow_null=True)
    horas_previstas_min = serializers.IntegerField(min_value=0, required=False, default=0)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from core.models import Setor
        from projetos.models import Projeto

        self.fields["setor_origem"].queryset = Setor.objects.filter(ativo=True)
        self.fields["projeto"].queryset = Projeto.objects.all()


class ChamadoUpdateSerializer(serializers.Serializer):
    """PATCH: só campos editáveis; prioridade e responsável passam por serviço próprio."""

    titulo = serializers.CharField(max_length=180, required=False)
    descricao = serializers.CharField(required=False)
    prioridade = serializers.ChoiceField(choices=Chamado.Prioridade.choices, required=False)
    responsavel = serializers.PrimaryKeyRelatedField(
        queryset=Categoria.objects.none(), required=False, allow_null=True
    )
    horas_previstas_min = serializers.IntegerField(min_value=0, required=False)
    projeto = serializers.PrimaryKeyRelatedField(queryset=Categoria.objects.none(), required=False, allow_null=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from core.models import User
        from projetos.models import Projeto

        self.fields["responsavel"].queryset = User.objects.filter(is_active=True)
        self.fields["projeto"].queryset = Projeto.objects.all()


class TransicaoSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Chamado.Status.choices)
    comentario = serializers.CharField(required=False, allow_blank=True, default="")


class ComentarioSerializer(serializers.ModelSerializer):
    autor = UsuarioResumoSerializer(read_only=True)

    class Meta:
        model = Comentario
        fields = ["id", "autor", "texto", "interno", "criado_em"]
        read_only_fields = ["id", "autor", "criado_em"]


class AnexoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Anexo
        fields = ["id", "arquivo", "nome_original", "tamanho_bytes", "criado_em"]
        read_only_fields = ["id", "nome_original", "tamanho_bytes", "criado_em"]

    def validate_arquivo(self, arquivo):
        if arquivo.size > settings.ANEXO_TAMANHO_MAXIMO_BYTES:
            raise serializers.ValidationError("Arquivo acima de 20 MB.")
        return arquivo


class HistoricoSerializer(serializers.ModelSerializer):
    usuario = UsuarioResumoSerializer(read_only=True)

    class Meta:
        model = HistoricoChamado
        fields = ["id", "quando", "usuario", "texto"]
