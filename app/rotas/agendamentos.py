"""
Rotas de gerenciamento de agendamentos.
CRUD + endpoints de consulta para o N8N.
"""

import json
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.bd import engine
from app.core.calculadora_agenda import calcular_proximo_envio

_UTC = ZoneInfo("UTC")

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agendamentos", tags=["agendamentos"])


# =============================================================================
# Schemas Pydantic
# =============================================================================


class Horario(BaseModel):
    """Horário de envio (hora + minuto no formato 24h)."""

    hora: int = Field(..., ge=0, le=23, description="Hora no formato 24h (0-23)", examples=[8])
    minuto: int = Field(0, ge=0, le=59, description="Minuto (0-59)", examples=[0])

    model_config = {
        "json_schema_extra": {"example": {"hora": 8, "minuto": 0}}
    }


class CriarAgendamento(BaseModel):
    """
    Agendamento de relatório ou alerta para envio automático.

    - **usuario_id**: ID do usuário dono do agendamento (obtido em `GET /usuarios`)
    - **tipo_recurso**: `relatorio` ou `alerta`
    - **recurso_id**: ID do relatório/alerta (obtido em `GET /relatorios` ou `GET /alertas`)
    - **frequencia**: `diaria`, `semanal` ou `mensal`
    - **dia_semana**: obrigatório se `frequencia=semanal` — 1=segunda ... 7=domingo
    - **dia_mes**: obrigatório se `frequencia=mensal` — dia do mês (1-31)
    - **horarios**: lista de horários de envio no dia (pode ter mais de um)
    - **apenas_dias_uteis**: se `true`, pula sábado e domingo
    - **canais**: lista de canais de envio, ex: `["whatsapp"]`, `["email"]`, `["whatsapp", "email"]`
    - **parametros**: parâmetros extras para o relatório/alerta (pode ser `{}`)
    """

    usuario_id: int = Field(..., description="ID do usuário (GET /usuarios)")
    tipo_recurso: str = Field(
        ...,
        pattern="^(relatorio|alerta)$",
        description="Tipo do recurso: `relatorio` ou `alerta`",
    )
    recurso_id: int = Field(
        ...,
        description="ID do recurso — obtido em GET /relatorios ou GET /alertas",
    )
    frequencia: str = Field(
        ...,
        pattern="^(diaria|semanal|mensal|intervalo)$",
        description="`diaria` | `semanal` (requer dia_semana) | `mensal` (requer dia_mes) | `intervalo` (requer intervalo_minutos)",
    )
    dia_semana: int | None = Field(
        None,
        ge=1,
        le=7,
        description="Dia da semana para frequência semanal: 1=seg, 2=ter, 3=qua, 4=qui, 5=sex, 6=sab, 7=dom",
    )
    dia_mes: int | None = Field(
        None,
        ge=1,
        le=31,
        description="Dia do mês para frequência mensal (1-31)",
    )
    intervalo_minutos: int | None = Field(
        None,
        ge=1,
        description="Minutos entre execuções (apenas quando frequencia=intervalo). Ex: 10 = a cada 10 min",
    )
    horarios: list[Horario] = Field(
        default_factory=list,
        description="Lista de horários de envio no dia. Ex: [{hora:8, minuto:0}, {hora:18, minuto:0}]. Ignorado quando frequencia=intervalo.",
    )
    apenas_dias_uteis: bool = Field(
        False,
        description="Se true, pula sábados e domingos",
    )
    timezone: str = Field(
        "America/Sao_Paulo",
        description="Timezone IANA dos horários (ex: America/Sao_Paulo, America/Cuiaba). Horários são interpretados neste fuso.",
    )
    parametros: dict = Field(
        default_factory=dict,
        description="Parâmetros extras para o relatório/alerta. Use {} se não houver.",
    )
    canais: list[str] = Field(
        ...,
        description='Canais de envio: ["whatsapp"], ["email"] ou ["whatsapp", "email"]',
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "usuario_id": 1,
                "tipo_recurso": "alerta",
                "recurso_id": 2,
                "frequencia": "intervalo",
                "intervalo_minutos": 10,
                "canais": ["whatsapp"],
                "parametros": {},
            }
        }
    }


