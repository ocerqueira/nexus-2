"""
Testes unitários para app.core.resolvedor_parametros.
Função pura — sem deps externas, sem BD.
"""

from calendar import monthrange
from datetime import date, timedelta

import pytest

from app.core.resolvedor_parametros import resolver_tokens


def _esperado_hoje() -> str:
    return str(date.today())


def _esperado_ontem() -> str:
    return str(date.today() - timedelta(days=1))


def _esperado_mes_atual_inicio() -> str:
    return str(date.today().replace(day=1))


def _esperado_mes_atual_fim() -> str:
    hoje = date.today()
    return str(hoje.replace(day=monthrange(hoje.year, hoje.month)[1]))


def _esperado_mes_anterior_inicio() -> str:
    hoje = date.today()
    if hoje.month == 1:
        return str(date(hoje.year - 1, 12, 1))
    return str(date(hoje.year, hoje.month - 1, 1))


def _esperado_mes_anterior_fim() -> str:
    hoje = date.today()
    if hoje.month == 1:
        mes_ant = date(hoje.year - 1, 12, 1)
    else:
        mes_ant = date(hoje.year, hoje.month - 1, 1)
    return str(mes_ant.replace(day=monthrange(mes_ant.year, mes_ant.month)[1]))


def _esperado_semana_atual_inicio() -> str:
    hoje = date.today()
    return str(hoje - timedelta(days=hoje.weekday()))


def _esperado_semana_atual_fim() -> str:
    hoje = date.today()
    return str(hoje - timedelta(days=hoje.weekday()) + timedelta(days=6))


# =============================================================================
# Tokens de data
# =============================================================================

def test_hoje():
    assert resolver_tokens({"d": "{{hoje}}"})["d"] == _esperado_hoje()


def test_ontem():
    assert resolver_tokens({"d": "{{ontem}}"})["d"] == _esperado_ontem()


def test_mes_atual_inicio():
    assert resolver_tokens({"d": "{{mes_atual_inicio}}"})["d"] == _esperado_mes_atual_inicio()


def test_mes_atual_fim():
    assert resolver_tokens({"d": "{{mes_atual_fim}}"})["d"] == _esperado_mes_atual_fim()


def test_mes_anterior_inicio():
    assert resolver_tokens({"d": "{{mes_anterior_inicio}}"})["d"] == _esperado_mes_anterior_inicio()


def test_mes_anterior_fim():
    assert resolver_tokens({"d": "{{mes_anterior_fim}}"})["d"] == _esperado_mes_anterior_fim()


def test_semana_atual_inicio():
    assert resolver_tokens({"d": "{{semana_atual_inicio}}"})["d"] == _esperado_semana_atual_inicio()


def test_semana_atual_fim():
    assert resolver_tokens({"d": "{{semana_atual_fim}}"})["d"] == _esperado_semana_atual_fim()


# =============================================================================
# Tokens inteiros (retornam string numérica)
# =============================================================================

def test_ano_atual():
    assert resolver_tokens({"a": "{{ano_atual}}"})["a"] == str(date.today().year)


def test_mes_atual():
    assert resolver_tokens({"m": "{{mes_atual}}"})["m"] == str(date.today().month)


def test_ano_anterior():
    assert resolver_tokens({"a": "{{ano_anterior}}"})["a"] == str(date.today().year - 1)


# =============================================================================
# Comportamento de passagem
# =============================================================================

def test_dict_vazio_retorna_vazio():
    assert resolver_tokens({}) == {}


def test_valor_nao_string_passa_sem_alteracao():
    parametros = {"n": 42, "b": True, "l": [1, 2], "f": 3.14}
    resultado = resolver_tokens(parametros)
    assert resultado == parametros


def test_token_desconhecido_mantido():
    assert resolver_tokens({"x": "{{foo}}"})["x"] == "{{foo}}"


def test_string_sem_token_mantida():
    assert resolver_tokens({"s": "sem token"})["s"] == "sem token"


def test_multiplos_tokens_na_mesma_string():
    resultado = resolver_tokens({"periodo": "{{mes_atual_inicio}} a {{mes_atual_fim}}"})
    esperado = f"{_esperado_mes_atual_inicio()} a {_esperado_mes_atual_fim()}"
    assert resultado["periodo"] == esperado


def test_token_e_texto_fixo_misturados():
    resultado = resolver_tokens({"q": "data_emissao >= '{{mes_anterior_inicio}}'"})
    assert resultado["q"] == f"data_emissao >= '{_esperado_mes_anterior_inicio()}'"


def test_dict_original_nao_e_mutado():
    original = {"d": "{{hoje}}"}
    resolver_tokens(original)
    assert original["d"] == "{{hoje}}"


def test_chaves_preservadas():
    params = {"data_ini": "{{hoje}}", "data_fim": "{{ontem}}"}
    resultado = resolver_tokens(params)
    assert set(resultado.keys()) == {"data_ini", "data_fim"}


# =============================================================================
# Caso de borda: janeiro → mês anterior é dezembro do ano anterior
# =============================================================================

def test_mes_anterior_em_janeiro(monkeypatch):
    class FakeDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 1, 15)

    import app.core.resolvedor_parametros as mod
    monkeypatch.setattr(mod, "date", FakeDate)

    resultado = resolver_tokens({
        "ini": "{{mes_anterior_inicio}}",
        "fim": "{{mes_anterior_fim}}",
    })
    assert resultado["ini"] == "2025-12-01"
    assert resultado["fim"] == "2025-12-31"


def test_semana_atual_inicio_e_sempre_segunda(monkeypatch):
    # Fixa hoje como quarta-feira para garantir que semana_atual_inicio seja segunda
    class FakeDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 6, 24)  # quarta-feira

    import app.core.resolvedor_parametros as mod
    monkeypatch.setattr(mod, "date", FakeDate)

    resultado = resolver_tokens({"ini": "{{semana_atual_inicio}}", "fim": "{{semana_atual_fim}}"})
    assert resultado["ini"] == "2026-06-22"  # segunda
    assert resultado["fim"] == "2026-06-28"  # domingo
