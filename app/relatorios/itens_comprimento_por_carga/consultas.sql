-- Consultas do relatorio: itens_comprimento_por_carga
-- Fonte: ERP Firebird


-- name: itens_comprimento_por_carga
-- Itens de telha e SBX com comprimento acima do limite, agrupados por carga.
-- Parametros: :data_inicio, :data_fim, :cod_empresa
SELECT
    c.SEQCARGA,
    c.NROCARGA,
    c.NOME_CARGA,
    c.DT_SAIDA,
    p.PEDIDO,
    i.ITEM              AS ITEM_PEDIDO,
    i.produto           AS COD_PRODUTO,
    i.NOME              AS PRODUTO,
    p.codic             AS CODIGO_CLIENTE,
    cad.nome            AS NOME_CLIENTE,
    p.CODIV             AS COD_VENDEDOR,
    v.NOME              AS NOME_VENDEDOR,
    it.COMPRIMENTO,
    it.COMPRIMENTO_SUPERIOR,
    it.COMPRIMENTO_INFERIOR,
    7500                AS LIMITE_MM,
    'TELHA'             AS ORIGEM_MEDIDA
FROM VD_CARGA c
JOIN VD_CARGADEF cd     ON cd.SEQCARGA = c.SEQCARGA AND cd.TIPO = 'E'
JOIN ARQES13 p          ON p.PEDIDO    = cd.PROCESSO
JOIN ARQES15 i          ON i.PEDIDO    = p.PEDIDO
JOIN ARQCAD cad         ON cad.TIPOC   = p.TIPOC AND cad.CODIC = p.CODIC
JOIN ARQ_ITENS_DEF_TELHA it
                        ON it.ORIGEM   = 'PDE' AND it.COD_LINK = i.SEQLANC
LEFT JOIN ARQCAD v      ON v.TIPOC     = p.TIPOV AND v.CODIC   = p.CODIV
WHERE c.SITUACAO    = 2
  AND (   it.COMPRIMENTO          > 7500
       OR it.COMPRIMENTO_SUPERIOR > 7500
       OR it.COMPRIMENTO_INFERIOR > 7500)
  AND c.DT_SAIDA >= :data_inicio
  AND c.DT_SAIDA <= :data_fim
  AND c.cod_empresa = :cod_empresa

UNION ALL

SELECT
    c.SEQCARGA,
    c.NROCARGA,
    c.NOME_CARGA,
    c.DT_SAIDA,
    p.PEDIDO,
    i.ITEM              AS ITEM_PEDIDO,
    i.produto           AS COD_PRODUTO,
    i.NOME              AS PRODUTO,
    p.codic             AS CODIGO_CLIENTE,
    cad.nome            AS NOME_CLIENTE,
    p.CODIV             AS COD_VENDEDOR,
    v.NOME              AS NOME_VENDEDOR,
    cp.COMPRIMENTO,
    NULL                AS COMPRIMENTO_SUPERIOR,
    NULL                AS COMPRIMENTO_INFERIOR,
    6000                AS LIMITE_MM,
    'SBX'               AS ORIGEM_MEDIDA
FROM VD_CARGA c
JOIN VD_CARGADEF cd     ON cd.SEQCARGA = c.SEQCARGA AND cd.TIPO = 'E'
JOIN ARQES13 p          ON p.PEDIDO    = cd.PROCESSO
JOIN ARQES15 i          ON i.PEDIDO    = p.PEDIDO
JOIN ARQCAD cad         ON cad.TIPOC   = p.TIPOC AND cad.CODIC = p.CODIC
JOIN PCP_FA_CALC_PESO cp ON cp.COD_LINK = i.SEQLANC
LEFT JOIN ARQCAD v      ON v.TIPOC     = p.TIPOV AND v.CODIC   = p.CODIV
WHERE c.SITUACAO    = 2
  AND cp.COMPRIMENTO > 6000
  AND c.DT_SAIDA >= :data_inicio
  AND c.DT_SAIDA <= :data_fim
  AND c.cod_empresa = :cod_empresa

ORDER BY 1, 5, 6
