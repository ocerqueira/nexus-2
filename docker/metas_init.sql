-- =============================================================================
-- Banco nexus_metas — schema + seed para desenvolvimento
-- =============================================================================

CREATE TABLE IF NOT EXISTS metas_vendedor (
    id           SERIAL PRIMARY KEY,
    cod_empresa  INTEGER NOT NULL DEFAULT 1,
    cod_vendedor INTEGER NOT NULL,
    nome_vendedor VARCHAR(200),
    ano          INTEGER NOT NULL,
    mes          INTEGER NOT NULL CHECK (mes BETWEEN 1 AND 12),
    meta_valor   NUMERIC(15,2) NOT NULL DEFAULT 0,
    meta_pedidos INTEGER NOT NULL DEFAULT 0,
    ativo        BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (cod_empresa, cod_vendedor, ano, mes)
);

CREATE INDEX IF NOT EXISTS idx_metas_periodo ON metas_vendedor(cod_empresa, ano, mes);
CREATE INDEX IF NOT EXISTS idx_metas_vendedor ON metas_vendedor(cod_vendedor);

-- =============================================================================
-- Seed — top vendedores do ERP (extraídos da consulta real jan/2025)
-- Cobre jan–jun 2025 para testes completos
-- =============================================================================

INSERT INTO metas_vendedor (cod_empresa, cod_vendedor, nome_vendedor, ano, mes, meta_valor, meta_pedidos) VALUES
-- Janeiro 2025
(1,    4, 'NOROACO',                          2025, 1,  8000000.00, 220),
(1,  578, 'DOUGLAS DONATO DA SILVA',          2025, 1,  2500000.00, 200),
(1, 1075, 'ODIRLEI RODRIGO KASCHUK',          2025, 1,  1800000.00, 110),
(1, 1098, 'NILSON RODRIGO DE OLIVEIRA',       2025, 1,  1500000.00, 100),
(1,  231, 'MAIZZENA FERRO E ACO REP COM LTDA',2025, 1,  1200000.00, 280),
(1,  420, 'CLENIO MARTINS DE LIMA',           2025, 1,  1300000.00, 130),
(1,  300, 'VENDEDOR 300',                     2025, 1,   800000.00,  80),
(1,  450, 'VENDEDOR 450',                     2025, 1,   600000.00,  60),
-- Fevereiro 2025
(1,    4, 'NOROACO',                          2025, 2,  8500000.00, 230),
(1,  578, 'DOUGLAS DONATO DA SILVA',          2025, 2,  2600000.00, 210),
(1, 1075, 'ODIRLEI RODRIGO KASCHUK',          2025, 2,  1900000.00, 115),
(1, 1098, 'NILSON RODRIGO DE OLIVEIRA',       2025, 2,  1600000.00, 105),
(1,  231, 'MAIZZENA FERRO E ACO REP COM LTDA',2025, 2,  1250000.00, 290),
(1,  420, 'CLENIO MARTINS DE LIMA',           2025, 2,  1350000.00, 135),
-- Março 2025
(1,    4, 'NOROACO',                          2025, 3,  9000000.00, 240),
(1,  578, 'DOUGLAS DONATO DA SILVA',          2025, 3,  2700000.00, 215),
(1, 1075, 'ODIRLEI RODRIGO KASCHUK',          2025, 3,  2000000.00, 120),
(1, 1098, 'NILSON RODRIGO DE OLIVEIRA',       2025, 3,  1700000.00, 110),
(1,  231, 'MAIZZENA FERRO E ACO REP COM LTDA',2025, 3,  1300000.00, 295),
(1,  420, 'CLENIO MARTINS DE LIMA',           2025, 3,  1400000.00, 140),
-- Abril 2025
(1,    4, 'NOROACO',                          2025, 4,  9000000.00, 240),
(1,  578, 'DOUGLAS DONATO DA SILVA',          2025, 4,  2700000.00, 215),
(1, 1075, 'ODIRLEI RODRIGO KASCHUK',          2025, 4,  2000000.00, 120),
(1, 1098, 'NILSON RODRIGO DE OLIVEIRA',       2025, 4,  1700000.00, 110),
(1,  231, 'MAIZZENA FERRO E ACO REP COM LTDA',2025, 4,  1300000.00, 295),
(1,  420, 'CLENIO MARTINS DE LIMA',           2025, 4,  1400000.00, 140),
-- Maio 2025
(1,    4, 'NOROACO',                          2025, 5,  9000000.00, 240),
(1,  578, 'DOUGLAS DONATO DA SILVA',          2025, 5,  2700000.00, 215),
(1, 1075, 'ODIRLEI RODRIGO KASCHUK',          2025, 5,  2000000.00, 120),
(1, 1098, 'NILSON RODRIGO DE OLIVEIRA',       2025, 5,  1700000.00, 110),
(1,  231, 'MAIZZENA FERRO E ACO REP COM LTDA',2025, 5,  1300000.00, 295),
(1,  420, 'CLENIO MARTINS DE LIMA',           2025, 5,  1400000.00, 140),
-- Junho 2025
(1,    4, 'NOROACO',                          2025, 6,  9000000.00, 240),
(1,  578, 'DOUGLAS DONATO DA SILVA',          2025, 6,  2700000.00, 215),
(1, 1075, 'ODIRLEI RODRIGO KASCHUK',          2025, 6,  2000000.00, 120),
(1, 1098, 'NILSON RODRIGO DE OLIVEIRA',       2025, 6,  1700000.00, 110),
(1,  231, 'MAIZZENA FERRO E ACO REP COM LTDA',2025, 6,  1300000.00, 295),
(1,  420, 'CLENIO MARTINS DE LIMA',           2025, 6,  1400000.00, 140)
ON CONFLICT (cod_empresa, cod_vendedor, ano, mes) DO NOTHING;
