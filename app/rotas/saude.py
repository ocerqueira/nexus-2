"""
Rotas de health check e operações administrativas.
"""

from fastapi import APIRouter
from sqlalchemy import text

from app.bd import engine
from app.core.sincronizador import sincronizar_filesystem_com_banco
from config import configuracoes

router = APIRouter(tags=["sistema"])


@router.get("/saude")
def verificar_saude() -> dict:
    """Health check do sistema."""
    banco_ok = False
    erro_banco = None

    try:
        with engine.connect() as conexao:
            resultado = conexao.execute(text("SELECT 1")).scalar()
            banco_ok = resultado == 1
    except Exception as erro:
        erro_banco = str(erro)

    resposta: dict = {
        "status": "ok" if banco_ok else "degradado",
        "servico": "nexus",
        "versao": configuracoes.api_versao,
        "ambiente": configuracoes.ambiente,
        "componentes": {
            "api": "ok",
            "banco_dados": "ok" if banco_ok else "erro",
        },
    }

    if erro_banco:
        resposta["componentes"]["erro_banco"] = erro_banco

    return resposta


@router.post("/sincronizar")
def sincronizar() -> dict:
    """
    Força sincronização do filesystem com o banco.
    Útil para refletir novos relatórios/alertas sem reiniciar.
    """
    resultado = sincronizar_filesystem_com_banco()
    return {
        "status": "ok",
        "mensagem": "Sincronização concluída",
        "detalhes": resultado,
    }
