"""
Processador do relatório: itens_comprimento_por_carga
Fonte: ERP Firebird — itens de telha/SBX com comprimento excedente, por carga.
"""

import logging
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from app.core.carregador_sql import carregar_query
from app.core.gerenciador_conexoes import gerenciador_conexoes

logger = logging.getLogger(__name__)

ARQUIVO_CONSULTAS = Path(__file__).parent / "consultas.sql"
CONEXAO_ERP = "REPLICA_TERRA"


def _dia_util_anterior(referencia: date | None = None) -> date:
    d = (referencia or date.today()) - timedelta(days=1)
    while d.weekday() >= 5:  # 5=sábado, 6=domingo
        d -= timedelta(days=1)
    return d


class ProcessadorItensComprimentoPorCarga:
    """Itens com comprimento excedente consolidados por carga."""

    @staticmethod
    def validar(parametros: dict) -> tuple[bool, str]:
        for campo in ("data_inicio", "data_fim"):
            valor = parametros.get(campo)
            if valor:
                try:
                    datetime.strptime(str(valor), "%Y-%m-%d")
                except ValueError:
                    return False, f"'{campo}' deve estar no formato AAAA-MM-DD"

        data_inicio = parametros.get("data_inicio")
        data_fim = parametros.get("data_fim")
        if data_inicio and data_fim and str(data_inicio) > str(data_fim):
            return False, "'data_inicio' não pode ser posterior a 'data_fim'"

        if "cod_empresa" in parametros:
            cod = parametros["cod_empresa"]
            if not isinstance(cod, int) or cod < 1:
                return False, "'cod_empresa' deve ser inteiro positivo"

        return True, ""

    @staticmethod
    def buscar_dados(parametros: dict) -> dict[str, Any]:
        cod_empresa = parametros.get("cod_empresa", 1)
        data_inicio = parametros.get("data_inicio") or _dia_util_anterior().isoformat()
        data_fim = parametros.get("data_fim") or data_inicio

        linhas = gerenciador_conexoes.executar(
            conexao=CONEXAO_ERP,
            query=carregar_query(ARQUIVO_CONSULTAS, "itens_comprimento_por_carga"),
            parametros={"cod_empresa": cod_empresa, "data_inicio": data_inicio, "data_fim": data_fim},
        )

        df = pd.DataFrame(linhas)

        if df.empty:
            return {
                "total_cargas": 0,
                "total_itens": 0,
                "maior_comprimento_m": 0.0,
                "cargas": [],
                "periodo": f"{data_inicio} a {data_fim}",
            }

        df.columns = [c.lower() for c in df.columns]

        for col in ("comprimento", "comprimento_superior", "comprimento_inferior", "limite_mm"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

        # Comprimento efetivo: maior entre os três campos disponíveis
        df["comprimento_efetivo"] = df[["comprimento", "comprimento_superior", "comprimento_inferior"]].max(axis=1)
        df["comprimento_m"] = (df["comprimento_efetivo"] / 1000).round(2)
        df["excedente_m"] = ((df["comprimento_efetivo"] - df["limite_mm"]) / 1000).round(2)

        # Colunas inteiras que o Firebird/pandas entrega como float (evita "123.0")
        for col in ("pedido", "item_pedido", "seqcarga", "nrocarga", "codigo_cliente", "cod_vendedor"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

        # Dedup: mesmo pedido+item em múltiplas linhas (ex: TELHA e SBX) — mantém maior comprimento
        df = (
            df.sort_values("comprimento_efetivo", ascending=False)
              .drop_duplicates(subset=["seqcarga", "pedido", "item_pedido"], keep="first")
        )

        # Limpar strings
        for col in ("nome_carga", "nome_cliente", "nome_vendedor", "produto", "origem_medida"):
            if col in df.columns:
                df[col] = df[col].fillna("").astype(str).str.strip()

        # Agrupar por carga
        cargas_dict: dict = defaultdict(lambda: {"itens": [], "comprimento_max": 0.0})

        for _, row in df.iterrows():
            seq = int(row["seqcarga"])
            carga = cargas_dict[seq]
            carga["seqcarga"] = seq
            carga["nrocarga"] = str(row.get("nrocarga", "")).strip()
            carga["nome_carga"] = str(row.get("nome_carga", "")).strip()
            dt_saida = row.get("dt_saida")
            if dt_saida and hasattr(dt_saida, "strftime"):
                carga["dt_saida"] = dt_saida.strftime("%d/%m/%Y")
            else:
                carga["dt_saida"] = str(dt_saida) if dt_saida else ""

            comprimento_m = float(row["comprimento_m"])
            if comprimento_m > carga["comprimento_max"]:
                carga["comprimento_max"] = comprimento_m

            carga["itens"].append({
                "pedido": str(row.get("pedido", "")).strip(),
                "item_pedido": str(row.get("item_pedido", "")).strip(),
                "cod_produto": str(row.get("cod_produto", "")).strip(),
                "produto": str(row.get("produto", "")).strip(),
                "codigo_cliente": str(row.get("codigo_cliente", "")).strip(),
                "nome_cliente": str(row.get("nome_cliente", "")).strip(),
                "cod_vendedor": str(row.get("cod_vendedor", "")).strip(),
                "nome_vendedor": str(row.get("nome_vendedor", "")).strip() or "—",
                "origem_medida": str(row.get("origem_medida", "")).strip(),
                "comprimento_m": comprimento_m,
                "excedente_m": float(row["excedente_m"]),
                "limite_mm": int(row.get("limite_mm", 0)),
            })

        # Ordenar cargas por número e itens por pedido/item
        cargas = sorted(cargas_dict.values(), key=lambda c: c["nrocarga"])
        for carga in cargas:
            carga["total_itens"] = len(carga["itens"])
            carga["itens"].sort(key=lambda i: (i["pedido"], i["item_pedido"]))

        maior_comprimento_m = float(df["comprimento_m"].max())

        return {
            "total_cargas": len(cargas),
            "total_itens": len(df),
            "maior_comprimento_m": round(maior_comprimento_m, 2),
            "cargas": cargas,
            "periodo": f"{data_inicio} a {data_fim}",
        }
