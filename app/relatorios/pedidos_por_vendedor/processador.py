"""
Processador do relatório: pedidos_por_vendedor
Fonte: ERP Firebird (ARQES13 + ARQES15 + ARQCAD)
"""

import base64
import io
import logging
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd

from app.core.carregador_sql import carregar_query
from app.core.gerenciador_conexoes import gerenciador_conexoes
from app.relatorios._cores import COR_AZUL

logger = logging.getLogger(__name__)

ARQUIVO_CONSULTAS = Path(__file__).parent / "consultas.sql"
CONEXAO_ERP = "REPLICA_TERRA"

matplotlib.use("Agg")
plt.style.use("seaborn-v0_8-whitegrid")

def _grafico_para_base64(fig: plt.Figure) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode("utf-8")
    plt.close(fig)
    return f"data:image/png;base64,{b64}"


def _gerar_grafico_ranking(df: pd.DataFrame, top_n: int = 15) -> str:
    """Barras horizontais: top N vendedores por valor total."""
    df_top = df.nlargest(top_n, "valor_total").sort_values("valor_total", ascending=True)

    nomes = df_top["nome_vendedor"].fillna("Sem nome").tolist()
    valores = df_top["valor_total"].tolist()

    fig, ax = plt.subplots(figsize=(10, max(5, len(nomes) * 0.55)))

    bars = ax.barh(nomes, valores, color=COR_AZUL, edgecolor="white", height=0.6)

    # Rótulo de valor no final de cada barra
    for bar, val in zip(bars, valores):
        ax.text(
            bar.get_width() + max(valores) * 0.01,
            bar.get_y() + bar.get_height() / 2,
            f"R$ {val:,.0f}",
            va="center",
            fontsize=8,
            color="#374151",
        )

    ax.set_xlabel("Valor Total (R$)", fontsize=10)
    ax.set_xlim(right=max(valores) * 1.20)
    ax.set_title(f"Ranking de Vendedores — Top {top_n}", fontsize=13, fontweight="bold", pad=12)
    ax.tick_params(axis="y", labelsize=9)

    fig.tight_layout()
    return _grafico_para_base64(fig)


class ProcessadorPedidosPorVendedor:
    """Ranking de pedidos por vendedor com top 5 produtos."""

    @staticmethod
    def validar(parametros: dict) -> tuple[bool, str]:
        for campo in ("data_inicio", "data_fim"):
            valor = parametros.get(campo)
            if not valor:
                return False, f"'{campo}' é obrigatório (formato AAAA-MM-DD)"
            try:
                datetime.strptime(str(valor), "%Y-%m-%d")
            except ValueError:
                return False, f"'{campo}' deve estar no formato AAAA-MM-DD"

        if parametros["data_inicio"] > parametros["data_fim"]:
            return False, "'data_inicio' não pode ser posterior a 'data_fim'"

        if "cod_empresa" in parametros:
            if not isinstance(parametros["cod_empresa"], int) or parametros["cod_empresa"] < 1:
                return False, "'cod_empresa' deve ser inteiro positivo"

        return True, ""

    @staticmethod
    def buscar_dados(parametros: dict) -> dict[str, Any]:
        cod_empresa = parametros.get("cod_empresa", 1)
        data_inicio = parametros["data_inicio"]
        data_fim = parametros["data_fim"]
        params_fb = {"cod_empresa": cod_empresa, "data_inicio": data_inicio, "data_fim": data_fim}

        # ── 1. Pedidos por vendedor ────────────────────────────────────
        linhas = gerenciador_conexoes.executar(
            conexao=CONEXAO_ERP,
            query=carregar_query(ARQUIVO_CONSULTAS, "pedidos_por_vendedor"),
            parametros=params_fb,
        )
        df = pd.DataFrame(linhas)
        if df.empty:
            return {
                "total_vendedores": 0,
                "total_pedidos": 0,
                "valor_total": 0.0,
                "ticket_medio": 0.0,
                "vendedores": [],
                "top_produtos": {},
                "grafico_ranking": None,
                "periodo": f"{data_inicio} a {data_fim}",
            }

        df.columns = [c.lower() for c in df.columns]
        df["valor_total"] = pd.to_numeric(df["valor_total"], errors="coerce").fillna(0)
        df["ticket_medio"] = pd.to_numeric(df["ticket_medio"], errors="coerce").fillna(0)
        df["qtd_pedidos"] = pd.to_numeric(df["qtd_pedidos"], errors="coerce").fillna(0).astype(int)
        df["ranking"] = range(1, len(df) + 1)

        # ── 2. Top 5 produtos por vendedor ─────────────────────────────
        top_produtos: dict[float, list[dict]] = defaultdict(list)
        try:
            linhas_prod = gerenciador_conexoes.executar(
                conexao=CONEXAO_ERP,
                query=carregar_query(ARQUIVO_CONSULTAS, "top_produtos_por_vendedor"),
                parametros=params_fb,
            )
            for row in linhas_prod:
                chave = row.get("cod_vendedor") or row.get("COD_VENDEDOR")
                top_produtos[chave].append({
                    "pos": int(row.get("pos") or row.get("POS") or 0),
                    "cod_produto": row.get("cod_produto") or row.get("COD_PRODUTO"),
                    "nome_produto": row.get("nome_produto") or row.get("NOME_PRODUTO") or "",
                    "qtd_total": float(row.get("qtd_total") or row.get("QTD_TOTAL") or 0),
                    "valor_total": float(row.get("valor_total") or row.get("VALOR_TOTAL") or 0),
                })
        except Exception:
            logger.warning("Erro ao buscar top produtos", exc_info=True)

        # ── 3. Gráfico ranking ─────────────────────────────────────────
        grafico = None
        try:
            grafico = _gerar_grafico_ranking(df)
        except Exception:
            logger.warning("Erro ao gerar gráfico ranking", exc_info=True)

        # ── 4. Totalizadores ───────────────────────────────────────────
        valor_total_geral = float(df["valor_total"].sum())
        total_pedidos = int(df["qtd_pedidos"].sum())
        ticket_medio_geral = valor_total_geral / total_pedidos if total_pedidos > 0 else 0

        # ── 5. Serializar ──────────────────────────────────────────────
        vendedores = df.to_dict("records")
        # converte cod_vendedor para string para uso como chave no template
        top_produtos_serial = {
            str(k): v for k, v in top_produtos.items()
        }
        for v in vendedores:
            v["_top_produtos"] = top_produtos_serial.get(str(v["cod_vendedor"]), [])

        return {
            "total_vendedores": len(vendedores),
            "total_pedidos": total_pedidos,
            "valor_total": round(valor_total_geral, 2),
            "ticket_medio": round(ticket_medio_geral, 2),
            "vendedores": vendedores,
            "top_produtos": top_produtos_serial,
            "grafico_ranking": grafico,
            "periodo": f"{data_inicio} a {data_fim}",
        }
