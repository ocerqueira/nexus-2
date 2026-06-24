-- =============================================================================
-- nexus_metas — Banco auxiliar PostgreSQL
-- =============================================================================
-- Complementa o ERP (Firebird) com:
--   1. Limites configuráveis de comprimento por tipo de produto
--   2. Metas de vendedores (para relatórios de desempenho)
--   3. Contatos adicionais que recebem alertas (setores, gestores)
--   4. Mapeamento de empresas
-- =============================================================================

-- =============================================================================
-- TABELA: empresas
-- =============================================================================
CREATE TABLE IF NOT EXISTS empresas (
    id              SERIAL PRIMARY KEY,
    cod_empresa     INTEGER NOT NULL UNIQUE,
    nome            VARCHAR(100) NOT NULL,
    cnpj            VARCHAR(18),
    ativo           BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE empresas IS 'Cadastro de empresas para referência cruzada com ERP';

-- =============================================================================
-- TABELA: metas_vendedor
-- =============================================================================
CREATE TABLE IF NOT EXISTS metas_vendedor (
    id              SERIAL PRIMARY KEY,
    cod_empresa     INTEGER NOT NULL REFERENCES empresas(cod_empresa),
    cod_vendedor    DOUBLE PRECISION NOT NULL,
    nome_vendedor   VARCHAR(200),
    ano             INTEGER NOT NULL,
    mes             INTEGER NOT NULL CHECK (mes BETWEEN 1 AND 12),
    meta_valor      NUMERIC(15,2) NOT NULL,
    meta_pedidos    INTEGER,
    ativo           BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em   TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (cod_empresa, cod_vendedor, ano, mes)
);

CREATE INDEX IF NOT EXISTS idx_metas_vendedor_empresa ON metas_vendedor(cod_empresa, ano, mes);

COMMENT ON TABLE metas_vendedor IS 'Metas mensais de vendedores por empresa';

-- =============================================================================
-- TABELA: limites_produto
-- =============================================================================
CREATE TABLE IF NOT EXISTS limites_produto (
    id                  SERIAL PRIMARY KEY,
    cod_empresa         INTEGER NOT NULL REFERENCES empresas(cod_empresa),
    origem_medida       VARCHAR(10) NOT NULL,
    comprimento_max_mm  INTEGER NOT NULL,
    descricao           VARCHAR(200),
    severidade          VARCHAR(20) NOT NULL DEFAULT 'aviso'
                        CHECK (severidade IN ('info', 'aviso', 'critico')),
    ativo               BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em       TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (cod_empresa, origem_medida)
);

COMMENT ON TABLE limites_produto IS 'Limites de comprimento por origem de medida e empresa';

-- =============================================================================
-- TABELA: contatos_alertas
-- =============================================================================
CREATE TABLE IF NOT EXISTS contatos_alertas (
    id              SERIAL PRIMARY KEY,
    cod_empresa     INTEGER REFERENCES empresas(cod_empresa),
    nome            VARCHAR(200) NOT NULL,
    setor           VARCHAR(100),
    email           VARCHAR(255),
    whatsapp        VARCHAR(20),
    recebe_alerta   BOOLEAN NOT NULL DEFAULT TRUE,
    ativo           BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_contatos_alertas_empresa ON contatos_alertas(cod_empresa) WHERE ativo AND recebe_alerta;

COMMENT ON TABLE contatos_alertas IS 'Contatos de setores/gestores que recebem alertas além dos vendedores';

-- =============================================================================
-- TABELA: vinculos_alerta_setor
-- =============================================================================
CREATE TABLE IF NOT EXISTS vinculos_alerta_setor (
    id              SERIAL PRIMARY KEY,
    origem_medida   VARCHAR(10) NOT NULL,
    contato_id      INTEGER NOT NULL REFERENCES contatos_alertas(id) ON DELETE CASCADE,
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (origem_medida, contato_id)
);

COMMENT ON TABLE vinculos_alerta_setor IS 'Quais setores recebem alertas de quais origens de medida';


-- =============================================================================
-- SEED DATA
-- =============================================================================

-- Empresas
INSERT INTO empresas (cod_empresa, nome) VALUES
    (1, 'Cerâmica Principal'),
    (2, 'Filial Sul')
ON CONFLICT (cod_empresa) DO NOTHING;

-- Metas de vendedores (Julho/2026)
INSERT INTO metas_vendedor (cod_empresa, cod_vendedor, nome_vendedor, ano, mes, meta_valor, meta_pedidos) VALUES
    (1, 1, 'João Silva',      2026, 7, 250000.00, 40),
    (1, 2, 'Maria Oliveira',  2026, 7, 300000.00, 50),
    (1, 3, 'Carlos Santos',   2026, 7, 180000.00, 30),
    (1, 4, 'Ana Costa',       2026, 7, 220000.00, 35),
    (1, 5, 'Paulo Mendes',    2026, 7, 280000.00, 45)
ON CONFLICT (cod_empresa, cod_vendedor, ano, mes) DO NOTHING;

-- Limites de comprimento por origem de medida
INSERT INTO limites_produto (cod_empresa, origem_medida, comprimento_max_mm, descricao, severidade) VALUES
    (1, 'TELHA', 7500, 'Telhas não podem exceder 7,5 metros', 'critico'),
    (1, 'SBX',   6000, 'Peças SBX não podem exceder 6 metros', 'aviso')
ON CONFLICT (cod_empresa, origem_medida) DO NOTHING;

-- Contatos de setores que recebem alertas
INSERT INTO contatos_alertas (cod_empresa, nome, setor, email, whatsapp) VALUES
    (1, 'Roberto Expedição',    'Expedição',    'roberto.exp@ceramica.com.br', '5511999990001'),
    (1, 'Fernanda Qualidade',   'Qualidade',    'fernanda.qual@ceramica.com.br', '5511999990002'),
    (1, 'Marcos Logística',     'Logística',    'marcos.log@ceramica.com.br', '5511999990003'),
    (1, 'Diretoria Industrial', 'Diretoria',    'diretoria@ceramica.com.br', NULL)
ON CONFLICT DO NOTHING;

-- Vinculação: quais setores recebem alertas de quais origens
-- TELHA → Expedição + Qualidade + Diretoria
-- SBX   → Qualidade + Logística
INSERT INTO vinculos_alerta_setor (origem_medida, contato_id)
SELECT 'TELHA', id FROM contatos_alertas WHERE setor IN ('Expedição', 'Qualidade', 'Diretoria') AND cod_empresa = 1
ON CONFLICT (origem_medida, contato_id) DO NOTHING;

INSERT INTO vinculos_alerta_setor (origem_medida, contato_id)
SELECT 'SBX', id FROM contatos_alertas WHERE setor IN ('Qualidade', 'Logística') AND cod_empresa = 1
ON CONFLICT (origem_medida, contato_id) DO NOTHING;
