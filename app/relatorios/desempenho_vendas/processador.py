"""
Processador do relatório: desempenho_vendas
Multi-banco: Firebird (ERP) + PostgreSQL (nexus_metas)

Demonstra:
  - Vendas do ERP (Firebird) vs Metas do PostgreSQL auxiliar
  - Join cross-database com pandas
  - Gráfico de barras: Vendas vs Meta por vendedor
  - Gráfico de tendência diária
  - Ranking e % de atingimento
"""

import base64
import io
from pathlib import Path
from typing import Any

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from app.core.carregador_sql import carregar_query
from app.core.gerenciador_conexoes import gerenciador_conexoes

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

ARQUIVO_CONSULTAS = Path(__file__).parent / "consultas.sql"
CONEXAO_ERP = "REPLICA_TERRA"
CONEXAO_METAS = "testes"

matplotlib.use("Agg")
plt.style.use("seaborn-v0_8-whitegrid")

COR_AZUL = "#2563eb"
COR_VERDE = "#10b981"
COR_VERMELHO = "#ef4444"
COR_AMARELO = "#f59e0b"
COR_CINZA = "#6b7280"


def _grafico_para_base64(figura: plt.Figure) -> str:
    buf = io.BytesIO()
    figura.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode("utf-8")
    plt.close(figura)
    return f"data:image/png;base64,{b64}"


def _gerar_grafico_vendas_vs_meta(df: pd.DataFrame, mes: int, ano: int) -> str:
    """
    Gráfico de barras horizontais: Vendas vs Meta por vendedor.
    """
    df = df.sort_values("total_vendido", ascending=True)
    vendedores = df["nome_vendedor"].tolist()
    vendas = df["total_vendido"].tolist()
    metas = df["meta_valor"].tolist()

    y = range(len(vendedores))
    altura = 0.35

    fig, ax = plt.subplots(figsize=(10, max(5, len(vendedores) * 0.6)))

    bars_meta = ax.barh(
        [i + altura / 2 for i in y], metas, altura,
        label="Meta", color=COR_CINZA, alpha=0.5, edgecolor="white"
    )
    bars_vendas = ax.barh(
        [i - altura / 2 for i in y], vendas, altura,
        label="Vendas", color=COR_AZUL, edgecolor="white"
    )

    # Rótulos de %
    for i, (v, m) in enumerate(zip(vendas, metas)):
        pct = (v / m * 100) if m > 0 else 0
        color = COR_VERDE if pct >= 100 else COR_VERMELHO
        ax.text(
            max(v, m) + max(vendas) * 0.02, i,
            f"{pct:.0f}%", va="center", fontsize=9,
            fontweight="bold", color=color
        )

    ax.set_yticks(list(y))
    ax.set_yticklabels(vendedores, fontsize=10)
    ax.set_xlabel("Valor (R$)", fontsize=11)
    ax.set_title(
        f"Vendas vs Meta — {mes:02d}/{ano}",
        fontsize=14, fontweight="bold", pad=15
    )
    ax.legend(loc="lower right", fontsize=10)
    ax.set_xlim(right=max(max(vendas), max(metas)) * 1.25)

    fig.tight_layout()
    return _grafico_para_base64(fig)


def _gerar_grafico_tendencia(df_diario: pd.DataFrame, mes: int, ano: int) -> str:
    """
    Gráfico de linha: vendas diárias no mês.
    """
    dias = df_diario["dia"].tolist()
    totais = df_diario["total_vendido"].tolist()

    fig, ax = plt.subplots(figsize=(10, 4.5))

    ax.fill_between(dias, totais, alpha=0.15, color=COR_AZUL)
    ax.plot(dias, totais, marker="o", linewidth=2, color=COR_AZUL,
            markersize=6, markerfacecolor="white", markeredgewidth=2)

    # Rótulo do último ponto
    if dias and totais:
        ax.annotate(
            f"R$ {totais[-1]:,.0f}",
            xy=(dias[-1], totais[-1]),
            xytext=(5, 5), textcoords="offset points",
            fontsize=9, fontweight="bold", color=COR_AZUL
        )

    ax.set_xticks(dias)
    ax.set_xticklabels([str(d) for d in dias], fontsize=8)
    ax.set_ylabel("Total Vendido (R$)", fontsize=11)
    ax.set_title(
        f"Tendência Diária de Vendas — {mes:02d}/{ano}",
        fontsize=14, fontweight="bold", pad=15
    )

    fig.tight_layout()
    return _grafico_para_base64(fig)


# ---------------------------------------------------------------------------
# Processador
# ---------------------------------------------------------------------------


