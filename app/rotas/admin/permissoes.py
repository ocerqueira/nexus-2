from typing import Annotated

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse

from ._base import engine, templates, text, _formatar_data, _PERM_USUARIOS_POR_PAGINA, _usuarios_lista, _recursos_lista

router = APIRouter()


def _permissoes_db(busca: str = "", tipo_filtro: str = "", pagina: int = 1) -> tuple[list[dict], int]:
    filtros = ["1=1"]
    params: dict = {}
    if busca:
        filtros.append("(u.nome ILIKE :b OR COALESCE(r.titulo, al.titulo) ILIKE :b)")
        params["b"] = f"%{busca}%"
    if tipo_filtro:
        filtros.append("p.tipo_recurso = :tp")
        params["tp"] = tipo_filtro
    where = " AND ".join(filtros)
    with engine.connect() as c:
        rows = c.execute(text(f"""
            SELECT p.id, p.usuario_id, u.nome AS usuario_nome,
                   p.tipo_recurso, p.recurso_id,
                   COALESCE(r.titulo, al.titulo) AS recurso_nome,
                   p.pode_solicitar, p.pode_agendar, p.limite_diario, p.criado_em
            FROM permissoes p
            JOIN usuarios u ON u.id = p.usuario_id
            LEFT JOIN relatorios r ON p.tipo_recurso='relatorio' AND r.id=p.recurso_id
            LEFT JOIN alertas al ON p.tipo_recurso='alerta' AND al.id=p.recurso_id
            WHERE {where}
            ORDER BY u.nome, p.tipo_recurso, COALESCE(r.titulo, al.titulo)
        """), params).mappings().all()

    grupos: dict = {}
    for r in rows:
        d = dict(r)
        d["criado_em_fmt"] = _formatar_data(d["criado_em"])
        uid = d["usuario_id"]
        if uid not in grupos:
            grupos[uid] = {"usuario_id": uid, "usuario_nome": d["usuario_nome"], "permissoes": []}
        grupos[uid]["permissoes"].append(d)

    grupos_list = list(grupos.values())
    total_usuarios = len(grupos_list)
    offset = (pagina - 1) * _PERM_USUARIOS_POR_PAGINA
    return grupos_list[offset:offset + _PERM_USUARIOS_POR_PAGINA], total_usuarios


def _permissoes_ctx(busca: str = "", tipo_filtro: str = "", pagina: int = 1,
                    msg: str = "", msg_tipo: str = "") -> dict:
    grupos, total = _permissoes_db(busca, tipo_filtro, pagina)
    return {
        "grupos": grupos, "total": total,
        "busca": busca, "tipo_filtro": tipo_filtro,
        "pagina": pagina, "total_paginas": max(1, -(-total // _PERM_USUARIOS_POR_PAGINA)),
        "msg": msg, "msg_tipo": msg_tipo,
    }


@router.get("/permissoes", response_class=HTMLResponse)
def admin_permissoes(request: Request,
                     busca: str = Query(""),
                     tipo_filtro: str = Query(""),
                     pagina: int = Query(1, ge=1)):
    return templates.TemplateResponse(request, "admin/permissoes.html",
                                      _permissoes_ctx(busca, tipo_filtro, pagina))


@router.get("/permissoes/form", response_class=HTMLResponse)
def admin_permissoes_form(request: Request):
    return templates.TemplateResponse(request, "admin/permissao_form.html", {
        "usuarios": _usuarios_lista(),
        "rel_opts": _recursos_lista("relatorio"),
    })


@router.post("/permissoes", response_class=HTMLResponse)
def admin_permissoes_criar(
    request: Request,
    usuario_id: Annotated[int, Form()],
    tipo_recurso: Annotated[str, Form()],
    recurso_id: Annotated[int, Form()],
    limite_diario: Annotated[int, Form()] = 10,
    pode_solicitar: Annotated[str | None, Form()] = None,
    pode_agendar: Annotated[str | None, Form()] = None,
):
    try:
        with engine.begin() as c:
            c.execute(text("""
                INSERT INTO permissoes (usuario_id, tipo_recurso, recurso_id,
                                       pode_solicitar, pode_agendar, limite_diario)
                VALUES (:usuario_id, :tipo_recurso, :recurso_id,
                        :pode_solicitar, :pode_agendar, :limite_diario)
            """), {
                "usuario_id": usuario_id, "tipo_recurso": tipo_recurso, "recurso_id": recurso_id,
                "pode_solicitar": pode_solicitar == "true",
                "pode_agendar": pode_agendar == "true",
                "limite_diario": limite_diario,
            })
        msg, msg_tipo = "Permissão concedida.", "ok"
    except Exception as e:
        msg = "Permissão já existe para este usuário/recurso." if "uq_permissoes" in str(e) else str(e)
        msg_tipo = "erro"
    return templates.TemplateResponse(request, "admin/permissoes.html",
                                      _permissoes_ctx(msg=msg, msg_tipo=msg_tipo))


@router.delete("/permissoes/{permissao_id}", response_class=HTMLResponse)
def admin_permissoes_revogar(request: Request, permissao_id: int):
    with engine.begin() as c:
        c.execute(text("DELETE FROM permissoes WHERE id=:id"), {"id": permissao_id})
    return templates.TemplateResponse(request, "admin/permissoes.html",
                                      _permissoes_ctx(msg="Permissão revogada.", msg_tipo="ok"))
