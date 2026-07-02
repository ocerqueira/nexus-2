"""
Processador do relatório: _modelo_relatorio
Multi-banco: Firebird (ERP) + PostgreSQL (nexus_metas)

Como usar:
  1. Copie esta pasta para app/relatorios/nome_do_relatorio/
  2. Renomeie a classe ProcessadorModeloRelatorio
  3. Ajuste CONEXAO_ERP / CONEXAO_METAS
  4. Adapte buscar_dados() com as queries reais
  Veja LEIAME.md para cenários avançados.
"""

import base64
import io
import logging
from datetime import date
from pathlib import Path
from typing import Any

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from app.core.carregador_sql import carregar_query
from app.core.gerenciador_conexoes import gerenciador_conexoes
from app.relatorios._cores import COR_AMARELO, COR_AZUL, COR_CINZA, COR_ROXO, COR_VERDE, COR_VERMELHO

logger = logging.getLogger(__name__)

ARQUIVO_CONSULTAS = Path(__file__).parent / "consultas.sql"
CONEXAO_ERP   = "REPLICA_TERRA"
CONEXAO_METAS = "nexus_metas"

matplotlib.use("Agg")
plt.style.use("seaborn-v0_8-whitegrid")


# =============================================================================
# Funções de gráfico
# =============================================================================

