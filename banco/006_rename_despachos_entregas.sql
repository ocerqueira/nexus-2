-- Renomeia tabela despachos → entregas e artefatos relacionados.
-- Idempotente: trata 3 estados possíveis após 005_dispatch_refactor.sql rodar.

DO $$
BEGIN
    IF EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = 'despachos')
       AND NOT EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = 'entregas') THEN
        -- Estado 1 (primeira execução): despachos existe, entregas não → renomear
        ALTER TABLE despachos RENAME TO entregas;

        ALTER SEQUENCE IF EXISTS despachos_id_seq RENAME TO entregas_id_seq;

        ALTER INDEX IF EXISTS despachos_pkey                RENAME TO entregas_pkey;
        ALTER INDEX IF EXISTS idx_despachos_pendentes       RENAME TO idx_entregas_pendentes;
        ALTER INDEX IF EXISTS idx_despachos_historico       RENAME TO idx_entregas_historico;
        ALTER INDEX IF EXISTS idx_despachos_usuario         RENAME TO idx_entregas_usuario;
        ALTER INDEX IF EXISTS idx_despachos_alerta          RENAME TO idx_entregas_alerta;
        ALTER INDEX IF EXISTS idx_despachos_relatorio       RENAME TO idx_entregas_relatorio;

    ELSIF EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = 'despachos')
          AND EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = 'entregas') THEN
        -- Estado 2 (reinício): 005 recriou despachos vazia, entregas já tem os dados reais → dropar a casca vazia
        DROP TABLE despachos;
    END IF;

    -- Estado 3: só entregas existe (ou nenhuma) → nada a fazer
END $$;
