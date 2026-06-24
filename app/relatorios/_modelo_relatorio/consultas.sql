-- =============================================================================
-- Queries do relatório: _modelo_relatorio
-- =============================================================================
-- Multi-banco: Firebird (ERP) + PostgreSQL (nexus_metas)
--
-- REGRAS DO CARREGADOR:
--   - Cada query começa com "-- name: nome_da_query"
--   - Parâmetros: :nome (Firebird) | %(nome)s (PostgreSQL)
-- =============================================================================


-- name: dados_principais
-- ═══════════════════════════════════════════════════════════════════════════
-- FIREBIRD — ERP
-- Dados detalhados do período. Um registro por linha do relatório.
-- Parâmetros: :cod_empresa, :ano, :mes
-- ═══════════════════════════════════════════════════════════════════════════
SELECT
    p.COD_EMPRESA,
    p.PEDIDO,
    p.DATA,
    p.CODIC                         AS CODIGO_CLIENTE,
    cad.NOME                        AS NOME,
    i.PRODUTO                       AS COD_PRODUTO,
    i.NOME                          AS PRODUTO,
    i.QUANTIDADE,
    i.VALOR_UNIT,
    i.VALOR_TOTAL                   AS VALOR,
    i.COD_CATEGORIA,
    p.CODIV                         AS COD_VENDEDOR,
    v.NOME                          AS NOME_VENDEDOR,
    COUNT(DISTINCT p.PEDIDO)
        OVER (PARTITION BY p.CODIV) AS PEDIDOS_VENDEDOR
FROM ARQES13 p
JOIN ARQES15 i     ON i.PEDIDO  = p.PEDIDO
JOIN ARQCAD cad    ON cad.TIPOC = p.TIPOC AND cad.CODIC = p.CODIC
LEFT JOIN ARQCAD v ON v.TIPOC   = p.TIPOV AND v.CODIC   = p.CODIV
WHERE p.COD_EMPRESA = :cod_empresa
  AND EXTRACT(YEAR  FROM p.DATA) = :ano
  AND EXTRACT(MONTH FROM p.DATA) = :mes
  AND p.SITU <> 'C'
ORDER BY i.VALOR_TOTAL DESC, p.PEDIDO, i.ITEM;


-- name: serie_temporal
-- ═══════════════════════════════════════════════════════════════════════════
-- FIREBIRD — ERP
-- Agrega por dia para gráfico de tendência.
-- Parâmetros: :cod_empresa, :ano, :mes
-- ═══════════════════════════════════════════════════════════════════════════
SELECT
    EXTRACT(DAY FROM p.DATA)    AS PERIODO,
    COUNT(DISTINCT p.PEDIDO)    AS QTD_PEDIDOS,
    SUM(i.VALOR_TOTAL)          AS VALOR
FROM ARQES13 p
JOIN ARQES15 i ON i.PEDIDO = p.PEDIDO
WHERE p.COD_EMPRESA = :cod_empresa
  AND EXTRACT(YEAR  FROM p.DATA) = :ano
  AND EXTRACT(MONTH FROM p.DATA) = :mes
  AND p.SITU <> 'C'
GROUP BY EXTRACT(DAY FROM p.DATA)
ORDER BY PERIODO;


-- name: dados_auxiliares
-- ═══════════════════════════════════════════════════════════════════════════
-- POSTGRESQL — nexus_metas
-- Metas/referências por categoria para join cross-database.
-- Parâmetros: %(cod_empresa)s, %(ano)s, %(mes)s
-- ═══════════════════════════════════════════════════════════════════════════
SELECT
    cod_categoria,
    descricao_categoria,
    meta,
    meta_quantidade,
    ativo
FROM metas_categoria
WHERE cod_empresa = %(cod_empresa)s
  AND ano         = %(ano)s
  AND mes         = %(mes)s
  AND ativo       = TRUE
ORDER BY cod_categoria;
