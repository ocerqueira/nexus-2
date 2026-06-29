# Deploy em Produção

## Pré-requisitos no servidor

- Docker + Docker Compose instalados
- PostgreSQL rodando e acessível (porta 5432)
- Firebird ERP acessível pelo servidor (porta 3050)

---

## 1. Gerar chave de criptografia

Execute no servidor (ou em qualquer máquina com Python 3):

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 
```
ou 

````bash
python3 -c "import base64; from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC; from cryptography.hazmat.primitives import hashes; kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=b'sal_fixo_de_teste', iterations=480000); print(base64.urlsafe_b64encode(kdf.derive(b'SuaPalavraAqui')).decode())"
````

Saída esperada (exemplo — a sua será diferente):

```
VhruMtBADWONpWNyyOaik4RnYmwvkTdYtQ-4WFCWsP0=
```

> **CRÍTICO:** Salve essa chave em lugar seguro (gerenciador de senhas).  
> Sem ela, todas as senhas de conexões no banco ficam ilegíveis — não há recuperação.  
> Nunca use a chave do ambiente de desenvolvimento em produção.

---

## 2. Preparar banco PostgreSQL

Crie o banco e o usuário antes de subir o Nexus:

```sql
CREATE DATABASE nexus;
CREATE USER nexus_admin WITH PASSWORD 'SENHA_FORTE_AQUI';
GRANT ALL PRIVILEGES ON DATABASE nexus TO nexus_admin;
```

---

## 3. Criar o arquivo `.env`

Na pasta do projeto no servidor, crie o arquivo `.env` a partir do exemplo:

```bash
cp .env.exemplo .env
nano .env  # ou vim .env
```

Preencha:

```env
AMBIENTE=producao
DEBUG=false

API_TITULO=Nexus - Gerador de Relatórios
API_VERSAO=0.1.0

# PostgreSQL — IP do servidor Postgres na rede interna
DATABASE_URL=postgresql+psycopg://nexus_admin:SENHA_FORTE_AQUI@192.168.1.X:5432/nexus

# Chave gerada no passo 1
CHAVE_CRIPTOGRAFIA=COLE_A_CHAVE_GERADA_AQUI

# Autenticação da API (obrigatório em produção)
API_KEY=sua-chave-secreta-aqui
```

> Substitua `192.168.1.X` pelo IP real do servidor PostgreSQL.

---

## 4. Subir o container

```bash
docker compose up -d --build
```

Verificar se subiu:

```bash
docker compose logs -f nexus
```

Saída esperada no final:

```
Nexus pronto para receber requisições.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

---

## 5. Cadastrar conexão com o ERP Firebird

Após o container estar rodando, cadastre a conexão via API.  
Use o Swagger (`http://SEU_SERVIDOR:8000/docs`) ou `curl`:

```bash
curl -X POST http://SEU_SERVIDOR:8000/conexoes \
  -H "Content-Type: application/json" \
  -d '{
    "nome": "erp_firebird",
    "tipo": "firebird",
    "host": "192.168.1.Y",
    "porta": 3050,
    "banco": "/caminho/para/ARQSIST.FDB",
    "usuario": "SYSDBA",
    "senha": "masterkey",
    "observacoes": "ERP principal"
  }'
```

> Substitua `192.168.1.Y` pelo IP do servidor onde o Firebird está rodando.  
> A senha é criptografada automaticamente — nunca fica em texto puro no banco.

Testar a conexão após cadastro (use o `id` retornado no POST anterior):

```bash
curl http://SEU_SERVIDOR:8000/conexoes/1/testar
```

Resposta esperada:

```json
{"status": "ok", "mensagem": "Conexão validada com sucesso"}
```

---

## 6. Cadastrar usuário e verificar sincronização

O Nexus sincroniza relatórios e alertas automaticamente no startup.  
Verifique se foram detectados:

```bash
curl http://SEU_SERVIDOR:8000/relatorios
curl http://SEU_SERVIDOR:8000/alertas
```

Cadastre o primeiro usuário:

```bash
curl -X POST http://SEU_SERVIDOR:8000/usuarios \
  -H "Content-Type: application/json" \
  -d '{
    "identificador": "5517981006771",
    "nome": "Nome do Usuário",
    "whatsapp_numero": "5517981006771",
    "email": "email@empresa.com"
  }'
```

---

## 7. Configurar N8N

Importe os três workflows em `docs/n8n/`:

1. N8N → **Settings → Import workflow** → selecione `nexus_dispatcher.json` (agendamentos → chama alertas/relatórios)
2. Repita para `nexus_despachos_sender.json` (polling de `/despachos/pendentes` → envia via Evolution/SMTP)
3. Repita para `nexus_chatbot.json` (chatbot WhatsApp sob demanda)
4. Em cada workflow importado, edite o nó **"⚙️ Config (Edite aqui)"** com os valores reais:

| Variável | Valor |
|---|---|
| `NEXUS_URL` | `http://192.168.1.X:8000` |
| `EVOLUTION_URL` | URL da sua instância Evolution API |
| `EVOLUTION_INSTANCE` | Nome da instância WhatsApp |
| `EVOLUTION_API_KEY` | Chave da Evolution API |

4. Ative os dois workflows.

---

## Troubleshooting

**Container não conecta no PostgreSQL:**
```bash
docker compose exec nexus python3 -c "
from sqlalchemy import create_engine, text
import os
e = create_engine(os.environ['DATABASE_URL'])
print(e.connect().execute(text('SELECT 1')).scalar())
"
```

**Container não conecta no Firebird:**
```bash
# Verificar se libfbclient2 está presente
docker compose exec nexus ldconfig -p | grep libfb
```

**Ver logs em tempo real:**
```bash
docker compose logs -f nexus
```

**Reiniciar sem rebuild (ex: após alterar .env):**
```bash
docker compose restart nexus
```

**Rebuild completo (após alterar código):**
```bash
docker compose up -d --build
```

**Limpar cache de conexão sem reiniciar** (após alterar senha/host de uma conexão no banco):  
```bash
# Use o ID da conexão (obtido em GET /conexoes)
curl -X POST http://SEU_SERVIDOR:8000/conexoes/1/limpar-cache
```
