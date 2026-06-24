"""
Testes da calculadora de próximas execuções.

Cobre os 7 cenários documentados em docs/PROJETO_NEXUS_PROXIMOS_PASSOS.md.
"""

from datetime import datetime

from app.core.calculadora_agenda import (
    _eh_dia_util,
    _ordenar_horarios,
    _proximo_dia_util,
    _proximo_mes,
    calcular_proximo_envio,
    calcular_proximo_envio_diaria,
    calcular_proximo_envio_mensal,
    calcular_proximo_envio_semanal,
)


# =============================================================================
# Helpers
# =============================================================================

def _ag(
    frequencia: str,
    horarios: list[dict],
    dia_semana: int | None = None,
    dia_mes: int | None = None,
    apenas_dias_uteis: bool = False,
) -> dict:
    """Factory de agendamento para encurtar os testes."""
    return {
        "frequencia": frequencia,
        "horarios": horarios,
        "dia_semana": dia_semana,
        "dia_mes": dia_mes,
        "apenas_dias_uteis": apenas_dias_uteis,
    }


# Junho 2026:
#   seg 22, ter 23, qua 24, qui 25, sex 26, sáb 27, dom 28


# =============================================================================
# Testes unitários das funções auxiliares
# =============================================================================

def test_eh_dia_util_segunda():
    from datetime import date
    assert _eh_dia_util(date(2026, 6, 22)) is True   # segunda
    assert _eh_dia_util(date(2026, 6, 23)) is True   # terça
    assert _eh_dia_util(date(2026, 6, 26)) is True   # sexta
    assert _eh_dia_util(date(2026, 6, 27)) is False  # sábado
    assert _eh_dia_util(date(2026, 6, 28)) is False  # domingo


def test_proximo_dia_util():
    from datetime import date
    assert _proximo_dia_util(date(2026, 6, 26)) == date(2026, 6, 26)  # já é útil
    assert _proximo_dia_util(date(2026, 6, 27)) == date(2026, 6, 29)  # sábado → segunda
    assert _proximo_dia_util(date(2026, 6, 28)) == date(2026, 6, 29)  # domingo → segunda


def test_ordenar_horarios():
    desordenados = [
        {"hora": 18, "minuto": 0},
        {"hora": 8, "minuto": 0},
        {"hora": 14, "minuto": 30},
    ]
    ordenados = _ordenar_horarios(desordenados)
    assert ordenados == [
        {"hora": 8, "minuto": 0},
        {"hora": 14, "minuto": 30},
        {"hora": 18, "minuto": 0},
    ]


def test_proximo_mes_mesmo_dia():
    from datetime import date
    assert _proximo_mes(date(2026, 6, 22), 5) == date(2026, 7, 5)


def test_proximo_mes_vira_ano():
    from datetime import date
    assert _proximo_mes(date(2026, 12, 10), 5) == date(2027, 1, 5)


def test_proximo_mes_dia_inexistente():
    from datetime import date
    # 31 não existe em fevereiro → ajusta para 28
    resultado = _proximo_mes(date(2026, 1, 15), 31)
    assert resultado == date(2026, 2, 28)


# =============================================================================
# Cenário 1: Diário 9h, partindo de segunda 10:30 → terça 09:00
# =============================================================================

def test_cenario_1_diario_9h_segunda_depois_do_horario():
    agendamento = _ag("diaria", [{"hora": 9, "minuto": 0}])
    a_partir_de = datetime(2026, 6, 22, 10, 30)  # segunda
    resultado = calcular_proximo_envio(agendamento, a_partir_de)
    assert resultado == datetime(2026, 6, 23, 9, 0)  # terça


# =============================================================================
# Cenário 2: Diário 8h/14h/18h, partindo de segunda 10:30 → mesmo dia 14:00
# =============================================================================

def test_cenario_2_diario_multihorario_proximo_mesmo_dia():
    agendamento = _ag("diaria", [
        {"hora": 8, "minuto": 0},
        {"hora": 14, "minuto": 0},
        {"hora": 18, "minuto": 0},
    ])
    a_partir_de = datetime(2026, 6, 22, 10, 30)  # segunda
    resultado = calcular_proximo_envio(agendamento, a_partir_de)
    assert resultado == datetime(2026, 6, 22, 14, 0)  # mesmo dia


# =============================================================================
# Cenário 3: Sexta 23:30, apenas dias úteis → próxima segunda 09:00
# =============================================================================

def test_cenario_3_sexta_noite_dias_uteis():
    agendamento = _ag("diaria", [{"hora": 9, "minuto": 0}], apenas_dias_uteis=True)
    a_partir_de = datetime(2026, 6, 26, 23, 30)  # sexta à noite
    resultado = calcular_proximo_envio(agendamento, a_partir_de)
    assert resultado == datetime(2026, 6, 29, 9, 0)  # segunda


# =============================================================================
# Cenário 4: Semanal segunda 8h, partindo de terça → próxima segunda
# =============================================================================

