"""
Rotas de solicitação de relatórios.
"""

import logging

from fastapi import APIRouter, HTTPException, Path, Query
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field

from app.core.orquestrador_relatorios import orquestrar_relatorio
from app.core.renderizador import gerar_pdf, renderizar_html
from app.relatorios.dashboard_conexoes.processador import ProcessadorDashboardConexoes
from app.relatorios.desempenho_vendas.processador import ProcessadorDesempenhoVendas
from app.relatorios.itens_comprimento_por_carga.processador import ProcessadorItensComprimentoPorCarga
from app.relatorios.pedidos_por_vendedor.processador import ProcessadorPedidosPorVendedor
from app.relatorios.teste_conexoes.processador import ProcessadorTesteConexoes

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/relatorios", tags=["relatorios"])


class RequisicaoRelatorio(BaseModel):
    """Body opcional para solicitar relatório."""

    parametros: dict = Field(default_factory=dict)


PROCESSADORES = {
    "dashboard_conexoes": {
        "classe": ProcessadorDashboardConexoes,
        "titulo": "Dashboard de Conexões",
        "subtitulo": "Visão consolidada com gráficos e estatísticas",
    },
    "teste_conexoes": {
        "classe": ProcessadorTesteConexoes,
        "titulo": "Teste de Conexões",
        "subtitulo": "Catálogo de conexões cadastradas no Nexus",
    },
    "desempenho_vendas": {
        "classe": ProcessadorDesempenhoVendas,
        "titulo": "Desempenho de Vendas",
        "subtitulo": "Dashboard de vendas por vendedor com metas e gráficos",
    },
    "pedidos_por_vendedor": {
        "classe": ProcessadorPedidosPorVendedor,
        "titulo": "Pedidos por Vendedor",
        "subtitulo": "Ranking de vendedores com ticket médio e top 5 produtos",
    },
    "itens_comprimento_por_carga": {
        "classe": ProcessadorItensComprimentoPorCarga,
        "titulo": "Itens com Comprimento Excedente por Carga",
        "subtitulo": "Consolidado por carga com pedido, item, cliente, vendedor e metragem",
    },
}


@router.post("/{nome_relatorio}/solicitar")
def solicitar_relatorio(
    nome_relatorio: str = Path(description="Nome técnico do relatório (ex: 'pedidos_por_vendedor', 'dashboard_conexoes')"),
    requisicao: RequisicaoRelatorio | None = None,
    formato: str = Query("json", description="Formato de saída: 'json' (dados), 'html' (página) ou 'pdf' (documento binário)"),
    notificar: bool = Query(False, description="Se True, cria despachos para destinatários configurados"),
    usuario_id: int | None = Query(None, description="ID do usuário solicitante (para despacho on-demand)"),
    agendamento_id: int | None = Query(None, description="ID do agendamento que originou esta solicitação"),
):
    """
    Solicita a geração de um relatório.

    Formatos disponíveis:
    - **json**: dados estruturados (padrão) — `{"status": "sucesso", "payload": {...}}`
    - **html**: visualização para email/web — retorna HTML renderizado
    - **pdf**: documento para download — retorna PDF binário com Content-Disposition: attachment

    Com `notificar=true`, cria despachos no banco para os destinatários configurados
    (relatorios_destinatarios + agendamentos_destinatarios + usuario_id avulso).
    Os despachos são processados pelo workflow `nexus_despachos_sender` no N8N.
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

    # 5. Criar despachos se solicitado
    despachos_info = None
    if notificar:
        try:
            despachos_info = orquestrar_relatorio(
                nome_relatorio=nome_relatorio,
                processador_classe=info_relatorio["classe"],
                titulo=info_relatorio["titulo"],
                subtitulo=info_relatorio.get("subtitulo"),
                parametros=parametros,
                agendamento_id=agendamento_id,
                usuario_solicitante_id=usuario_id,
                comprimir_pdf=True,
            )
        except Exception as e:
            logger.error(f"Erro ao criar despachos para '{nome_relatorio}': {e}", exc_info=True)

    # 6. Retornar conforme formato
    if formato == "json":
        resp: dict = {
            "status": "sucesso",
            "relatorio": nome_relatorio,
            "payload": dados,
        }
        if despachos_info:
            resp["despachos"] = despachos_info
        return resp

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
    """Lista relatórios disponíveis com ID do banco (necessário para permissões e agendamentos)."""
    from sqlalchemy import text

    from app.bd import engine

    with engine.connect() as conexao:
        resultado = (
            conexao.execute(
                text("""
                    SELECT id, nome, titulo, descricao, categoria, status
                    FROM relatorios
                    WHERE status = 'ativo'
                    ORDER BY nome
                """)
            )
            .mappings()
            .all()
        )

    return {
        "total": len(resultado),
        "relatorios": [dict(r) for r in resultado],
    }