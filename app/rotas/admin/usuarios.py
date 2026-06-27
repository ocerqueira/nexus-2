from typing import Annotated

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse

from ._base import engine, templates, text, _POR_PAGINA

router = APIRouter()

_SQL_USUARIO = text("""
    SELECT id, nome, identificador, origem, email, whatsapp_numero, departamento, cargo, ativo,
           silencio_ativo,
           TO_CHAR(silencio_inicio, 'HH24:MI') AS silencio_inicio,
           TO_CHAR(silencio_fim,   'HH24:MI') AS silencio_fim
    FROM usuarios WHERE id = :id
""")


def _usuarios_db(busca: str = "", pagina: int = 1,
                 origem_filtro: str = "", status_filtro: str = "") -> tuple[list[dict], int]:
    filtros = ["1=1"]
    params: dict = {"lim": _POR_PAGINA, "off": (pagina - 1) * _POR_PAGINA}
    if busca:
        filtros.append("(nome ILIKE :f OR identificador ILIKE :f OR COALESCE(email,'') ILIKE :f)")
        params["f"] = f"%{busca}%"
    if origem_filtro:
        filtros.append("origem = :orig")
        params["orig"] = origem_filtro
    if status_filtro == "ativo":
        filtros.append("ativo = TRUE")
    elif status_filtro == "inativo":
        filtros.append("ativo = FALSE")
    where = " AND ".join(filtros)
    with engine.connect() as c:
        total = c.execute(text(f"SELECT COUNT(*) FROM usuarios WHERE {where}"), params).scalar() or 0
        rows = c.execute(text(f"""
            SELECT id, nome, identificador, origem, email, whatsapp_numero, departamento, cargo, ativo
            FROM usuarios WHERE {where} ORDER BY nome LIMIT :lim OFFSET :off
        """), params).mappings().all()
    return [dict(r) for r in rows], total


