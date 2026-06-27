-- Renomeia tabela despachos → entregas e artefatos relacionados.

ALTER TABLE despachos RENAME TO entregas;

ALTER SEQUENCE IF EXISTS despachos_id_seq RENAME TO entregas_id_seq;

ALTER INDEX IF EXISTS despachos_pkey RENAME TO entregas_pkey;
ALTER INDEX IF EXISTS despachos_alerta_id_idx RENAME TO entregas_alerta_id_idx;
ALTER INDEX IF EXISTS despachos_relatorio_id_idx RENAME TO entregas_relatorio_id_idx;
ALTER INDEX IF EXISTS despachos_status_idx RENAME TO entregas_status_idx;
ALTER INDEX IF EXISTS despachos_usuario_id_idx RENAME TO entregas_usuario_id_idx;
ALTER INDEX IF EXISTS despachos_canal_idx RENAME TO entregas_canal_idx;
ALTER INDEX IF EXISTS despachos_criado_em_idx RENAME TO entregas_criado_em_idx;
