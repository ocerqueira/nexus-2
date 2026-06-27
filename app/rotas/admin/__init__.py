"""
Interface admin HTML — Tailwind CSS (CDN) + HTMX + Jinja2 templates.
Não aparece no Swagger (include_in_schema=False).
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from . import agendamentos, alertas, conexoes, dashboard, despachos, permissoes, relatorios, testes, usuarios
from ._base import templates

router = APIRouter(prefix="/admin", include_in_schema=False)


@router.get("", response_class=HTMLResponse)
def admin_index(request: Request):
    return templates.TemplateResponse(request, "admin/base.html", {})

router.include_router(dashboard.router)
router.include_router(relatorios.router)
router.include_router(alertas.router)
router.include_router(conexoes.router)
router.include_router(usuarios.router)
router.include_router(agendamentos.router)
router.include_router(permissoes.router)
router.include_router(despachos.router)
router.include_router(testes.router)
