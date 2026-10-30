def test_perfil_proprio_exige_senha_para_trocar_email(cliente, admin):
    criado = cliente.post("/usuarios", headers=admin, json={
        "nome": "Pessoa de Teste", "email": "perfil.teste@treele.com.br",
        "senha": "senha-de-perfil-1234",
    })
    assert criado.status_code == 201, criado.text
    login = cliente.post("/auth/login", json={
        "email": "perfil.teste@treele.com.br", "senha": "senha-de-perfil-1234",
    })
    assert login.status_code == 200, login.text
    cabecalhos = {"Authorization": f"Bearer {login.json()['token']}"}

    assert cliente.patch("/auth/perfil", json={
        "nome": "Outro nome", "email": "perfil.teste@treele.com.br",
    }).status_code == 401

    nome = cliente.patch("/auth/perfil", headers=cabecalhos, json={
        "nome": "Nome atualizado", "email": "perfil.teste@treele.com.br",
    })
    assert nome.status_code == 200, nome.text
    assert nome.json()["nome"] == "Nome atualizado"

    sem_senha = cliente.patch("/auth/perfil", headers=cabecalhos, json={
        "nome": "Nome atualizado", "email": "perfil.novo@treele.com.br",
    })
    assert sem_senha.status_code == 400
    assert cliente.get("/auth/eu", headers=cabecalhos).json()["email"] == "perfil.teste@treele.com.br"

    fora_dominio = cliente.patch("/auth/perfil", headers=cabecalhos, json={
        "nome": "Nome atualizado", "email": "admin@teste.com.br",
        "senha_atual": "senha-de-perfil-1234",
    })
    assert fora_dominio.status_code == 400

    atualizado = cliente.patch("/auth/perfil", headers=cabecalhos, json={
        "nome": "Nome atualizado", "email": "perfil.novo@treele.com.br",
        "senha_atual": "senha-de-perfil-1234",
    })
    assert atualizado.status_code == 200, atualizado.text
    assert atualizado.json()["email"] == "perfil.novo@treele.com.br"
    assert cliente.get("/auth/eu", headers=cabecalhos).json()["email"] == "perfil.novo@treele.com.br"
