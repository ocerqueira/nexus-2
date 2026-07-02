"""
Processador do alerta: _modelo_alerta
Fonte: ERP Firebird + PostgreSQL (nexus_metas)

Como usar:
  1. Copie esta pasta para app/alertas/nome_do_alerta/
  2. Renomeie a classe (precisa começar com 'Processador' — é assim que o
     sistema descobre; o contrato validar+verificar é conferido no startup)
  3. Ajuste as conexões (CONEXAO_ERP / CONEXAO_METAS)
  4. Adapte verificar() com a lógica real
  Veja LEIAME.md para cenários avançados e tudo que o orquestrador faz por você.
"""

import hashlib
import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from app.core.carregador_sql import carregar_query
from app.core.entregas_comum import normalizar_whatsapp
from app.core.gerenciador_conexoes import gerenciador_conexoes

logger = logging.getLogger(__name__)

ARQUIVO_CONSULTAS = Path(__file__).parent / "consultas.sql"
CONEXAO_ERP   = "REPLICA_TERRA"   # Firebird — ERP principal
CONEXAO_METAS = "nexus_metas"     # PostgreSQL — banco auxiliar


class ProcessadorModeloAlerta:
    """
    Detecta [descreva aqui].

    Padrão esperado pelo orquestrador:
      validar(parametros)  → tuple[bool, str]
      verificar(parametros) → dict[str, Any]
    """

    @staticmethod
    def validar(parametros: dict) -> tuple[bool, str]:
        """
        Valida parâmetros antes de executar qualquer query.
        Retorna (True, "") se OK; (False, "mensagem") se inválido.
        """
        # inteiro positivo
        if "cod_empresa" in parametros:
            cod = parametros["cod_empresa"]
            if not isinstance(cod, int) or cod < 1:
                return False, "Parâmetro 'cod_empresa' deve ser inteiro positivo"

        # data no formato YYYY-MM-DD
        if "data_inicio" in parametros and parametros["data_inicio"] is not None:
            try:
                datetime.strptime(str(parametros["data_inicio"]), "%Y-%m-%d")
            except ValueError:
                return False, "'data_inicio' deve estar no formato AAAA-MM-DD"

        # enum
        severidades_validas = {"baixo", "medio", "alto", "critico"}
        if "severidade_minima" in parametros:
            if parametros["severidade_minima"] not in severidades_validas:
                return False, f"'severidade_minima' deve ser um de: {sorted(severidades_validas)}"

        return True, ""

    @staticmethod
    def verificar(parametros: dict) -> dict[str, Any]:
        """
        Executa as queries, processa com pandas e retorna o payload completo.

        Chaves obrigatórias no retorno (o orquestrador depende delas):
          encontrou_dados  bool   — se há dados para disparar notificação
          total            int    — quantidade de registros encontrados
          resumo           str    — texto curto para logs e subject de email
          dados            list   — registros individuais (iteram nos templates;
                                    a dedup por cooldown é POR ITEM desta lista)

        Chaves opcionais consumidas pelo orquestrador:
          contatos_setores         list  — destinatários dinâmicos extraídos do ERP:
                                           [{"nome", "whatsapp", "email", "setor"}]
                                           Mesclados aos fixos, dedup por whatsapp.
          grupos_por_destinatario  list  — cada destinatário recebe SÓ os itens dele:
                                           [{"destinatario": {"nome","whatsapp","email"},
                                             "itens": [...]}]
          fingerprint              str   — auditoria (historico.hash_arquivo). A dedup
                                           real é por item: SHA-256 de cada linha de
                                           'dados', controlada pelo orquestrador.

        Chaves livres (viram variáveis nos templates Jinja):
          estatisticas             dict  — métricas agregadas para os cards
          estatisticas_por_grupo   list  — agregação por dimensão
          qualquer_outra           ...   — disponível como {{ qualquer_outra }}
        """
        # ── Parâmetros com defaults ────────────────────────────────────────
        cod_empresa     = parametros.get("cod_empresa", 1)
        data_inicio     = parametros.get("data_inicio") or (
            date.today() - timedelta(days=30)
        ).isoformat()
        severidade_min  = parametros.get("severidade_minima", "medio")

        # ── 1. Consulta principal: Firebird (ERP) ─────────────────────────
        linhas = gerenciador_conexoes.executar(
            conexao=CONEXAO_ERP,
            query=carregar_query(ARQUIVO_CONSULTAS, "detectar_anomalias"),
            parametros={"cod_empresa": cod_empresa, "data_inicio": data_inicio},
        )

        df = pd.DataFrame(linhas)

        if df.empty:
            return {
                "encontrou_dados": False,
                "total": 0,
                "resumo": f"Nenhuma anomalia detectada desde {data_inicio}",
                "dados": [],
                "estatisticas": {},
                "estatisticas_por_grupo": [],
                "contatos_setores": [],
            }

        # Firebird retorna colunas em UPPERCASE — normaliza para lowercase
        df.columns = [c.lower() for c in df.columns]

        # ── 2. Consulta auxiliar: PostgreSQL (com fallback) ───────────────
        # Use try/except quando o banco auxiliar for OPCIONAL.
        # Se for obrigatório, remova o try/except e deixe estourar.
        df_config = pd.DataFrame()
        try:
            linhas_config = gerenciador_conexoes.executar(
                conexao=CONEXAO_METAS,
                query=carregar_query(ARQUIVO_CONSULTAS, "buscar_configuracoes"),
                parametros={"cod_empresa": cod_empresa},
            )
            df_config = pd.DataFrame(linhas_config)
            if not df_config.empty:
                df_config.columns = [c.lower() for c in df_config.columns]
        except Exception:
            logger.warning("nexus_metas indisponível — alerta sem configurações de limite")

        # ── 3. Conversões de tipo ─────────────────────────────────────────
        # Firebird pode retornar Decimal, str ou None — to_numeric resolve tudo.
        for col in ["valor", "quantidade", "valor_unit"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

        # Datas como string formatada para os templates Jinja
        if "data" in df.columns:
            df["data"] = pd.to_datetime(df["data"], errors="coerce")
            df["data_fmt"] = df["data"].dt.strftime("%d/%m/%Y").fillna("N/D")
            df["data"] = df["data_fmt"]  # sobrescreve para simplificar template

        # ── 4. Join cross-database com pandas ────────────────────────────
        # Combina ERP (Firebird) com metas/config (PostgreSQL) por chave comum.
        if not df_config.empty and "cod_categoria" in df.columns and "cod_categoria" in df_config.columns:
            df = df.merge(
                df_config[["cod_categoria", "limite", "descricao_categoria"]],
                on="cod_categoria",
                how="left",
            )
            df["limite"] = pd.to_numeric(df["limite"], errors="coerce").fillna(0)
        else:
            df["limite"]              = 0
            df["descricao_categoria"] = ""

        # ── 5. Cálculos derivados ─────────────────────────────────────────
        if "valor" in df.columns and "limite" in df.columns:
            df["excedente"]     = (df["valor"] - df["limite"]).clip(lower=0).round(2)
            df["pct_excedente"] = (
                (df["excedente"] / df["limite"] * 100)
                .where(df["limite"] > 0, other=0)
                .round(1)
            )

        # Filtra por severidade mínima se a coluna existir
        _ordem = {"baixo": 0, "medio": 1, "alto": 2, "critico": 3}
        if "severidade" in df.columns:
            nivel_min = _ordem.get(severidade_min, 1)
            df = df[df["severidade"].map(_ordem).fillna(0) >= nivel_min]

        if df.empty:
            return {
                "encontrou_dados": False,
                "total": 0,
                "resumo": f"Nenhuma anomalia com severidade >= {severidade_min}",
                "dados": [],
                "estatisticas": {},
                "estatisticas_por_grupo": [],
                "contatos_setores": [],
            }

        # ── 6. Agregação por grupo (dimensão principal) ───────────────────
        estatisticas_por_grupo = []
        if "cod_categoria" in df.columns and "valor" in df.columns:
            df_grupo = (
                df.groupby("cod_categoria")
                .agg(
                    total       = ("cod_categoria", "count"),
                    valor_total = ("valor", "sum"),
                    valor_max   = ("valor", "max"),
                    valor_medio = ("valor", "mean"),
                )
                .reset_index()
            )
            df_grupo["valor_medio"] = df_grupo["valor_medio"].round(2)
            estatisticas_por_grupo = df_grupo.sort_values("valor_total", ascending=False).to_dict("records")

        # ── 7. Métricas globais ───────────────────────────────────────────
        total              = len(df)
        valor_total        = float(df["valor"].sum())         if "valor" in df.columns else 0.0
        valor_max          = float(df["valor"].max())         if "valor" in df.columns else 0.0
        excedente_total    = float(df["excedente"].sum())     if "excedente" in df.columns else 0.0
        categorias_unicas  = df["cod_categoria"].nunique()    if "cod_categoria" in df.columns else 0
        vendedores_unicos  = df["cod_vendedor"].nunique()     if "cod_vendedor" in df.columns else 0
        pedidos_unicos     = df["pedido"].nunique()           if "pedido" in df.columns else 0

        # ── 8. Resumo legível ─────────────────────────────────────────────
        if total == 1:
            resumo = f"1 anomalia detectada (valor: R$ {valor_max:,.2f})"
        else:
            resumo = (
                f"{total} anomalias em {pedidos_unicos} pedido(s) — "
                f"maior valor: R$ {valor_max:,.2f}"
            )

        # ── 9. Destinatários dinâmicos (contatos_setores) ─────────────────
        # Extraídos do ERP/banco auxiliar em runtime — sem cadastro no Nexus.
        # O orquestrador mescla com os fixos (alertas_destinatarios) e
        # deduplica por whatsapp. SEMPRE normalize o telefone com
        # normalizar_whatsapp() — formatos variados do ERP viram o formato
        # da Evolution API (5517999990000) ou None (descartado).
        contatos_setores: list[dict] = []
        vistos: set[str] = set()
        try:
            linhas_contatos = gerenciador_conexoes.executar(
                conexao=CONEXAO_METAS,
                query=carregar_query(ARQUIVO_CONSULTAS, "buscar_contatos_notificacao"),
                parametros={"cod_empresa": cod_empresa},
            )
            for c in linhas_contatos:
                fone = normalizar_whatsapp(c.get("whatsapp") or c.get("telefone"))
                if fone and fone not in vistos:
                    vistos.add(fone)
                    contatos_setores.append({
                        "nome":     str(c.get("nome") or "").strip(),
                        "whatsapp": fone,
                        "email":    c.get("email"),
                        "setor":    c.get("setor", ""),
                    })
        except Exception:
            logger.warning("Não foi possível carregar contatos de notificação")

        # ── 9b. (Alternativa) grupos_por_destinatario ──────────────────────
        # Use quando cada destinatário deve receber SÓ os itens dele
        # (ex: cada vendedor recebe apenas os pedidos dele). O orquestrador
        # cria entregas por (destinatário × itens do grupo). Descomente e adapte:
        #
        # grupos = []
        # for cod_vend, df_v in df.groupby("cod_vendedor"):
        #     primeiro = df_v.iloc[0]
        #     fone = normalizar_whatsapp(primeiro.get("telefone_vendedor"))
        #     if not fone:
        #         continue
        #     grupos.append({
        #         "destinatario": {
        #             "nome":     str(primeiro.get("nome_vendedor") or ""),
        #             "whatsapp": fone,
        #             "email":    primeiro.get("email_vendedor"),
        #         },
        #         "itens": df_v.to_dict("records"),
        #     })
        # # no payload final: "grupos_por_destinatario": grupos

        # ── 10. Fingerprint (auditoria) ────────────────────────────────────
        # Vai para historico.hash_arquivo. A deduplicação REAL é por item:
        # o orquestrador calcula SHA-256 de cada linha de 'dados' e controla
        # o cooldown por item em alertas_itens_notificados — item novo dispara
        # na hora, item repetido espera o cooldown. Este hash do conjunto serve
        # só para rastrear "o que foi visto" na auditoria.
        chaves_dedup = sorted(
            (
                str(row.get("pedido", "")),
                str(row.get("cod_produto", "")),
                str(row.get("item_pedido", "")),
            )
            for row in df.to_dict("records")
        )
        fingerprint = hashlib.sha256(json.dumps(chaves_dedup).encode()).hexdigest()

        # ── 11. Payload final ─────────────────────────────────────────────
        return {
            "encontrou_dados": True,
            "total": total,
            "resumo": resumo,
            "fingerprint": fingerprint,
            "dados": df.to_dict("records"),
            "contatos_setores": contatos_setores,
            # "grupos_por_destinatario": grupos,  # ver seção 9b
            "estatisticas": {
                "valor_total":       valor_total,
                "valor_max":         valor_max,
                "excedente_total":   excedente_total,
                "categorias_unicas": int(categorias_unicas),
                "vendedores_unicos": int(vendedores_unicos),
                "pedidos_unicos":    int(pedidos_unicos),
            },
            "estatisticas_por_grupo": estatisticas_por_grupo,
        }
