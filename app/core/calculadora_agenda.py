"""
Calculadora de próximas execuções de agendamentos.
Considera frequência, horários múltiplos e dias úteis.
"""

import logging
from datetime import date, datetime, time, timedelta
from typing import Any

logger = logging.getLogger(__name__)


# Dias úteis: segunda(1) a sexta(5)
DIAS_UTEIS = {1, 2, 3, 4, 5}


def _eh_dia_util(data: date) -> bool:
    """Verifica se a data é dia útil (segunda a sexta)."""
    # Python: monday=0, sunday=6
    # Nossa convenção: segunda=1, domingo=7
    dia_python = data.weekday()  # 0=segunda, 6=domingo
    dia_nosso = dia_python + 1
    return dia_nosso in DIAS_UTEIS


def _proximo_dia_util(data: date) -> date:
    """Avança até cair em um dia útil."""
    while not _eh_dia_util(data):
        data += timedelta(days=1)
    return data


def _ordenar_horarios(horarios: list[dict]) -> list[dict]:
    """Ordena horários por hora e minuto (do menor para o maior)."""
    return sorted(horarios, key=lambda h: (h["hora"], h["minuto"]))


def _proximo_horario_no_dia(
    data: date,
    horarios: list[dict],
    agora: datetime,
) -> datetime | None:
    """
    Encontra o próximo horário disponível no dia informado.
    Retorna None se nenhum horário desse dia ainda é futuro em relação a 'agora'.
    """
    horarios_ordenados = _ordenar_horarios(horarios)

    for h in horarios_ordenados:
        candidato = datetime.combine(
            data,
            time(hour=h["hora"], minute=h["minuto"]),
        )
        if candidato > agora:
            return candidato

    return None


def calcular_proximo_envio_diaria(
    agendamento: dict,
    a_partir_de: datetime | None = None,
) -> datetime:
    """
    Calcula próximo envio para frequência diária.
    """
    agora = a_partir_de or datetime.now()
    horarios = agendamento["horarios"]
    apenas_dias_uteis = agendamento.get("apenas_dias_uteis", False)

    data_candidata = agora.date()

    # Se for restrito a dias úteis, avança para próximo dia útil
    if apenas_dias_uteis and not _eh_dia_util(data_candidata):
        data_candidata = _proximo_dia_util(data_candidata)
        # Como mudou o dia, pega o primeiro horário do dia
        primeiro_horario = _ordenar_horarios(horarios)[0]
        return datetime.combine(
            data_candidata,
            time(primeiro_horario["hora"], primeiro_horario["minuto"]),
        )

    # Tenta achar um horário ainda hoje
    proximo = _proximo_horario_no_dia(data_candidata, horarios, agora)
    if proximo:
        return proximo

    # Não tem mais horário hoje, vai para o próximo dia
    data_candidata += timedelta(days=1)

    if apenas_dias_uteis:
        data_candidata = _proximo_dia_util(data_candidata)

    primeiro_horario = _ordenar_horarios(horarios)[0]
    return datetime.combine(
        data_candidata,
        time(primeiro_horario["hora"], primeiro_horario["minuto"]),
    )


def calcular_proximo_envio_semanal(
    agendamento: dict,
    a_partir_de: datetime | None = None,
) -> datetime:
    """
    Calcula próximo envio para frequência semanal.
    Roda apenas no dia_semana configurado.
    """
    agora = a_partir_de or datetime.now()
    horarios = agendamento["horarios"]
    dia_semana_alvo = agendamento["dia_semana"]  # 1-7 (nossa convenção)
    apenas_dias_uteis = agendamento.get("apenas_dias_uteis", False)

    # Converte nossa convenção (1=seg, 7=dom) para Python (0=seg, 6=dom)
    dia_python_alvo = dia_semana_alvo - 1

    # Verifica se hoje é o dia configurado
    if agora.weekday() == dia_python_alvo:
        # Se for dia útil OK, ou não exige dia útil
        if not apenas_dias_uteis or _eh_dia_util(agora.date()):
            proximo = _proximo_horario_no_dia(agora.date(), horarios, agora)
            if proximo:
                return proximo

    # Avança dia a dia até cair no dia_semana correto
    data_candidata = agora.date() + timedelta(days=1)
    while data_candidata.weekday() != dia_python_alvo:
        data_candidata += timedelta(days=1)

    # Se cair em fim de semana mas exige dia útil, avança
    if apenas_dias_uteis and not _eh_dia_util(data_candidata):
        # Pula esse dia_semana e vai para o próximo (próxima semana)
        data_candidata += timedelta(days=7)
        # Se ainda assim cair em fim de semana, continua avançando
        while not _eh_dia_util(data_candidata):
            data_candidata += timedelta(days=7)

    primeiro_horario = _ordenar_horarios(horarios)[0]
    return datetime.combine(
        data_candidata,
        time(primeiro_horario["hora"], primeiro_horario["minuto"]),
    )


