import json
from typing import Annotated

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse

from ._base import (
    engine, logger, templates, text,
    _badge, _formatar_datetime,
    _usuarios_lista, _recursos_lista, _parse_horarios,
    _AG_USUARIOS_POR_PAGINA, calcular_proximo_envio,
)

router = APIRouter()


def _agendamentos_db(busca: str = "", tipo_filtro: str = "",
                     freq_filtro: str = "", status_filtro: str = "",
                     pagina: int = 1) -> tuple[list[dict], int]:
    """
    Retorna agendamentos agrupados por usuário para exibição na listagem.
    A paginação é por usuário (não por agendamento individual) — cada página
    mostra _AG_USUARIOS_POR_PAGINA usuários com todos os seus agendamentos.
    """
    filtros = ["1=1"]
    params: dict = {}
    if busca:
        filtros.append("(u.nome ILIKE :b OR COALESCE(r.titulo, al.titulo) ILIKE :b)")
        params["b"] = f"%{busca}%"
    if tipo_filtro:
        filtros.append("a.tipo_recurso = :tp")
        params["tp"] = tipo_filtro
    if freq_filtro:
        filtros.append("a.frequencia = :fq")
        params["fq"] = freq_filtro
    if status_filtro == "ativo":
        filtros.append("a.ativo = TRUE")
    elif status_filtro == "inativo":
        filtros.append("a.ativo = FALSE")
    where = " AND ".join(filtros)

    with engine.connect() as c:
        rows = c.execute(text(f"""
            SELECT a.id, u.id AS usuario_id, u.nome AS usuario_nome, a.tipo_recurso,
                   COALESCE(r.titulo, al.titulo) AS recurso_nome,
                   a.frequencia, a.horarios, a.intervalo_minutos, a.canais, a.apenas_dias_uteis,
                   a.proximo_envio, a.ativo
            FROM agendamentos a
            LEFT JOIN usuarios u ON u.id = a.usuario_id
            LEFT JOIN relatorios r ON a.tipo_recurso='relatorio' AND r.id=a.recurso_id
            LEFT JOIN alertas al ON a.tipo_recurso='alerta' AND al.id=a.recurso_id
            WHERE {where}
            ORDER BY u.nome NULLS LAST, a.ativo DESC, a.proximo_envio ASC NULLS LAST
        """), params).mappings().all()

    grupos: dict = {}
    for r in rows:
        d = dict(r)
        uid = d.get("usuario_id") or 0
        horarios_raw = d.get("horarios") or []
        if d.get("frequencia") == "intervalo":
            d["horarios_str"] = f'a cada {d.get("intervalo_minutos")} min'
        else:
            d["horarios_str"] = ", ".join(
                f'{h["hora"]:02d}:{h["minuto"]:02d}' for h in horarios_raw
            ) if isinstance(horarios_raw, list) else str(horarios_raw)
        d["proximo_envio_fmt"] = _formatar_datetime(d.get("proximo_envio"))
        canais = d.get("canais") or []
        d["canais"] = canais if isinstance(canais, list) else []
        if uid not in grupos:
            grupos[uid] = {
                "usuario_id": uid,
                "usuario_nome": d.get("usuario_nome") or "Sem usuário",
                "agendamentos": [],
            }
        grupos[uid]["agendamentos"].append(d)

    grupos_list = list(grupos.values())
    total_usuarios = len(grupos_list)
    offset = (pagina - 1) * _AG_USUARIOS_POR_PAGINA
    return grupos_list[offset:offset + _AG_USUARIOS_POR_PAGINA], total_usuarios


def _ag_dest_ctx(agendamento_id: int) -> dict:
    with engine.connect() as c:
        row_ag = c.execute(text("""
            SELECT a.id, COALESCE(r.titulo, al.titulo) AS recurso_nome
            FROM agendamentos a
            LEFT JOIN relatorios r ON a.tipo_recurso='relatorio' AND r.id=a.recurso_id
            LEFT JOIN alertas al ON a.tipo_recurso='alerta' AND al.id=a.recurso_id
            WHERE a.id = :id
        """), {"id": agendamento_id}).mappings().first()
        dests_raw = c.execute(text("""
            SELECT ad.usuario_id, u.nome AS usuario_nome, ad.canais
            FROM agendamentos_destinatarios ad
            JOIN usuarios u ON u.id = ad.usuario_id
            WHERE ad.agendamento_id = :id
            ORDER BY u.nome
        """), {"id": agendamento_id}).mappings().all()
        usuarios = [dict(r) for r in c.execute(text(
            "SELECT id, nome FROM usuarios WHERE ativo=TRUE ORDER BY nome"
        )).mappings().all()]
    return {
        "dests": [dict(d) for d in dests_raw],
        "usuarios": usuarios,
        "agendamento_id": agendamento_id,
        "agendamento": dict(row_ag) if row_ag else {},
    }