class AtualizarAgendamento(BaseModel):
    """Atualização parcial — envie apenas os campos que deseja alterar."""

    usuario_id: int | None = None
    tipo_recurso: str | None = Field(None, pattern="^(relatorio|alerta)$")
    recurso_id: int | None = None
    frequencia: str | None = Field(
        None,
        pattern="^(diaria|semanal|mensal|intervalo)$",
        description="`diaria` | `semanal` | `mensal` | `intervalo`",
    )
    dia_semana: int | None = Field(None, ge=1, le=7, description="1=seg ... 7=dom")
    dia_mes: int | None = Field(None, ge=1, le=31)
    intervalo_minutos: int | None = Field(None, ge=1, description="Minutos entre execuções (frequencia=intervalo)")
    horarios: list[Horario] | None = None
    apenas_dias_uteis: bool | None = None
    timezone: str | None = Field(None, description="Timezone IANA (ex: America/Cuiaba)")
    parametros: dict | None = None
    canais: list[str] | None = None
    ativo: bool | None = Field(None, description="false = desativa sem deletar")


# =============================================================================
# Helpers
# =============================================================================


def _horarios_para_jsonb(horarios: list[Horario]) -> list[dict]:
    """Converte lista de Horario para lista de dicts (formato JSONB)."""
    return [{"hora": h.hora, "minuto": h.minuto} for h in horarios]


def _linha_para_dict(linha) -> dict:
    """Converte resultado do SQLAlchemy para dict Python."""
    return dict(linha)


