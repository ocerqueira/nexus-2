-- =============================================================================
-- Queries do relatório: teste_conexoes
-- =============================================================================
-- Consulta o catálogo de conexões cadastradas no próprio Nexus.
-- =============================================================================


-- name: listar_todas_conexoes
-- Lista todas as conexões cadastradas, ativas ou não.
SELECT
    id,
    nome,
    tipo,
    host,
    porta,
    banco,
    usuario,
    observacoes,
    ativo,
    criado_em
FROM conexoes_bd
ORDER BY id;


-- name: listar_apenas_ativas
-- Lista somente conexões ativas.
SELECT
    id,
    nome,
    tipo,
    host,
    porta,
    banco,
    usuario,
    observacoes,
    criado_em
FROM conexoes_bd
WHERE ativo = TRUE
ORDER BY id;


-- name: filtrar_por_tipo
-- Filtra conexões por tipo de banco (postgres, firebird, mysql).
SELECT
    id,
    nome,
    tipo,
    host,
    porta,
    banco,
    ativo,
    observacoes
FROM conexoes_bd
WHERE tipo = :tipo_banco
ORDER BY id;


-- name: filtrar_ativas_por_tipo
-- Combina os dois filtros: apenas ativas + tipo específico.
SELECT
    id,
    nome,
    tipo,
    host,
    porta,
    banco,
    observacoes
FROM conexoes_bd
WHERE ativo = TRUE
  AND tipo = :tipo_banco
ORDER BY id;


-- name: contar_por_tipo
-- Conta quantas conexões existem por tipo de banco.
SELECT
    tipo,
    COUNT(*) AS total,
    COUNT(*) FILTER (WHERE ativo) AS ativas,
    COUNT(*) FILTER (WHERE NOT ativo) AS inativas
FROM conexoes_bd
GROUP BY tipo
ORDER BY tipo;
