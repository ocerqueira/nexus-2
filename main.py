"""
Ponto de entrada do sistema Nexus.
"""

import logging
import logging.handlers
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from app.core.autenticacao import middleware_api_key
from app.core.inicializador import garantir_estrutura_banco
from app.core.sincronizador import sincronizar_filesystem_com_banco
from app.rotas import ad, admin, agendamentos, alertas, chatbot, conexoes, permissoes, relatorios, saude, usuarios
from config import configuracoes

_LOG_DIR = Path("/app/logs")
_LOG_DIR.mkdir(parents=True, exist_ok=True)

_fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")

_handler_stdout = logging.StreamHandler()
_handler_stdout.setFormatter(_fmt)

_handler_file = logging.handlers.RotatingFileHandler(
    _LOG_DIR / "nexus.log",
    maxBytes=10 * 1024 * 1024,  # 10 MB por arquivo
    backupCount=5,
    encoding="utf-8",
)
_handler_file.setFormatter(_fmt)

logging.basicConfig(level=logging.INFO, handlers=[_handler_stdout, _handler_file])
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
    swagger_ui_parameters={"persistAuthorization": True},
)

app.middleware("http")(middleware_api_key)


def _openapi_schema():
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    if configuracoes.api_key:
        schema.setdefault("components", {}).setdefault("securitySchemes", {})[
            "ApiKeyHeader"
        ] = {"type": "apiKey", "in": "header", "name": "X-API-Key"}
        # Aplica em todas as rotas exceto as livres
        for path_item in schema.get("paths", {}).values():
            for method in path_item:
                path_item[method].setdefault("security", []).append({"ApiKeyHeader": []})
    app.openapi_schema = schema
    return schema


app.openapi = _openapi_schema

app.include_router(admin.router)
app.include_router(saude.router)
app.include_router(ad.router)
app.include_router(usuarios.router)
app.include_router(conexoes.router)
app.include_router(permissoes.router)
app.include_router(relatorios.router)
app.include_router(alertas.router)
app.include_router(agendamentos.router)
app.include_router(chatbot.router)