"""
Rotas de solicitação de relatórios.
"""

import base64
import importlib
import json
import logging
from pathlib import Path as FilePath

from fastapi import APIRouter, HTTPException, Path, Query
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field

from app.core.orquestrador_relatorios import orquestrar_relatorio
from app.core.renderizador import gerar_pdf, renderizar_html
from app.core.resolvedor_parametros import resolver_tokens

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/relatorios", tags=["relatorios"])

_PASTA_RELATORIOS = FilePath(__file__).parent.parent / "relatorios"


class RequisicaoRelatorio(BaseModel):
    """Body opcional para solicitar relatório."""

    parametros: dict = Field(default_factory=dict)


def _carregar_relatorio(nome: str) -> dict | None:
    """
    Carrega dinamicamente o processador e config de um relatório pelo nome da pasta.
    Retorna {classe, titulo, subtitulo} ou None se não encontrado.
    Novo relatório = nova pasta em app/relatorios/ — sem mexer neste arquivo.
    """
    config_path = _PASTA_RELATORIOS / nome / "config.json"
    if not config_path.exists():
        return None

    try:
        mod = importlib.import_module(f"app.relatorios.{nome}.processador")
    except ImportError:
        return None

    cfg = json.loads(config_path.read_text(encoding="utf-8"))

    for attr_name in dir(mod):
        attr = getattr(mod, attr_name)
        if isinstance(attr, type) and attr_name.startswith("Processador") and attr_name != "Processador":
            return {
                "classe":    attr,
                "titulo":    cfg.get("titulo", nome),
                "subtitulo": cfg.get("subtitulo"),
            }

    return None


@router.post("/{nome_relatorio}/solicitar")
def solicitar_relatorio(
    nome_relatorio: str = Path(description="Nome técnico do relatório (ex: 'pedidos_por_vendedor', 'dashboard_conexoes')"),
    requisicao: RequisicaoRelatorio | None = None,
    formato: str = Query("json", description="Formato de saída: 'json' (dados), 'html' (página) ou 'pdf' (documento binário)"),
    notificar: bool = Query(False, description="Se True, cria entregas para destinatários configurados"),
    usuario_id: int | None = Query(None, description="ID do usuário solicitante (para entrega on-demand)"),
    agendamento_id: int | None = Query(None, description="ID do agendamento que originou esta solicitação"),
):
    """
    Solicita a geração de um relatório.

    Formatos disponíveis:
    - **json**: dados estruturados (padrão) — `{"status": "sucesso", "payload": {...}}`
    - **html**: visualização para email/web — retorna HTML renderizado
    - **pdf**: documento para download — retorna PDF binário com Content-Disposition: attachment

    Com `notificar=true`, cria entregas no banco para os destinatários configurados
    (relatorios_destinatarios + agendamentos_destinatarios + usuario_id avulso).
    As entregas são processadas pelo workflow `nexus_entregas_sender` no N8N.
    """
    # 1. Validar formato
    formatos_validos = ["json", "html", "pdf", "base64"]
    if formato not in formatos_validos:
        raise HTTPException(
            status_code=400,
            detail=f"Formato inválido. Use: {formatos_validos}",
        )

    # 2. Carregar relatório dinamicamente
    info_relatorio = _carregar_relatorio(nome_relatorio)
    if not info_relatorio:
        raise HTTPException(
            status_code=404,
            detail=f"Relatório '{nome_relatorio}' não encontrado",
        )

    # Extrair parâmetros e resolver tokens dinâmicos ({{mes_anterior_inicio}}, etc.)
    parametros = resolver_tokens(requisicao.parametros if requisicao else {})

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

    # 5. Criar entregas se solicitado
    entregas_info = None
    if notificar:
        try:
            entregas_info = orquestrar_relatorio(
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
            logger.error(f"Erro ao criar entregas para '{nome_relatorio}': {e}", exc_info=True)

    # 6. Retornar conforme formato
    if formato == "json":
        resp: dict = {
            "status": "sucesso",
            "relatorio": nome_relatorio,
            "payload": dados,
        }
        if entregas_info:
            resp["entregas"] = entregas_info
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

    elif formato == "base64":
        pdf = gerar_pdf(
            nome_relatorio=nome_relatorio,
            dados=dados,
            titulo=info_relatorio["titulo"],
            subtitulo=info_relatorio["subtitulo"],
        )
        resp = {
            "status": "sucesso",
            "relatorio": nome_relatorio,
            "pdf_base64": base64.b64encode(pdf).decode(),
            "filename": f"{nome_relatorio}.pdf",
        }
        if entregas_info:
            resp["entregas"] = entregas_info
        return resp


@router.get("/{nome_relatorio}/config")
def obter_config_relatorio(
    nome_relatorio: str = Path(description="Nome técnico do relatório"),
) -> dict:
    """
    Retorna o schema de parâmetros do relatório lido do config.json.

    Usado pelo chatbot N8N para construir o fluxo de coleta dinamicamente
    e pelo admin para renderizar campos no formulário de agendamento.

    Inclui tokens dinâmicos suportados para referência.
    """
    config_path = _PASTA_RELATORIOS / nome_relatorio / "config.json"
    if not config_path.exists():
        raise HTTPException(status_code=404, detail=f"Relatório '{nome_relatorio}' não encontrado")

    config = json.loads(config_path.read_text(encoding="utf-8"))

    return {
        "nome": nome_relatorio,
        "titulo": config.get("titulo", nome_relatorio),
        "descricao": config.get("descricao"),
        "categoria": config.get("categoria"),
        "modo_execucao": config.get("modo_execucao", "unico"),
        "parametros": config.get("parametros", []),
        "tokens_disponiveis": [
            {"token": "{{hoje}}", "descricao": "Data de hoje (AAAA-MM-DD)"},
            {"token": "{{ontem}}", "descricao": "Ontem (AAAA-MM-DD)"},
            {"token": "{{mes_atual_inicio}}", "descricao": "Primeiro dia do mês atual"},
            {"token": "{{mes_atual_fim}}", "descricao": "Último dia do mês atual"},
            {"token": "{{mes_anterior_inicio}}", "descricao": "Primeiro dia do mês anterior"},
            {"token": "{{mes_anterior_fim}}", "descricao": "Último dia do mês anterior"},
            {"token": "{{semana_atual_inicio}}", "descricao": "Segunda-feira da semana atual"},
            {"token": "{{semana_atual_fim}}", "descricao": "Domingo da semana atual"},
            {"token": "{{ano_atual}}", "descricao": "Ano corrente como número"},
            {"token": "{{mes_atual}}", "descricao": "Mês corrente como número"},
            {"token": "{{ano_anterior}}", "descricao": "Ano anterior como número"},
        ],
    }


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