"""
Renderizador de mensagens de alertas.
Renderiza templates Jinja2 por canal e modo.

Conceito atual: alertas WhatsApp são sempre enviados em modo 'individual'
(1 despacho por item detectado). O modo 'agrupado' existe no código mas
não é o fluxo ativo — cada ocorrência gera sua própria mensagem.

Convenção de arquivos em alertas/{nome}/mensagens/:
  whatsapp_individual.txt         → WhatsApp, 1 despacho por item  ← fluxo ativo
  email_individual_assunto.txt    → Email individual: linha de assunto
  email_individual_html.html      → Email individual: corpo HTML
  email_consolidado_assunto.txt   → Email agrupado: linha de assunto
  email_consolidado_html.html     → Email agrupado: corpo HTML
  sms_individual.txt              → SMS individual (futuro)

API canônica: renderizar_despacho(nome_alerta, canal, modo, contexto)
Retorna dict com payload pronto para inserir em despachos.payload.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Literal

from jinja2 import Environment, FileSystemLoader, TemplateNotFound, select_autoescape

logger = logging.getLogger(__name__)

PASTA_ALERTAS = Path(__file__).resolve().parent.parent / "alertas"

# Mapeamento (canal, modo) → arquivos de template
# Valor: lista de (nome_arquivo, é_html, chave_no_payload)
_TEMPLATES: dict[tuple[str, str], list[tuple[str, bool, str]]] = {
    ("whatsapp", "individual"): [
        ("whatsapp_individual.txt", False, "mensagem"),
    ],
    ("whatsapp", "agrupado"): [
        # Não é o fluxo ativo — WhatsApp usa sempre modo 'individual'
        ("whatsapp_consolidado.txt", False, "mensagem"),
    ],
    ("email", "individual"): [
        ("email_individual_assunto.txt", False, "assunto"),
        ("email_individual_html.html",   True,  "html"),
    ],
    ("email", "agrupado"): [
        ("email_consolidado_assunto.txt", False, "assunto"),
        ("email_consolidado_html.html",   True,  "html"),
    ],
    ("sms", "individual"): [
        ("sms_individual.txt", False, "texto"),
    ],
    ("sms", "agrupado"): [
        ("sms_individual.txt", False, "texto"),
    ],
}


def _criar_ambiente_jinja(pasta: Path, autoescape: bool) -> Environment:
    return Environment(
        loader=FileSystemLoader(str(pasta)),
        autoescape=select_autoescape(["html"]) if autoescape else False,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _renderizar_arquivo(pasta: Path, nome: str, autoescape: bool, contexto: dict) -> str | None:
    if not (pasta / nome).exists():
        return None
    try:
        env = _criar_ambiente_jinja(pasta, autoescape)
        return env.get_template(nome).render(**contexto).strip()
    except TemplateNotFound:
        return None


def _contexto_base(contexto: dict) -> dict:
    return {**contexto, "data_geracao": datetime.now().strftime("%d/%m/%Y às %H:%M")}


# ─────────────────────────────────────────────────────────────────────────────
# API CANÔNICA
# ─────────────────────────────────────────────────────────────────────────────

def renderizar_despacho(
    nome_alerta: str,
    canal: str,
    modo: str,
    contexto: dict,
    linha: dict | None = None,
) -> dict | None:
    """
    Renderiza payload para um despacho específico.

    Args:
        nome_alerta: Nome técnico do alerta (pasta em app/alertas/)
        canal:       'whatsapp' | 'email' | 'sms'
        modo:        'individual' (por item) | 'agrupado' (todos os itens)
        contexto:    Dados gerais do alerta (titulo, severidade, dados, resumo, etc.)
        linha:       Dados de UM item específico (apenas para modo='individual')

    Returns:
        Dict com payload renderizado pronto para despachos.payload:
          whatsapp → {"mensagem": "..."}
          email    → {"assunto": "...", "html": "..."}
          sms      → {"texto": "..."}
        None se nenhum template existe para este canal+modo.
    """
    pasta = PASTA_ALERTAS / nome_alerta / "mensagens"
    if not pasta.exists():
        logger.warning(f"Pasta mensagens inexistente: {pasta}")
        return None

    specs = _TEMPLATES.get((canal, modo))
    if not specs:
        logger.warning(f"Canal+modo não suportado: ({canal}, {modo})")
        return None

    ctx = _contexto_base({**contexto, **(linha or {})})
    payload: dict[str, str] = {}

    for nome_arquivo, autoescape, chave in specs:
        conteudo = _renderizar_arquivo(pasta, nome_arquivo, autoescape, ctx)
        if conteudo:
            payload[chave] = conteudo

    return payload if payload else None


def canais_disponiveis(nome_alerta: str) -> dict[str, list[str]]:
    """
    Detecta quais combinações (canal, modo) têm template disponível.

    Returns:
        {"individual": ["whatsapp", "email"], "agrupado": ["whatsapp"]}
    """
    pasta = PASTA_ALERTAS / nome_alerta / "mensagens"
    resultado: dict[str, list[str]] = {"individual": [], "agrupado": []}

    if not pasta.exists():
        return resultado

    for (canal, modo), specs in _TEMPLATES.items():
        if any((pasta / nome).exists() for nome, _, _ in specs):
            resultado.setdefault(modo, []).append(canal)

    return resultado


# ─────────────────────────────────────────────────────────────────────────────
# COMPAT: funções antigas mantidas para não quebrar código existente
# ─────────────────────────────────────────────────────────────────────────────

def renderizar_mensagens_individuais(
    nome_alerta: str,
    contexto_base: dict,
    linha: dict,
) -> dict[str, str]:
    """Legado. Use renderizar_despacho(canal='whatsapp'|'email', modo='individual')."""
    resultado = {}
    for canal, chave_wp, chave_as, chave_html in [
        ("whatsapp", "whatsapp", None, None),
        ("email",    None, "email_assunto", "email_html"),
    ]:
        payload = renderizar_despacho(nome_alerta, canal, "individual", contexto_base, linha)
        if payload:
            if canal == "whatsapp":
                resultado["whatsapp"] = payload.get("mensagem", "")
            elif canal == "email":
                if "assunto" in payload:
                    resultado["email_assunto"] = payload["assunto"]
                if "html" in payload:
                    resultado["email_html"] = payload["html"]
    return resultado


def renderizar_mensagens_consolidadas(
    nome_alerta: str,
    contexto: dict,
) -> dict[str, str]:
    """Legado — modo consolidado não é mais utilizado para WhatsApp. Use renderizar_despacho(modo='individual')."""
    resultado = {}
    for canal in ("whatsapp", "email"):
        payload = renderizar_despacho(nome_alerta, canal, "agrupado", contexto)
        if payload:
            if canal == "whatsapp":
                resultado["whatsapp"] = payload.get("mensagem", "")
            elif canal == "email":
                if "assunto" in payload:
                    resultado["email_assunto"] = payload["assunto"]
                if "html" in payload:
                    resultado["email_html"] = payload["html"]
    return resultado


def detectar_capacidades_alerta(nome_alerta: str) -> dict:
    """Legado. Use canais_disponiveis()."""
    caps = canais_disponiveis(nome_alerta)
    return {
        "tem_consolidado":    bool(caps.get("agrupado")),
        "tem_individual":     bool(caps.get("individual")),
        "canais_consolidado": caps.get("agrupado", []),
        "canais_individual":  caps.get("individual", []),
    }
