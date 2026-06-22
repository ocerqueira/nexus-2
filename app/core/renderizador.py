import logging
from datetime import datetime
from multiprocessing import context
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

logger = logging.getLogger(__name__)

# Pasta dos templates compartilhados (base.html, etc)
PASTA_TEMPLATES_BASE = Path(__file__).parent / "templates"

# Pasta dos relatórios (cada relatório tem seu template.html)
PASTA_RELATORIOS = Path(__file__).parent.parent / "relatorios"


def _criar_ambiente_jinja(pasta_relatorio: Path) -> Environment:
    return Environment(
        loader=FileSystemLoader(
            [
                str(pasta_relatorio),
                str(PASTA_TEMPLATES_BASE),
            ]
        ),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def renderizar_html(
    nome_relatorio: str,
    dados: dict,
    titulo: str,
    subtitulo: str | None = None,
) -> str:
    """
    Renderiza o template do relatório em HTML.

    Args:
        nome_relatorio: Nome técnico (pasta em app/relatorios/)
        dados: Dict com dados do processador
        titulo: Título visível no relatório
        subtitulo: Subtítulo opcional

    Returns:
        String HTML completa
    """
    pasta_relatorio = PASTA_RELATORIOS / nome_relatorio
    arquivo_template = pasta_relatorio / "template.html"

    if not arquivo_template.exists():
        raise FileNotFoundError(f"Template não encontrado: {arquivo_template}")

    ambiente = _criar_ambiente_jinja(pasta_relatorio)
    template = ambiente.get_template("template.html")

    contexto = {
        **dados,
        "titulo": titulo,
        "subtitulo": subtitulo,
        "data_geracao": datetime.now().strftime("%d/%m/%Y às %H:%M"),
    }

    html_renderizado = template.render(**contexto)
    logger.info(
        f"HTML renderizado para '{nome_relatorio}' ({len(html_renderizado)} chars)"
    )

    return html_renderizado


def gerar_pdf(
    nome_relatorio: str,
    dados: dict,
    titulo: str,
    subtitulo: str | None = None,
) -> bytes:
    """
    Gera PDF do relatório a partir do template HTML.

    Args:
        Mesmo do renderizar_html

    Returns:
        Bytes do PDF gerado
    """
    html = renderizar_html(nome_relatorio, dados, titulo, subtitulo)

    pdf_bytes = HTML(string=html).write_pdf()
    logger.info(f"PDF gerado para '{nome_relatorio}' ({len(pdf_bytes)} bytes)")

    return pdf_bytes
