from typing import Annotated

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse

from ._base import engine, templates, text, _badge, criptografar, gerenciador_conexoes

router = APIRouter()


def _conexoes_db(status_filtro: str = "") -> list[dict]:
    filtro_sql = ""
    if status_filtro == "ativo":
        filtro_sql = " WHERE ativo = TRUE"
    elif status_filtro == "inativo":
        filtro_sql = " WHERE ativo = FALSE"
    with engine.connect() as c:
        rows = c.execute(text(
            "SELECT id, nome, tipo, host, porta, banco, usuario, observacoes, ativo "
            f"FROM conexoes_bd{filtro_sql} ORDER BY nome"
        )).mappings().all()
    return [dict(r) for r in rows]


@router.get("/conexoes", response_class=HTMLResponse)
def admin_conexoes(request: Request, status_filtro: str = Query("")):
    return templates.TemplateResponse(request, "admin/conexoes.html", {
        "conexoes": _conexoes_db(status_filtro), "msg": "", "msg_tipo": "", "status_filtro": status_filtro,
    })


@router.get("/conexoes/form", response_class=HTMLResponse)
def admin_conexoes_form(request: Request):
    return templates.TemplateResponse(request, "admin/conexoes_form.html", {})


@router.post("/conexoes", response_class=HTMLResponse)
def admin_conexoes_criar(
    request: Request,
    nome: Annotated[str, Form()],
    tipo: Annotated[str, Form()],
    host: Annotated[str, Form()],
    porta: Annotated[int, Form()],
    banco: Annotated[str, Form()],
    usuario: Annotated[str, Form()],
    senha: Annotated[str, Form()],
    observacoes: Annotated[str | None, Form()] = None,
):
    try:
        with engine.begin() as c:
            c.execute(text("""
                INSERT INTO conexoes_bd (nome, tipo, host, porta, banco, usuario, senha_criptografada, observacoes)
                VALUES (:nome, :tipo, :host, :porta, :banco, :usuario, :senha, :obs)
            """), {
                "nome": nome, "tipo": tipo, "host": host, "porta": porta,
                "banco": banco, "usuario": usuario, "senha": criptografar(senha),
                "obs": observacoes or None,
            })
        msg, msg_tipo = f"Conexão '{nome}' criada.", "ok"
    except Exception as e:
        msg = f"Conexão '{nome}' já existe." if "conexoes_bd_nome_key" in str(e) else str(e)
        msg_tipo = "erro"
    return templates.TemplateResponse(request, "admin/conexoes.html", {
        "conexoes": _conexoes_db(), "msg": msg, "msg_tipo": msg_tipo,
    })


@router.delete("/conexoes/{conexao_id}", response_class=HTMLResponse)
def admin_conexoes_desativar(request: Request, conexao_id: int):
    with engine.begin() as c:
        c.execute(text("UPDATE conexoes_bd SET ativo=FALSE, atualizado_em=NOW() WHERE id=:id"), {"id": conexao_id})
    return templates.TemplateResponse(request, "admin/conexoes.html", {
        "conexoes": _conexoes_db(), "msg": "Conexão desativada.", "msg_tipo": "ok", "status_filtro": "",
    })


@router.delete("/conexoes/{conexao_id}/deletar", response_class=HTMLResponse)
def admin_conexoes_deletar(request: Request, conexao_id: int):
    try:
        with engine.begin() as c:
            c.execute(text("DELETE FROM conexoes_bd WHERE id=:id"), {"id": conexao_id})
        msg, msg_tipo = "Conexão deletada permanentemente.", "ok"
    except Exception as e:
        msg, msg_tipo = f"Erro ao deletar: {e}", "erro"
    return templates.TemplateResponse(request, "admin/conexoes.html", {
        "conexoes": _conexoes_db(), "msg": msg, "msg_tipo": msg_tipo, "status_filtro": "",
    })


@router.post("/conexoes/{conexao_id}/reativar", response_class=HTMLResponse)
def admin_conexoes_reativar(request: Request, conexao_id: int):
    with engine.begin() as c:
        c.execute(text("UPDATE conexoes_bd SET ativo=TRUE, atualizado_em=NOW() WHERE id=:id"), {"id": conexao_id})
    return templates.TemplateResponse(request, "admin/conexoes.html", {
        "conexoes": _conexoes_db(), "msg": "Conexão reativada.", "msg_tipo": "ok",
    })


@router.post("/conexoes/{conexao_id}/testar", response_class=HTMLResponse)
def admin_conexoes_testar(conexao_id: int):
    with engine.connect() as c:
        row = c.execute(text("SELECT nome FROM conexoes_bd WHERE id=:id"), {"id": conexao_id}).mappings().first()
    if not row:
        return HTMLResponse("—")
    resultado = gerenciador_conexoes.testar_conexao(row["nome"])
    return HTMLResponse(_badge("✓ OK", "green") if resultado["status"] == "ok" else _badge("✗ Erro", "red"))


@router.post("/conexoes/{conexao_id}/limpar-cache", response_class=HTMLResponse)
def admin_conexoes_limpar_cache(conexao_id: int):
    with engine.connect() as c:
        row = c.execute(text("SELECT nome FROM conexoes_bd WHERE id=:id"), {"id": conexao_id}).mappings().first()
    if not row:
        return HTMLResponse("—")
    gerenciador_conexoes.limpar_cache(row["nome"])
    return HTMLResponse(_badge("cache limpo", "blue"))
