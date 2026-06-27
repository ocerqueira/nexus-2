from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from ._base import engine, logger, templates, text, _badge, sincronizar_ad, sincronizar_filesystem_com_banco

router = APIRouter()


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


@router.post("/ad/sincronizar", response_class=HTMLResponse)
def admin_ad_sincronizar():
    try:
        r = sincronizar_ad()
        msg = f"AD: +{r.criados} criados, ~{r.atualizados} atualizados, -{r.desativados} desativados ({r.total_ad} no AD)"
        return HTMLResponse(_badge(msg, "green"))
    except Exception as e:
        return HTMLResponse(_badge(f"Erro AD: {e}", "red"))


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
