"""
Calculadora de próximas execuções de agendamentos.
Considera frequência, horários múltiplos, dias úteis e timezone da unidade.

Horários no agendamento são sempre em hora LOCAL da unidade.
proximo_envio retornado é sempre UTC naive (para comparação consistente com utcnow()).
"""

import logging
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

_UTC = ZoneInfo("UTC")

# Dias úteis: segunda(1) a sexta(5) — convenção interna
DIAS_UTEIS = {1, 2, 3, 4, 5}


def _eh_dia_util(data: date) -> bool:
    dia_python = data.weekday()  # 0=seg, 6=dom
    return (dia_python + 1) in DIAS_UTEIS


def _proximo_dia_util(data: date) -> date:
    while not _eh_dia_util(data):
        data += timedelta(days=1)
    return data


def _ordenar_horarios(horarios: list[dict]) -> list[dict]:
    return sorted(horarios, key=lambda h: (h["hora"], h["minuto"]))


def _proximo_horario_no_dia(data: date, horarios: list[dict], agora_local: datetime) -> datetime | None:
    """Encontra o próximo horário disponível no dia em hora local."""
    for h in _ordenar_horarios(horarios):
        candidato = datetime.combine(data, time(h["hora"], h["minuto"]))
        if candidato > agora_local:
            return candidato
    return None


def _agora_utc(a_partir_de: datetime | None) -> datetime:
    """Retorna datetime UTC aware. Trata entrada naive como UTC."""
    if a_partir_de is None:
        return datetime.now(_UTC)
    if a_partir_de.tzinfo is None:
        return a_partir_de.replace(tzinfo=_UTC)
    return a_partir_de.astimezone(_UTC)


def _local_para_utc_naive(dt_local: datetime, tz: ZoneInfo) -> datetime:
    """Converte datetime local naive → UTC naive."""
    return dt_local.replace(tzinfo=tz).astimezone(_UTC).replace(tzinfo=None)


def calcular_proximo_envio_diaria(
    agendamento: dict,
    a_partir_de: datetime | None = None,
    timezone_str: str = "UTC",
) -> datetime:
    """Próximo horário diário em hora local, convertido para UTC naive."""
    tz = ZoneInfo(timezone_str)
    agora_utc = _agora_utc(a_partir_de)
    agora_local = agora_utc.astimezone(tz).replace(tzinfo=None)

    horarios = agendamento["horarios"]
    apenas_dias_uteis = agendamento.get("apenas_dias_uteis", False)
    data_candidata = agora_local.date()

    if apenas_dias_uteis and not _eh_dia_util(data_candidata):
        data_candidata = _proximo_dia_util(data_candidata)
        primeiro = _ordenar_horarios(horarios)[0]
        resultado = datetime.combine(data_candidata, time(primeiro["hora"], primeiro["minuto"]))
        return _local_para_utc_naive(resultado, tz)

    proximo = _proximo_horario_no_dia(data_candidata, horarios, agora_local)
    if proximo:
        return _local_para_utc_naive(proximo, tz)

    data_candidata += timedelta(days=1)
    if apenas_dias_uteis:
        data_candidata = _proximo_dia_util(data_candidata)

    primeiro = _ordenar_horarios(horarios)[0]
    resultado = datetime.combine(data_candidata, time(primeiro["hora"], primeiro["minuto"]))
    return _local_para_utc_naive(resultado, tz)


def calcular_proximo_envio_semanal(
    agendamento: dict,
    a_partir_de: datetime | None = None,
    timezone_str: str = "UTC",
) -> datetime:
    """
    Próximo envio no dia da semana configurado (dia_semana: 1=seg, 7=dom).
    Se hoje é o dia alvo mas já passou o horário, avança 7 dias.
    """
    tz = ZoneInfo(timezone_str)
    agora_utc = _agora_utc(a_partir_de)
    agora_local = agora_utc.astimezone(tz).replace(tzinfo=None)

    horarios = agendamento["horarios"]
    dia_semana_alvo = agendamento["dia_semana"]  # 1=seg, 7=dom
    apenas_dias_uteis = agendamento.get("apenas_dias_uteis", False)

    dia_python_alvo = dia_semana_alvo - 1  # Python: 0=seg, 6=dom

    if agora_local.weekday() == dia_python_alvo:
        if not apenas_dias_uteis or _eh_dia_util(agora_local.date()):
            proximo = _proximo_horario_no_dia(agora_local.date(), horarios, agora_local)
            if proximo:
                return _local_para_utc_naive(proximo, tz)

    data_candidata = agora_local.date() + timedelta(days=1)
    while data_candidata.weekday() != dia_python_alvo:
        data_candidata += timedelta(days=1)

    if apenas_dias_uteis and not _eh_dia_util(data_candidata):
        data_candidata += timedelta(days=7)
        while not _eh_dia_util(data_candidata):
            data_candidata += timedelta(days=7)

    primeiro = _ordenar_horarios(horarios)[0]
    resultado = datetime.combine(data_candidata, time(primeiro["hora"], primeiro["minuto"]))
    return _local_para_utc_naive(resultado, tz)


