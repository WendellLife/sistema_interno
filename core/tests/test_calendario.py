"""Testes puros do calendário de horas úteis — não precisam de banco."""

from datetime import date, datetime

from core.calendario import FUSO, minutos_uteis_entre, somar_horas_uteis


def dt(y, m, d, h, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=FUSO)


def test_critica_aberta_sexta_16h_vence_segunda_11h():
    # 21/08/2026 é sexta. 16→17 = 1h; segunda 08→11 = 3h.
    resultado = somar_horas_uteis(dt(2026, 8, 21, 16), 4).astimezone(FUSO)
    assert resultado == dt(2026, 8, 24, 11)


def test_pula_almoco():
    assert somar_horas_uteis(dt(2026, 8, 24, 11), 2).astimezone(FUSO) == dt(2026, 8, 24, 14)


def test_aberto_fora_da_jornada_comeca_as_8h():
    assert somar_horas_uteis(dt(2026, 8, 24, 6), 1).astimezone(FUSO) == dt(2026, 8, 24, 9)
    assert somar_horas_uteis(dt(2026, 8, 24, 19), 1).astimezone(FUSO) == dt(2026, 8, 25, 9)


def test_respeita_feriado_da_tabela():
    feriados = frozenset({date(2026, 8, 25)})
    assert somar_horas_uteis(dt(2026, 8, 24, 16), 2, feriados).astimezone(FUSO) == dt(2026, 8, 26, 9)


def test_24h_uteis_sao_3_dias():
    assert somar_horas_uteis(dt(2026, 8, 24, 8), 24).astimezone(FUSO) == dt(2026, 8, 26, 17)


def test_minutos_uteis_entre_inverso_de_somar():
    inicio = dt(2026, 8, 21, 16)
    fim = somar_horas_uteis(inicio, 4)
    assert minutos_uteis_entre(inicio, fim) == 240
