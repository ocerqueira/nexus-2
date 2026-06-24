"""
Teste end-to-end dos endpoints de agendamento.

Fluxo: criar -> listar -> proximas execucoes -> marcar executado -> verificar recalculo -> atualizar -> desativar

Pre-requisitos:
  1. Docker Postgres rodando:  docker compose up -d
  2. API rodando:              uv run uvicorn main:app --reload
  3. Dependencias instaladas:  uv sync --group dev

Uso:
  uv run python testes/test_agendamentos_e2e.py
"""

import sys
import requests

BASE = "http://localhost:8000"


def check(condicao: bool, mensagem: str) -> None:
    if not condicao:
        print(f"  [FALHOU] {mensagem}")
        sys.exit(1)
    print(f"  [OK] {mensagem}")


def main():
    print("=" * 60)
    print("TESTE END-TO-END -- AGENDAMENTOS")
    print("=" * 60)

    # ------------------------------------------------------------------
    # 0. Health check
    # ------------------------------------------------------------------
    print("\n[0] Verificando saude da API...")
    r = requests.get(f"{BASE}/saude")
    check(r.status_code == 200, f"GET /saude -> {r.status_code}")
    dados = r.json()
    check(dados["status"] == "ok", f"API status = {dados['status']}")
    check(dados["componentes"]["banco_dados"] == "ok", "Banco de dados OK")

    # ------------------------------------------------------------------
    # 1. Obter IDs de recursos existentes
    # ------------------------------------------------------------------
    print("\n[1] Verificando dados de seed...")
    r = requests.get(f"{BASE}/relatorios")
    check(r.status_code == 200, f"GET /relatorios -> {r.status_code}")
    relatorios = r.json()
    check(len(relatorios.get("relatorios", [])) > 0, "Ha relatorios cadastrados")
    relatorio_id = relatorios["relatorios"][0]["id"]
    print(f"    Usando relatorio_id={relatorio_id}")

    r = requests.get(f"{BASE}/alertas")
    check(r.status_code == 200, f"GET /alertas -> {r.status_code}")
    alertas = r.json()
    check(len(alertas.get("alertas", [])) > 0, "Ha alertas cadastrados")
    alerta_id = alertas["alertas"][0]["id"]
    print(f"    Usando alerta_id={alerta_id}")

    USUARIO = 1  # admin_nexus do seed

    # ------------------------------------------------------------------
    # 2. Criar agendamento diario 9h
    # ------------------------------------------------------------------
    print("\n[2] POST /agendamentos -- criando agendamento diario 9h...")
    payload = {
        "usuario_id": USUARIO,
        "tipo_recurso": "alerta",
        "recurso_id": alerta_id,
        "frequencia": "diaria",
        "horarios": [{"hora": 9, "minuto": 0}],
        "apenas_dias_uteis": False,
        "parametros": {"forcar": False},
        "canais": ["whatsapp"],
    }
    r = requests.post(f"{BASE}/agendamentos", json=payload)
    check(r.status_code == 201, f"POST /agendamentos -> {r.status_code}")
    resp = r.json()
    check(resp["status"] == "criado", f"Status = {resp['status']}")
    agendamento_id = resp["id"]
    check(isinstance(agendamento_id, int), f"ID retornado: {agendamento_id}")
    print(f"    Agendamento criado: id={agendamento_id}")
    print(f"    proximo_envio calculado: {resp['proximo_envio']}")

    # ------------------------------------------------------------------
    # 3. Criar agendamento semanal (segunda 8h)
    # ------------------------------------------------------------------
    print("\n[3] POST /agendamentos -- criando agendamento semanal...")
    payload = {
        "usuario_id": USUARIO,
        "tipo_recurso": "relatorio",
        "recurso_id": relatorio_id,
        "frequencia": "semanal",
        "dia_semana": 1,
        "horarios": [{"hora": 8, "minuto": 0}],
        "canais": ["email"],
    }
    r = requests.post(f"{BASE}/agendamentos", json=payload)
    check(r.status_code == 201, f"POST /agendamentos (semanal) -> {r.status_code}")
    resp = r.json()
    semanal_id = resp["id"]
    print(f"    Agendamento semanal criado: id={semanal_id}")
    print(f"    proximo_envio: {resp['proximo_envio']}")

    # ------------------------------------------------------------------
    # 4. Criar agendamento mensal (dia 5, 14h)
    # ------------------------------------------------------------------
    print("\n[4] POST /agendamentos -- criando agendamento mensal...")
    payload = {
        "usuario_id": USUARIO,
        "tipo_recurso": "alerta",
        "recurso_id": alerta_id,
        "frequencia": "mensal",
        "dia_mes": 5,
        "horarios": [{"hora": 14, "minuto": 0}],
        "apenas_dias_uteis": True,
        "canais": ["whatsapp", "email"],
    }
    r = requests.post(f"{BASE}/agendamentos", json=payload)
    check(r.status_code == 201, f"POST /agendamentos (mensal) -> {r.status_code}")
    resp = r.json()
    mensal_id = resp["id"]
    print(f"    Agendamento mensal criado: id={mensal_id}")
    print(f"    proximo_envio: {resp['proximo_envio']}")

    # ------------------------------------------------------------------
    # 5. Listar agendamentos
    # ------------------------------------------------------------------
    print("\n[5] GET /agendamentos -- listando...")
    r = requests.get(f"{BASE}/agendamentos")
    check(r.status_code == 200, f"GET /agendamentos -> {r.status_code}")
    resp = r.json()
    check(resp["total"] >= 3, f"Total >= 3 (encontrados: {resp['total']})")
    print(f"    {resp['total']} agendamentos cadastrados")

    r = requests.get(f"{BASE}/agendamentos?tipo_recurso=alerta")
    check(r.status_code == 200, "Filtro por tipo_recurso=alerta OK")
    resp = r.json()
    check(resp["total"] >= 2, f"Alertas agendados >= 2 (encontrados: {resp['total']})")

    # ------------------------------------------------------------------
    # 6. Proximas execucoes (devem estar vazias agora)
    # ------------------------------------------------------------------
    print("\n[6] GET /agendamentos/proximas-execucoes...")
    r = requests.get(f"{BASE}/agendamentos/proximas-execucoes")
    check(r.status_code == 200, f"GET /proximas-execucoes -> {r.status_code}")
    resp = r.json()
    print(f"    Prontos para executar agora: {resp['total']}")

    # ------------------------------------------------------------------
    # 7. Marcar como executado
    # ------------------------------------------------------------------
    print(f"\n[7] POST /agendamentos/{agendamento_id}/marcar-executado...")
    r = requests.post(f"{BASE}/agendamentos/{agendamento_id}/marcar-executado")
    check(r.status_code == 200, f"POST marcar-executado -> {r.status_code}")
    resp = r.json()
    check(resp["status"] == "executado", f"Status = {resp['status']}")
    check("proximo_envio" in resp, "proximo_envio recalculado")
    print(f"    Executado. Novo proximo_envio: {resp['proximo_envio']}")

    # ------------------------------------------------------------------
    # 8. Atualizar agendamento (PATCH)
    # ------------------------------------------------------------------
    print(f"\n[8] PATCH /agendamentos/{semanal_id} -- mudando dia_semana...")
    r = requests.patch(
        f"{BASE}/agendamentos/{semanal_id}",
        json={"dia_semana": 3, "frequencia": "semanal"},
    )
    check(r.status_code == 200, f"PATCH -> {r.status_code}")
    resp = r.json()
    check(resp["status"] == "atualizado", f"Status = {resp['status']}")
    check("proximo_envio" in resp, "proximo_envio recalculado apos PATCH")
    print(f"    Atualizado. Novo proximo_envio: {resp['proximo_envio']}")

    # ------------------------------------------------------------------
    # 9. Desativar (soft delete)
    # ------------------------------------------------------------------
    print(f"\n[9] DELETE /agendamentos/{mensal_id} -- desativando...")
    r = requests.delete(f"{BASE}/agendamentos/{mensal_id}")
    check(r.status_code == 200, f"DELETE -> {r.status_code}")
    resp = r.json()
    check(resp["status"] == "desativado", f"Status = {resp['status']}")

    r = requests.get(f"{BASE}/agendamentos?apenas_ativos=true")
    check(r.status_code == 200, "Listagem apos desativacao OK")
    resp = r.json()
    ids_ativos = [a["id"] for a in resp["agendamentos"]]
    check(mensal_id not in ids_ativos, "Agendamento desativado nao aparece nos ativos")
    print(f"    Agendamento {mensal_id} removido da lista de ativos")

    # ------------------------------------------------------------------
    # 10. Validacao: semanal sem dia_semana deve ser rejeitado
    # ------------------------------------------------------------------
    print("\n[10] Validacao: frequencia semanal sem dia_semana...")
    r = requests.post(
        f"{BASE}/agendamentos",
        json={
            "usuario_id": USUARIO,
            "tipo_recurso": "alerta",
            "recurso_id": alerta_id,
            "frequencia": "semanal",
            "horarios": [{"hora": 9, "minuto": 0}],
            "canais": ["whatsapp"],
        },
    )
    check(r.status_code == 422, f"Validacao Pydantic rejeitou -> {r.status_code}")

    # ------------------------------------------------------------------
    # RESUMO
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("[SUCESSO] TODOS OS TESTES PASSARAM")
    print("=" * 60)
    print(f"  Agendamentos criados: {agendamento_id} (diario), {semanal_id} (semanal), {mensal_id} (mensal)")
    print(f"  Fluxo validado: criar -> listar -> proximas execucoes -> executar -> atualizar -> desativar")


if __name__ == "__main__":
    try:
        main()
    except requests.ConnectionError:
        print("\n[ERRO] API nao esta respondendo em http://localhost:8000")
        print("   Execute: uv run uvicorn main:app --reload")
        sys.exit(1)
