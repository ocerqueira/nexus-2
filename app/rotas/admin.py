"""
Interface admin HTML — Tailwind CSS (CDN) + HTMX + Jinja2 templates.
Não aparece no Swagger (include_in_schema=False).
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text

from app.alertas.conexoes_inativas.processador import ProcessadorConexoesInativas
from app.alertas.item_comprimento_excedente.processador import ProcessadorItemComprimentoExcedente
from app.bd import engine
from app.core.calculadora_agenda import calcular_proximo_envio
from app.core.criptografia import criptografar
from app.core.gerenciador_conexoes import gerenciador_conexoes
from app.core.orquestrador_alertas import orquestrar_alerta
from app.core.sincronizador import sincronizar_filesystem_com_banco
from app.core.sincronizador_ad import sincronizar_ad
from app.relatorios.dashboard_conexoes.processador import ProcessadorDashboardConexoes
from app.relatorios.desempenho_vendas.processador import ProcessadorDesempenhoVendas
from app.relatorios.itens_comprimento_por_carga.processador import ProcessadorItensComprimentoPorCarga
from app.relatorios.pedidos_por_vendedor.processador import ProcessadorPedidosPorVendedor
from app.relatorios.teste_conexoes.processador import ProcessadorTesteConexoes

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", include_in_schema=False)

templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

_POR_PAGINA = 20
_HIST_POR_PAGINA = 25
_PERM_USUARIOS_POR_PAGINA = 10

# =============================================================================
# Badge helper (apenas para respostas inline mínimas)
# =============================================================================

def _badge(texto: str, cor: str) -> str:
    paleta = {
        "green":  "bg-green-100 text-green-700",
        "gray":   "bg-slate-100 text-slate-500",
        "orange": "bg-orange-100 text-orange-700",
        "blue":   "bg-blue-100 text-blue-700",
        "red":    "bg-red-100 text-red-600",
    }
    cls = paleta.get(cor, paleta["gray"])
    return f'<span class="inline-flex px-2 py-0.5 rounded-full text-xs font-medium {cls}">{texto}</span>'


# =============================================================================
# DB helpers
# =============================================================================

def _usuarios_lista() -> list[dict]:
    with engine.connect() as c:
        rows = c.execute(text(
            "SELECT id, nome, identificador FROM usuarios WHERE ativo=TRUE ORDER BY nome"
        )).mappings().all()
    return [dict(r) for r in rows]


def _recursos_lista(tipo: str) -> list[dict]:
    with engine.connect() as c:
        if tipo == "relatorio":
            rows = c.execute(text(
                "SELECT id, titulo FROM relatorios WHERE status='ativo' ORDER BY titulo"
            )).mappings().all()
        else:
            rows = c.execute(text(
                "SELECT id, titulo FROM alertas WHERE status='ativo' ORDER BY titulo"
            )).mappings().all()
    return [dict(r) for r in rows]


def _parse_horarios(horarios_str: str) -> list[dict]:
    result = []
    for h in horarios_str.split(","):
        h = h.strip()
        if ":" in h:
            partes = h.split(":", 1)
            try:
                result.append({"hora": int(partes[0]), "minuto": int(partes[1])})
            except ValueError:
                pass
    return result


def _fmt_dt(dt) -> str:
    if not dt:
        return "—"
    return dt.strftime("%d/%m/%y %H:%M")


def _fmt_date(dt) -> str:
    if not dt:
        return "—"
    return dt.strftime("%d/%m/%Y")


# =============================================================================
# GET /admin — shell page
# =============================================================================

@router.get("", response_class=HTMLResponse)
def admin_index(request: Request):
    return templates.TemplateResponse(request, "admin/base.html", {})


# =============================================================================
# HTMX: opções de recurso dinâmicas
# =============================================================================

@router.get("/recursos", response_class=HTMLResponse)
def admin_recursos(tipo_recurso: str = Query("relatorio")):
    rows = _recursos_lista(tipo_recurso)
    return "".join(f'<option value="{r["id"]}">{r["titulo"]}</option>' for r in rows)


# =============================================================================
# DASHBOARD
# =============================================================================

@router.get("/dashboard", response_class=HTMLResponse)
def admin_dashboard(request: Request):
    with engine.connect() as c:
        n_rel = c.execute(text("SELECT COUNT(*) FROM relatorios WHERE status='ativo'")).scalar() or 0
        n_ale = c.execute(text("SELECT COUNT(*) FROM alertas WHERE status='ativo'")).scalar() or 0
        n_usr = c.execute(text("SELECT COUNT(*) FROM usuarios WHERE ativo=TRUE")).scalar() or 0
        n_age = c.execute(text("SELECT COUNT(*) FROM agendamentos WHERE ativo=TRUE")).scalar() or 0
        rows = c.execute(text("""
            SELECT h.tipo_recurso, h.recurso_nome, h.status, h.mensagem_erro, h.criado_em,
                   u.nome AS usuario_nome
            FROM historico h LEFT JOIN usuarios u ON u.id = h.usuario_id
            ORDER BY h.criado_em DESC LIMIT 15
        """)).mappings().all()

    hist = []
    for h in rows:
        d = dict(h)
        d["criado_em_fmt"] = _fmt_dt(d["criado_em"])
        err = str(d.get("mensagem_erro") or "")
        d["erro_resumo"] = (err[:70] + "…") if err else ""
        hist.append(d)

    return templates.TemplateResponse(request, "admin/dashboard.html", {
        "n_rel": n_rel, "n_ale": n_ale, "n_usr": n_usr, "n_age": n_age,
        "hist": hist,
    })


# =============================================================================
# RELATÓRIOS
# =============================================================================

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


PROCESSADORES_RELATORIO = {
    "dashboard_conexoes": {"classe": ProcessadorDashboardConexoes},
    "teste_conexoes": {"classe": ProcessadorTesteConexoes},
    "desempenho_vendas": {"classe": ProcessadorDesempenhoVendas},
    "pedidos_por_vendedor": {"classe": ProcessadorPedidosPorVendedor},
    "itens_comprimento_por_carga": {"classe": ProcessadorItensComprimentoPorCarga},
}

PROCESSADORES_ALERTA = {
    "conexoes_inativas": ProcessadorConexoesInativas,
    "item_comprimento_excedente": ProcessadorItemComprimentoExcedente,
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
    info = PROCESSADORES_RELATORIO.get(nome)
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


# =============================================================================
# ALERTAS
# =============================================================================

def _alertas_db(status_filtro: str = "") -> tuple[list[dict], int]:
    params: dict = {}
    filtro_sql = ""
    if status_filtro:
        filtro_sql = "WHERE a.status = :sf"
        params["sf"] = status_filtro
    with engine.connect() as c:
        rows = c.execute(text(f"""
            SELECT a.id, a.nome, a.titulo, a.severidade, a.status, a.ultimo_sync,
                   COUNT(ac.id) FILTER (WHERE ac.ativo) AS condicoes_ativas
            FROM alertas a
            LEFT JOIN alertas_condicoes ac ON ac.alerta_id = a.id
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
    classe = PROCESSADORES_ALERTA.get(nome)
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


