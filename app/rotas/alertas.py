"""
Rotas de verificação de alertas.
"""

import logging
from pathlib import Path as FilePath

from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel, Field

from app.core.orquestrador_alertas import AlertaNaoEncontrado, orquestrar_alerta
from app.core.processadores import carregar_processador
from app.core.resolvedor_parametros import resolver_tokens

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/alertas", tags=["alertas"])

_PASTA_ALERTAS = FilePath(__file__).parent.parent / "alertas"


class RequisicaoAlerta(BaseModel):
    """Body opcional para verificar alerta."""

    parametros: dict = Field(
        default_factory=dict, description="Parâmetros específicos do alerta"
    )


def _carregar_alerta(nome: str) -> type | None:
    """
    Carrega dinamicamente a classe processador de um alerta pelo nome da pasta.
    Retorna a classe ou None se não encontrado.
    Novo alerta = nova pasta em app/alertas/ — sem mexer neste arquivo.
    """
    config_path = _PASTA_ALERTAS / nome / "config.json"
    if not config_path.exists():
        return None
    return carregar_processador("alerta", nome)


@router.post("/{nome_alerta}/verificar")
def verificar_alerta(
    nome_alerta: str = Path(description="Nome técnico do alerta (ex: 'conexoes_inativas', 'item_comprimento_excedente')"),
    requisicao: RequisicaoAlerta | None = None,
    forcar: bool = Query(False, description="Se True, ignora cooldown e deduplicação por fingerprint"),
    notificar: bool = Query(True, description="Se False, executa verificação mas não cria entregas nem atualiza cooldowns (uso: chatbot)"),
) -> dict:
    """
    Verifica um alerta e retorna payload completo para notificação.

    O payload inclui destinatários resolvidos, mensagens renderizadas
    (consolidadas e individuais) e metadados para o N8N decidir se deve notificar.
    Quando `forcar=true`, ignora cooldown e deduplicação — útil para testes manuais.
    Quando `notificar=false`, retorna resultado sem criar entregas (uso: chatbot interativo).
    """
    # 1. Carregar processador dinamicamente
    processador_classe = _carregar_alerta(nome_alerta)
    if not processador_classe:
        raise HTTPException(
            status_code=404,
            detail=f"Alerta '{nome_alerta}' não encontrado",
        )

    # Extrair parâmetros e resolver tokens dinâmicos ({{mes_anterior_inicio}}, etc.)
    parametros = resolver_tokens(requisicao.parametros if requisicao else {})
    logger.info(
        f"Verificando alerta '{nome_alerta}' (forçar={forcar}, notificar={notificar}) params={parametros}"
    )

    # 2. Delegar para o orquestrador
    try:
        return orquestrar_alerta(
            nome_alerta=nome_alerta,
            parametros=parametros,
            processador_classe=processador_classe,
            forcar=forcar,
            notificar=notificar,
        )
    except AlertaNaoEncontrado as erro:
        raise HTTPException(status_code=404, detail=str(erro))
    except Exception as erro:
        logger.error(f"Erro ao orquestrar alerta: {erro}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro: {erro!s}")


@router.get("")
def listar_alertas() -> dict:
    """Lista todos os alertas disponíveis."""
    from sqlalchemy import text

    from app.bd import engine

    with engine.connect() as conexao:
        resultado = (
            conexao.execute(
                text("""
                SELECT id, nome, titulo, descricao, severidade, status
                FROM alertas
                WHERE status = 'ativo'
                ORDER BY nome
            """)
            )
            .mappings()
            .all()
        )

    return {
        "total": len(resultado),
        "alertas": [dict(linha) for linha in resultado],
    }