def _para_iso_local(dt: datetime | None, timezone_str: str) -> str | None:
    """Converte datetime UTC (aware ou naive) para ISO string no fuso local."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_UTC)
    return dt.astimezone(ZoneInfo(timezone_str)).isoformat()


def _converter_datetimes_para_local(ag: dict) -> dict:
    """Converte proximo_envio e ultimo_envio de UTC para o timezone do agendamento."""
    tz_str = ag.get("timezone") or "America/Sao_Paulo"
    for campo in ("proximo_envio", "ultimo_envio"):
        if ag.get(campo) is not None:
            ag[campo] = _para_iso_local(ag[campo], tz_str)
    return ag


def _validar_frequencia(dados: dict) -> None:
    """Valida constraints de frequência (semanal precisa de dia_semana, etc)."""
    if dados.get("frequencia") == "semanal" and not dados.get("dia_semana"):
        raise HTTPException(
            status_code=400,
            detail="Frequência 'semanal' exige o campo 'dia_semana' (1-7)",
        )
    if dados.get("frequencia") == "mensal" and not dados.get("dia_mes"):
        raise HTTPException(
            status_code=400,
            detail="Frequência 'mensal' exige o campo 'dia_mes' (1-31)",
        )
    if dados.get("frequencia") == "intervalo" and not dados.get("intervalo_minutos"):
        raise HTTPException(
            status_code=400,
            detail="Frequência 'intervalo' exige o campo 'intervalo_minutos' (>= 1)",
        )


# =============================================================================
# Endpoints
# =============================================================================


@router.get("/proximas-execucoes")
def listar_proximas_execucoes() -> dict:
    """
    **Endpoint para o n8n** — consultar a cada minuto via Cron.

    Retorna agendamentos ativos cujo `proximo_envio` já passou.
    Tolerância de 60 min: se atrasou mais que isso, recalcula o próximo envio e pula.

    Após processar cada item, chame `POST /agendamentos/{id}/marcar-executado`.
    """
    with engine.connect() as conexao:
        resultado = (
            conexao.execute(
                text("""
                    SELECT a.id, a.usuario_id, a.tipo_recurso, a.recurso_id,
                           a.frequencia, a.dia_semana, a.dia_mes, a.intervalo_minutos, a.horarios,
                           a.apenas_dias_uteis, a.timezone, a.parametros, a.canais,
                           a.ultimo_envio, a.proximo_envio,
                           COALESCE(r.nome, al.nome) AS recurso_nome,
                           u.nome AS usuario_nome,
                           u.whatsapp_numero AS usuario_whatsapp,
                           u.email AS usuario_email
                    FROM agendamentos a
                    LEFT JOIN relatorios r
                           ON a.tipo_recurso = 'relatorio' AND r.id = a.recurso_id
                    LEFT JOIN alertas al
                           ON a.tipo_recurso = 'alerta' AND al.id = a.recurso_id
                    LEFT JOIN usuarios u ON u.id = a.usuario_id
                    WHERE a.ativo = TRUE
                      AND a.proximo_envio IS NOT NULL
                    ORDER BY a.proximo_envio ASC
                """),
            )
            .mappings()
            .all()
        )

    agora = datetime.utcnow()
    tolerancia_60min = agora - timedelta(minutes=60)

    prontos = []
    for linha in resultado:
        ag = _linha_para_dict(linha)
        proximo = ag["proximo_envio"]

        # Normaliza para UTC naive (banco retorna com TZ=UTC)
        if proximo is not None and proximo.tzinfo is not None:
            proximo = proximo.replace(tzinfo=None)

        if proximo is None:
            continue

        if proximo <= agora:
            tz_str = ag.get("timezone") or "America/Sao_Paulo"
            # Se atrasou mais de 60 min, recalcula e pula
            if proximo < tolerancia_60min:
                logger.info(
                    f"Agendamento {ag['id']} atrasou >60min, recalculando..."
                )
                try:
                    novo_proximo = calcular_proximo_envio(ag, a_partir_de=agora)
                    with engine.begin() as conn:
                        conn.execute(
                            text("""
                                UPDATE agendamentos
                                SET proximo_envio = :proximo,
                                    atualizado_em = NOW()
                                WHERE id = :id
                            """),
                            {"proximo": novo_proximo, "id": ag["id"]},
                        )
                    ag["proximo_envio"] = _para_iso_local(novo_proximo, tz_str)
                except Exception as erro:
                    logger.error(
                        f"Erro ao recalcular agendamento {ag['id']}: {erro}"
                    )
                continue

            ag["proximo_envio"] = _para_iso_local(proximo, tz_str)
            ag["ultimo_envio"] = _para_iso_local(ag.get("ultimo_envio"), tz_str)

            prontos.append(ag)

    return {
        "total": len(prontos),
        "agendamentos": prontos,
    }


@router.get("")
def listar_agendamentos(
    tipo_recurso: str | None = Query(
        None, pattern="^(relatorio|alerta)$"
    ),
    apenas_ativos: bool = Query(True),
) -> dict:
    """Lista todos os agendamentos com filtros opcionais."""
    with engine.connect() as conexao:
        consulta = """
            SELECT id, usuario_id, tipo_recurso, recurso_id,
                   frequencia, dia_semana, dia_mes, intervalo_minutos, horarios,
                   apenas_dias_uteis, timezone, parametros, canais,
                   ativo, ultimo_envio, proximo_envio,
                   criado_em, atualizado_em
            FROM agendamentos
            WHERE 1=1
        """
        params = {}

        if apenas_ativos:
            consulta += " AND ativo = TRUE"
        if tipo_recurso:
            consulta += " AND tipo_recurso = :tipo"
            params["tipo"] = tipo_recurso

        consulta += " ORDER BY criado_em DESC"

        resultado = (
            conexao.execute(text(consulta), params).mappings().all()
        )

    return {
        "total": len(resultado),
        "agendamentos": [_converter_datetimes_para_local(_linha_para_dict(linha)) for linha in resultado],
    }


@router.post("", status_code=201)
def criar_agendamento(dados: CriarAgendamento) -> dict:
    """
    Cria agendamento de relatório ou alerta.

    **Passo a passo antes de criar:**
    1. `GET /relatorios` ou `GET /alertas` → anote o `id` do recurso desejado
    2. `GET /usuarios` → anote o `id` do usuário
    3. Preencha o body abaixo e submeta

    **Regras de frequência:**
    - `diaria` → não precisa de `dia_semana` nem `dia_mes`
    - `semanal` → obrigatório `dia_semana` (1=seg, 2=ter, 3=qua, 4=qui, 5=sex, 6=sab, 7=dom)
    - `mensal` → obrigatório `dia_mes` (1-31)

    O campo `proximo_envio` é calculado automaticamente.
    """
    # Converter para dict e validar
    ag = dados.model_dump()
    _validar_frequencia(ag)

    # Converter horarios para JSONB
    horarios_jsonb = _horarios_para_jsonb(dados.horarios)

    # Montar dict para a calculadora (inclui timezone)
    ag_para_calculo = {
        "frequencia": ag["frequencia"],
        "horarios": horarios_jsonb,
        "dia_semana": ag.get("dia_semana"),
        "dia_mes": ag.get("dia_mes"),
        "intervalo_minutos": ag.get("intervalo_minutos"),
        "apenas_dias_uteis": ag.get("apenas_dias_uteis", False),
        "timezone": ag.get("timezone", "America/Sao_Paulo"),
    }

    # Calcular próximo envio (retorna UTC naive)
    try:
        proximo = calcular_proximo_envio(ag_para_calculo)
    except (ValueError, KeyError) as erro:
        raise HTTPException(status_code=400, detail=str(erro))

    with engine.begin() as conexao:
        resultado = conexao.execute(
            text("""
                INSERT INTO agendamentos (
                    usuario_id, tipo_recurso, recurso_id,
                    frequencia, dia_semana, dia_mes, intervalo_minutos,
                    horarios, apenas_dias_uteis,
                    timezone, parametros, canais, proximo_envio
                ) VALUES (
                    :usuario_id, :tipo_recurso, :recurso_id,
                    :frequencia, :dia_semana, :dia_mes, :intervalo_minutos,
                    :horarios, :apenas_dias_uteis,
                    :timezone, :parametros, :canais, :proximo_envio
                )
                RETURNING id
            """),
            {
                "usuario_id": ag["usuario_id"],
                "tipo_recurso": ag["tipo_recurso"],
                "recurso_id": ag["recurso_id"],
                "frequencia": ag["frequencia"],
                "dia_semana": ag.get("dia_semana"),
                "dia_mes": ag.get("dia_mes"),
                "intervalo_minutos": ag.get("intervalo_minutos"),
                "horarios": json.dumps(horarios_jsonb),
                "apenas_dias_uteis": ag["apenas_dias_uteis"],
                "timezone": ag.get("timezone", "America/Sao_Paulo"),
                "parametros": json.dumps(ag["parametros"]),
                "canais": json.dumps(ag["canais"]),
                "proximo_envio": proximo,
            },
        )
        novo_id = resultado.scalar()

    logger.info(f"Agendamento {novo_id} criado: {ag['frequencia']} {ag['tipo_recurso']}")

    return {
        "status": "criado",
        "id": novo_id,
        "proximo_envio": _para_iso_local(proximo, ag.get("timezone", "America/Sao_Paulo")),
    }


@router.post("/{agendamento_id}/marcar-executado")
def marcar_executado(agendamento_id: int) -> dict:
    """
    Chamado pelo N8N após executar o agendamento.
    Atualiza ultimo_envio e recalcula proximo_envio.
    """
    agora = datetime.utcnow()

    with engine.connect() as conexao:
        # Buscar dados do agendamento
        linha = (
            conexao.execute(
                text("""
                    SELECT id, frequencia, horarios, dia_semana, dia_mes,
                           intervalo_minutos, apenas_dias_uteis, timezone
                    FROM agendamentos
                    WHERE id = :id AND ativo = TRUE
                """),
                {"id": agendamento_id},
            )
            .mappings()
            .first()
        )

        if not linha:
            raise HTTPException(
                status_code=404,
                detail=f"Agendamento {agendamento_id} não encontrado ou inativo",
            )

        ag = _linha_para_dict(linha)

    # Calcular próximo envio a partir de agora
    try:
        novo_proximo = calcular_proximo_envio(ag, a_partir_de=agora)
    except ValueError as erro:
        raise HTTPException(status_code=400, detail=str(erro))

    # Atualizar no banco
    with engine.begin() as conexao:
        conexao.execute(
            text("""
                UPDATE agendamentos
                SET ultimo_envio = :agora,
                    proximo_envio = :proximo,
                    atualizado_em = NOW()
                WHERE id = :id
            """),
            {
                "agora": agora,
                "proximo": novo_proximo,
                "id": agendamento_id,
            },
        )

    logger.info(
        f"Agendamento {agendamento_id} marcado como executado. "
        f"Próximo: {novo_proximo.isoformat()}"
    )

    tz_str = ag.get("timezone", "America/Sao_Paulo")
    return {
        "status": "executado",
        "id": agendamento_id,
        "ultimo_envio": _para_iso_local(agora, tz_str),
        "proximo_envio": _para_iso_local(novo_proximo, tz_str),
    }


@router.patch("/{agendamento_id}")
def atualizar_agendamento(
    agendamento_id: int, dados: AtualizarAgendamento
) -> dict:
    """
    Atualiza parcialmente um agendamento.
    Se campos que afetam o cálculo mudarem, recalcula proximo_envio.
    """
    atualizacoes = dados.model_dump(exclude_unset=True)

    if not atualizacoes:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    # Converter horarios se enviados
    if "horarios" in atualizacoes and atualizacoes["horarios"] is not None:
        atualizacoes["horarios"] = json.dumps(_horarios_para_jsonb(dados.horarios))
    if "parametros" in atualizacoes and atualizacoes["parametros"] is not None:
        atualizacoes["parametros"] = json.dumps(atualizacoes["parametros"])
    if "canais" in atualizacoes and atualizacoes["canais"] is not None:
        atualizacoes["canais"] = json.dumps(atualizacoes["canais"])

    # Verificar se precisa recalcular
    campos_que_afetam_calculo = {
        "frequencia",
        "horarios",
        "dia_semana",
        "dia_mes",
        "intervalo_minutos",
        "apenas_dias_uteis",
        "timezone",
    }
    precisa_recalcular = bool(
        campos_que_afetam_calculo & set(atualizacoes.keys())
    )

    if precisa_recalcular:
        # Buscar agendamento atual para mesclar com updates
        with engine.connect() as conexao:
            linha = (
                conexao.execute(
                    text("""
                        SELECT id, frequencia, horarios, dia_semana,
                               dia_mes, intervalo_minutos, apenas_dias_uteis, timezone
                        FROM agendamentos
                        WHERE id = :id
                    """),
                    {"id": agendamento_id},
                )
                .mappings()
                .first()
            )

        if not linha:
            raise HTTPException(
                status_code=404,
                detail=f"Agendamento {agendamento_id} não encontrado",
            )

        ag_atual = _linha_para_dict(linha)

        # Mesclar dados enviados com os atuais para cálculo
        ag_para_calculo = {**ag_atual, **atualizacoes}
        _validar_frequencia(ag_para_calculo)

        try:
            novo_proximo = calcular_proximo_envio(ag_para_calculo)
        except ValueError as erro:
            raise HTTPException(status_code=400, detail=str(erro))

        atualizacoes["proximo_envio"] = novo_proximo

    # Montar SET dinâmico
    set_clausulas = []
    params = {"id": agendamento_id}

    for campo, valor in atualizacoes.items():
        set_clausulas.append(f"{campo} = :{campo}")
        params[campo] = valor

    set_clausulas.append("atualizado_em = NOW()")
    sql = f"""
        UPDATE agendamentos
        SET {', '.join(set_clausulas)}
        WHERE id = :id
    """

    with engine.begin() as conexao:
        resultado = conexao.execute(text(sql), params)

    if resultado.rowcount == 0:
        raise HTTPException(
            status_code=404,
            detail=f"Agendamento {agendamento_id} não encontrado",
        )

    logger.info(f"Agendamento {agendamento_id} atualizado")

    resposta = {"status": "atualizado", "id": agendamento_id}
    if "proximo_envio" in atualizacoes:
        tz_str = atualizacoes.get("timezone") or ag_atual.get("timezone", "America/Sao_Paulo")
        resposta["proximo_envio"] = _para_iso_local(atualizacoes["proximo_envio"], tz_str)

    return resposta


@router.delete("/{agendamento_id}")
def desativar_agendamento(agendamento_id: int) -> dict:
    """
    Desativa um agendamento (soft delete).
    Não remove o registro, apenas marca ativo = FALSE.
    """
    with engine.begin() as conexao:
        resultado = conexao.execute(
            text("""
                UPDATE agendamentos
                SET ativo = FALSE, atualizado_em = NOW()
                WHERE id = :id AND ativo = TRUE
            """),
            {"id": agendamento_id},
        )

    if resultado.rowcount == 0:
        raise HTTPException(
            status_code=404,
            detail=f"Agendamento {agendamento_id} não encontrado ou já inativo",
        )

    logger.info(f"Agendamento {agendamento_id} desativado")

    return {"status": "desativado", "id": agendamento_id}
