import json
from typing import Annotated

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse

from ._base import (
    engine, logger, templates, text,
    _badge, _fmt_dt,
    _carregar_processador_relatorio,
)

router = APIRouter()


def _relatorios_db(busca: str = "", status_filtro: str = "") -> list[dict]:
    filtros = ["1=1"]
    params: dict = {}
    if busca:
        filtros.append("(nome ILIKE :b OR titulo ILIKE :b)")
        params["b"] = f"%{busca}%"
    if status_filtro:
        filtros.append("status = :sf")
        params["sf"] = status_filtro
    where = " AND ".join(filtros)
    with engine.connect() as c:
        rows = c.execute(text(
            f"SELECT id, nome, titulo, categoria, status, ultimo_sync FROM relatorios WHERE {where} ORDER BY categoria NULLS LAST, nome"
        ), params).mappings().all()
    result = []
    for r in rows:
        d = dict(r)
        d["ultimo_sync_fmt"] = _fmt_dt(d["ultimo_sync"])
        result.append(d)
    return result


def _rel_dest_ctx(relatorio_id: int) -> dict:
    with engine.connect() as c:
        row_rel = c.execute(text(
            "SELECT nome, titulo, COALESCE(modo_execucao, 'unico') AS modo_execucao FROM relatorios WHERE id=:id"
        ), {"id": relatorio_id}).mappings().first()
        dests_raw = c.execute(text("""
            SELECT rd.id, rd.usuario_id, u.nome AS usuario_nome,
                   rd.canais, rd.formato_whatsapp, rd.filtro_parametros
            FROM relatorios_destinatarios rd
            JOIN usuarios u ON u.id = rd.usuario_id
            WHERE rd.relatorio_id = :id
            ORDER BY u.nome
        """), {"id": relatorio_id}).mappings().all()
        usuarios = [dict(r) for r in c.execute(text(
            "SELECT id, nome FROM usuarios WHERE ativo=TRUE ORDER BY nome"
        )).mappings().all()]
    dests = []
    for d in dests_raw:
        dd = dict(d)
        fp = dd.get("filtro_parametros") or {}
        dd["filtro_parametros_json"] = json.dumps(fp, ensure_ascii=False, indent=2) if fp else ""
        dests.append(dd)
    return {
        "dests": dests,
        "usuarios": usuarios,
        "relatorio_id": relatorio_id,
        "relatorio": dict(row_rel) if row_rel else {},
    }


@router.get("/relatorios", response_class=HTMLResponse)
def admin_relatorios(request: Request,
                     busca: str = Query(""),
                     status_filtro: str = Query("")):
    return templates.TemplateResponse(request, "admin/relatorios.html", {
        "relatorios": _relatorios_db(busca, status_filtro),
        "busca": busca,
        "status_filtro": status_filtro,
        "msg": "", "msg_tipo": "",
    })


@router.get("/relatorios/form", response_class=HTMLResponse)
def admin_relatorios_form(request: Request):
    return templates.TemplateResponse(request, "admin/relatorios_form.html", {})


@router.delete("/relatorios/{relatorio_id}/deletar", response_class=HTMLResponse)
def admin_relatorios_deletar(request: Request, relatorio_id: int):
    try:
        with engine.begin() as c:
            c.execute(text("DELETE FROM relatorios WHERE id=:id"), {"id": relatorio_id})
        msg, msg_tipo = "Relatório deletado permanentemente.", "ok"
    except Exception as e:
        msg, msg_tipo = f"Erro ao deletar: {e}", "erro"
    return templates.TemplateResponse(request, "admin/relatorios.html", {
        "relatorios": _relatorios_db(), "busca": "", "status_filtro": "",
        "msg": msg, "msg_tipo": msg_tipo,
    })


@router.post("/relatorios/{relatorio_id}/ativar", response_class=HTMLResponse)
def admin_relatorios_ativar(request: Request, relatorio_id: int):
    with engine.begin() as c:
        c.execute(text("UPDATE relatorios SET status='ativo', atualizado_em=NOW() WHERE id=:id"), {"id": relatorio_id})
    return templates.TemplateResponse(request, "admin/relatorios.html", {
        "relatorios": _relatorios_db(), "busca": "", "status_filtro": "",
        "msg": "Relatório ativado.", "msg_tipo": "ok",
    })


