"""Camada 1 da permissão: *pode chamar a ação?* (a camada 2 é o queryset escopado)."""

from __future__ import annotations

from django.conf import settings
from django.core.cache import cache
from rest_framework.permissions import SAFE_METHODS, BasePermission

from . import papeis
from .models import PermissaoModulo


def papeis_de(user) -> set[str]:
    if not user.is_authenticated:
        return set()
    chave = f"papeis:{user.pk}"
    valor = cache.get(chave)
    if valor is None:
        valor = set(user.groups.values_list("name", flat=True))
        cache.set(chave, valor, settings.PERMISSOES_CACHE_SEGUNDOS)
    return valor


def invalidar_papeis(user) -> None:
    cache.delete(f"papeis:{user.pk}")


def matriz() -> dict[tuple[str, str], str]:
    valor = cache.get("permissoes:matriz")
    if valor is None:
        valor = {(p.papel, p.modulo): p.nivel for p in PermissaoModulo.objects.all()}
        cache.set("permissoes:matriz", valor, settings.PERMISSOES_CACHE_SEGUNDOS)
    return valor


def invalidar_matriz() -> None:
    cache.delete("permissoes:matriz")


def nivel_no_modulo(user, modulo: str) -> str:
    """Maior nível entre os papéis do usuário no módulo ('-', 'V' ou 'E')."""
    ordem = {"-": 0, "V": 1, "E": 2}
    m = matriz()
    melhor = "-"
    for papel in papeis_de(user):
        n = m.get((papel, modulo), "-")
        if ordem[n] > ordem[melhor]:
            melhor = n
    return melhor


def ve_todos_setores(user) -> bool:
    return bool(papeis_de(user) & papeis.VE_TODOS_SETORES)


class AcessoModulo(BasePermission):
    """Leitura exige 'V'; escrita exige 'E'. Defina `modulo` no viewset."""

    def has_permission(self, request, view) -> bool:
        modulo = getattr(view, "modulo", None)
        if modulo is None:
            return True
        nivel = nivel_no_modulo(request.user, modulo)
        if request.method in SAFE_METHODS:
            return nivel in ("V", "E")
        return nivel == "E"


class AcessoModuloVisivel(BasePermission):
    """Exige apenas que o módulo seja VISÍVEL ('V' ou 'E'), mesmo em POST.

    Para ação cujo direito vem do PAPEL, não do nível de escrita do módulo: aprovar
    solicitação é do gerente do setor, que tem 'V' em almoxarifado. Continua havendo
    duas camadas — esta (o módulo aparece para mim?) e a classe de papel (posso esta
    ação?) —, mais o queryset escopado, que decide o que existe para mim.
    """

    def has_permission(self, request, view) -> bool:
        modulo = getattr(view, "modulo", None)
        if modulo is None:
            return True
        return nivel_no_modulo(request.user, modulo) in ("V", "E")


class PodeAprovarHoras(BasePermission):
    def has_permission(self, request, view) -> bool:
        return bool(papeis_de(request.user) & papeis.APROVA_HORAS)


class EhAdministrador(BasePermission):
    def has_permission(self, request, view) -> bool:
        return papeis.ADMINISTRADOR in papeis_de(request.user)


class EhTI(BasePermission):
    """Usuário do setor TI ou Gerente de TI/Admin — vê comentários internos."""

    def has_permission(self, request, view) -> bool:
        return eh_ti(request.user)


def eh_ti(user) -> bool:
    return user.setor.sigla == "TI" or bool(
        papeis_de(user) & {papeis.GERENTE_TI, papeis.ADMINISTRADOR}
    )
