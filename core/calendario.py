"""Horas úteis: jornada 08:00–12:00 / 13:00–17:00, seg–sex, sem feriados.

Função pura — recebe o conjunto de feriados para ser testável sem banco.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

FUSO = ZoneInfo("America/Sao_Paulo")
JORNADA: tuple[tuple[time, time], ...] = ((time(8, 0), time(12, 0)), (time(13, 0), time(17, 0)))
MINUTOS_POR_DIA_UTIL = 480


@lru_cache(maxsize=8)
def feriados_nacionais(ano: int) -> frozenset[date]:
    try:
        from workalendar.america import Brazil
    except ImportError:  # pragma: no cover
        return frozenset()
    return frozenset(d for d, _ in Brazil().holidays(ano))


def feriados_do_sistema(ano: int) -> frozenset[date]:
    """Nacionais (workalendar) + tabela editável `core.Feriado`."""
    from .models import Feriado

    municipais = Feriado.objects.filter(data__year=ano).values_list("data", flat=True)
    return feriados_nacionais(ano) | frozenset(municipais)


def dia_util(dia: date, feriados: frozenset[date] | set[date] = frozenset()) -> bool:
    return dia.weekday() < 5 and dia not in feriados


def _proximo_inicio_jornada(dia: date, feriados) -> datetime:
    dia = dia + timedelta(days=1)
    while not dia_util(dia, feriados):
        dia += timedelta(days=1)
    return datetime.combine(dia, JORNADA[0][0], tzinfo=FUSO)


def somar_minutos_uteis(inicio: datetime, minutos: int, feriados=frozenset()) -> datetime:
    """Avança `minutos` úteis a partir de `inicio` (aware). Retorna aware em UTC."""
    if minutos < 0:
        raise ValueError("minutos deve ser >= 0")
    atual = inicio.astimezone(FUSO)
    restante = minutos
    while True:
        if not dia_util(atual.date(), feriados):
            atual = _proximo_inicio_jornada(atual.date(), feriados)
            continue
        for ini, fim in JORNADA:
            bloco_ini = datetime.combine(atual.date(), ini, tzinfo=FUSO)
            bloco_fim = datetime.combine(atual.date(), fim, tzinfo=FUSO)
            if atual >= bloco_fim:
                continue
            if atual < bloco_ini:
                atual = bloco_ini
            disponivel = int((bloco_fim - atual).total_seconds() // 60)
            if disponivel >= restante:
                return (atual + timedelta(minutes=restante)).astimezone(ZoneInfo("UTC"))
            restante -= disponivel
            atual = bloco_fim
        atual = _proximo_inicio_jornada(atual.date(), feriados)


def somar_horas_uteis(inicio: datetime, horas: int, feriados=frozenset()) -> datetime:
    return somar_minutos_uteis(inicio, horas * 60, feriados)


def minutos_uteis_entre(inicio: datetime, fim: datetime, feriados=frozenset()) -> int:
    """Minutos úteis entre dois instantes (fim >= inicio). Usado para 'tempo restante'."""
    if fim <= inicio:
        return 0
    a = inicio.astimezone(FUSO)
    b = fim.astimezone(FUSO)
    total = 0
    dia = a.date()
    while dia <= b.date():
        if dia_util(dia, feriados):
            for ini, fimj in JORNADA:
                bi = max(datetime.combine(dia, ini, tzinfo=FUSO), a)
                bf = min(datetime.combine(dia, fimj, tzinfo=FUSO), b)
                if bf > bi:
                    total += int((bf - bi).total_seconds() // 60)
        dia += timedelta(days=1)
    return total
