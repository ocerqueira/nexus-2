-- Despachos de teste para relatórios (schema real: alerta_id/relatorio_id)
-- usuario_id=2 (Lucas Cerqueira), relatorio_id=4 (pedidos_por_vendedor)

-- Reset entregas anteriores que falharam
UPDATE entregas
SET status = 'pendente', tentativas = 0, ultimo_erro = NULL
WHERE status = 'falhou';

-- 1. WP texto (resumo do relatório)
INSERT INTO entregas (relatorio_id, usuario_id, canal, destino, payload, status)
VALUES (
  4,
  2,
  'whatsapp',
  '5517997685182',
  jsonb_build_object(
    'mensagem',
    E'📊 *Pedidos por Vendedor*\n\nRelatório de teste gerado agora.\n\n• Vendedor: João Silva — 15 pedidos — R$ 4.500,00\n• Vendedor: Maria Souza — 27 pedidos — R$ 7.845,00\n\n*Total: R$ 12.345,00*'
  ),
  'pendente'
);

-- 2. Email HTML (usa email hardcoded pois usuarios não têm email no banco local)
INSERT INTO entregas (relatorio_id, usuario_id, canal, destino, payload, status)
VALUES (
  4,
  2,
  'email',
  'lucacersan@gmail.com',
  jsonb_build_object(
    'assunto', '[TESTE] Pedidos por Vendedor',
    'html', '<h2 style="font-family:sans-serif">Pedidos por Vendedor</h2><p style="font-family:sans-serif">Relatório de teste.</p><table border="1" cellpadding="6" style="border-collapse:collapse;font-family:sans-serif"><tr><th>Vendedor</th><th>Pedidos</th><th>Total</th></tr><tr><td>João Silva</td><td>15</td><td>R$ 4.500,00</td></tr><tr><td>Maria Souza</td><td>27</td><td>R$ 7.845,00</td></tr></table>'
  ),
  'pendente'
);

-- Confirma estado final
SELECT id, relatorio_id, alerta_id, canal, destino, status, tentativas
FROM entregas
ORDER BY id;
