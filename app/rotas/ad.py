"""Endpoints de sincronização com Active Directory."""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.sincronizador_ad import sincronizar_ad

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ad", tags=["Active Directory"])


class SincronizarBody(BaseModel):
    """
    Parâmetros opcionais para o sync AD.

    - **ou**: override da OU configurada no .env — útil para testar ou sincronizar
      uma unidade específica sem alterar a configuração global.
      Ex: `"OU=TI,DC=empresa,DC=com"`
    """

    ou: str | None = None


@router.post("/sincronizar")
def sincronizar(body: SincronizarBody | None = None) -> dict:
    """
    Sincroniza usuários do Active Directory com o Nexus.

    - Cria usuários novos (`origem='ad_sync'`)
    - Atualiza nome, email, telefone, departamento, cargo e objectGUID
    - Desativa (`ativo=false`) usuários AD que sumiram da OU ou foram desabilitados
    - Registra `ultimo_sync` em todos os usuários processados
    """
    ou = body.ou if body else None
    try:
        resultado = sincronizar_ad(ou=ou)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Erro no sync AD: %s", e)
        raise HTTPException(status_code=500, detail=f"Erro LDAP: {e}")

    return {
        "status": "ok",
        "total_ad": resultado.total_ad,
        "criados": resultado.criados,
        "atualizados": resultado.atualizados,
        "desativados": resultado.desativados,
        "erros": resultado.erros,
    }
