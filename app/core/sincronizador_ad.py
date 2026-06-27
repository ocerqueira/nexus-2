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


def _ler_atributo_ldap(entrada_ldap, nome_atributo: str) -> str | None:
    """
    Lê um atributo de uma entrada LDAP (objeto ldap3).
    Atributos podem retornar lista ou valor único dependendo do schema do AD;
    sempre retornamos o primeiro elemento como string.
    """
    if nome_atributo not in entrada_ldap:
        return None
    val = entrada_ldap[nome_atributo].value
    if val is None:
        return None
    return str(val[0] if isinstance(val, list) else val) or None


def _guid_hex(entrada) -> str | None:
    """
    Converte o objectGUID (bytes brutos do AD) para string hexadecimal.
    Usado como chave estável de identificação — o sAMAccountName pode mudar,
    o GUID não.
    """
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
    """
    Sincroniza usuários do Active Directory com a tabela 'usuarios'.

    Estratégia:
      - UPSERT por 'identificador' (sAMAccountName): cria novos, atualiza existentes.
      - Soft-delete: usuários presentes no banco mas ausentes do AD são marcados ativo=FALSE.
      - Apenas contas habilitadas são sincronizadas (filtro LDAP exclui desabilitadas).

    Args:
        ou: Organizational Unit LDAP (ex: "OU=Usuarios,DC=empresa,DC=com").
            Se None, usa AD_OU do .env.
    """
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
            sam = _ler_atributo_ldap(entrada, "sAMAccountName")
            if not sam:
                continue

            guid = _guid_hex(entrada)
            metadados = json.dumps({"objectGUID": guid} if guid else {})

            try:
                row = c.execute(
                    _SQL_UPSERT,
                    {
                        "ident": sam,
                        "nome": _ler_atributo_ldap(entrada, "displayName") or sam,
                        "email": _ler_atributo_ldap(entrada, "mail"),
                        "telefone": _ler_atributo_ldap(entrada, "telephoneNumber") or _ler_atributo_ldap(entrada, "mobile"),
                        "departamento": _ler_atributo_ldap(entrada, "department"),
                        "cargo": _ler_atributo_ldap(entrada, "title"),
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
