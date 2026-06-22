"""
Ponto de entrada do sistema Nexus.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.inicializador import garantir_estrutura_banco
from app.core.sincronizador import sincronizar_filesystem_com_banco
from app.rotas import alertas, relatorios, saude
from config import configuracoes

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def ciclo_vida(app: FastAPI):
    """Gerencia inicialização e finalização da aplicação."""
    logger.info("Iniciando Nexus...")

    try:
        # 1. Garante estrutura do banco
        garantir_estrutura_banco()

        # 2. Sincroniza filesystem com banco
        sincronizar_filesystem_com_banco()
    except Exception as erro:
        logger.error(f"Erro na inicialização: {erro}")
        raise

    logger.info("Nexus pronto para receber requisições.")
    yield
    logger.info("Encerrando Nexus...")


app = FastAPI(
    title=configuracoes.api_titulo,
    description="API para geração de relatórios e alertas",
    version=configuracoes.api_versao,
    lifespan=ciclo_vida,
)

app.include_router(saude.router)
app.include_router(relatorios.router)
app.include_router(alertas.router)
