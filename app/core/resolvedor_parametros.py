"""
Resolução de tokens dinâmicos em dicionários de parâmetros.

Tokens suportados (formato {{token}}):

  Datas → string AAAA-MM-DD
    {{hoje}}                  data de hoje
    {{ontem}}                 ontem
    {{mes_atual_inicio}}      primeiro dia do mês atual
    {{mes_atual_fim}}         último dia do mês atual
    {{mes_anterior_inicio}}   primeiro dia do mês anterior
    {{mes_anterior_fim}}      último dia do mês anterior
    {{semana_atual_inicio}}   segunda-feira da semana atual
    {{semana_atual_fim}}      domingo da semana atual

  Inteiros → string numérica
    {{ano_atual}}             ex: "2025"
    {{mes_atual}}             ex: "6"
    {{ano_anterior}}          ex: "2024"

Tokens desconhecidos são mantidos sem alteração.
"""

import re
from calendar import monthrange
from datetime import date, timedelta

_TOKEN = re.compile(r'\{\{(\w+)\}\}')


def _mapa_tokens() -> dict[str, str]:
    hoje = date.today()

    mes_ant = date(hoje.year - 1, 12, 1) if hoje.month == 1 else date(hoje.year, hoje.month - 1, 1)

    return {
        "hoje":                str(hoje),
        "ontem":               str(hoje - timedelta(days=1)),
        "mes_atual_inicio":    str(hoje.replace(day=1)),
        "mes_atual_fim":       str(hoje.replace(day=monthrange(hoje.year, hoje.month)[1])),
        "mes_anterior_inicio": str(mes_ant),
        "mes_anterior_fim":    str(mes_ant.replace(day=monthrange(mes_ant.year, mes_ant.month)[1])),
        "semana_atual_inicio": str(hoje - timedelta(days=hoje.weekday())),
        "semana_atual_fim":    str(hoje - timedelta(days=hoje.weekday()) + timedelta(days=6)),
        "ano_atual":           str(hoje.year),
        "mes_atual":           str(hoje.month),
        "ano_anterior":        str(hoje.year - 1),
    }


def resolver_tokens(parametros: dict) -> dict:
    """
    Substitui tokens {{...}} nos valores string de um dict de parâmetros.
    Valores não-string e tokens desconhecidos passam sem alteração.
    Dict original não é modificado.
    """
    if not parametros:
        return parametros
    mapa = _mapa_tokens()
    return {
        # m.group(1) = nome do token (ex: "hoje"); m.group(0) = token completo (ex: "{{hoje}}")
        # se o token não existe no mapa, mantém o original sem alteração
        k: _TOKEN.sub(lambda m: mapa.get(m.group(1), m.group(0)), v) if isinstance(v, str) else v
        for k, v in parametros.items()
    }