@router.get("/agendamentos", response_class=HTMLResponse)
def admin_agendamentos(request: Request,
                       busca: str = Query(""),
                       tipo_filtro: str = Query(""),
                       freq_filtro: str = Query(""),
                       status_filtro: str = Query(""),
                       pagina: int = Query(1, ge=1)):
    grupos, total = _agendamentos_db(busca, tipo_filtro, freq_filtro, status_filtro, pagina)
    return templates.TemplateResponse(request, "admin/agendamentos.html", {
        "grupos": grupos, "total": total,
        "busca": busca, "tipo_filtro": tipo_filtro,
        "freq_filtro": freq_filtro, "status_filtro": status_filtro,
        "pagina": pagina,
        "total_paginas": max(1, -(-total // _AG_USUARIOS_POR_PAGINA)),
        "msg": "", "msg_tipo": "",
    })


@router.get("/agendamentos/form", response_class=HTMLResponse)
def admin_agendamentos_form(request: Request):
    return templates.TemplateResponse(request, "admin/agendamento_form.html", {
        "usuarios": _usuarios_lista(),
        "rel_opts": _recursos_lista("relatorio"),
    })


@router.post("/agendamentos", response_class=HTMLResponse)
def admin_agendamentos_criar(
    request: Request,
    usuario_id: Annotated[int, Form()],
    tipo_recurso: Annotated[str, Form()],
    recurso_id: Annotated[int, Form()],
    frequencia: Annotated[str, Form()],
    horarios_str: Annotated[str | None, Form()] = None,
    timezone: Annotated[str, Form()] = "America/Sao_Paulo",
    dia_semana: Annotated[int | None, Form()] = None,
    dia_mes: Annotated[int | None, Form()] = None,
    intervalo_minutos: Annotated[int | None, Form()] = None,
    apenas_dias_uteis: Annotated[str | None, Form()] = None,
    canais: Annotated[list[str] | None, Form()] = None,
):
    def _ctx(msg, msg_tipo="erro"):
        grupos, total = _agendamentos_db()
        return templates.TemplateResponse(request, "admin/agendamentos.html", {
            "grupos": grupos, "total": total, "busca": "", "tipo_filtro": "",
            "freq_filtro": "", "status_filtro": "", "pagina": 1,
            "total_paginas": max(1, -(-total // _AG_USUARIOS_POR_PAGINA)),
            "msg": msg, "msg_tipo": msg_tipo,
        })

    if not canais:
        return _ctx("Selecione ao menos um canal.")
    if frequencia == "intervalo":
        if not intervalo_minutos or intervalo_minutos < 1:
            return _ctx("Frequência 'intervalo' exige intervalo_minutos >= 1.")
        horarios = []
    else:
        horarios = _parse_horarios(horarios_str or "")
        if not horarios:
            return _ctx("Horários inválidos. Use formato HH:MM separados por vírgula.")
    if frequencia == "semanal" and not dia_semana:
        return _ctx("Frequência semanal exige dia da semana.")
    if frequencia == "mensal" and not dia_mes:
        return _ctx("Frequência mensal exige dia do mês.")
    uteis = apenas_dias_uteis == "true"
    try:
        proximo = calcular_proximo_envio({
            "frequencia": frequencia, "horarios": horarios,
            "dia_semana": dia_semana, "dia_mes": dia_mes,
            "intervalo_minutos": intervalo_minutos,
            "apenas_dias_uteis": uteis, "timezone": timezone,
        })
    except (ValueError, KeyError) as e:
        return _ctx(str(e))
    try:
        with engine.begin() as c:
            c.execute(text("""
                INSERT INTO agendamentos (
                    usuario_id, tipo_recurso, recurso_id, frequencia, dia_semana, dia_mes,
                    intervalo_minutos, horarios, apenas_dias_uteis, timezone, parametros, canais, proximo_envio
                ) VALUES (
                    :usuario_id, :tipo_recurso, :recurso_id, :frequencia, :dia_semana, :dia_mes,
                    :intervalo_minutos, :horarios, :apenas_dias_uteis, :timezone, :parametros, :canais, :proximo_envio
                )
            """), {
                "usuario_id": usuario_id, "tipo_recurso": tipo_recurso, "recurso_id": recurso_id,
                "frequencia": frequencia, "dia_semana": dia_semana, "dia_mes": dia_mes,
                "intervalo_minutos": intervalo_minutos,
                "horarios": json.dumps(horarios), "apenas_dias_uteis": uteis, "timezone": timezone,
                "parametros": json.dumps({}), "canais": json.dumps(canais), "proximo_envio": proximo,
            })
        return _ctx("Agendamento criado.", "ok")
    except Exception as e:
        return _ctx(str(e))


@router.delete("/agendamentos/{agendamento_id}", response_class=HTMLResponse)
def admin_agendamentos_desativar(request: Request, agendamento_id: int):
    with engine.begin() as c:
        c.execute(text("UPDATE agendamentos SET ativo=FALSE, atualizado_em=NOW() WHERE id=:id"), {"id": agendamento_id})
    grupos, total = _agendamentos_db()
    return templates.TemplateResponse(request, "admin/agendamentos.html", {
        "grupos": grupos, "total": total, "busca": "", "tipo_filtro": "",
        "freq_filtro": "", "status_filtro": "", "pagina": 1,
        "total_paginas": max(1, -(-total // _AG_USUARIOS_POR_PAGINA)),
        "msg": "Agendamento desativado.", "msg_tipo": "ok",
    })


@router.delete("/agendamentos/{agendamento_id}/deletar", response_class=HTMLResponse)
def admin_agendamentos_deletar(request: Request, agendamento_id: int):
    try:
        with engine.begin() as c:
            c.execute(text("DELETE FROM agendamentos WHERE id=:id"), {"id": agendamento_id})
        msg, msg_tipo = "Agendamento deletado permanentemente.", "ok"
    except Exception as e:
        msg, msg_tipo = f"Erro ao deletar: {e}", "erro"
    grupos, total = _agendamentos_db()
    return templates.TemplateResponse(request, "admin/agendamentos.html", {
        "grupos": grupos, "total": total, "busca": "", "tipo_filtro": "",
        "freq_filtro": "", "status_filtro": "", "pagina": 1,
        "total_paginas": max(1, -(-total // _AG_USUARIOS_POR_PAGINA)),
        "msg": msg, "msg_tipo": msg_tipo,
    })


@router.post("/agendamentos/{agendamento_id}/reativar", response_class=HTMLResponse)
def admin_agendamentos_reativar(request: Request, agendamento_id: int):
    with engine.begin() as c:
        c.execute(text("UPDATE agendamentos SET ativo=TRUE, atualizado_em=NOW() WHERE id=:id"), {"id": agendamento_id})
    grupos, total = _agendamentos_db()
    return templates.TemplateResponse(request, "admin/agendamentos.html", {
        "grupos": grupos, "total": total, "busca": "", "tipo_filtro": "",
        "freq_filtro": "", "status_filtro": "", "pagina": 1,
        "total_paginas": max(1, -(-total // _AG_USUARIOS_POR_PAGINA)),
        "msg": "Agendamento reativado.", "msg_tipo": "ok",
    })


@router.post("/agendamentos/{agendamento_id}/executar-agora", response_class=HTMLResponse)
def admin_agendamentos_executar_agora(request: Request, agendamento_id: int):
    """Força o próximo_envio para NOW() — o N8N captura na próxima execução (≤1 min)."""
    with engine.begin() as c:
        c.execute(
            text("UPDATE agendamentos SET proximo_envio=NOW(), atualizado_em=NOW() WHERE id=:id"),
            {"id": agendamento_id},
        )
    return HTMLResponse(_badge("⏳ na fila", "green"))


@router.get("/agendamentos/{agendamento_id}/destinatarios", response_class=HTMLResponse)
def admin_agendamentos_destinatarios(request: Request, agendamento_id: int):
    return templates.TemplateResponse(request, "admin/agendamentos_destinatarios.html",
                                      _ag_dest_ctx(agendamento_id))


@router.post("/agendamentos/{agendamento_id}/destinatarios", response_class=HTMLResponse)
def admin_agendamentos_dest_add(
    request: Request, agendamento_id: int,
    usuario_id: Annotated[int, Form()],
    canais: Annotated[list[str], Form()] = [],
):
    canais_validos = [ch for ch in canais if ch in ("whatsapp", "email", "sms")]
    try:
        with engine.begin() as c:
            c.execute(text("""
                INSERT INTO agendamentos_destinatarios (agendamento_id, usuario_id, canais)
                VALUES (:ag_id, :uid, CAST(:canais AS jsonb))
                ON CONFLICT (agendamento_id, usuario_id) DO UPDATE SET canais=CAST(:canais AS jsonb)
            """), {"ag_id": agendamento_id, "uid": usuario_id, "canais": json.dumps(canais_validos)})
    except Exception as e:
        logger.error(f"Erro ao adicionar destinatário agendamento: {e}")
    return templates.TemplateResponse(request, "admin/agendamentos_destinatarios.html",
                                      _ag_dest_ctx(agendamento_id))


@router.delete("/agendamentos_destinatarios/{agendamento_id}/{usuario_id}", response_class=HTMLResponse)
def admin_agendamentos_dest_rm(request: Request, agendamento_id: int, usuario_id: int):
    with engine.begin() as c:
        c.execute(text("""
            DELETE FROM agendamentos_destinatarios
            WHERE agendamento_id=:ag_id AND usuario_id=:uid
        """), {"ag_id": agendamento_id, "uid": usuario_id})
    return templates.TemplateResponse(request, "admin/agendamentos_destinatarios.html",
                                      _ag_dest_ctx(agendamento_id))