# =============================================================================
# ALERTAS — CONDIÇÕES (drawer)
# =============================================================================

def _cond_ctx(alerta_id: int) -> dict:
    with engine.connect() as c:
        conds_raw = c.execute(text("""
            SELECT id, nome, cooldown_minutos, canais, destinatarios,
                   ativo, ultimo_disparo
            FROM alertas_condicoes WHERE alerta_id = :id ORDER BY nome
        """), {"id": alerta_id}).mappings().all()
        usuarios = [dict(r) for r in c.execute(text(
            "SELECT id, nome FROM usuarios WHERE ativo=TRUE ORDER BY nome"
        )).mappings().all()]

    conds = []
    for cd in conds_raw:
        d = dict(cd)
        d["ultimo_disparo_fmt"] = _fmt_dt(d["ultimo_disparo"])
        dests_raw = d.get("destinatarios") or []
        if not isinstance(dests_raw, list):
            dests_raw = []
        umap = {u["id"]: u["nome"] for u in usuarios}
        d["destinatarios_info"] = [
            {"usuario_id": x["usuario_id"], "nome": umap.get(x["usuario_id"], "?")}
            for x in dests_raw if x.get("usuario_id")
        ]
        conds.append(d)

    return {"conds": conds, "usuarios": usuarios, "alerta_id": alerta_id}


@router.get("/alertas/{alerta_id}/condicoes", response_class=HTMLResponse)
def admin_alertas_condicoes(request: Request, alerta_id: int):
    return templates.TemplateResponse(request, "admin/alertas_condicoes.html",
                                      _cond_ctx(alerta_id))


