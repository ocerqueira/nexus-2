"""
Processador do alerta: item_comprimento_excedente
Fonte: ERP Firebird (VD_CARGA + ARQES13 + ARQES15 + ARQ_ITENS_DEF_TELHA + PCP_FA_CALC_PESO)
"""

import hashlib
import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from app.core.carregador_sql import carregar_query
from app.core.gerenciador_conexoes import gerenciador_conexoes

logger = logging.getLogger(__name__)

ARQUIVO_CONSULTAS = Path(__file__).parent / "consultas.sql"
CONEXAO_ERP = "REPLICA_TERRA"


class ProcessadorItemComprimentoExcedente:
    """Detecta itens de telha/SBX com comprimento acima do limite."""

    @staticmethod
    def validar(parametros: dict) -> tuple[bool, str]:
        if "cod_empresa" in parametros:
            cod = parametros["cod_empresa"]
            if not isinstance(cod, int) or cod < 1:
                return False, "Parâmetro 'cod_empresa' deve ser inteiro positivo"
        if "data_inicio" in parametros and parametros["data_inicio"] is not None:
            try:
                datetime.strptime(str(parametros["data_inicio"]), "%Y-%m-%d")
            except ValueError:
                return False, "'data_inicio' deve estar no formato AAAA-MM-DD"
        return True, ""

    @staticmethod
    def verificar(parametros: dict) -> dict[str, Any]:
        cod_empresa = parametros.get("cod_empresa", 1)
        data_inicio = parametros.get("data_inicio") or (
            date.today() - timedelta(days=30)
        ).isoformat()

        # ── 1. Firebird: detectar itens com comprimento excedente ───────
        linhas = gerenciador_conexoes.executar(
            conexao=CONEXAO_ERP,
            query=carregar_query(ARQUIVO_CONSULTAS, "detectar_itens_comprimento_excedente"),
            parametros={"cod_empresa": cod_empresa, "data_inicio": data_inicio},
        )

        # ── 2. DataFrame pandas ────────────────────────────────────────
        df = pd.DataFrame(linhas)

        if df.empty:
            return {
                "encontrou_dados": False,
                "total": 0,
                "resumo": f"Nenhum item com comprimento excedente desde {data_inicio}",
                "dados": [],
                "contatos_setores": [],
                "limites": {},
                "estatisticas": {},
                "estatisticas_por_origem": [],
            }

        df.columns = [c.lower() for c in df.columns]

        if "comprimento" in df.columns:
            df["comprimento"] = pd.to_numeric(df["comprimento"], errors="coerce")
            df["comprimento_m"] = (df["comprimento"] / 1000).round(2)

        # ── 3. Agregações ──────────────────────────────────────────────
        total = len(df)
        origens_afetadas = df["origem_medida"].nunique() if "origem_medida" in df.columns else 0
        vendedores_afetados = df["cod_vendedor"].nunique() if "cod_vendedor" in df.columns else 0
        pedidos_afetados = df["pedido"].nunique() if "pedido" in df.columns else 0
        maior_comp = float(df["comprimento_m"].max()) if "comprimento_m" in df.columns else 0.0

        if "origem_medida" in df.columns and "comprimento_m" in df.columns:
            df_por_origem = (
                df.groupby("origem_medida")
                .agg(
                    total=("pedido", "count"),
                    comprimento_max=("comprimento_m", "max"),
                    comprimento_medio=("comprimento_m", "mean"),
                )
                .reset_index()
            )
            df_por_origem["comprimento_medio"] = df_por_origem["comprimento_medio"].round(2)
            estatisticas_por_origem = df_por_origem.to_dict("records")
        else:
            estatisticas_por_origem = []

        # ── 4. Resumo ──────────────────────────────────────────────────
        if total == 1:
            resumo = f"1 item com comprimento excedente ({maior_comp}m)"
        else:
            resumo = (
                f"{total} itens com comprimento excedente "
                f"em {pedidos_afetados} pedido(s) — "
                f"maior: {maior_comp}m"
            )

        # ── 5. Fingerprint para deduplicação ──────────────────────────
        chaves_dedup = sorted(
            (
                str(row.get("pedido", "")),
                str(row.get("seqcarga", "")),
                str(row.get("origem_medida", "")),
            )
            for row in df.to_dict("records")
        )
        fingerprint = hashlib.sha256(json.dumps(chaves_dedup).encode()).hexdigest()

        # ── 6. Payload ─────────────────────────────────────────────────
        return {
            "encontrou_dados": True,
            "total": total,
            "resumo": resumo,
            "dados": df.to_dict("records"),
            "contatos_setores": [],   # populado pelo nexus_metas quando disponível
            "limites": {},
            "fingerprint": fingerprint,
            "estatisticas": {
                "origens_afetadas": int(origens_afetadas),
                "vendedores_afetados": int(vendedores_afetados),
                "pedidos_afetados": int(pedidos_afetados),
                "maior_comprimento_m": maior_comp,
            },
            "estatisticas_por_origem": estatisticas_por_origem,
        }