def calcular_proximo_envio_mensal(
    agendamento: dict,
    a_partir_de: datetime | None = None,
    timezone_str: str = "UTC",
) -> datetime:
    """
    Próximo envio no dia do mês configurado (dia_mes: 1-31).
    Se o dia não existe no mês (ex: dia 31 em fevereiro), avança para o próximo mês.
    """
    tz = ZoneInfo(timezone_str)
    agora_utc = _agora_utc(a_partir_de)
    agora_local = agora_utc.astimezone(tz).replace(tzinfo=None)

    horarios = agendamento["horarios"]
    dia_mes_alvo = agendamento["dia_mes"]
    apenas_dias_uteis = agendamento.get("apenas_dias_uteis", False)

    try:
        data_candidata = agora_local.date().replace(day=dia_mes_alvo)
    except ValueError:
        data_candidata = _proximo_mes(agora_local.date(), dia_mes_alvo)

    if data_candidata < agora_local.date():
        data_candidata = _proximo_mes(agora_local.date(), dia_mes_alvo)
    elif data_candidata == agora_local.date():
        if apenas_dias_uteis and not _eh_dia_util(data_candidata):
            data_candidata = _proximo_mes(agora_local.date(), dia_mes_alvo)
        else:
            proximo = _proximo_horario_no_dia(data_candidata, horarios, agora_local)
            if proximo:
                return _local_para_utc_naive(proximo, tz)
            data_candidata = _proximo_mes(agora_local.date(), dia_mes_alvo)

    if apenas_dias_uteis:
        while not _eh_dia_util(data_candidata):
            data_candidata += timedelta(days=1)

    primeiro = _ordenar_horarios(horarios)[0]
    resultado = datetime.combine(data_candidata, time(primeiro["hora"], primeiro["minuto"]))
    return _local_para_utc_naive(resultado, tz)


def _proximo_mes(data_atual: date, dia_alvo: int) -> date:
    """
    Retorna a data no próximo mês com o dia desejado.
    Faz fallback para 30, 29 ou 28 se o dia não existe no mês destino
    (ex: dia_alvo=31 em abril → retorna 30/04).
    """
    ano = data_atual.year
    mes = data_atual.month + 1
    if mes > 12:
        ano += 1
        mes = 1
    try:
        return date(ano, mes, dia_alvo)
    except ValueError:
        for dia in [30, 29, 28]:
            try:
                return date(ano, mes, dia)
            except ValueError:
                continue
        return date(ano, mes, 28)


def calcular_proximo_envio_intervalo(
    agendamento: dict,
    a_partir_de: datetime | None = None,
) -> datetime:
    """Próximo envio = agora + intervalo_minutos. Retorna UTC naive."""
    agora_utc = _agora_utc(a_partir_de)
    intervalo = agendamento["intervalo_minutos"]
    return (agora_utc + timedelta(minutes=intervalo)).replace(tzinfo=None)


def calcular_proximo_envio(
    agendamento: dict,
    a_partir_de: datetime | None = None,
    timezone_str: str | None = None,
) -> datetime:
    """
    Calcula próximo envio em UTC naive.

    Horários no agendamento são em hora LOCAL do timezone configurado.
    Se agendamento contém chave 'timezone', usa ela; senão usa timezone_str; senão 'UTC'.

    Returns:
        datetime UTC naive para armazenar em proximo_envio.
    """
    tz_str = agendamento.get("timezone") or timezone_str or "UTC"
    frequencia = agendamento["frequencia"]

    if frequencia == "diaria":
        return calcular_proximo_envio_diaria(agendamento, a_partir_de, tz_str)
    elif frequencia == "semanal":
        return calcular_proximo_envio_semanal(agendamento, a_partir_de, tz_str)
    elif frequencia == "mensal":
        return calcular_proximo_envio_mensal(agendamento, a_partir_de, tz_str)
    elif frequencia == "intervalo":
        return calcular_proximo_envio_intervalo(agendamento, a_partir_de)
    else:
        raise ValueError(f"Frequência não suportada: {frequencia}")