@router.post("/condicoes/{condicao_id}/toggle", response_class=HTMLResponse)
def admin_condicao_toggle(request: Request, condicao_id: int):
    with engine.begin() as c:
        row = c.execute(text("SELECT alerta_id, ativo FROM alertas_condicoes WHERE id=:id"),
                        {"id": condicao_id}).mappings().first()
        if not row:
            return HTMLResponse("—")
        c.execute(text("UPDATE alertas_condicoes SET ativo=:v, atualizado_em=NOW() WHERE id=:id"),
                  {"v": not row["ativo"], "id": condicao_id})
        alerta_id = row["alerta_id"]
    return templates.TemplateResponse(request, "admin/alertas_condicoes.html",
                                      _cond_ctx(alerta_id))


@router.post("/condicoes/{condicao_id}/cooldown", response_class=HTMLResponse)
def admin_condicao_cooldown(request: Request, condicao_id: int, cooldown: Annotated[int, Form()]):
    with engine.begin() as c:
        c.execute(text("UPDATE alertas_condicoes SET cooldown_minutos=:v, atualizado_em=NOW() WHERE id=:id"),
                  {"v": cooldown, "id": condicao_id})
    return templates.TemplateResponse(request, "admin/condicao_cooldown.html",
                                      {"condicao_id": condicao_id, "cooldown": cooldown})


def _dest_ctx(condicao_id: int) -> dict:
    with engine.connect() as c:
        row = c.execute(text("SELECT destinatarios FROM alertas_condicoes WHERE id=:id"),
                        {"id": condicao_id}).mappings().first()
        usuarios = [dict(r) for r in c.execute(text(
            "SELECT id, nome FROM usuarios WHERE ativo=TRUE ORDER BY nome"
        )).mappings().all()]
    dests_raw = (row["destinatarios"] if row and isinstance(row["destinatarios"], list) else [])
    umap = {u["id"]: u["nome"] for u in usuarios}
    destinatarios = [
        {"usuario_id": d["usuario_id"], "nome": umap.get(d["usuario_id"], "?")}
        for d in dests_raw if d.get("usuario_id")
    ]
    return {"condicao_id": condicao_id, "destinatarios": destinatarios, "usuarios": usuarios}


@router.post("/condicoes/{condicao_id}/destinatarios", response_class=HTMLResponse)
def admin_condicao_add_dest(request: Request, condicao_id: int, usuario_id: Annotated[int, Form()]):
    with engine.begin() as c:
        row = c.execute(text("SELECT destinatarios FROM alertas_condicoes WHERE id=:id"),
                        {"id": condicao_id}).mappings().first()
        if not row:
            return HTMLResponse("—")
        dests = row["destinatarios"] if isinstance(row["destinatarios"], list) else []
        if not any(d.get("usuario_id") == usuario_id for d in dests):
            dests.append({"usuario_id": usuario_id})
            c.execute(text("UPDATE alertas_condicoes SET destinatarios=CAST(:d AS jsonb), atualizado_em=NOW() WHERE id=:id"),
                      {"d": json.dumps(dests), "id": condicao_id})
    return templates.TemplateResponse(request, "admin/dest_div.html", _dest_ctx(condicao_id))


@router.delete("/condicoes/{condicao_id}/destinatarios/{usuario_id}", response_class=HTMLResponse)
def admin_condicao_rm_dest(request: Request, condicao_id: int, usuario_id: int):
    with engine.begin() as c:
        row = c.execute(text("SELECT destinatarios FROM alertas_condicoes WHERE id=:id"),
                        {"id": condicao_id}).mappings().first()
        if not row:
            return HTMLResponse("—")
        dests = [d for d in (row["destinatarios"] or []) if d.get("usuario_id") != usuario_id]
        c.execute(text("UPDATE alertas_condicoes SET destinatarios=CAST(:d AS jsonb), atualizado_em=NOW() WHERE id=:id"),
                  {"d": json.dumps(dests), "id": condicao_id})
    return templates.TemplateResponse(request, "admin/dest_div.html", _dest_ctx(condicao_id))


# =============================================================================
# CONEXÕES
# =============================================================================

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


# =============================================================================
# USUÁRIOS
# =============================================================================

