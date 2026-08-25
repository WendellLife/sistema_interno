"""Camada 2 da permissão: *vê o quê?* — queryset escopado por setor e papel."""

from __future__ import annotations

from .permissions import ve_todos_setores


class SetorScopedQuerysetMixin:
    """Aplicar em TODO viewset. Sobrescreva `escopar_para_setor` quando o escopo
    do Colaborador for mais estreito do que 'o próprio setor'."""

    campo_setor = "setor"

    def get_queryset(self):
        qs = super().get_queryset()  # type: ignore[misc]
        user = self.request.user  # type: ignore[attr-defined]
        if ve_todos_setores(user):
            return qs
        return self.escopar_para_setor(qs, user)

    def escopar_para_setor(self, qs, user):
        return qs.filter(**{self.campo_setor: user.setor})