def test_cenario_4_semanal_segunda_partindo_terca():
    agendamento = _ag("semanal", [{"hora": 8, "minuto": 0}], dia_semana=1)
    a_partir_de = datetime(2026, 6, 23, 10, 0)  # terça
    resultado = calcular_proximo_envio(agendamento, a_partir_de)
    assert resultado == datetime(2026, 6, 29, 8, 0)  # próxima segunda


# =============================================================================
# Cenário 5: Mensal dia 5 às 14h, partindo de dia 10 → próximo mês
# =============================================================================

def test_cenario_5_mensal_dia_5_partindo_dia_10():
    agendamento = _ag("mensal", [{"hora": 14, "minuto": 0}], dia_mes=5)
    a_partir_de = datetime(2026, 6, 10, 12, 0)  # dia 10, depois do dia 5
    resultado = calcular_proximo_envio(agendamento, a_partir_de)
    assert resultado == datetime(2026, 7, 5, 14, 0)  # próximo mês


# =============================================================================
# Cenário 6: Mensal dia 31, partindo de 31/jan às 16h → 28/fev (ajuste)
# =============================================================================

def test_cenario_6_mensal_dia_31_ajuste_fevereiro():
    agendamento = _ag("mensal", [{"hora": 9, "minuto": 0}], dia_mes=31)
    # 31 de janeiro às 16h — já passou do horário das 9h
    a_partir_de = datetime(2026, 1, 31, 16, 0)
    resultado = calcular_proximo_envio(agendamento, a_partir_de)
    # Fevereiro 2026 tem 28 dias → ajusta de 31 para 28
    assert resultado == datetime(2026, 2, 28, 9, 0)


# =============================================================================
# Cenário 7: 8h e 18h apenas dias úteis, sexta 19h → segunda 08:00
# =============================================================================

def test_cenario_7_multihorario_dias_uteis_sexta_noite():
    agendamento = _ag("diaria", [
        {"hora": 8, "minuto": 0},
        {"hora": 18, "minuto": 0},
    ], apenas_dias_uteis=True)
    a_partir_de = datetime(2026, 6, 26, 19, 0)  # sexta 19h
    resultado = calcular_proximo_envio(agendamento, a_partir_de)
    assert resultado == datetime(2026, 6, 29, 8, 0)  # segunda


# =============================================================================
# Testes de borda adicionais
# =============================================================================

def test_diaria_sem_horario_futuro_hoje():
    """Se nenhum horário hoje é futuro, vai para amanhã no primeiro horário."""
    agendamento = _ag("diaria", [{"hora": 8, "minuto": 0}, {"hora": 12, "minuto": 0}])
    a_partir_de = datetime(2026, 6, 22, 14, 0)  # segunda 14h
    resultado = calcular_proximo_envio(agendamento, a_partir_de)
    assert resultado == datetime(2026, 6, 23, 8, 0)  # terça 8h


def test_semanal_mesmo_dia_horario_valido():
    """Segunda 7h, partindo de segunda 6h → mesmo dia 8h."""
    agendamento = _ag("semanal", [{"hora": 8, "minuto": 0}], dia_semana=1)
    a_partir_de = datetime(2026, 6, 22, 6, 0)  # segunda cedo
    resultado = calcular_proximo_envio(agendamento, a_partir_de)
    assert resultado == datetime(2026, 6, 22, 8, 0)  # mesmo dia


def test_mensal_mesmo_dia_horario_valido():
    """Dia 22 às 7h, partindo de dia 22 às 6h → mesmo dia 14h."""
    agendamento = _ag("mensal", [{"hora": 14, "minuto": 0}], dia_mes=22)
    a_partir_de = datetime(2026, 6, 22, 6, 0)
    resultado = calcular_proximo_envio(agendamento, a_partir_de)
    assert resultado == datetime(2026, 6, 22, 14, 0)


def test_frequencia_invalida():
    """Frequência não suportada deve lançar ValueError."""
    agendamento = _ag("anual", [{"hora": 9, "minuto": 0}])
    try:
        calcular_proximo_envio(agendamento)
        assert False, "Deveria ter lançado ValueError"
    except ValueError as e:
        assert "anual" in str(e)


def test_dispatcher_chama_funcao_correta():
    """Verifica que o dispatcher chama a função correta para cada frequência."""
    # diaria
    r = calcular_proximo_envio(
        _ag("diaria", [{"hora": 10, "minuto": 0}]),
        datetime(2026, 6, 22, 9, 0),
    )
    assert r == datetime(2026, 6, 22, 10, 0)

    # semanal
    r = calcular_proximo_envio(
        _ag("semanal", [{"hora": 10, "minuto": 0}], dia_semana=1),
        datetime(2026, 6, 22, 9, 0),
    )
    assert r == datetime(2026, 6, 22, 10, 0)

    # mensal
    r = calcular_proximo_envio(
        _ag("mensal", [{"hora": 10, "minuto": 0}], dia_mes=22),
        datetime(2026, 6, 22, 9, 0),
    )
    assert r == datetime(2026, 6, 22, 10, 0)
