-- =============================================================================
-- Queries do alerta: _modelo_alerta
-- =============================================================================
-- Multi-banco: Firebird (ERP) + PostgreSQL (nexus_metas)
--
-- REGRAS DO CARREGADOR:
--   - Cada query começa com "-- name: nome_da_query"
--   - Parâmetros nomeados: :nome_param (Firebird) ou %(nome_param)s (PostgreSQL)
--   - O processador escolhe a query certa pelo nome
-- =============================================================================


-- name: detectar_anomalias
-- ═══════════════════════════════════════════════════════════════════════════
-- FIREBIRD — ERP
-- Detecta registros que satisfazem a condição de alerta.
-- Parâmetros: :cod_empresa, :data_inicio (str 'YYYY-MM-DD')
--
-- DICAS FIREBIRD:
--   - Use ROWS 1 em vez de LIMIT 1
--   - EXTRACT(YEAR FROM campo) para filtrar por ano/mês
--   - DATEDIFF(DAY, data1, data2) para diferença em dias
--   - Casting: CAST(campo AS DECIMAL(15,2))
--   - Concatenação: campo1 || ' ' || campo2
-- ═══════════════════════════════════════════════════════════════════════════
SELECT
    p.COD_EMPRESA,
    p.PEDIDO,
    p.DATA,
    p.CODIC                     AS CODIGO_CLIENTE,
    cad.NOME                    AS NOME_CLIENTE,
    i.ITEM                      AS ITEM_PEDIDO,
    i.PRODUTO                   AS COD_PRODUTO,
    i.NOME                      AS PRODUTO,
    i.QUANTIDADE,
    i.VALOR_UNIT,
    i.VALOR_TOTAL               AS VALOR,
    i.COD_CATEGORIA,
    p.CODIV                     AS COD_VENDEDOR,
    v.NOME                      AS NOME_VENDEDOR,
    v.FONE1                     AS TELEFONE_VENDEDOR,
    v.FONE2                     AS TELEFONE_VENDEDOR2,
    v.EMAIL                     AS EMAIL_VENDEDOR
FROM ARQES13 p
JOIN ARQES15 i     ON i.PEDIDO  = p.PEDIDO
JOIN ARQCAD cad    ON cad.TIPOC = p.TIPOC   AND cad.CODIC = p.CODIC
LEFT JOIN ARQCAD v ON v.TIPOC   = p.TIPOV   AND v.CODIC   = p.CODIV
WHERE p.COD_EMPRESA = :cod_empresa
  AND p.DATA        >= :data_inicio
  AND p.SITU        <> 'C'
  -- Condição principal do alerta — adapte aqui:
  AND i.VALOR_TOTAL > 0   -- substitua pela condição real
ORDER BY p.DATA DESC, p.PEDIDO, i.ITEM;


-- name: buscar_configuracoes
-- ═══════════════════════════════════════════════════════════════════════════
-- POSTGRESQL — nexus_metas
-- Carrega limites/configurações por categoria do banco auxiliar.
-- Parâmetro: %(cod_empresa)s
--
-- DICAS POSTGRESQL:
--   - Parâmetros com %(nome)s (psycopg2) em vez de :nome (Firebird)
--   - Use TRUE/FALSE sem aspas
--   - ILIKE para busca case-insensitive
--   - ANY(:lista) para IN com lista Python
-- ═══════════════════════════════════════════════════════════════════════════
SELECT
    cod_categoria,
    descricao_categoria,
    limite,
    severidade,
    ativo
FROM configuracoes_alerta
WHERE cod_empresa = %(cod_empresa)s
  AND ativo = TRUE
ORDER BY cod_categoria;


-- name: buscar_contatos_notificacao
-- ═══════════════════════════════════════════════════════════════════════════
-- POSTGRESQL — nexus_metas
-- Retorna contatos que devem receber este alerta.
-- Parâmetro: %(cod_empresa)s
-- ═══════════════════════════════════════════════════════════════════════════
SELECT
    ca.nome,
    ca.setor,
    ca.email,
    ca.whatsapp,
    ca.tipo_notificacao     -- 'email' | 'whatsapp' | 'ambos'
FROM contatos_alertas ca
JOIN vinculos_alerta_contato vac ON vac.contato_id = ca.id
WHERE vac.nome_alerta = 'modelo_alerta'   -- substitua pelo nome real da pasta
  AND vac.cod_empresa  = %(cod_empresa)s
  AND ca.ativo         = TRUE
  AND ca.recebe_alerta = TRUE
ORDER BY ca.setor, ca.nome;