def calcular_proximo_envio_mensal(
    agendamento: dict,
    a_partir_de: datetime | None = None,
) -> datetime:
    """
    Calcula próximo envio para frequência mensal.
    Roda no dia_mes configurado.
    """
    agora = a_partir_de or datetime.now()
    horarios = agendamento["horarios"]
    dia_mes_alvo = agendamento["dia_mes"]
    apenas_dias_uteis = agendamento.get("apenas_dias_uteis", False)

    # Tenta no mês atual
    try:
        data_candidata = agora.date().replace(day=dia_mes_alvo)
    except ValueError:
        # Dia não existe no mês (ex: 31 em fevereiro) → pula para o próximo
        data_candidata = _proximo_mes(agora.date(), dia_mes_alvo)

    # Se a data já passou (ou é hoje sem horário válido), vai para o próximo mês
    if data_candidata < agora.date():
        data_candidata = _proximo_mes(agora.date(), dia_mes_alvo)
    elif data_candidata == agora.date():
        # Mesmo dia, mas pode ter horário válido ainda hoje
        if apenas_dias_uteis and not _eh_dia_util(data_candidata):
            data_candidata = _proximo_mes(agora.date(), dia_mes_alvo)
        else:
            proximo = _proximo_horario_no_dia(data_candidata, horarios, agora)
            if proximo:
                return proximo
            # Sem horário válido hoje, próximo mês
            data_candidata = _proximo_mes(agora.date(), dia_mes_alvo)

    # Avança até cair em dia útil se necessário
    if apenas_dias_uteis:
        while not _eh_dia_util(data_candidata):
            # Para mensal, se cair em fim de semana, vai para o próximo dia útil
            data_candidata += timedelta(days=1)

    primeiro_horario = _ordenar_horarios(horarios)[0]
    return datetime.combine(
        data_candidata,
        time(primeiro_horario["hora"], primeiro_horario["minuto"]),
    )


def _proximo_mes(data_atual: date, dia_alvo: int) -> date:
    """Retorna a mesma data no próximo mês, ajustando se o dia não existe."""
    ano = data_atual.year
    mes = data_atual.month + 1

    if mes > 12:
        ano += 1
        mes = 1

    # Tenta o dia alvo, se não existe pega o último dia do mês
    try:
        return date(ano, mes, dia_alvo)
    except ValueError:
        # Próximo mês não tem esse dia (ex: 31 de fev)
        # Tenta encontrar o último dia válido do mês
        for dia_tentativa in [30, 29, 28]:
            try:
                return date(ano, mes, dia_tentativa)
            except ValueError:
                continue
        # Não deveria chegar aqui
        return date(ano, mes, 28)


def calcular_proximo_envio(
    agendamento: dict,
    a_partir_de: datetime | None = None,
) -> datetime:
    """
    Calcula o próximo envio com base na configuração do agendamento.

    Args:
        agendamento: Dict com campos frequencia, horarios, dia_semana, dia_mes, etc
        a_partir_de: Data/hora base do cálculo (default: agora)

    Returns:
        datetime do próximo envio
    """
    frequencia = agendamento["frequencia"]

    if frequencia == "diaria":
        return calcular_proximo_envio_diaria(agendamento, a_partir_de)
    elif frequencia == "semanal":
        return calcular_proximo_envio_semanal(agendamento, a_partir_de)
    elif frequencia == "mensal":
        return calcular_proximo_envio_mensal(agendamento, a_partir_de)
    else:
        raise ValueError(f"Frequência não suportada: {frequencia}")
