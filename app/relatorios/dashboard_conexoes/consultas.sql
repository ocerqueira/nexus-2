-- =============================================================================
-- Queries do relatório: dashboard_conexoes
-- =============================================================================
-- Demonstra múltiplas queries para alimentar pandas + matplotlib.
-- =============================================================================


-- name: listar_conexoes_completas
-- Lista todas as conexões com status, tipo e observações.
SELECT
    id,
    nome,
    tipo,
    host,
    porta,
    banco,
    usuario,
    ativo,
    observacoes,
    criado_em
FROM conexoes_bd
ORDER BY tipo, nome;


-- name: listar_apenas_ativas
-- Filtra apenas conexões ativas.
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
ORDER BY tipo, nome;


-- name: filtrar_por_tipo
-- Filtra por tipo de banco específico.
SELECT
    id,
    nome,
    tipo,
    host,
    porta,
    banco,
    usuario,
    ativo,
    observacoes,
    criado_em
FROM conexoes_bd
WHERE tipo = :tipo_banco
ORDER BY nome;


-- name: filtrar_ativas_por_tipo
-- Apenas ativas de um tipo específico.
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
  AND tipo = :tipo_banco
ORDER BY nome;


-- name: agregar_por_tipo_status
-- Contagem agregada por tipo e status para gráficos.
SELECT
    tipo,
    COUNT(*) AS total,
    COUNT(*) FILTER (WHERE ativo) AS ativas,
    COUNT(*) FILTER (WHERE NOT ativo) AS inativas
FROM conexoes_bd
GROUP BY tipo
ORDER BY tipo;


-- name: agregar_por_tipo_status_filtrado
-- Agregação filtrada por tipo de banco.
SELECT
    tipo,
    COUNT(*) AS total,
    COUNT(*) FILTER (WHERE ativo) AS ativas,
    COUNT(*) FILTER (WHERE NOT ativo) AS inativas
FROM conexoes_bd
WHERE tipo = :tipo_banco
GROUP BY tipo
ORDER BY tipo;