def _usuarios_ctx(busca: str = "", pagina: int = 1,
                  origem_filtro: str = "", status_filtro: str = "",
                  msg: str = "", msg_tipo: str = "") -> dict:
    usuarios, total = _usuarios_db(busca, pagina, origem_filtro, status_filtro)
    total_paginas = max(1, -(-total // _POR_PAGINA))
    return {
        "usuarios": usuarios, "total": total,
        "busca": busca, "pagina": pagina, "total_paginas": total_paginas,
        "origem_filtro": origem_filtro, "status_filtro": status_filtro,
        "msg": msg, "msg_tipo": msg_tipo,
    }


@router.get("/usuarios", response_class=HTMLResponse)
def admin_usuarios(request: Request,
                   busca: str = Query(""),
                   pagina: int = Query(1, ge=1),
                   origem_filtro: str = Query(""),
                   status_filtro: str = Query("")):
    return templates.TemplateResponse(request, "admin/usuarios.html",
                                      _usuarios_ctx(busca, pagina, origem_filtro, status_filtro))


@router.get("/usuarios/form", response_class=HTMLResponse)
def admin_usuarios_form(request: Request):
    return templates.TemplateResponse(request, "admin/usuario_form.html", {})


@router.get("/usuarios/{usuario_id}/editar", response_class=HTMLResponse)
def admin_usuarios_editar(request: Request, usuario_id: int):
    with engine.connect() as c:
        row = c.execute(_SQL_USUARIO, {"id": usuario_id}).mappings().first()
    if not row:
        return HTMLResponse("—")
    return templates.TemplateResponse(request, "admin/usuario_linha_editar.html", {"u": dict(row)})


@router.get("/usuarios/{usuario_id}/linha", response_class=HTMLResponse)
def admin_usuarios_linha(request: Request, usuario_id: int):
    with engine.connect() as c:
        row = c.execute(_SQL_USUARIO, {"id": usuario_id}).mappings().first()
    if not row:
        return HTMLResponse("—")
    return templates.TemplateResponse(request, "admin/usuario_linha.html", {"u": dict(row)})


@router.post("/usuarios/{usuario_id}/salvar", response_class=HTMLResponse)
def admin_usuarios_salvar(
    request: Request,
    usuario_id: int,
    whatsapp_numero: Annotated[str | None, Form()] = None,
    email: Annotated[str | None, Form()] = None,
    silencio_ativo: Annotated[str | None, Form()] = None,
    silencio_inicio: Annotated[str | None, Form()] = None,
    silencio_fim: Annotated[str | None, Form()] = None,
):
    with engine.begin() as c:
        c.execute(text("""
            UPDATE usuarios SET
                whatsapp_numero = :wpp,
                email = :email,
                silencio_ativo = :sil_ativo,
                silencio_inicio = CAST(:sil_inicio AS time),
                silencio_fim    = CAST(:sil_fim AS time),
                atualizado_em = NOW()
            WHERE id = :id
        """), {
            "wpp": whatsapp_numero or None,
            "email": email or None,
            "sil_ativo": silencio_ativo == "true",
            "sil_inicio": silencio_inicio or None,
            "sil_fim": silencio_fim or None,
            "id": usuario_id,
        })
        row = c.execute(_SQL_USUARIO, {"id": usuario_id}).mappings().first()
    if not row:
        return HTMLResponse("—")
    return templates.TemplateResponse(request, "admin/usuario_linha.html", {"u": dict(row)})


@router.post("/usuarios", response_class=HTMLResponse)
def admin_usuarios_criar(
    request: Request,
    identificador: Annotated[str, Form()],
    nome: Annotated[str, Form()],
    whatsapp_numero: Annotated[str | None, Form()] = None,
    email: Annotated[str | None, Form()] = None,
    departamento: Annotated[str | None, Form()] = None,
    cargo: Annotated[str | None, Form()] = None,
    silencio_ativo: Annotated[str | None, Form()] = None,
    silencio_inicio: Annotated[str | None, Form()] = None,
    silencio_fim: Annotated[str | None, Form()] = None,
):
    try:
        with engine.begin() as c:
            c.execute(text("""
                INSERT INTO usuarios (identificador, nome, origem, whatsapp_numero, email, departamento, cargo,
                                     silencio_ativo, silencio_inicio, silencio_fim)
                VALUES (:ident, :nome, 'manual', :wpp, :email, :depto, :cargo,
                        :sil_ativo,
                        CAST(:sil_inicio AS time),
                        CAST(:sil_fim AS time))
            """), {"ident": identificador, "nome": nome, "wpp": whatsapp_numero or None,
                   "email": email or None, "depto": departamento or None, "cargo": cargo or None,
                   "sil_ativo": silencio_ativo == "true",
                   "sil_inicio": silencio_inicio or None, "sil_fim": silencio_fim or None})
        return templates.TemplateResponse(request, "admin/usuarios.html",
                                          _usuarios_ctx(msg=f"Usuário '{nome}' criado.", msg_tipo="ok"))
    except Exception as e:
        msg = f"Identificador '{identificador}' já existe." if "usuarios_identificador_key" in str(e) else str(e)
        return templates.TemplateResponse(request, "admin/usuarios.html", _usuarios_ctx(msg=msg))


@router.delete("/usuarios/{usuario_id}", response_class=HTMLResponse)
def admin_usuarios_desativar(request: Request, usuario_id: int):
    with engine.begin() as c:
        c.execute(text("UPDATE usuarios SET ativo=FALSE, atualizado_em=NOW() WHERE id=:id"), {"id": usuario_id})
    return templates.TemplateResponse(request, "admin/usuarios.html",
                                      _usuarios_ctx(msg="Usuário desativado.", msg_tipo="ok"))


@router.delete("/usuarios/{usuario_id}/deletar", response_class=HTMLResponse)
def admin_usuarios_deletar(request: Request, usuario_id: int):
    try:
        with engine.begin() as c:
            c.execute(text("DELETE FROM usuarios WHERE id=:id"), {"id": usuario_id})
        msg, msg_tipo = "Usuário deletado permanentemente.", "ok"
    except Exception as e:
        msg, msg_tipo = f"Erro ao deletar: {e}", "erro"
    return templates.TemplateResponse(request, "admin/usuarios.html",
                                      _usuarios_ctx(msg=msg, msg_tipo=msg_tipo))


@router.post("/usuarios/{usuario_id}/reativar", response_class=HTMLResponse)
def admin_usuarios_reativar(request: Request, usuario_id: int):
    with engine.begin() as c:
        c.execute(text("UPDATE usuarios SET ativo=TRUE, atualizado_em=NOW() WHERE id=:id"), {"id": usuario_id})
    return templates.TemplateResponse(request, "admin/usuarios.html",
                                      _usuarios_ctx(msg="Usuário reativado.", msg_tipo="ok"))
