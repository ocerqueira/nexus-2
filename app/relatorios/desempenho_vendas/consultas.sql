-- =============================================================================
-- Queries do relatório: desempenho_vendas
-- =============================================================================
-- Multi-banco: Firebird (ERP) + PostgreSQL (nexus_metas)
-- =============================================================================


-- name: vendas_por_vendedor
-- ═══════════════════════════════════════════════════════════════════════════
-- FIREBIRD — ERP
-- Total de vendas por vendedor no período (mês atual).
-- Soma TOTAL dos pedidos (ARQES13) agrupados por vendedor.
-- ═══════════════════════════════════════════════════════════════════════════
SELECT
    p.CODIV                 AS COD_VENDEDOR,
    v.NOME                  AS NOME_VENDEDOR,
    COUNT(DISTINCT p.PEDIDO) AS QTD_PEDIDOS,
    SUM(p.TOTAL)            AS TOTAL_VENDIDO
FROM ARQES13 p
LEFT JOIN ARQCAD v ON v.TIPOC = p.TIPOV AND v.CODIC = p.CODIV
WHERE p.COD_EMPRESA = :cod_empresa
  AND EXTRACT(YEAR FROM p.DATA) = :ano
  AND EXTRACT(MONTH FROM p.DATA) = :mes
  AND p.SITU <> 'C'
GROUP BY p.CODIV, v.NOME
ORDER BY TOTAL_VENDIDO DESC;


-- name: vendas_diarias
-- ═══════════════════════════════════════════════════════════════════════════
-- FIREBIRD — ERP
-- Vendas diárias do mês (para gráfico de tendência).
-- ═══════════════════════════════════════════════════════════════════════════
SELECT
    EXTRACT(DAY FROM p.DATA)    AS DIA,
    COUNT(DISTINCT p.PEDIDO)    AS QTD_PEDIDOS,
    SUM(p.TOTAL)                AS TOTAL_VENDIDO
FROM ARQES13 p
WHERE p.COD_EMPRESA = :cod_empresa
  AND EXTRACT(YEAR FROM p.DATA) = :ano
  AND EXTRACT(MONTH FROM p.DATA) = :mes
  AND p.SITU <> 'C'
GROUP BY EXTRACT(DAY FROM p.DATA)
ORDER BY DIA;


-- name: metas_vendedor
-- ═══════════════════════════════════════════════════════════════════════════
-- POSTGRESQL — nexus_metas
-- Metas mensais dos vendedores.
-- ═══════════════════════════════════════════════════════════════════════════
SELECT
    cod_vendedor,
    nome_vendedor,
    meta_valor,
    meta_pedidos
FROM metas_vendedor
WHERE cod_empresa = :cod_empresa
  AND ano = :ano
  AND mes = :mes
  AND ativo = TRUE
ORDER BY meta_valor DESC;
