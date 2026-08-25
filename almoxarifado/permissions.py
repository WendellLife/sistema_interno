"""Quem pode o quê no almoxarifado (regra §12). O escopo de dados fica no viewset."""

from rest_framework.permissions import BasePermission

from core import papeis
from core.permissions import papeis_de

MOVIMENTA = {papeis.RESPONSAVEL, papeis.COMPRAS, papeis.ADMINISTRADOR}
COMPRAS_OU_ADMIN = {papeis.COMPRAS, papeis.ADMINISTRADOR}
APROVA_SOLICITACAO = {papeis.GERENTE_SETOR, papeis.COMPRAS, papeis.ADMINISTRADOR}
ABRE_INVENTARIO = {papeis.RESPONSAVEL, papeis.COMPRAS, papeis.ADMINISTRADOR}


def tem_papel(user, conjunto) -> bool:
    return bool(papeis_de(user) & conjunto)


class PodeMovimentar(BasePermission):
    def has_permission(self, request, view):
        return tem_papel(request.user, MOVIMENTA)


class EhCompras(BasePermission):
    def has_permission(self, request, view):
        return tem_papel(request.user, COMPRAS_OU_ADMIN)


class PodeAprovarSolicitacao(BasePermission):
    def has_permission(self, request, view):
        return tem_papel(request.user, APROVA_SOLICITACAO)


class PodeInventariar(BasePermission):
    def has_permission(self, request, view):
        return tem_papel(request.user, ABRE_INVENTARIO)


def setor_permitido(user, setor) -> bool:
    """Compras/Admin: qualquer setor; demais: só o próprio."""
    return tem_papel(user, COMPRAS_OU_ADMIN) or setor.pk == user.setor_id
