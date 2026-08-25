from rest_framework.permissions import BasePermission


class TemEscopo(BasePermission):
    """Exige autenticação por chave de sistema com o escopo declarado em `view.escopo`."""

    message = "Escopo insuficiente para esta chave."

    def has_permission(self, request, view) -> bool:
        sistema = getattr(request, "sistema_externo", None)
        if sistema is None:
            return False
        escopo = getattr(view, "escopo", None)
        return escopo is None or sistema.tem_escopo(escopo)