def _figura_para_base64(fig: plt.Figure) -> str:
    """Serializa figura matplotlib para data URI embutível no HTML."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode("utf-8")
    plt.close(fig)
    return f"data:image/png;base64,{b64}"


def _grafico_barras_horizontais(
    df: pd.DataFrame,
    col_categoria: str,
    col_valor: str,
    titulo: str,
    col_meta: str | None = None,
    max_itens: int = 20,
) -> str:
    """
    Barras horizontais ordenadas por valor.
    col_meta: se informado, adiciona linha de meta e % de atingimento nos rótulos.
    max_itens: limita para não gerar PDF ilegível.
    """
    df = df.nlargest(max_itens, col_valor).sort_values(col_valor, ascending=True)
    cats   = df[col_categoria].tolist()
    vals   = df[col_valor].tolist()
    metas  = df[col_meta].tolist() if col_meta and col_meta in df.columns else []

    fig, ax = plt.subplots(figsize=(10, max(5, len(cats) * 0.55)))

    cores = [COR_VERDE if (metas and v >= m) else COR_AZUL for v, m in zip(vals, metas or [0] * len(vals))]
    bars  = ax.barh(cats, vals, color=cores, edgecolor="white", height=0.6)

    for bar, val, *rest in zip(bars, vals, *(([metas]) if metas else [])):
        meta = rest[0] if rest else None
        pct_txt = f" ({val / meta * 100:.0f}%)" if meta and meta > 0 else ""
        ax.text(
            bar.get_width() + max(vals) * 0.015,
            bar.get_y() + bar.get_height() / 2,
            f"R$ {val:,.0f}{pct_txt}",
            va="center", ha="left", fontsize=8, color="#374151",
        )

    if metas:
        meta_ref = max(metas)
        ax.axvline(meta_ref, color=COR_AMARELO, linewidth=1.8, linestyle="--",
                   label=f"Meta máx: R$ {meta_ref:,.0f}")
        ax.legend(fontsize=9)

    ax.set_title(titulo, fontsize=14, fontweight="bold", pad=15)
    ax.set_xlabel("Valor (R$)", fontsize=11)
    ax.set_xlim(right=max(vals) * 1.22)
    fig.tight_layout()
    return _figura_para_base64(fig)


def _grafico_linha_tendencia(
    df: pd.DataFrame,
    col_x: str,
    col_y: str,
    titulo: str,
    col_y2: str | None = None,
    label_y2: str = "Comparativo",
) -> str:
    """
    Linha com preenchimento. col_y2 opcional para série comparativa (ex: ano anterior).
    """
    x  = df[col_x].tolist()
    y  = df[col_y].tolist()

    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.fill_between(x, y, alpha=0.12, color=COR_AZUL)
    ax.plot(x, y, marker="o", linewidth=2, color=COR_AZUL, markersize=5,
            markerfacecolor="white", markeredgewidth=2, label="Principal")

    if col_y2 and col_y2 in df.columns:
        y2 = df[col_y2].tolist()
        ax.plot(x, y2, marker="s", linewidth=1.8, color=COR_CINZA, markersize=4,
                linestyle="--", markerfacecolor="white", label=label_y2)
        ax.legend(fontsize=9)

    if x and y:
        ax.annotate(
            f"R$ {y[-1]:,.0f}",
            xy=(x[-1], y[-1]),
            xytext=(5, 5), textcoords="offset points",
            fontsize=8, fontweight="bold", color=COR_AZUL,
        )

    rotacao = 45 if len(x) > 15 else 0
    ax.set_xticks(x)
    ax.set_xticklabels([str(xi) for xi in x], fontsize=8, rotation=rotacao)
    ax.set_ylabel("Valor (R$)", fontsize=11)
    ax.set_title(titulo, fontsize=14, fontweight="bold", pad=15)
    fig.tight_layout()
    return _figura_para_base64(fig)


def _grafico_pizza(
    df: pd.DataFrame,
    col_categoria: str,
    col_valor: str,
    titulo: str,
    min_pct: float = 3.0,
) -> str:
    """
    Pizza com agrupamento de fatias menores que min_pct% em 'Outros'.
    Ideal para mostrar distribuição percentual por categoria.
    """
    df = df.copy()
    total = df[col_valor].sum()
    if total == 0:
        return ""
    df["_pct"] = df[col_valor] / total * 100

    grandes = df[df["_pct"] >= min_pct].copy()
    outros  = df[df["_pct"] <  min_pct]
    if not outros.empty:
        grandes = pd.concat([
            grandes,
            pd.DataFrame([{col_categoria: "Outros", col_valor: outros[col_valor].sum()}]),
        ], ignore_index=True)

    cores = [COR_AZUL, COR_VERDE, COR_AMARELO, COR_VERMELHO, COR_ROXO,
             COR_CINZA, "#06b6d4", "#f97316", "#84cc16", "#ec4899"]

    fig, ax = plt.subplots(figsize=(8, 6))
    _, _, autotexts = ax.pie(
        grandes[col_valor],
        labels=grandes[col_categoria],
        autopct="%1.1f%%",
        colors=cores[:len(grandes)],
        startangle=90,
        wedgeprops={"edgecolor": "white", "linewidth": 2},
    )
    for at in autotexts:
        at.set_fontsize(8)

    ax.set_title(titulo, fontsize=13, fontweight="bold", pad=15)
    fig.tight_layout()
    return _figura_para_base64(fig)


def _grafico_barras_agrupadas(
    df: pd.DataFrame,
    col_categoria: str,
    col_realizado: str,
    col_meta: str,
    titulo: str,
) -> str:
    """
    Barras agrupadas: realizado x meta lado a lado por categoria.
    Útil para comparar atingimento de meta de forma visual.
    """
    df = df.sort_values(col_realizado, ascending=False).head(15)
    cats      = df[col_categoria].tolist()
    realizados = df[col_realizado].tolist()
    metas      = df[col_meta].tolist()

    x      = np.arange(len(cats))
    largura = 0.38

    fig, ax = plt.subplots(figsize=(10, max(5, len(cats) * 0.5)))
    ax.bar(x - largura / 2, realizados, largura, label="Realizado", color=COR_AZUL, edgecolor="white")
    ax.bar(x + largura / 2, metas,      largura, label="Meta",      color=COR_CINZA, alpha=0.55, edgecolor="white")

    for i, (r, m) in enumerate(zip(realizados, metas)):
        pct   = r / m * 100 if m > 0 else 0
        cor   = COR_VERDE if pct >= 100 else COR_VERMELHO
        ax.text(i, max(r, m) + max(realizados) * 0.02, f"{pct:.0f}%",
                ha="center", va="bottom", fontsize=8, fontweight="bold", color=cor)

    ax.set_xticks(x)
    ax.set_xticklabels(cats, rotation=30 if len(cats) > 6 else 0, ha="right", fontsize=9)
    ax.set_ylabel("Valor (R$)", fontsize=11)
    ax.set_title(titulo, fontsize=14, fontweight="bold", pad=15)
    ax.legend(fontsize=10)
    fig.tight_layout()
    return _figura_para_base64(fig)


# =============================================================================
# Processador
# =============================================================================

class ProcessadorModeloRelatorio:
    """
    [Descreva o relatório aqui]

    Padrão esperado pelo sistema:
      validar(parametros)    → tuple[bool, str]
      buscar_dados(parametros) → dict[str, Any]
    """

    @staticmethod
    def validar(parametros: dict) -> tuple[bool, str]:
        for campo in ["cod_empresa", "ano", "mes"]:
            if campo in parametros:
                if not isinstance(parametros[campo], int) or parametros[campo] < 1:
                    return False, f"'{campo}' deve ser inteiro positivo"

        if "mes" in parametros and parametros["mes"] > 12:
            return False, "'mes' deve ser entre 1 e 12"

        return True, ""

    @staticmethod
    def buscar_dados(parametros: dict) -> dict[str, Any]:
        """
        Executa as queries, processa com pandas, gera gráficos e retorna o payload.

        Chaves do payload (usadas em template.html via Jinja):
          total          int    — total de registros
          periodo        str    — "MM/YYYY" para exibição
          registros      list   — linhas detalhadas
          grupos         list   — agregação por categoria
          top5           list   — top 5 por valor
          resumo_global  dict   — KPIs globais
          grafico_*      str|None — data URI base64 dos gráficos

        Chaves consumidas pelo ORQUESTRADOR (entrega com notificar=true):
          resumo         str   — texto do WhatsApp: caption do PDF ou mensagem
                                 inteira quando formato_whatsapp='resumo_texto'
          grupos_por_destinatario  list — 1 PDF filtrado por destinatário
                                 (contrato documentado no config.json desta pasta)
        """
        hoje        = date.today()
        cod_empresa = parametros.get("cod_empresa", 1)
        ano         = parametros.get("ano", hoje.year)
        mes         = parametros.get("mes", hoje.month)
        params      = {"cod_empresa": cod_empresa, "ano": ano, "mes": mes}
        periodo     = f"{mes:02d}/{ano}"

        _vazio = {
            "total": 0, "periodo": periodo,
            "resumo": f"Nenhum dado para o período {periodo}.",
            "registros": [], "grupos": [], "top5": [],
            "resumo_global": {},
            "grafico_barras": None, "grafico_tendencia": None,
            "grafico_pizza": None, "grafico_agrupado": None,
        }

        # ── 1. Firebird: dados principais ─────────────────────────────────
        linhas = gerenciador_conexoes.executar(
            conexao=CONEXAO_ERP,
            query=carregar_query(ARQUIVO_CONSULTAS, "dados_principais"),
            parametros=params,
        )
        df = pd.DataFrame(linhas)
        if df.empty:
            return _vazio
        df.columns = [c.lower() for c in df.columns]

        # ── 2. PostgreSQL: dados auxiliares (com fallback) ─────────────────
        df_aux = pd.DataFrame()
        try:
            linhas_aux = gerenciador_conexoes.executar(
                conexao=CONEXAO_METAS,
                query=carregar_query(ARQUIVO_CONSULTAS, "dados_auxiliares"),
                parametros=params,
            )
            df_aux = pd.DataFrame(linhas_aux)
            if not df_aux.empty:
                df_aux.columns = [c.lower() for c in df_aux.columns]
        except Exception:
            logger.warning("nexus_metas indisponível — relatório sem metas")

        # ── 3. Firebird: série temporal ────────────────────────────────────
        df_serie = pd.DataFrame()
        try:
            linhas_serie = gerenciador_conexoes.executar(
                conexao=CONEXAO_ERP,
                query=carregar_query(ARQUIVO_CONSULTAS, "serie_temporal"),
                parametros=params,
            )
            df_serie = pd.DataFrame(linhas_serie)
            if not df_serie.empty:
                df_serie.columns = [c.lower() for c in df_serie.columns]
        except Exception:
            pass

        # ── 4. Conversões de tipo ──────────────────────────────────────────
        for col in ["valor", "quantidade", "valor_unit"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

        if not df_serie.empty:
            for col in ["valor", "qtd_pedidos"]:
                if col in df_serie.columns:
                    df_serie[col] = pd.to_numeric(df_serie[col], errors="coerce").fillna(0)

        # ── 5. Join cross-database ─────────────────────────────────────────
        # Combina ERP (Firebird) com metas (PostgreSQL) pela chave cod_categoria.
        if not df_aux.empty and "cod_categoria" in df.columns and "cod_categoria" in df_aux.columns:
            df = df.merge(
                df_aux[["cod_categoria", "meta", "descricao_categoria"]],
                on="cod_categoria",
                how="left",
            )
            df["meta"] = pd.to_numeric(df["meta"], errors="coerce").fillna(0)
        else:
            df["meta"]                = 0
            df["descricao_categoria"] = df.get("cod_categoria", pd.Series(dtype=str)).astype(str)

        # ── 6. Cálculos derivados ──────────────────────────────────────────
        if "valor" in df.columns and "meta" in df.columns:
            df["atingimento_pct"] = np.where(
                df["meta"] > 0,
                (df["valor"] / df["meta"] * 100).round(1),
                0.0,
            )

        # ── 7. Agrupamento por categoria ───────────────────────────────────
        grupos = []
        df_grupos = pd.DataFrame()
        if "cod_categoria" in df.columns and "valor" in df.columns:
            df_grupos = (
                df.groupby("cod_categoria")
                .agg(
                    qtd         = ("cod_categoria", "count"),
                    valor_total = ("valor", "sum"),
                    valor_medio = ("valor", "mean"),
                    valor_max   = ("valor", "max"),
                    meta_total  = ("meta",  "sum"),
                )
                .reset_index()
            )
            df_grupos["valor_medio"] = df_grupos["valor_medio"].round(2)
            df_grupos["atingimento_pct"] = np.where(
                df_grupos["meta_total"] > 0,
                (df_grupos["valor_total"] / df_grupos["meta_total"] * 100).round(1),
                0.0,
            )
            grupos = df_grupos.sort_values("valor_total", ascending=False).to_dict("records")

        # ── 8. Top 5 ──────────────────────────────────────────────────────
        cols_top = [c for c in ["nome", "cod_categoria", "valor", "meta", "atingimento_pct"] if c in df.columns]
        top5 = (
            df.nlargest(5, "valor")[cols_top].to_dict("records")
            if "valor" in df.columns
            else []
        )

        # ── 9. Resumo global ──────────────────────────────────────────────
        valor_total        = float(df["valor"].sum())  if "valor" in df.columns else 0.0
        meta_total         = float(df["meta"].sum())   if "meta"  in df.columns else 0.0
        atingimento_global = round(valor_total / meta_total * 100, 1) if meta_total > 0 else 0.0
        qtd_acima_meta     = int((df["atingimento_pct"] >= 100).sum()) if "atingimento_pct" in df.columns else 0

        resumo_global = {
            "valor_total":           valor_total,
            "meta_total":            meta_total,
            "atingimento_global_pct": atingimento_global,
            "qtd_total":             len(df),
            "qtd_acima_meta":        qtd_acima_meta,
            "qtd_abaixo_meta":       len(df) - qtd_acima_meta,
        }

        # ── 10. Gráficos ──────────────────────────────────────────────────
        grafico_barras = grafico_tendencia = grafico_pizza = grafico_agrupado = None
        try:
            if "nome" in df.columns and "valor" in df.columns and len(df) > 0:
                grafico_barras = _grafico_barras_horizontais(
                    df, "nome", "valor",
                    titulo=f"Valor por Registro — {periodo}",
                    col_meta="meta" if "meta" in df.columns else None,
                )

            if not df_serie.empty and "periodo" in df_serie.columns and "valor" in df_serie.columns:
                grafico_tendencia = _grafico_linha_tendencia(
                    df_serie, "periodo", "valor",
                    titulo=f"Tendência — {periodo}",
                )

            if not df_grupos.empty and "cod_categoria" in df_grupos.columns:
                grafico_pizza = _grafico_pizza(
                    df_grupos, "cod_categoria", "valor_total",
                    titulo="Distribuição por Categoria",
                )

            if not df_grupos.empty and "meta_total" in df_grupos.columns and df_grupos["meta_total"].sum() > 0:
                grafico_agrupado = _grafico_barras_agrupadas(
                    df_grupos, "cod_categoria", "valor_total", "meta_total",
                    titulo=f"Realizado vs Meta por Categoria — {periodo}",
                )
        except Exception:
            logger.exception("Erro ao gerar gráficos")

        # ── 11. Payload final ─────────────────────────────────────────────
        # 'resumo' vira o texto do WhatsApp na entrega (caption do PDF, ou a
        # mensagem inteira quando o destinatário usa formato 'resumo_texto').
        resumo = (
            f"Relatório {periodo}: {len(df)} registro(s), "
            f"R$ {valor_total:,.2f} — atingimento {atingimento_global:.0f}%"
        )

        return {
            "total":            len(df),
            "periodo":          periodo,
            "resumo":           resumo,
            "registros":        df.to_dict("records"),
            "grupos":           grupos,
            "top5":             top5,
            "resumo_global":    resumo_global,
            "grafico_barras":   grafico_barras,
            "grafico_tendencia": grafico_tendencia,
            "grafico_pizza":    grafico_pizza,
            "grafico_agrupado": grafico_agrupado,
        }
