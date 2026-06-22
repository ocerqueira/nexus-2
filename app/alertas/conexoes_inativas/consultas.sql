-- =============================================================================
-- Queries do alerta: conexoes_inativas
-- =============================================================================


-- name: verificar_conexoes_inativas
-- Verifica se há conexões cadastradas mas desativadas.
-- Se retornar linhas, o alerta deve disparar.
SELECT
    id,
    nome,
    tipo,
    host,
    porta,
    banco
FROM conexoes_bd
WHERE ativo = FALSE
ORDER BY nome;


-- name: verificar_conexoes_inativas_com_observacoes
-- Mesma query, mas incluindo o campo observacoes.
SELECT
    id,
    nome,
    tipo,
    host,
    porta,
    banco,
    observacoes
FROM conexoes_bd
WHERE ativo = FALSE
ORDER BY nome;
