-- =============================================================================
-- Migration 005b: Migrar alertas_condicoes → novas tabelas + DROP
-- =============================================================================
-- PRÉ-REQUISITO: 005_dispatch_refactor.sql já executado.
--
-- Sequência:
--   1. Copiar cooldown + ultimo_disparo para alertas
--   2. Migrar destinatários para alertas_destinatarios
--   3. Validar (ver SELECT abaixo)
--   4. DROP alertas_condicoes (descomentar quando validado)
-- =============================================================================


-- ─────────────────────────────────────────────────────────────────────────────
-- PASSO 1: Cooldown → alertas.cooldown_minutos
-- Usa o maior cooldown entre as condições do alerta (comportamento mais restritivo)
-- ─────────────────────────────────────────────────────────────────────────────

UPDATE alertas a
SET cooldown_minutos = sub.max_cooldown
FROM (
    SELECT alerta_id, MAX(cooldown_minutos) AS max_cooldown
    FROM alertas_condicoes
    WHERE ativo = TRUE
    GROUP BY alerta_id
) sub
WHERE a.id = sub.alerta_id;


-- ─────────────────────────────────────────────────────────────────────────────
-- PASSO 2: ultimo_disparo → alertas.ultimo_disparo
-- Pega o mais recente entre todas as condições
-- ─────────────────────────────────────────────────────────────────────────────

UPDATE alertas a
SET ultimo_disparo = sub.ultimo
FROM (
    SELECT alerta_id, MAX(ultimo_disparo) AS ultimo
    FROM alertas_condicoes
    WHERE ultimo_disparo IS NOT NULL
    GROUP BY alerta_id
) sub
WHERE a.id = sub.alerta_id;


-- ─────────────────────────────────────────────────────────────────────────────
-- PASSO 3: Destinatários → alertas_destinatarios
-- alertas_condicoes.destinatarios = [{"usuario_id": 1}, ...]
-- alertas_condicoes.canais        = ["whatsapp", "email"]
-- ─────────────────────────────────────────────────────────────────────────────

INSERT INTO alertas_destinatarios (alerta_id, usuario_id, canais, modo_mensagem, ativo)
SELECT DISTINCT ON (ac.alerta_id, (dest->>'usuario_id')::INTEGER)
    ac.alerta_id,
    (dest->>'usuario_id')::INTEGER AS usuario_id,
    ac.canais,
    'individual' AS modo_mensagem,
    ac.ativo
FROM alertas_condicoes ac
CROSS JOIN LATERAL jsonb_array_elements(ac.destinatarios) AS dest
WHERE dest->>'usuario_id' IS NOT NULL
  AND (dest->>'usuario_id')::INTEGER IN (SELECT id FROM usuarios WHERE ativo = TRUE)
ORDER BY ac.alerta_id, (dest->>'usuario_id')::INTEGER, ac.ativo DESC
ON CONFLICT (alerta_id, usuario_id) DO UPDATE
    SET canais    = EXCLUDED.canais,
        ativo     = EXCLUDED.ativo;


-- ─────────────────────────────────────────────────────────────────────────────
-- VALIDAÇÃO: executar e conferir antes do DROP
-- ─────────────────────────────────────────────────────────────────────────────

SELECT
    a.nome                             AS alerta,
    a.cooldown_minutos                 AS cooldown_migrado,
    a.ultimo_disparo                   AS ultimo_disparo_migrado,
    COUNT(ad.id)                       AS destinatarios_migrados,
    STRING_AGG(u.nome, ', ')           AS nomes_destinatarios
FROM alertas a
LEFT JOIN alertas_destinatarios ad ON ad.alerta_id = a.id
LEFT JOIN usuarios u               ON u.id = ad.usuario_id
GROUP BY a.id, a.nome, a.cooldown_minutos, a.ultimo_disparo
ORDER BY a.nome;


-- ─────────────────────────────────────────────────────────────────────────────
-- PASSO 4: DROP alertas_condicoes
-- Descomentar APENAS após validar o SELECT acima
-- ─────────────────────────────────────────────────────────────────────────────

-- DROP TABLE alertas_condicoes;
