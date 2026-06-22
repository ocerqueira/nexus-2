# Recuperação de Acesso ao Nexus

## Em caso de perda da chave de criptografia:

1. Acessar gerenciador de senhas (1Password / Bitwarden)
2. Buscar "Nexus - Chave de Criptografia"
3. Copiar valor para o .env (variável CHAVE_CRIPTOGRAFIA)
4. Reiniciar a aplicação

## Em caso de NÃO ter backup da chave:

1. Aceitar que senhas atuais foram perdidas
2. Limpar tabela conexoes_bd: TRUNCATE conexoes_bd CASCADE;
3. Gerar nova chave: 
   uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
4. Atualizar .env com nova chave
5. Recadastrar todas as conexões manualmente
