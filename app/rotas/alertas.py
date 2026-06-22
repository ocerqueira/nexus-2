"""
Rotas de verificação de alertas.
"""

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.alertas.conexoes_inativas.processador import ProcessadorConexoesInativas
from app.core.orquestrador_alertas import AlertaNaoEncontrado, orquestrar_alerta

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/alertas", tags=["alertas"])


# Schema do body da requisição
class RequisicaoAlerta(BaseModel):
    """Body opcional para verificar alerta."""

    parametros: dict = Field(
        default_factory=dict, description="Parâmetros específicos do alerta"
    )


# Mapeamento nome → classe do processador
PROCESSADORES = {
    "conexoes_inativas": ProcessadorConexoesInativas,
}


@router.post("/{nome_alerta}/verificar")
def verificar_alerta(
    nome_alerta: str,
    requisicao: RequisicaoAlerta | None = None,
    forcar: bool = Query(False, description="Ignora cooldown se True"),
) -> dict:
    """
    Verifica um alerta e retorna payload completo para notificação.
    """
    # 1. Validar que o processador existe
    if nome_alerta not in PROCESSADORES:
        raise HTTPException(
            status_code=404,
            detail=f"Alerta '{nome_alerta}' não tem processador registrado",
        )

    # Extrair parâmetros (com fallback)
    parametros = requisicao.parametros if requisicao else {}
    logger.info(
        f"Verificando alerta '{nome_alerta}' (forçar={forcar}) params={parametros}"
    )

    # 2. Delegar para o orquestrador
    try:
        return orquestrar_alerta(
            nome_alerta=nome_alerta,
            parametros=parametros,
            processador_classe=PROCESSADORES[nome_alerta],
            forcar=forcar,
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
