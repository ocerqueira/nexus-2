-- Despachos de teste para relatórios
-- Executa no banco local (nexus-pg-local:5433)
-- Usa primeiro relatório e primeiro usuário ativo com destino configurado

-- 1. WP texto (resumo do relatório)
INSERT INTO despachos (tipo_recurso, recurso_id, usuario_id, canal, destino, payload, status, relatorio_nome)
SELECT
  'relatorio',
  r.id,
  u.id,
  'whatsapp',
  u.whatsapp,
  jsonb_build_object(
    'mensagem',
    '📊 *' || r.nome || '*' || chr(10) || chr(10) ||
    'Relatório de teste gerado em ' || TO_CHAR(NOW(), 'DD/MM/YYYY HH24:MI') || chr(10) ||
    chr(10) || '• Registros: 42' || chr(10) || '• Total: R$ 12.345,00'
  ),
  'pendente',
  r.nome
FROM relatorios r
CROSS JOIN usuarios u
WHERE u.whatsapp IS NOT NULL AND u.whatsapp != '' AND u.ativo = true
LIMIT 1;

-- 2. Email com HTML (sem PDF)
INSERT INTO despachos (tipo_recurso, recurso_id, usuario_id, canal, destino, payload, status, relatorio_nome)
SELECT
  'relatorio',
  r.id,
  u.id,
  'email',
  u.email,
  jsonb_build_object(
    'assunto', '[TESTE] ' || r.nome || ' — ' || TO_CHAR(NOW(), 'DD/MM/YYYY'),
    'html', '<h2 style="font-family:sans-serif">' || r.nome || '</h2>' ||
            '<p style="font-family:sans-serif">Relatório de teste gerado em ' ||
            TO_CHAR(NOW(), 'DD/MM/YYYY HH24:MI') || '</p>' ||
            '<table border="1" cellpadding="6" style="border-collapse:collapse;font-family:sans-serif">' ||
            '<tr><th>Vendedor</th><th>Pedidos</th><th>Total</th></tr>' ||
            '<tr><td>João Silva</td><td>15</td><td>R$ 4.500,00</td></tr>' ||
            '<tr><td>Maria Souza</td><td>27</td><td>R$ 7.845,00</td></tr>' ||
            '</table>'
  ),
  'pendente',
  r.nome
FROM relatorios r
CROSS JOIN usuarios u
WHERE u.email IS NOT NULL AND u.email != '' AND u.ativo = true
LIMIT 1;

-- Verifica o que foi inserido
SELECT id, tipo_recurso, recurso_id, canal, destino, status, relatorio_nome
FROM despachos
WHERE tipo_recurso = 'relatorio'
ORDER BY id DESC
LIMIT 5;
