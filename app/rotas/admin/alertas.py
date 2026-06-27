import json
from typing import Annotated

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse

from ._base import (
    engine, logger, templates, text,
    _badge, _fmt_dt, orquestrar_alerta,
    _carregar_processador_alerta,
)

router = APIRouter()


def _alertas_db(status_filtro: str = "") -> tuple[list[dict], int]:
    params: dict = {}
    filtro_sql = ""
    if status_filtro:
        filtro_sql = "WHERE a.status = :sf"
        params["sf"] = status_filtro
    with engine.connect() as c:
        rows = c.execute(text(f"""
            SELECT a.id, a.nome, a.titulo, a.severidade, a.status, a.ultimo_sync,
                   COALESCE(a.cooldown_minutos, 60) AS cooldown_minutos,
                   COUNT(ad.id) FILTER (WHERE ad.ativo) AS destinatarios_ativos
            FROM alertas a
            LEFT JOIN alertas_destinatarios ad ON ad.alerta_id = a.id
            {filtro_sql}
            GROUP BY a.id
            ORDER BY
                CASE a.severidade WHEN 'critico' THEN 0 WHEN 'aviso' THEN 1 ELSE 2 END,
                a.nome
        """), params).mappings().all()

    _ordem = ["critico", "aviso", "info"]
    grupos: dict = {s: [] for s in _ordem}
    for r in rows:
        d = dict(r)
        d["ultimo_sync_fmt"] = _fmt_dt(d["ultimo_sync"])
        grupos.setdefault(d["severidade"], []).append(d)

    grupos_list = [{"severidade": s, "alertas": grupos[s]} for s in _ordem if grupos.get(s)]
    total = sum(len(g["alertas"]) for g in grupos_list)
    return grupos_list, total


def _alertas_ctx(status_filtro: str = "", msg: str = "", msg_tipo: str = "") -> dict:
    grupos, total = _alertas_db(status_filtro)
    return {"grupos": grupos, "total_alertas": total,
            "status_filtro": status_filtro, "msg": msg, "msg_tipo": msg_tipo}


def _alertas_dest_ctx(alerta_id: int) -> dict:
    with engine.connect() as c:
        row_alerta = c.execute(text(
            "SELECT cooldown_minutos FROM alertas WHERE id=:id"
        ), {"id": alerta_id}).mappings().first()
        dests_raw = c.execute(text("""
            SELECT ad.id, ad.usuario_id, u.nome AS usuario_nome,
                   ad.canais, ad.modo_mensagem, ad.limite_hora, ad.limite_dia, ad.ativo
            FROM alertas_destinatarios ad
            JOIN usuarios u ON u.id = ad.usuario_id
            WHERE ad.alerta_id = :id
            ORDER BY u.nome
        """), {"id": alerta_id}).mappings().all()
        usuarios = [dict(r) for r in c.execute(text(
            "SELECT id, nome FROM usuarios WHERE ativo=TRUE ORDER BY nome"
        )).mappings().all()]
    cooldown = (row_alerta["cooldown_minutos"] if row_alerta else None) or 60
    return {
        "dests": [dict(d) for d in dests_raw],
        "usuarios": usuarios,
        "alerta_id": alerta_id,
        "cooldown_minutos": cooldown,
    }


@router.get("/alertas", response_class=HTMLResponse)
def admin_alertas(request: Request, status_filtro: str = Query("")):
    return templates.TemplateResponse(request, "admin/alertas.html",
                                      _alertas_ctx(status_filtro))


@router.delete("/alertas/{alerta_id}/deletar", response_class=HTMLResponse)
def admin_alertas_deletar(request: Request, alerta_id: int):
    try:
        with engine.begin() as c:
            c.execute(text("DELETE FROM alertas WHERE id=:id"), {"id": alerta_id})
        msg, msg_tipo = "Alerta deletado permanentemente.", "ok"
    except Exception as e:
        msg, msg_tipo = f"Erro ao deletar: {e}", "erro"
    return templates.TemplateResponse(request, "admin/alertas.html",
                                      _alertas_ctx(msg=msg, msg_tipo=msg_tipo))


@router.post("/alertas/{alerta_id}/ativar", response_class=HTMLResponse)
def admin_alertas_ativar(request: Request, alerta_id: int):
    with engine.begin() as c:
        c.execute(text("UPDATE alertas SET status='ativo', atualizado_em=NOW() WHERE id=:id"), {"id": alerta_id})
    return templates.TemplateResponse(request, "admin/alertas.html",
                                      _alertas_ctx(msg="Alerta ativado.", msg_tipo="ok"))


@router.post("/alertas/{alerta_id}/inativar", response_class=HTMLResponse)
def admin_alertas_inativar(request: Request, alerta_id: int):
    with engine.begin() as c:
        c.execute(text("UPDATE alertas SET status='inativo', atualizado_em=NOW() WHERE id=:id"), {"id": alerta_id})
    return templates.TemplateResponse(request, "admin/alertas.html",
                                      _alertas_ctx(msg="Alerta inativado.", msg_tipo="ok"))


