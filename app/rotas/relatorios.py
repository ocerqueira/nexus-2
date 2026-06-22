"""
Rotas de solicitação de relatórios.
"""

import logging

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field

from app.core.renderizador import gerar_pdf, renderizar_html
from app.relatorios.teste_conexoes.processador import ProcessadorTesteConexoes

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/relatorios", tags=["relatorios"])


class RequisicaoRelatorio(BaseModel):
    """Body opcional para solicitar relatório."""

    parametros: dict = Field(default_factory=dict)


PROCESSADORES = {
    "teste_conexoes": {
        "classe": ProcessadorTesteConexoes,
        "titulo": "Teste de Conexões",
        "subtitulo": "Catálogo de conexões cadastradas no Nexus",
    },
}


@router.post("/{nome_relatorio}/solicitar")
def solicitar_relatorio(
    nome_relatorio: str,
    requisicao: RequisicaoRelatorio | None = None,
    formato: str = Query("json", description="Formato: json, html ou pdf"),
):
    """
    Solicita a geração de um relatório.

    Formatos disponíveis:
    - json: dados estruturados (padrão)
    - html: visualização para email/web
    - pdf: documento para download
    """
    # 1. Validar formato
    formatos_validos = ["json", "html", "pdf"]
    if formato not in formatos_validos:
        raise HTTPException(
            status_code=400,
            detail=f"Formato inválido. Use: {formatos_validos}",
        )

    # 2. Validar relatório
    if nome_relatorio not in PROCESSADORES:
        raise HTTPException(
            status_code=404,
            detail=f"Relatório '{nome_relatorio}' não encontrado",
        )

    # Extrair parâmetros (com fallback se body for vazio)
    parametros = requisicao.parametros if requisicao else {}
    info_relatorio = PROCESSADORES[nome_relatorio]

    logger.info(
        f"Solicitação: relatorio={nome_relatorio} formato={formato} params={parametros}"
    )

    # 3. Validar parâmetros
    processador = info_relatorio["classe"]()
    valido, erro = processador.validar(parametros)
    if not valido:
        raise HTTPException(status_code=400, detail=erro)

    # 4. Buscar dados
    try:
        dados = processador.buscar_dados(parametros)
    except Exception as erro:
        logger.error(f"Erro ao processar: {erro}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro: {erro!s}")

    # 5. Retornar conforme formato
    if formato == "json":
        return {
            "status": "sucesso",
            "relatorio": nome_relatorio,
            "payload": dados,
        }

    elif formato == "html":
        html = renderizar_html(
            nome_relatorio=nome_relatorio,
            dados=dados,
            titulo=info_relatorio["titulo"],
            subtitulo=info_relatorio["subtitulo"],
        )
        return HTMLResponse(content=html)

    elif formato == "pdf":
        pdf = gerar_pdf(
            nome_relatorio=nome_relatorio,
            dados=dados,
            titulo=info_relatorio["titulo"],
            subtitulo=info_relatorio["subtitulo"],
        )
        return Response(
            content=pdf,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={nome_relatorio}.pdf"
            },
        )


@router.get("")
def listar_relatorios() -> dict:
    """Lista todos os relatórios disponíveis."""
    return {
        "total": len(PROCESSADORES),
        "relatorios": [
            {
                "nome": nome,
                "titulo": info["titulo"],
                "subtitulo": info["subtitulo"],
            }
            for nome, info in PROCESSADORES.items()
        ],
    }
