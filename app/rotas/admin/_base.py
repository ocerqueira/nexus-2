"""Shared imports, constants and helpers for the admin sub-package."""

import importlib
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import Form, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text

from app.bd import engine
from app.core.calculadora_agenda import calcular_proximo_envio
from app.core.criptografia import criptografar
from app.core.gerenciador_conexoes import gerenciador_conexoes
from app.core.orquestrador_alertas import orquestrar_alerta
from app.core.sincronizador import sincronizar_filesystem_com_banco
from app.core.sincronizador_ad import sincronizar_ad

_APP = Path(__file__).parent.parent.parent  # app/
_PASTA_RELATORIOS = _APP / "relatorios"
_PASTA_ALERTAS = _APP / "alertas"

logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory=str(_APP / "templates"))

_POR_PAGINA = 20
_HIST_POR_PAGINA = 25
_PERM_USUARIOS_POR_PAGINA = 10
_AG_USUARIOS_POR_PAGINA = 10
_ENTREGAS_POR_PAGINA = 30

_TZ_SP = ZoneInfo("America/Sao_Paulo")
_TZ_UTC = ZoneInfo("UTC")


def _badge(texto: str, cor: str) -> str:
    paleta = {
        "green":  "bg-green-100 text-green-700",
        "gray":   "bg-slate-100 text-slate-500",
        "orange": "bg-orange-100 text-orange-700",
        "blue":   "bg-blue-100 text-blue-700",
        "red":    "bg-red-100 text-red-600",
    }
    cls = paleta.get(cor, paleta["gray"])
    return f'<span class="inline-flex px-2 py-0.5 rounded-full text-xs font-medium {cls}">{texto}</span>'


def _usuarios_lista() -> list[dict]:
    with engine.connect() as c:
        rows = c.execute(text(
            "SELECT id, nome, identificador FROM usuarios WHERE ativo=TRUE ORDER BY nome"
        )).mappings().all()
    return [dict(r) for r in rows]


def _recursos_lista(tipo: str) -> list[dict]:
    with engine.connect() as c:
        if tipo == "relatorio":
            rows = c.execute(text(
                "SELECT id, titulo FROM relatorios WHERE status='ativo' ORDER BY titulo"
            )).mappings().all()
        else:
            rows = c.execute(text(
                "SELECT id, titulo FROM alertas WHERE status='ativo' ORDER BY titulo"
            )).mappings().all()
    return [dict(r) for r in rows]


def _parse_horarios(horarios_str: str) -> list[dict]:
    """
    Converte string de horários do formulário HTML para lista de dicts.
    Formato esperado: "08:00,12:30,18:00"
    Retorna: [{"hora": 8, "minuto": 0}, {"hora": 12, "minuto": 30}, ...]
    """
    result = []
    for h in horarios_str.split(","):
        h = h.strip()
        if ":" in h:
            partes = h.split(":", 1)
            try:
                result.append({"hora": int(partes[0]), "minuto": int(partes[1])})
            except ValueError:
                pass
    return result


def _formatar_datetime(dt) -> str:
    """Converte datetime (UTC ou naive=UTC) para string local de São Paulo."""
    if not dt:
        return "—"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_TZ_UTC)
    return dt.astimezone(_TZ_SP).strftime("%d/%m/%y %H:%M")


def _formatar_data(dt) -> str:
    if not dt:
        return "—"
    return dt.strftime("%d/%m/%Y")


def _carregar_processador_relatorio(nome: str) -> dict | None:
    """
    Carrega dinamicamente a classe Processador* de app/relatorios/{nome}/processador.py.
    Usa importlib para descobrir a classe sem precisar importar cada módulo no startup.
    Retorna None se o config.json não existir ou o módulo não puder ser importado.
    """
    if not (_PASTA_RELATORIOS / nome / "config.json").exists():
        return None
    try:
        mod = importlib.import_module(f"app.relatorios.{nome}.processador")
    except ImportError:
        return None
    for attr_name in dir(mod):
        attr = getattr(mod, attr_name)
        if isinstance(attr, type) and attr_name.startswith("Processador") and attr_name != "Processador":
            return {"classe": attr}
    return None


def _carregar_processador_alerta(nome: str):
    """
    Carrega dinamicamente a classe Processador* de app/alertas/{nome}/processador.py.
    Mesma estratégia de _carregar_processador_relatorio, mas para alertas.
    """
    try:
        mod = importlib.import_module(f"app.alertas.{nome}.processador")
    except ImportError:
        return None
    for attr_name in dir(mod):
        attr = getattr(mod, attr_name)
        if isinstance(attr, type) and attr_name.startswith("Processador") and attr_name != "Processador":
            return attr
    return None
