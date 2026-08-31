"""Efeitos colaterais idempotentes de setup (grupos e matriz padrão) após `migrate`."""

from django.contrib.auth.models import Group

from . import papeis
from .calendario import invalidar_feriados
from .models import Feriado, PermissaoModulo


def garantir_papeis_e_matriz(**kwargs) -> None:
    for nome in papeis.TODOS:
        Group.objects.get_or_create(name=nome)
    if not PermissaoModulo.objects.exists():
        PermissaoModulo.objects.bulk_create(
            PermissaoModulo(papel=papel, modulo=modulo, nivel=nivel)
            for modulo, linha in papeis.MATRIZ_PADRAO.items()
            for papel, nivel in linha.items()
        )


def limpar_cache_de_feriados(sender, instance: Feriado, **kwargs) -> None:
    """Editar o calendário tem de valer na próxima requisição, não no fim do TTL."""
    invalidar_feriados(instance.data.year)
