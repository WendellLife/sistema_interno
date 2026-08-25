from rest_framework import serializers

from . import papeis
from .models import CentroCusto, PermissaoModulo, Setor, User
from .permissions import nivel_no_modulo, papeis_de


class SetorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Setor
        fields = ["id", "nome", "sigla", "ativo"]


class UsuarioResumoSerializer(serializers.ModelSerializer):
    nome = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = ["id", "nome", "matricula"]


class CentroCustoSerializer(serializers.ModelSerializer):
    class Meta:
        model = CentroCusto
        fields = ["id", "codigo", "descricao", "setor", "projeto", "ativo"]


class PermissaoModuloSerializer(serializers.ModelSerializer):
    class Meta:
        model = PermissaoModulo
        fields = ["id", "papel", "modulo", "nivel"]


ORDEM_MENU = ["painel", "tarefas", "tarefa", "projetos", "almoxarifado", "compras", "config"]


def montar_me(user) -> dict:
    """Payload de /auth/me/ — o menu é decidido AQUI, nunca no cliente."""
    meus_papeis = papeis_de(user)
    niveis = {m: nivel_no_modulo(user, m) for m in papeis.MODULOS}
    return {
        "id": user.id,
        "nome": user.nome,
        "matricula": user.matricula,
        "setor": SetorSerializer(user.setor).data,
        "papeis": sorted(meus_papeis),
        "permissoes": {
            "ver_painel": niveis["painel"] != "-",
            "ver_projetos": niveis["projetos"] != "-",
            "ver_compras": niveis["compras"] != "-",
            "ver_config": niveis["config"] != "-",
            "todos_setores": bool(meus_papeis & papeis.VE_TODOS_SETORES),
            "aprovar_horas": bool(meus_papeis & papeis.APROVA_HORAS),
            "niveis": niveis,
        },
        "menu": [m for m in ORDEM_MENU if niveis[m] != "-"],
    }
