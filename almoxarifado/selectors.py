from __future__ import annotations

from decimal import Decimal

from django.db.models import Case, Count, DecimalField, F, Q, Sum, Value, When

from .models import Estoque, Item, Movimento


def itens_com_saldo(setor=None):
    """Itens com saldo do setor anotado (0 quando não há Estoque) e flag abaixo_minimo."""
    filtro = Q(estoques__setor=setor) if setor else Q()
    return (
        Item.objects.filter(ativo=True)
        .select_related("setor_dono")
        .annotate(
            saldo=Sum("estoques__saldo", filter=filtro, default=Value(Decimal("0")),
                      output_field=DecimalField(max_digits=14, decimal_places=3))
        )  # fmt: skip
        .annotate(abaixo_minimo=Case(When(saldo__lte=F("estoque_minimo"), then=Value(True)),
                                     default=Value(False)))  # fmt: skip
    )


def estoque_por_setor(setor):
    return Estoque.objects.filter(setor=setor).select_related("item", "item__setor_dono").order_by("item__codigo")


def saldo(item, setor) -> Decimal:
    return Estoque.objects.filter(item=item, setor=setor).values_list("saldo", flat=True).first() or Decimal("0")


def consumo(de=None, ate=None, setor=None, sem_os: bool | None = None):
    """Saídas (consumo) no período. `sem_os=True` = consumo geral (regra §8)."""
    qs = Movimento.objects.filter(tipo=Movimento.Tipo.SAIDA).select_related(
        "item", "setor", "centro_custo", "usuario"
    )
    if de:
        qs = qs.filter(criado_em__date__gte=de)
    if ate:
        qs = qs.filter(criado_em__date__lte=ate)
    if setor:
        qs = qs.filter(setor=setor)
    if sem_os is not None:
        geral = Q(os_ref="") & Q(chamado__isnull=True) & Q(projeto__isnull=True)
        qs = qs.filter(geral) if sem_os else qs.exclude(geral)
    return qs


def consumo_por_setor(qs):
    # `setor` e `setor_id` são campos do próprio Movimento: usá-los como apelido de anotação
    # faz o Django recusar a consulta. Agrega pelo caminho e renomeia depois.
    linhas = (
        qs.values("setor_id", "setor__sigla")
        .annotate(valor=Sum(F("quantidade") * F("item__custo_unitario"),
                            output_field=DecimalField(max_digits=16, decimal_places=2)),
                  movimentos=Count("id"))  # fmt: skip
        .order_by("-valor")
    )
    return [
        {
            "setor_id": linha["setor_id"],
            "setor": linha["setor__sigla"],
            "valor": linha["valor"],
            "movimentos": linha["movimentos"],
        }
        for linha in linhas
    ]


def reconciliar() -> list[dict]:
    """Estoque.saldo deve ser igual a Σ(quantidade × sinal) dos movimentos. Retorna divergências."""
    somas = {
        (m["item_id"], m["setor_id"]): m["total"]
        for m in Movimento.objects.values("item_id", "setor_id").annotate(
            total=Sum(F("quantidade") * F("sinal"), output_field=DecimalField(max_digits=16, decimal_places=3))
        )
    }
    problemas = []
    for e in Estoque.objects.all():
        esperado = somas.get((e.item_id, e.setor_id), Decimal("0"))
        if e.saldo != esperado:
            problemas.append({"item_id": e.item_id, "setor_id": e.setor_id, "saldo": e.saldo, "esperado": esperado})
    return problemas