class ProcessadorDesempenhoVendas:
    """Dashboard de vendas vs metas com gráficos."""

    @staticmethod
    def validar(parametros: dict) -> tuple[bool, str]:
        for campo in ["cod_empresa", "ano", "mes"]:
            if campo in parametros:
                if not isinstance(parametros[campo], int) or parametros[campo] < 1:
                    return False, f"Parâmetro '{campo}' deve ser inteiro positivo"

        if "mes" in parametros and parametros["mes"] > 12:
            return False, "Parâmetro 'mes' deve ser entre 1 e 12"

        return True, ""

    @staticmethod
    def buscar_dados(parametros: dict) -> dict[str, Any]:
        cod_empresa = parametros.get("cod_empresa", 1)
        ano = parametros.get("ano", 2026)
        mes = parametros.get("mes", 7)
        params_fb = {"cod_empresa": cod_empresa, "ano": ano, "mes": mes}

        # ── 1. Firebird: vendas por vendedor ──────────────────────────
        query_vendas = carregar_query(ARQUIVO_CONSULTAS, "vendas_por_vendedor")
        linhas_vendas = gerenciador_conexoes.executar(
            conexao=CONEXAO_ERP,
            query=query_vendas,
            parametros=params_fb,
        )
        df_vendas = pd.DataFrame(linhas_vendas)
        if not df_vendas.empty:
            df_vendas.columns = [c.lower() for c in df_vendas.columns]

        # ── 2. PostgreSQL metas: metas dos vendedores ─────────────────
        try:
            query_metas = carregar_query(ARQUIVO_CONSULTAS, "metas_vendedor")
            linhas_metas = gerenciador_conexoes.executar(
                conexao=CONEXAO_METAS,
                query=query_metas,
                parametros=params_fb,
            )
            df_metas = pd.DataFrame(linhas_metas)
            if not df_metas.empty:
                df_metas.columns = [c.lower() for c in df_metas.columns]
        except Exception:
            df_metas = pd.DataFrame()

        # ── 3. Firebird: vendas diárias ──────────────────────────────
        try:
            query_diario = carregar_query(ARQUIVO_CONSULTAS, "vendas_diarias")
            linhas_diario = gerenciador_conexoes.executar(
                conexao=CONEXAO_ERP,
                query=query_diario,
                parametros=params_fb,
            )
            df_diario = pd.DataFrame(linhas_diario)
            if not df_diario.empty:
                df_diario.columns = [c.lower() for c in df_diario.columns]
        except Exception:
            df_diario = pd.DataFrame()

        # ── 4. Join cross-database: vendas + metas ────────────────────
        if not df_vendas.empty and not df_metas.empty:
            df_merged = df_vendas.merge(
                df_metas,
                on="cod_vendedor",
                how="left",
                suffixes=("", "_meta"),
            )
            # Se nome_vendedor_meta existir e nome_vendedor for nulo, usa o da meta
            if "nome_vendedor" in df_merged.columns and "nome_vendedor_meta" in df_merged.columns:
                df_merged["nome_vendedor"] = df_merged["nome_vendedor"].fillna(
                    df_merged["nome_vendedor_meta"]
                )
                df_merged = df_merged.drop(columns=["nome_vendedor_meta"])

            # Preenche meta_valor ausente com 0
            if "meta_valor" in df_merged.columns:
                df_merged["meta_valor"] = df_merged["meta_valor"].fillna(0)
            else:
                df_merged["meta_valor"] = 0

            df_merged["atingimento_pct"] = np.where(
                df_merged["meta_valor"] > 0,
                (df_merged["total_vendido"] / df_merged["meta_valor"] * 100).round(1),
                0,
            )
        else:
            df_merged = df_vendas.copy() if not df_vendas.empty else pd.DataFrame()

        # ── 5. Agregações ──────────────────────────────────────────────
        total_vendido = float(df_merged["total_vendido"].sum()) if not df_merged.empty else 0
        total_meta = float(df_merged["meta_valor"].sum()) if not df_merged.empty and "meta_valor" in df_merged.columns else 0
        atingimento_global = round(total_vendido / total_meta * 100, 1) if total_meta > 0 else 0
        qtd_vendedores = len(df_merged) if not df_merged.empty else 0

        # Vendedores acima e abaixo da meta
        if not df_merged.empty and "atingimento_pct" in df_merged.columns:
            acima_meta = int((df_merged["atingimento_pct"] >= 100).sum())
            abaixo_meta = qtd_vendedores - acima_meta
        else:
            acima_meta = abaixo_meta = 0

        # Top 3
        if not df_merged.empty:
            top3 = df_merged.nlargest(3, "total_vendido")[
                ["nome_vendedor", "total_vendido", "meta_valor", "atingimento_pct"]
            ].to_dict("records")
        else:
            top3 = []

        # ── 6. Gráficos ────────────────────────────────────────────────
        grafico_vendas_meta = None
        grafico_tendencia = None

        try:
            if not df_merged.empty and "meta_valor" in df_merged.columns:
                grafico_vendas_meta = _gerar_grafico_vendas_vs_meta(
                    df_merged, mes, ano
                )
            if not df_diario.empty:
                grafico_tendencia = _gerar_grafico_tendencia(df_diario, mes, ano)
        except Exception:
            pass

        # ── 7. Payload ─────────────────────────────────────────────────
        return {
            "total": qtd_vendedores,
            "total_vendido": total_vendido,
            "total_meta": total_meta,
            "atingimento_global_pct": atingimento_global,
            "acima_meta": acima_meta,
            "abaixo_meta": abaixo_meta,
            "top3": top3,
            "vendedores": df_merged.to_dict("records") if not df_merged.empty else [],
            "grafico_vendas_meta": grafico_vendas_meta,
            "grafico_tendencia": grafico_tendencia,
            "periodo": f"{mes:02d}/{ano}",
        }
