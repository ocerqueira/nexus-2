"""
Processador do relatório: dashboard_conexoes
Demonstra uso de pandas para transformações/agregações e matplotlib
para geração de gráficos com legendas embutidos no PDF.
"""

import base64
import io
from pathlib import Path
from typing import Any

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd

from app.core.carregador_sql import carregar_query
from app.core.gerenciador_conexoes import gerenciador_conexoes

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

ARQUIVO_CONSULTAS = Path(__file__).parent / "consultas.sql"
CONEXAO = "nexus_proprio"

# Backend não-interativo para matplotlib (essencial em servidor/sem display)
matplotlib.use("Agg")

# Estilo visual limpo e profissional
plt.style.use("seaborn-v0_8-whitegrid")

# Paleta de cores do Nexus (azul corporativo + tons)
COR_AZUL = "#2563eb"
COR_VERDE = "#10b981"
COR_VERMELHO = "#ef4444"
COR_AMARELO = "#f59e0b"
COR_CINZA = "#6b7280"
COR_AZUL_CLARO = "#93c5fd"
COR_VERMELHO_CLARO = "#fca5a5"

PALETA_TIPOS = {
    "postgres": "#2563eb",
    "firebird": "#f59e0b",
    "mysql": "#10b981",
}


# ---------------------------------------------------------------------------
# Helpers de gráficos
# ---------------------------------------------------------------------------


def _grafico_para_base64(figura: plt.Figure) -> str:
    """Converte uma figura matplotlib para string base64 inline HTML."""
    buf = io.BytesIO()
    figura.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode("utf-8")
    plt.close(figura)
    return f"data:image/png;base64,{b64}"


def _gerar_grafico_barras_agrupadas(df_agg: pd.DataFrame) -> str:
    """
    Gráfico de barras agrupadas: Ativas vs Inativas por tipo de banco.

    Args:
        df_agg: DataFrame com colunas [tipo, total, ativas, inativas]
    """
    tipos = df_agg["tipo"].tolist()
    ativas = df_agg["ativas"].tolist()
    inativas = df_agg["inativas"].tolist()

    x = range(len(tipos))
    largura = 0.35

    fig, ax = plt.subplots(figsize=(8, 5))

    barras_ativas = ax.bar(
        [i - largura / 2 for i in x],
        ativas,
        largura,
        label="Ativas",
        color=COR_VERDE,
        edgecolor="white",
        linewidth=0.5,
    )
    barras_inativas = ax.bar(
        [i + largura / 2 for i in x],
        inativas,
        largura,
        label="Inativas",
        color=COR_VERMELHO_CLARO,
        edgecolor="white",
        linewidth=0.5,
    )

    # Rótulos nas barras
    for barra in barras_ativas:
        altura = barra.get_height()
        if altura > 0:
            ax.text(
                barra.get_x() + barra.get_width() / 2,
                altura + 0.1,
                str(int(altura)),
                ha="center",
                va="bottom",
                fontsize=9,
                fontweight="bold",
                color=COR_VERDE,
            )
    for barra in barras_inativas:
        altura = barra.get_height()
        if altura > 0:
            ax.text(
                barra.get_x() + barra.get_width() / 2,
                altura + 0.1,
                str(int(altura)),
                ha="center",
                va="bottom",
                fontsize=9,
                fontweight="bold",
                color=COR_VERMELHO,
            )

    ax.set_xticks(list(x))
    ax.set_xticklabels([t.capitalize() for t in tipos], fontsize=11)
    ax.set_ylabel("Quantidade", fontsize=11)
    ax.set_title("Conexões por Tipo e Status", fontsize=14, fontweight="bold", pad=15)
    ax.legend(loc="upper right", fontsize=10, frameon=True)
    ax.set_ylim(top=max(max(ativas), max(inativas)) * 1.3 if max(ativas + inativas) > 0 else 1)

    fig.tight_layout()
    return _grafico_para_base64(fig)


def _gerar_grafico_pizza(df_agg: pd.DataFrame) -> str:
    """
    Gráfico de pizza (donut) da distribuição de conexões por tipo.

    Args:
        df_agg: DataFrame com colunas [tipo, total]
    """
    tipos = df_agg["tipo"].tolist()
    totais = df_agg["total"].tolist()
    cores = [PALETA_TIPOS.get(t, COR_CINZA) for t in tipos]

    fig, ax = plt.subplots(figsize=(7, 7))

    wedges, texts, autotexts = ax.pie(
        totais,
        labels=[t.capitalize() for t in tipos],
        autopct="%1.1f%%",
        startangle=90,
        colors=cores,
        wedgeprops={"width": 0.4, "edgecolor": "white", "linewidth": 1.5},
        textprops={"fontsize": 11},
        pctdistance=0.78,
    )

    for autotext in autotexts:
        autotext.set_fontweight("bold")
        autotext.set_fontsize(11)

    ax.set_title(
        "Distribuição por Tipo de Banco",
        fontsize=14,
        fontweight="bold",
        pad=20,
    )

    fig.tight_layout()
    return _grafico_para_base64(fig)