@router.post("/alertas/{alerta_id}/disparar", response_class=HTMLResponse)
def admin_alertas_disparar(request: Request, alerta_id: int):
    with engine.connect() as c:
        row = c.execute(text("SELECT nome FROM alertas WHERE id=:id"),
                        {"id": alerta_id}).mappings().first()
    if not row:
        return HTMLResponse(_badge("não encontrado", "red"))

    nome = row["nome"]
    classe = _carregar_processador_alerta(nome)
    if not classe:
        return HTMLResponse(_badge("sem processador", "orange"))

    try:
        resultado = orquestrar_alerta(
            nome_alerta=nome, parametros={}, processador_classe=classe, forcar=True
        )
        if resultado.get("deve_notificar"):
            return HTMLResponse(_badge(f"✓ disparado ({resultado.get('total', 0)} itens)", "green"))
        motivo = resultado.get("motivo", "")
        return HTMLResponse(_badge(motivo.replace("_", " "), "gray"))
    except Exception as e:
        return HTMLResponse(_badge(f"erro: {e!s}"[:60], "red"))


@router.get("/alertas/{alerta_id}/destinatarios", response_class=HTMLResponse)
def admin_alertas_destinatarios(request: Request, alerta_id: int):
    return templates.TemplateResponse(request, "admin/alertas_destinatarios.html",
                                      _alertas_dest_ctx(alerta_id))


@router.post("/alertas/{alerta_id}/destinatarios", response_class=HTMLResponse)
def admin_alertas_dest_add(
    request: Request, alerta_id: int,
    usuario_id: Annotated[int, Form()],
    canais: Annotated[list[str], Form()] = [],
    modo_mensagem: Annotated[str, Form()] = "individual",
    limite_hora: Annotated[int | None, Form()] = None,
    limite_dia: Annotated[int | None, Form()] = None,
):
    canais_validos = [ch for ch in canais if ch in ("whatsapp", "email", "sms")]
    try:
        with engine.begin() as c:
            c.execute(text("""
                INSERT INTO alertas_destinatarios
                    (alerta_id, usuario_id, canais, modo_mensagem, limite_hora, limite_dia)
                VALUES (:aid, :uid, CAST(:canais AS jsonb), :modo, :lh, :ld)
                ON CONFLICT (alerta_id, usuario_id) DO UPDATE SET
                    canais=CAST(:canais AS jsonb), modo_mensagem=:modo,
                    limite_hora=:lh, limite_dia=:ld, ativo=TRUE
            """), {"aid": alerta_id, "uid": usuario_id,
                   "canais": json.dumps(canais_validos), "modo": modo_mensagem,
                   "lh": limite_hora or None, "ld": limite_dia or None})
    except Exception as e:
        logger.error(f"Erro ao adicionar destinatário alerta: {e}")
    return templates.TemplateResponse(request, "admin/alertas_destinatarios.html",
                                      _alertas_dest_ctx(alerta_id))


@router.delete("/alertas_destinatarios/{dest_id}", response_class=HTMLResponse)
def admin_alertas_dest_rm(request: Request, dest_id: int):
    with engine.begin() as c:
        row = c.execute(text(
            "SELECT alerta_id FROM alertas_destinatarios WHERE id=:id"
        ), {"id": dest_id}).mappings().first()
        if not row:
            return HTMLResponse("—")
        alerta_id = row["alerta_id"]
        c.execute(text("DELETE FROM alertas_destinatarios WHERE id=:id"), {"id": dest_id})
    return templates.TemplateResponse(request, "admin/alertas_destinatarios.html",
                                      _alertas_dest_ctx(alerta_id))


@router.post("/alertas_destinatarios/{dest_id}/toggle", response_class=HTMLResponse)
def admin_alertas_dest_toggle(request: Request, dest_id: int):
    with engine.begin() as c:
        row = c.execute(text(
            "SELECT alerta_id, ativo FROM alertas_destinatarios WHERE id=:id"
        ), {"id": dest_id}).mappings().first()
        if not row:
            return HTMLResponse("—")
        c.execute(text("UPDATE alertas_destinatarios SET ativo=:v WHERE id=:id"),
                  {"v": not row["ativo"], "id": dest_id})
        alerta_id = row["alerta_id"]
    return templates.TemplateResponse(request, "admin/alertas_destinatarios.html",
                                      _alertas_dest_ctx(alerta_id))


@router.post("/alertas/{alerta_id}/cooldown", response_class=HTMLResponse)
def admin_alertas_cooldown(request: Request, alerta_id: int, cooldown: Annotated[int, Form()]):
    with engine.begin() as c:
        c.execute(text("UPDATE alertas SET cooldown_minutos=:v WHERE id=:id"),
                  {"v": cooldown, "id": alerta_id})
    return HTMLResponse(f'<span id="cooldown-val-{alerta_id}" class="text-xs text-green-600 font-medium">{cooldown} min ✓</span>')
