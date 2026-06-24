-- Queries do alerta: item_comprimento_excedente
-- Multi-banco: Firebird (ERP) + PostgreSQL (nexus_metas)


-- name: detectar_itens_comprimento_excedente
-- FIREBIRD - ERP
-- Detecta itens de telha/SBX com comprimento acima do limite.
-- Parametro data_inicio: data de corte (padrao: 30 dias atras via processador).
SELECT
    p.cod_empresa,
    c.SITUACAO,
    p.DATA,
    c.SEQCARGA,
    c.NROCARGA,
    p.codic             AS CODIGO_CLIENTE,
    cad.nome            AS NOME_CLIENTE,
    p.PEDIDO,
    i.ITEM              AS ITEM_PEDIDO,
    i.produto           AS COD_PRODUTO,
    i.NOME              AS PRODUTO,
    it.COMPRIMENTO,
    p.CODIV             AS COD_VENDEDOR,
    v.NOME              AS NOME_VENDEDOR,
    v.fone1             AS TELEFONE_VENDEDOR,
    v.fone2             AS TELEFONE_VENDEDOR2,
    'TELHA'             AS ORIGEM_MEDIDA
FROM VD_CARGA c
JOIN VD_CARGADEF cd    ON cd.SEQCARGA = c.SEQCARGA AND cd.TIPO = 'E'
JOIN ARQES13 p         ON p.PEDIDO   = cd.PROCESSO
JOIN ARQES15 i         ON i.PEDIDO   = p.PEDIDO
JOIN ARQCAD cad        ON cad.TIPOC  = p.TIPOC AND cad.CODIC = p.CODIC
JOIN ARQ_ITENS_DEF_TELHA it
        ON it.ORIGEM = 'PDE' AND it.COD_LINK = i.SEQLANC
LEFT JOIN ARQCAD v     ON v.TIPOC = p.TIPOV AND v.CODIC = p.CODIV
WHERE c.SITUACAO = 2
  AND (it.COMPRIMENTO          > 7500
    OR it.COMPRIMENTO_SUPERIOR > 7500
    OR it.COMPRIMENTO_INFERIOR > 7500)
  AND p.data >= :data_inicio
  AND c.cod_empresa = :cod_empresa

UNION ALL

SELECT
    p.cod_empresa,
    c.SITUACAO,
    p.DATA,
    c.SEQCARGA,
    c.NROCARGA,
    p.codic             AS CODIGO_CLIENTE,
    cad.nome            AS NOME_CLIENTE,
    p.PEDIDO,
    i.ITEM              AS ITEM_PEDIDO,
    i.produto           AS COD_PRODUTO,
    i.NOME,
    cp.COMPRIMENTO,
    p.CODIV             AS COD_VENDEDOR,
    v.NOME              AS NOME_VENDEDOR,
    v.fone1             AS TELEFONE_VENDEDOR,
    v.fone2             AS TELEFONE_VENDEDOR2,
    'SBX'
FROM VD_CARGA c
JOIN VD_CARGADEF cd    ON cd.SEQCARGA = c.SEQCARGA AND cd.TIPO = 'E'
JOIN ARQES13 p         ON p.PEDIDO   = cd.PROCESSO
JOIN ARQES15 i         ON i.PEDIDO   = p.PEDIDO
JOIN ARQCAD cad        ON cad.TIPOC  = p.TIPOC AND cad.CODIC = p.CODIC
JOIN PCP_FA_CALC_PESO cp ON cp.COD_LINK = i.SEQLANC
LEFT JOIN ARQCAD v     ON v.TIPOC = p.TIPOV AND v.CODIC = p.CODIV
WHERE c.SITUACAO = 2
  AND cp.COMPRIMENTO > 6000
  AND p.data >= :data_inicio
  AND c.cod_empresa = :cod_empresa

ORDER BY 1, 3, 4;


-- name: buscar_limites_configurados
-- POSTGRESQL - nexus_metas
SELECT
    origem_medida,
    comprimento_max_mm,
    descricao,
    severidade
FROM limites_produto
WHERE cod_empresa = :cod_empresa
  AND ativo = TRUE
ORDER BY origem_medida;


-- name: buscar_contatos_setores
-- POSTGRESQL - nexus_metas
SELECT DISTINCT
    v.origem_medida,
    ca.nome,
    ca.setor,
    ca.email,
    ca.whatsapp
FROM vinculos_alerta_setor v
JOIN contatos_alertas ca ON ca.id = v.contato_id
WHERE v.origem_medida = ANY(:origens)
  AND ca.ativo = TRUE
  AND ca.recebe_alerta = TRUE
ORDER BY v.origem_medida, ca.setor;
