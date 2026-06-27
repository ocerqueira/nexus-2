"""Middleware de autenticação por API Key."""

from fastapi import Request
from fastapi.responses import JSONResponse

from config import configuracoes

# Rotas isentas da verificação de API Key por este middleware.
# /admin usa autenticação própria (sessão); /docs e /redoc são docs do Swagger.
_PREFIXOS_ISENTOS = ("/admin", "/docs", "/redoc", "/openapi.json")
_ROTAS_ISENTAS = {"/saude"}


async def middleware_api_key(request: Request, call_next):
    if not configuracoes.api_key:
        return await call_next(request)

    path = request.url.path

    if path in _ROTAS_ISENTAS or any(path.startswith(p) for p in _PREFIXOS_ISENTOS):
        return await call_next(request)

    if request.headers.get("X-Api-Key") != configuracoes.api_key:
        return JSONResponse(
            status_code=401,
            content={"detail": "X-Api-Key ausente ou inválida"},
        )

    return await call_next(request)
