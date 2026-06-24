"""Sincronização de usuários com Active Directory via LDAP."""

import json
import logging
from dataclasses import dataclass, field

from ldap3 import SUBTREE, Connection, Server
from sqlalchemy import text

from app.bd import engine
from config import configuracoes

logger = logging.getLogger(__name__)

_ATRIBUTOS = [
    "sAMAccountName",
    "displayName",
    "mail",
    "telephoneNumber",
    "mobile",
    "department",
    "title",
    "objectGUID",
]

# Filtra user accounts habilitados — exclui computadores, grupos e contas desabilitadas
_FILTRO = (
    "(&(objectClass=user)"
    "(sAMAccountType=805306368)"
    "(!(userAccountControl:1.2.840.113556.1.4.803:=2)))"
)

_SQL_UPSERT = text("""
    INSERT INTO usuarios (
        identificador, origem, nome, email, telefone,
        departamento, cargo, metadados, ultimo_sync
    ) VALUES (
        :ident, 'ad_sync', :nome, :email, :telefone,
        :departamento, :cargo, CAST(:metadados AS jsonb), NOW()
    )
    ON CONFLICT (identificador) DO UPDATE SET
        nome          = EXCLUDED.nome,
        email         = EXCLUDED.email,
        telefone      = EXCLUDED.telefone,
        departamento  = EXCLUDED.departamento,
        cargo         = EXCLUDED.cargo,
        metadados     = EXCLUDED.metadados,
        ultimo_sync   = NOW(),
        ativo         = TRUE,
        atualizado_em = NOW()
    RETURNING (xmax = 0) AS inserido
""")


@dataclass
class ResultadoSync:
    total_ad: int = 0
    criados: int = 0
    atualizados: int = 0
    desativados: int = 0
    erros: list[str] = field(default_factory=list)


def _attr(entrada, nome: str) -> str | None:
    if nome not in entrada:
        return None
    val = entrada[nome].value
    if val is None:
        return None
    return str(val[0] if isinstance(val, list) else val) or None


def _guid_hex(entrada) -> str | None:
    try:
        raw = entrada["objectGUID"].raw_values
        return raw[0].hex() if raw else None
    except Exception:
        return None


def _conectar() -> Connection:
    if not configuracoes.ad_servidor:
        raise ValueError("AD_SERVIDOR não configurado")
    if not configuracoes.ad_bind_user or not configuracoes.ad_bind_password:
        raise ValueError("AD_BIND_USER / AD_BIND_PASSWORD não configurados")

    servidor = Server(
        configuracoes.ad_servidor,
        port=configuracoes.ad_porta,
        use_ssl=configuracoes.ad_usar_tls,
        get_info="ALL",
    )
    return Connection(
        servidor,
        user=configuracoes.ad_bind_user,
        password=configuracoes.ad_bind_password,
        auto_bind=True,
    )


def sincronizar_ad(ou: str | None = None) -> ResultadoSync:
    resultado = ResultadoSync()

    base = ou or configuracoes.ad_ou
    if not base:
        raise ValueError("OU não definida (AD_OU no .env ou parâmetro 'ou')")

    conn = _conectar()
    try:
        conn.search(
            search_base=base,
            search_filter=_FILTRO,
            search_scope=SUBTREE,
            attributes=_ATRIBUTOS,
        )
        entradas = list(conn.entries)
    finally:
        conn.unbind()

    resultado.total_ad = len(entradas)
    sincronizados: set[str] = set()

    with engine.begin() as c:
        for entrada in entradas:
            sam = _attr(entrada, "sAMAccountName")
            if not sam:
                continue

            guid = _guid_hex(entrada)
            metadados = json.dumps({"objectGUID": guid} if guid else {})

            try:
                row = c.execute(
                    _SQL_UPSERT,
                    {
                        "ident": sam,
                        "nome": _attr(entrada, "displayName") or sam,
                        "email": _attr(entrada, "mail"),
                        "telefone": _attr(entrada, "telephoneNumber") or _attr(entrada, "mobile"),
                        "departamento": _attr(entrada, "department"),
                        "cargo": _attr(entrada, "title"),
                        "metadados": metadados,
                    },
                )
                if row.scalar():
                    resultado.criados += 1
                else:
                    resultado.atualizados += 1
                sincronizados.add(sam)
            except Exception as e:
                logger.warning("Erro ao sincronizar %s: %s", sam, e)
                resultado.erros.append(f"{sam}: {e}")

        if sincronizados:
            placeholders = ", ".join(f":sid_{i}" for i in range(len(sincronizados)))
            ids_params = {f"sid_{i}": v for i, v in enumerate(sincronizados)}
            r = c.execute(
                text(f"""
                    UPDATE usuarios SET ativo = FALSE, atualizado_em = NOW()
                    WHERE origem = 'ad_sync' AND ativo = TRUE
                    AND identificador NOT IN ({placeholders})
                """),
                ids_params,
            )
            resultado.desativados = r.rowcount

    return resultado
