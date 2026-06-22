"""
Renderizador de mensagens de alertas.
Renderiza templates Jinja2 (.txt e .html) por canal.

Convenção dos arquivos:
  whatsapp_consolidado.txt        → corpo WhatsApp agrupado
  whatsapp_individual.txt         → corpo WhatsApp por linha
  email_consolidado_assunto.txt   → assunto email agrupado
  email_consolidado_html.html     → corpo HTML email agrupado
  email_individual_assunto.txt    → assunto email por linha
  email_individual_html.html      → corpo HTML email por linha
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Literal

from jinja2 import Environment, FileSystemLoader, TemplateNotFound, select_autoescape

logger = logging.getLogger(__name__)

PASTA_ALERTAS = Path(__file__).resolve().parent.parent / "alertas"


# Tipos de mensagem que o sistema pode renderizar
ARQUIVOS_POR_TIPO = {
    "whatsapp_consolidado": ("whatsapp_consolidado.txt", False),
    "whatsapp_individual": ("whatsapp_individual.txt", False),
    "email_consolidado_assunto": ("email_consolidado_assunto.txt", False),
    "email_consolidado_html": ("email_consolidado_html.html", True),
    "email_individual_assunto": ("email_individual_assunto.txt", False),
    "email_individual_html": ("email_individual_html.html", True),
}


def _criar_ambiente_jinja(pasta_mensagens: Path, autoescape: bool) -> Environment:
    """Cria ambiente Jinja2 para a pasta de mensagens do alerta."""
    return Environment(
        loader=FileSystemLoader(str(pasta_mensagens)),
        autoescape=select_autoescape(["html"]) if autoescape else False,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _renderizar_arquivo(
    pasta_mensagens: Path,
    nome_arquivo: str,
    autoescape: bool,
    contexto: dict,
) -> str | None:
    """
    Renderiza um arquivo específico.
    Retorna None se o arquivo não existir.
    """
    arquivo = pasta_mensagens / nome_arquivo

    if not arquivo.exists():
        return None

    ambiente = _criar_ambiente_jinja(pasta_mensagens, autoescape)

    try:
        template = ambiente.get_template(nome_arquivo)
        return template.render(**contexto).strip()
    except TemplateNotFound:
        return None


def renderizar_mensagens_consolidadas(
    nome_alerta: str,
    contexto: dict,
) -> dict[str, str]:
    """
    Renderiza todas as mensagens consolidadas disponíveis para um alerta.

    Args:
        nome_alerta: Nome técnico do alerta (pasta em app/alertas/)
        contexto: Dict com dados para o template (total, dados, titulo, etc)

    Returns:
        Dict com as mensagens renderizadas. Chaves possíveis:
        - whatsapp
        - email_assunto
        - email_html

        Se um template não existir, a chave correspondente não aparece.
    """
    pasta_mensagens = PASTA_ALERTAS / nome_alerta / "mensagens"

    if not pasta_mensagens.exists():
        logger.warning(f"Pasta de mensagens não existe: {pasta_mensagens}")
        return {}

    # Adiciona variáveis "sempre disponíveis"
    contexto_completo = {
        **contexto,
        "data_geracao": datetime.now().strftime("%d/%m/%Y às %H:%M"),
    }

    resultado = {}

    # WhatsApp consolidado
    whatsapp = _renderizar_arquivo(
        pasta_mensagens, "whatsapp_consolidado.txt", False, contexto_completo
    )
    if whatsapp:
        resultado["whatsapp"] = whatsapp

    # Email consolidado: assunto
    assunto = _renderizar_arquivo(
        pasta_mensagens, "email_consolidado_assunto.txt", False, contexto_completo
    )
    if assunto:
        resultado["email_assunto"] = assunto

    # Email consolidado: HTML
    html = _renderizar_arquivo(
        pasta_mensagens, "email_consolidado_html.html", True, contexto_completo
    )
    if html:
        resultado["email_html"] = html

    return resultado


def renderizar_mensagens_individuais(
    nome_alerta: str,
    contexto_base: dict,
    linha: dict,
) -> dict[str, str]:
    """
    Renderiza mensagens individuais (1 por linha do resultado SQL).

    Args:
        nome_alerta: Nome técnico do alerta
        contexto_base: Dados gerais (titulo, severidade, etc)
        linha: Dados de UMA linha específica do resultado SQL

    Returns:
        Dict com mensagens renderizadas (whatsapp, email_assunto, email_html).
    """
    pasta_mensagens = PASTA_ALERTAS / nome_alerta / "mensagens"

    if not pasta_mensagens.exists():
        return {}

    # Contexto: dados base + dados da linha específica + data
    contexto_completo = {
        **contexto_base,
        **linha,
        "data_geracao": datetime.now().strftime("%d/%m/%Y às %H:%M"),
    }

    resultado = {}

    whatsapp = _renderizar_arquivo(
        pasta_mensagens, "whatsapp_individual.txt", False, contexto_completo
    )
    if whatsapp:
        resultado["whatsapp"] = whatsapp

    assunto = _renderizar_arquivo(
        pasta_mensagens, "email_individual_assunto.txt", False, contexto_completo
    )
    if assunto:
        resultado["email_assunto"] = assunto

    html = _renderizar_arquivo(
        pasta_mensagens, "email_individual_html.html", True, contexto_completo
    )
    if html:
        resultado["email_html"] = html

    return resultado


def detectar_capacidades_alerta(nome_alerta: str) -> dict[str, bool]:
    """
    Detecta o que o alerta SABE fazer baseado nos templates que existem.

    Returns:
        {
            "tem_consolidado": True/False,
            "tem_individual": True/False,
            "canais_consolidado": ["whatsapp", "email"],
            "canais_individual": [...]
        }
    """
    pasta_mensagens = PASTA_ALERTAS / nome_alerta / "mensagens"

    if not pasta_mensagens.exists():
        return {
            "tem_consolidado": False,
            "tem_individual": False,
            "canais_consolidado": [],
            "canais_individual": [],
        }

    canais_consolidado = []
    if (pasta_mensagens / "whatsapp_consolidado.txt").exists():
        canais_consolidado.append("whatsapp")
    if (pasta_mensagens / "email_consolidado_html.html").exists():
        canais_consolidado.append("email")

    canais_individual = []
    if (pasta_mensagens / "whatsapp_individual.txt").exists():
        canais_individual.append("whatsapp")
    if (pasta_mensagens / "email_individual_html.html").exists():
        canais_individual.append("email")

    return {
        "tem_consolidado": len(canais_consolidado) > 0,
        "tem_individual": len(canais_individual) > 0,
        "canais_consolidado": canais_consolidado,
        "canais_individual": canais_individual,
    }
