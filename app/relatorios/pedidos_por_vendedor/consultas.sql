-- =============================================================================
-- Queries do relatorio: pedidos_por_vendedor
-- Fonte: ERP Firebird
-- Tabelas: ARQES13 (pedidos) + ARQES15 (itens) + ARQCAD (cadastro)
-- =============================================================================


-- name: pedidos_por_vendedor
-- FIREBIRD - ERP
-- Agrega pedidos nao cancelados por vendedor no periodo.
-- Retorna: qtd pedidos, valor total, ticket medio.
SELECT
    p.CODIV                       AS COD_VENDEDOR,
    TRIM(v.NOME)                  AS NOME_VENDEDOR,
    COUNT(DISTINCT p.PEDIDO)      AS QTD_PEDIDOS,
    SUM(p.TOTAL)                  AS VALOR_TOTAL,
    SUM(p.TOTAL) / COUNT(DISTINCT p.PEDIDO) AS TICKET_MEDIO
FROM ARQES13 p
LEFT JOIN ARQCAD v ON v.TIPOC = p.TIPOV AND v.CODIC = p.CODIV
WHERE p.COD_EMPRESA = :cod_empresa
  AND p.DATA >= :data_inicio
  AND p.DATA <= :data_fim
  AND p.SITU <> 'C'
GROUP BY p.CODIV, v.NOME
ORDER BY SUM(p.TOTAL) DESC;


-- name: top_produtos_por_vendedor
-- FIREBIRD - ERP
-- Top 5 produtos por valor total para cada vendedor no periodo.
-- Usa CTE + ROW_NUMBER() (Firebird 3.0+).
WITH vendas_prod AS (
    SELECT
        p.CODIV            AS COD_VENDEDOR,
        i.PRODUTO          AS COD_PRODUTO,
        TRIM(i.NOME)       AS NOME_PRODUTO,
        SUM(i.QTDE)        AS QTD_TOTAL,
        SUM(i.VTOTAL)      AS VALOR_TOTAL
    FROM ARQES13 p
    JOIN ARQES15 i ON i.PEDIDO = p.PEDIDO
    WHERE p.COD_EMPRESA = :cod_empresa
      AND p.DATA >= :data_inicio
      AND p.DATA <= :data_fim
      AND p.SITU <> 'C'
    GROUP BY p.CODIV, i.PRODUTO, i.NOME
),
ranked AS (
    SELECT
        COD_VENDEDOR,
        COD_PRODUTO,
        NOME_PRODUTO,
        QTD_TOTAL,
        VALOR_TOTAL,
        ROW_NUMBER() OVER (PARTITION BY COD_VENDEDOR ORDER BY VALOR_TOTAL DESC) AS POS
    FROM vendas_prod
)
SELECT COD_VENDEDOR, COD_PRODUTO, NOME_PRODUTO, QTD_TOTAL, VALOR_TOTAL, POS
FROM ranked
WHERE POS <= 5
ORDER BY COD_VENDEDOR, POS;