@router.post("/relatorios/{relatorio_id}/inativar", response_class=HTMLResponse)
def admin_relatorios_inativar(request: Request, relatorio_id: int):
    with engine.begin() as c:
        c.execute(text("UPDATE relatorios SET status='inativo', atualizado_em=NOW() WHERE id=:id"), {"id": relatorio_id})
    return templates.TemplateResponse(request, "admin/relatorios.html", {
        "relatorios": _relatorios_db(), "busca": "", "status_filtro": "",
        "msg": "Relatório inativado.", "msg_tipo": "ok",
    })


@router.post("/relatorios/{relatorio_id}/disparar", response_class=HTMLResponse)
def admin_relatorios_disparar(request: Request, relatorio_id: int):
    with engine.connect() as c:
        row = c.execute(text("SELECT nome FROM relatorios WHERE id=:id"),
                        {"id": relatorio_id}).mappings().first()
    if not row:
        return HTMLResponse(_badge("não encontrado", "red"))

    nome = row["nome"]
    info = _carregar_processador_relatorio(nome)
    if not info:
        return HTMLResponse(_badge("sem processador", "orange"))

    try:
        processador = info["classe"]()
        processador.validar({})
        dados = processador.buscar_dados({})
        if isinstance(dados, dict):
            total = dados.get("total", len(dados.get("dados", [])))
        else:
            total = len(dados)
        return HTMLResponse(_badge(f"✓ ok ({total})", "green"))
    except Exception as e:
        return HTMLResponse(_badge(f"erro: {e!s}"[:60], "red"))


@router.get("/relatorios/{relatorio_id}/destinatarios", response_class=HTMLResponse)
def admin_relatorios_destinatarios(request: Request, relatorio_id: int):
    return templates.TemplateResponse(request, "admin/relatorios_destinatarios.html",
                                      _rel_dest_ctx(relatorio_id))


@router.post("/relatorios/{relatorio_id}/destinatarios", response_class=HTMLResponse)
def admin_relatorios_dest_add(
    request: Request, relatorio_id: int,
    usuario_id: Annotated[int, Form()],
    canais: Annotated[list[str], Form()] = [],
    formato_whatsapp: Annotated[str, Form()] = "documento",
    filtro_parametros_json: Annotated[str | None, Form()] = None,
):
    canais_validos = [ch for ch in canais if ch in ("whatsapp", "email", "sms")]
    try:
        filtro = json.loads(filtro_parametros_json) if filtro_parametros_json and filtro_parametros_json.strip() else {}
    except Exception:
        filtro = {}
    try:
        with engine.begin() as c:
            c.execute(text("""
                INSERT INTO relatorios_destinatarios
                    (relatorio_id, usuario_id, canais, formato_whatsapp, filtro_parametros)
                VALUES (:rid, :uid, CAST(:canais AS jsonb), :fmt, CAST(:fp AS jsonb))
                ON CONFLICT (relatorio_id, usuario_id) DO UPDATE SET
                    canais=CAST(:canais AS jsonb), formato_whatsapp=:fmt,
                    filtro_parametros=CAST(:fp AS jsonb)
            """), {"rid": relatorio_id, "uid": usuario_id,
                   "canais": json.dumps(canais_validos), "fmt": formato_whatsapp,
                   "fp": json.dumps(filtro)})
    except Exception as e:
        logger.error(f"Erro ao adicionar destinatário relatório: {e}")
    return templates.TemplateResponse(request, "admin/relatorios_destinatarios.html",
                                      _rel_dest_ctx(relatorio_id))


@router.delete("/relatorios_destinatarios/{dest_id}", response_class=HTMLResponse)
def admin_relatorios_dest_rm(request: Request, dest_id: int):
    with engine.begin() as c:
        row = c.execute(text(
            "SELECT relatorio_id FROM relatorios_destinatarios WHERE id=:id"
        ), {"id": dest_id}).mappings().first()
        if not row:
            return HTMLResponse("—")
        relatorio_id = row["relatorio_id"]
        c.execute(text("DELETE FROM relatorios_destinatarios WHERE id=:id"), {"id": dest_id})
    return templates.TemplateResponse(request, "admin/relatorios_destinatarios.html",
                                      _rel_dest_ctx(relatorio_id))
