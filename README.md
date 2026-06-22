chave_cript=VhruMtBADWONpWNyyOaik4RnYmwvkTdYtQ-4WFCWsP0=



INSERT INTO conexoes_bd (
    nome, tipo, host, porta, banco, usuario, senha_criptografada, observacoes
) VALUES (
    'nexus_proprio',
    'postgres',
    'localhost',
    5432,
    'nexus',
    'nexus_admin',
    'gAAAAABqOEIiO-KQJTvxKV_hdHKz7ISbzQQjanGtPXGQSkdkeQQP4xlCQFFPfclLWS3SIl0MPhZi_ehAx4lI7GA7ouRfyEtJsQ==',  -- COLE A SENHA CRIPTOGRAFADA AQUI
    'Conexão de teste apontando para o próprio banco do Nexus'
);
