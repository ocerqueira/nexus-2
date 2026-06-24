# Firebird - Setup ERP

## Versão
Firebird 5.0+

## Backup disponível
`C:\Users\lucas\Documents\base votu\ARQSIST_Votuporanga-02-02-2026-22\ARQSIST_Votuporanga.FBK`

## Restaurar backup para .FDB
```
gbak -r -user SYSDBA -password masterkey "C:\Users\lucas\Documents\base votu\ARQSIST_Votuporanga-02-02-2026-22\ARQSIST_Votuporanga.FBK" "C:\Users\lucas\Documents\base votu\ARQSIST.FDB"
```

## Conexão no Nexus
- Nome esperado: `REPLICA_TERRA` (ou o nome que você cadastrar — ver `app/alertas/item_comprimento_excedente/processador.py`)
- Cadastrar na tabela `conexoes` do banco nexus antes de testar alertas/relatórios do ERP

## Pendências
- [ ] Restaurar .FBK → .FDB
- [x] Cadastrar conexão `REPLICA_TERRA` no nexus
- [x] Implementar deduplicação por fingerprint no alerta `item_comprimento_excedente`
- [x] Criar relatório `pedidos_por_vendedor` (ARQES13 + ARQES15 + ARQCAD)