_SQL_USUARIO = text("""
    SELECT id, nome, identificador, origem, email, whatsapp_numero, departamento, cargo, ativo
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
):
    with engine.begin() as c:
        c.execute(text("UPDATE usuarios SET whatsapp_numero=:wpp, email=:email, atualizado_em=NOW() WHERE id=:id"),
                  {"wpp": whatsapp_numero or None, "email": email or None, "id": usuario_id})
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
):
    try:
        with engine.begin() as c:
            c.execute(text("""
                INSERT INTO usuarios (identificador, nome, origem, whatsapp_numero, email, departamento, cargo)
                VALUES (:ident, :nome, 'manual', :wpp, :email, :depto, :cargo)
            """), {"ident": identificador, "nome": nome, "wpp": whatsapp_numero or None,
                   "email": email or None, "depto": departamento or None, "cargo": cargo or None})
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


# =============================================================================
# AGENDAMENTOS
# =============================================================================

_AG_USUARIOS_POR_PAGINA = 10


def _agendamentos_db(busca: str = "", tipo_filtro: str = "",
                     freq_filtro: str = "", status_filtro: str = "",
                     pagina: int = 1) -> tuple[list[dict], int]:
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

    # Agrupar por usuário em Python
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
        d["proximo_envio_fmt"] = _fmt_dt(d.get("proximo_envio"))
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


# =============================================================================
# PERMISSÕES
# =============================================================================

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
        d["criado_em_fmt"] = _fmt_date(d["criado_em"])
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


# =============================================================================
# HISTÓRICO
# =============================================================================

def _historico_db(tipo: str = "", status: str = "", busca: str = "",
                  periodo: str = "", pagina: int = 1) -> tuple[list[dict], int]:
    filtros = ["1=1"]
    params: dict = {"lim": _HIST_POR_PAGINA, "off": (pagina - 1) * _HIST_POR_PAGINA}
    if tipo:
        filtros.append("h.tipo_recurso = :tipo")
        params["tipo"] = tipo
    if status:
        filtros.append("h.status = :status")
        params["status"] = status
    if busca:
        filtros.append("h.recurso_nome ILIKE :busca")
        params["busca"] = f"%{busca}%"
    if periodo == "hoje":
        filtros.append("h.criado_em >= CURRENT_DATE")
    elif periodo == "semana":
        filtros.append("h.criado_em >= NOW() - INTERVAL '7 days'")
    elif periodo == "mes":
        filtros.append("h.criado_em >= NOW() - INTERVAL '30 days'")
    where = " AND ".join(filtros)
    with engine.connect() as c:
        total = c.execute(text(f"SELECT COUNT(*) FROM historico h WHERE {where}"), params).scalar() or 0
        rows = c.execute(text(f"""
            SELECT h.id, h.tipo_recurso, h.recurso_nome, h.tipo_solicitacao,
                   h.status, h.mensagem_erro, h.parametros, h.tamanho_arquivo,
                   h.hash_arquivo, h.enviado_para, h.criado_em, u.nome AS usuario_nome
            FROM historico h LEFT JOIN usuarios u ON u.id = h.usuario_id
            WHERE {where} ORDER BY h.criado_em DESC LIMIT :lim OFFSET :off
        """), params).mappings().all()
    result = []
    for r in rows:
        d = dict(r)
        d["criado_em_fmt"] = _fmt_dt(d["criado_em"])
        d["criado_em_date"] = d["criado_em"].strftime("%d/%m/%Y") if d.get("criado_em") else "—"
        err = str(d.get("mensagem_erro") or "")
        d["erro_resumo"] = (err[:80] + "…") if err else ""
        result.append(d)
    return result, total


@router.get("/historico", response_class=HTMLResponse)
def admin_historico(request: Request,
                    tipo: str = Query(""),
                    status: str = Query(""),
                    busca: str = Query(""),
                    periodo: str = Query(""),
                    pagina: int = Query(1, ge=1)):
    registros, total = _historico_db(tipo, status, busca, periodo, pagina)
    return templates.TemplateResponse(request, "admin/historico.html", {
        "registros": registros, "total": total,
        "tipo": tipo, "status": status, "busca": busca, "periodo": periodo,
        "pagina": pagina, "total_paginas": max(1, -(-total // _HIST_POR_PAGINA)),
        "msg": "", "msg_tipo": "",
    })


@router.get("/historico/{registro_id}/detalhe", response_class=HTMLResponse)
def admin_historico_detalhe(request: Request, registro_id: int):
    with engine.connect() as c:
        row = c.execute(text("""
            SELECT h.*, u.nome AS usuario_nome
            FROM historico h LEFT JOIN usuarios u ON u.id = h.usuario_id
            WHERE h.id = :id
        """), {"id": registro_id}).mappings().first()
    if not row:
        return HTMLResponse("")
    h = dict(row)
    h["criado_em_fmt"] = _fmt_dt(h.get("criado_em"))
    try:
        h["parametros_fmt"] = json.dumps(h["parametros"], ensure_ascii=False, indent=2) if h.get("parametros") else ""
    except Exception:
        h["parametros_fmt"] = str(h.get("parametros", ""))
    return templates.TemplateResponse(request, "admin/historico_detalhe.html", {"h": h})


# =============================================================================
# CONFIGURAÇÕES INTERNAS (key-value)
# =============================================================================

def _init_config_table() -> None:
    try:
        with engine.begin() as c:
            c.execute(text("""
                CREATE TABLE IF NOT EXISTS configuracoes (
                    chave TEXT PRIMARY KEY,
                    valor TEXT,
                    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """))
    except Exception as e:
        logger.warning(f"Não foi possível criar tabela configuracoes: {e}")


_init_config_table()


def _cfg(chave: str) -> str:
    try:
        with engine.connect() as c:
            row = c.execute(text("SELECT valor FROM configuracoes WHERE chave=:k"), {"k": chave}).first()
        return (row[0] or "") if row else ""
    except Exception:
        return ""


def _cfg_set(chave: str, valor: str | None) -> None:
    with engine.begin() as c:
        c.execute(text("""
            INSERT INTO configuracoes (chave, valor, atualizado_em)
            VALUES (:k, :v, NOW())
            ON CONFLICT (chave) DO UPDATE SET valor = EXCLUDED.valor, atualizado_em = NOW()
        """), {"k": chave, "v": valor or None})


# =============================================================================
# TESTES
# =============================================================================

def _testes_ctx(msg: str = "", msg_tipo: str = "") -> dict:
    return {
        "modo_teste": _cfg("modo_teste") == "true",
        "test_email": _cfg("test_email"),
        "test_whatsapp": _cfg("test_whatsapp"),
        "msg": msg, "msg_tipo": msg_tipo,
    }


@router.get("/testes/status")
def admin_testes_status():
    return {"ativo": _cfg("modo_teste") == "true"}


@router.get("/testes", response_class=HTMLResponse)
def admin_testes(request: Request):
    return templates.TemplateResponse(request, "admin/testes.html", _testes_ctx())


@router.post("/testes/config", response_class=HTMLResponse)
def admin_testes_config(
    request: Request,
    test_email: Annotated[str | None, Form()] = None,
    test_whatsapp: Annotated[str | None, Form()] = None,
    modo_teste: Annotated[str | None, Form()] = None,
):
    _cfg_set("test_email", test_email)
    _cfg_set("test_whatsapp", test_whatsapp)
    _cfg_set("modo_teste", "true" if modo_teste == "true" else "false")
    ativo = modo_teste == "true"
    msg = "Modo Teste ATIVADO — todas as notificações irão para o contato de teste." if ativo else "Modo Teste desativado."
    return templates.TemplateResponse(request, "admin/testes.html",
                                      _testes_ctx(msg=msg, msg_tipo="ok" if not ativo else "aviso"))


# =============================================================================
# AD SYNC
# =============================================================================

@router.post("/ad/sincronizar", response_class=HTMLResponse)
def admin_ad_sincronizar():
    try:
        r = sincronizar_ad()
        msg = f"AD: +{r.criados} criados, ~{r.atualizados} atualizados, -{r.desativados} desativados ({r.total_ad} no AD)"
        return HTMLResponse(_badge(msg, "green"))
    except Exception as e:
        return HTMLResponse(_badge(f"Erro AD: {e}", "red"))


# =============================================================================
# SINCRONIZAR FILESYSTEM
# =============================================================================

@router.post("/sincronizar", response_class=HTMLResponse)
def admin_sincronizar():
    try:
        r = sincronizar_filesystem_com_banco()
        rel = r["relatorios"]
        alt = r["alertas"]
        msg = (
            f"Relatórios: +{rel['inseridos']} novos, ~{rel['atualizados']} atualizados, "
            f"-{rel['removidos']} removidos | "
            f"Alertas: +{alt['inseridos']} novos, ~{alt['atualizados']} atualizados, "
            f"-{alt['removidos']} removidos"
        )
        return HTMLResponse(_badge(msg, "green"))
    except Exception as e:
        return HTMLResponse(_badge(f"Erro: {e}", "red"))