# ---------------------------------------------------------------------------
# Processador
# ---------------------------------------------------------------------------


class ProcessadorDashboardConexoes:
    """Dashboard consolidado com pandas + matplotlib."""

    @staticmethod
    def validar(parametros: dict) -> tuple[bool, str]:
        if "apenas_ativas" in parametros:
            if not isinstance(parametros["apenas_ativas"], bool):
                return False, "Parâmetro 'apenas_ativas' deve ser true ou false"

        if "tipo_banco" in parametros and parametros["tipo_banco"]:
            tipos_validos = ["postgres", "firebird", "mysql"]
            if parametros["tipo_banco"] not in tipos_validos:
                return (
                    False,
                    f"Parâmetro 'tipo_banco' deve ser um de: {tipos_validos}",
                )

        return True, ""

    @staticmethod
    def buscar_dados(parametros: dict) -> dict[str, Any]:
        apenas_ativas = parametros.get("apenas_ativas", False)
        tipo_banco = parametros.get("tipo_banco")

        # ── 1. Escolher query de listagem ──────────────────────────────
        if tipo_banco and apenas_ativas:
            nome_query = "filtrar_ativas_por_tipo"
            params_query = {"tipo_banco": tipo_banco}
        elif tipo_banco:
            nome_query = "filtrar_por_tipo"
            params_query = {"tipo_banco": tipo_banco}
        elif apenas_ativas:
            nome_query = "listar_apenas_ativas"
            params_query = {}
        else:
            nome_query = "listar_conexoes_completas"
            params_query = {}

        query = carregar_query(ARQUIVO_CONSULTAS, nome_query)
        linhas = gerenciador_conexoes.executar(
            conexao=CONEXAO,
            query=query,
            parametros=params_query,
        )

        # ── 2. DataFrame principal ────────────────────────────────────
        df = pd.DataFrame(linhas)

        # ── 3. Agregações com pandas ──────────────────────────────────
        if df.empty:
            return {
                "total": 0,
                "ativas": 0,
                "inativas": 0,
                "conexoes": [],
                "grafico_barras": None,
                "grafico_pizza": None,
                "estatisticas_por_tipo": [],
                "filtros_aplicados": {
                    "apenas_ativas": apenas_ativas,
                    "tipo_banco": tipo_banco or "todos",
                },
            }

        # Estatísticas básicas
        total = int(df["id"].count())
        ativas_count = int(df["ativo"].sum()) if "ativo" in df.columns else 0
        inativas_count = total - ativas_count

        # Distribuição por tipo (DataFrame agregado)
        df_por_tipo = (
            df.groupby("tipo")
            .agg(
                total=("id", "count"),
                ativas=("ativo", "sum") if "ativo" in df.columns else ("id", "count"),
            )
            .reset_index()
        )
        df_por_tipo["inativas"] = df_por_tipo["total"] - df_por_tipo["ativas"]
        df_por_tipo["pct_ativas"] = (
            (df_por_tipo["ativas"] / df_por_tipo["total"] * 100).round(1)
        )

        # Tipos de banco distintos
        tipos_distintos = int(df["tipo"].nunique())

        # Banco mais comum
        tipo_mais_comum = (
            df["tipo"].value_counts().index[0] if not df.empty else "—"
        )

        # ── 4. Gerar gráficos ─────────────────────────────────────────
        grafico_barras = None
        grafico_pizza = None

        try:
            # Gráfico de barras: sempre usa agregação global (não a filtrada)
            # para mostrar visão completa mesmo quando há filtro
            query_agg = carregar_query(ARQUIVO_CONSULTAS, "agregar_por_tipo_status")
            linhas_agg = gerenciador_conexoes.executar(
                conexao=CONEXAO,
                query=query_agg,
            )
            df_agg_global = pd.DataFrame(linhas_agg)

            if not df_agg_global.empty:
                grafico_barras = _gerar_grafico_barras_agrupadas(df_agg_global)
                grafico_pizza = _gerar_grafico_pizza(df_agg_global)
        except Exception:
            # Gráficos são bônus visual; se falharem o relatório ainda funciona
            pass

        # ── 5. Montar payload ─────────────────────────────────────────
        return {
            "total": total,
            "ativas": ativas_count,
            "inativas": inativas_count,
            "taxa_atividade_pct": round(ativas_count / total * 100, 1) if total > 0 else 0,
            "tipos_distintos": tipos_distintos,
            "tipo_mais_comum": tipo_mais_comum,
            "conexoes": df.to_dict("records"),
            "estatisticas_por_tipo": df_por_tipo.to_dict("records"),
            "grafico_barras": grafico_barras,
            "grafico_pizza": grafico_pizza,
            "filtros_aplicados": {
                "apenas_ativas": apenas_ativas,
                "tipo_banco": tipo_banco or "todos",
            },
        }
