"""Checkup geral do sistema (TREELE, 04/11/2026): cada teste aqui reproduz um
defeito encontrado na revisão — horário em UTC, acesso de projetista externo a
outras disciplinas, conversa longa no chat, modelo 3D velho depois de substituir
o IFC e o que mais apareceu."""

from datetime import datetime, timezone

import pytest

from app.config import settings
from app.services.storage import armazenamento

from .conftest import autenticar, autorizar, enviar_arquivo

SENHA = "senha-checkup-12345"
IFC = b"ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n" + b" " * 300
PDF = b"%PDF-1.7\n" + b"0" * 200
CASA = "Rua de Teste, 100 – Centro – Curitiba – PR"


def _obra(cliente, admin, codigo):
    r = cliente.post("/obras", json={"codigo": codigo, "nome": f"Obra {codigo}", "endereco": CASA}, headers=admin)
    assert r.status_code == 201, r.text
    return r.json()


def _pessoa(cliente, admin, obra, apelido, papel=None, comercial=False):
    email = f"{apelido}@chk.teste.com.br"
    corpo = {"nome": apelido.title(), "email": email, "senha": SENHA}
    if comercial:
        corpo["tipo"] = "comercial"
    u = cliente.post("/usuarios", json=corpo, headers=admin)
    assert u.status_code == 201, u.text
    if papel:
        m = cliente.post(f"/obras/{obra['id']}/membros", json={"usuario_id": u.json()["id"], "papel": papel}, headers=admin)
        assert m.status_code in (200, 201), m.text
    return autenticar(cliente, email, SENHA), u.json()["id"]


def _externo(cliente, admin, obra, apelido, disciplinas):
    """Projetista de fora, aprovado só nas disciplinas dadas (o caminho real)."""
    email = f"{apelido}@fora.exemplo.com"
    r = cliente.post("/acesso/solicitacoes", json={
        "nome": apelido.title(), "email": email, "funcao": "projetista", "obras": [obra["id"]],
        "disciplinas": disciplinas, "senha": SENHA,
    })
    assert r.status_code == 201, r.text
    pedido = next(s for s in cliente.get("/acesso/solicitacoes?situacao=pendente", headers=admin).json() if s["email"] == email)
    r = cliente.post(f"/acesso/solicitacoes/{pedido['id']}/aprovar",
                     json={"funcao": "projetista", "obras": [obra["id"]], "disciplinas": disciplinas}, headers=admin)
    assert r.status_code == 200, r.text
    return autenticar(cliente, email, SENHA), r.json()


@pytest.fixture(scope="module")
def m(cliente, admin):
    """Obra com um documento de ARQ e um de HID, e gente de cada tipo."""
    obra = _obra(cliente, admin, "CHK")
    coord, coord_id = _pessoa(cliente, admin, obra, "coordchk", "coordenador")
    campo, _ = _pessoa(cliente, admin, obra, "campochk", "obra")
    comercial, _ = _pessoa(cliente, admin, obra, "comchk", comercial=True)
    externo, _ = _externo(cliente, admin, obra, "extchk", ["HID"])
    ids = {}
    for nome, conteudo in (("CHK-ARQ-PE-001-R00.ifc", IFC), ("CHK-HID-PE-001-R00.ifc", IFC)):
        r = enviar_arquivo(cliente, coord, obra["id"], nome, conteudo)
        assert r.status_code == 200, r.text
        ids[nome] = {"arquivo": r.json()["arquivo"]["id"], "revisao": r.json()["revisao"]["id"]}
        p = cliente.post(f"/revisoes/{r.json()['revisao']['id']}/publicar", json={"avisar": False}, headers=coord)
        assert p.status_code == 200, p.text
    docs = cliente.get(f"/obras/{obra['id']}/documentos", headers=coord).json()["itens"]
    por = {d["codigo"]: d["id"] for d in docs}
    return {"obra": obra, "coord": coord, "coord_id": coord_id, "campo": campo, "comercial": comercial,
            "externo": externo, "ARQ": ids["CHK-ARQ-PE-001-R00.ifc"], "HID": ids["CHK-HID-PE-001-R00.ifc"],
            "doc_arq": por["CHK-ARQ-PE-001"], "doc_hid": por["CHK-HID-PE-001"]}


# ------------------------------------------------------------ horário de Brasília


def test_hoje_e_de_brasilia_nao_utc(monkeypatch):
    """Depois das 21h a Vercel (UTC) já está em amanhã: "hoje" e as datas saíam erradas."""
    from app.services import tempo

    noite = datetime(2026, 11, 4, 1, 30, tzinfo=timezone.utc)  # 03/11, 22h30 em Curitiba
    monkeypatch.setattr(tempo, "_agora_utc", lambda: noite)
    assert tempo.hoje().isoformat() == "2026-11-03"
    assert tempo.data_br(noite) == "03/11/2026"
    assert tempo.data_hora_br(noite) == "03/11/2026 22:30"
    # O SQLite devolve sem fuso, mas é UTC do mesmo jeito.
    assert tempo.data_br(noite.replace(tzinfo=None)) == "03/11/2026"


def test_ata_e_chat_mostram_data_de_brasilia():
    from app.services.ata_pdf import _data
    from app.services.chat_ferramentas import _data as data_chat

    noite = datetime(2026, 11, 4, 1, 30, tzinfo=timezone.utc)
    assert _data(noite) == "03/11/2026"
    assert data_chat(noite) == "03/11/2026 22:30"


def test_lista_mestra_com_hora_de_brasilia_e_so_o_que_chegou(cliente, admin):
    obra = _obra(cliente, admin, "CHKCSV")
    r = enviar_arquivo(cliente, admin, obra["id"], "CHKCSV-ARQ-PE-001-R00.pdf", PDF, titulo="=HYPERLINK(1)")
    assert r.status_code == 200, r.text
    # Um DWG que começou a subir e não terminou não é arquivo da revisão ainda.
    i = cliente.post(f"/obras/{obra['id']}/uploads/iniciar", json={
        "nome_arquivo": "CHKCSV-ARQ-PE-001-R00.dwg", "tamanho": 10, "descricao": "Parcial"}, headers=admin)
    assert i.status_code == 201, i.text
    p = cliente.post(f"/revisoes/{r.json()['revisao']['id']}/publicar", json={"avisar": False}, headers=admin)
    assert p.status_code == 200, p.text
    publicada = datetime.fromisoformat(p.json()["publicada_em"].replace("Z", "+00:00"))
    csv = cliente.get(f"/obras/{obra['id']}/documentos/exportar", headers=admin).text
    linha = next(x for x in csv.splitlines() if x.startswith("CHKCSV-ARQ-PE-001"))
    from app.services import tempo

    assert tempo.data_hora_br(publicada) in linha
    assert ";PDF" in linha and "DWG" not in linha
    # Texto que começa com = viraria fórmula ao abrir no Excel.
    assert ";'=HYPERLINK(1);" in linha or ';"\'=HYPERLINK(1)";' in linha


# ------------------------------------------------------------ o que cada um vê


def test_lista_de_usuarios_e_de_quem_monta_equipe(cliente, admin, m):
    """A lista traz o e-mail de todo mundo: projetista externo não pode ver."""
    assert cliente.get("/usuarios", headers=admin).status_code == 200
    assert cliente.get("/usuarios", headers=m["coord"]).status_code == 200
    for quem in (m["externo"], m["campo"], m["comercial"]):
        assert cliente.get("/usuarios", headers=quem).status_code == 403
    # O engenheiro responsável monta a equipe da obra dele.
    resp, resp_id = _pessoa(cliente, admin, m["obra"], "respchk", "obra")
    assert cliente.get("/usuarios", headers=resp).status_code == 403
    cliente.patch(f"/obras/{m['obra']['id']}", json={"responsavel_id": resp_id}, headers=admin)
    assert cliente.get("/usuarios", headers=resp).status_code == 200
    cliente.patch(f"/obras/{m['obra']['id']}", json={"responsavel_id": 0}, headers=admin)


def test_equipe_com_emails_e_de_quem_cuida_da_obra(cliente, m):
    url = f"/obras/{m['obra']['id']}/membros"
    assert cliente.get(url, headers=m["coord"]).status_code == 200
    for quem in (m["externo"], m["campo"]):
        assert cliente.get(url, headers=quem).status_code == 403


def test_projetista_nao_renomeia_documento_de_outra_disciplina(cliente, m):
    assert cliente.patch(f"/documentos/{m['doc_arq']}", json={"titulo": "Título invasor"}, headers=m["externo"]).status_code == 404
    assert cliente.get(f"/documentos/{m['doc_arq']}", headers=m["coord"]).json()["titulo"] != "Título invasor"
    assert cliente.patch(f"/documentos/{m['doc_hid']}", json={"titulo": "Título dele"}, headers=m["externo"]).status_code == 200


def test_conferir_nome_nao_revela_outra_disciplina(cliente, m):
    r = cliente.post(f"/obras/{m['obra']['id']}/nomenclatura/validar",
                     json={"nomes": ["CHK-ARQ-PE-001-R01.pdf", "CHK-HID-PE-001-R00.pdf"]}, headers=m["externo"])
    assert r.status_code == 200, r.text
    arq, hid = r.json()["resultados"]
    assert not arq["valido"] and "disciplina ARQ" in " ".join(arq["erros"])
    assert arq["documento_titulo"] is None and not arq["documento_existe"]
    assert hid["documento_existe"]


def test_numero_de_revisoes_so_conta_o_que_a_pessoa_ve(cliente, m):
    """A obra não sabe que existe R01 em análise: o total não pode contar."""
    autorizar(cliente, m["coord"], m["obra"]["id"], "CHK-HID-PE-001")
    r = enviar_arquivo(cliente, m["coord"], m["obra"]["id"], "CHK-HID-PE-001-R01.ifc", IFC)
    assert r.status_code == 200, r.text
    url = f"/obras/{m['obra']['id']}/documentos?busca=CHK-HID-PE-001"
    assert cliente.get(url, headers=m["coord"]).json()["itens"][0]["total_revisoes"] == 2
    assert cliente.get(url, headers=m["campo"]).json()["itens"][0]["total_revisoes"] == 1
    assert cliente.get(f"/documentos/{m['doc_hid']}", headers=m["campo"]).json()["total_revisoes"] == 1


def test_vistas_respeitam_comercial_e_disciplina(cliente, m):
    obra_id = m["obra"]["id"]
    corpo = {"titulo": "Vista ARQ", "arquivos": [m["ARQ"]["arquivo"]], "camera": {"posicao": [0, 0, 1], "alvo": [0, 0, 0]}}
    r = cliente.post(f"/obras/{obra_id}/vistas", json=corpo, headers=m["coord"])
    assert r.status_code == 201, r.text
    vista = r.json()["vista"]["id"]
    from app.db import SessionLocal
    from app.models import VistaModelo

    with SessionLocal() as db:
        v = db.get(VistaModelo, vista)
        v.imagem_tamanho = 10
        db.commit()
    assert any(x["id"] == vista for x in cliente.get(f"/obras/{obra_id}/vistas", headers=m["coord"]).json())
    # Comercial não vê vista nenhuma; projetista de HID não vê vista só de ARQ.
    assert cliente.get(f"/obras/{obra_id}/vistas", headers=m["comercial"]).status_code == 403
    assert cliente.get(f"/vistas/{vista}", headers=m["comercial"]).status_code == 403
    assert all(x["id"] != vista for x in cliente.get(f"/obras/{obra_id}/vistas", headers=m["externo"]).json())
    assert cliente.get(f"/vistas/{vista}", headers=m["externo"]).status_code == 404


def _achado(arq, hid):
    return {
        "arquivo_a_id": hid, "arquivo_b_id": arq, "guids_a": ["GA1"], "guid_b": "GB1",
        "categoria_a": "IFCFLOWSEGMENT", "categoria_b": "IFCBEAM", "nome_a": "Tubo", "nome_b": "Viga",
        "centro": [0, 1, 0], "caixa_min": [0, 1, 0], "caixa_max": [1, 2, 1], "medida": 0.1,
    }


def test_conflitos_so_das_disciplinas_da_pessoa(cliente, admin, m):
    obra_id = m["obra"]["id"]
    config = {"a": {"disciplinas": []}, "b": {"disciplinas": []}, "modo": "interferencia"}
    cj = cliente.post(f"/obras/{obra_id}/conjuntos-conflito", json={"nome": "Checkup", "config": config}, headers=m["coord"]).json()
    # Um segundo documento de ARQ: conflito ARQ × ARQ não é assunto de quem é só de HID.
    r = enviar_arquivo(cliente, m["coord"], obra_id, "CHK-ARQ-PE-002-R00.ifc", IFC)
    outro = r.json()["arquivo"]["id"]
    achados = [_achado(m["ARQ"]["arquivo"], m["HID"]["arquivo"]),
               {**_achado(m["ARQ"]["arquivo"], outro), "guids_a": ["GA2"], "guid_b": "GB2"}]
    r = cliente.post(f"/conjuntos-conflito/{cj['id']}/rodadas",
                     json={"arquivos": [m["ARQ"]["arquivo"], m["HID"]["arquivo"], outro], "achados": achados}, headers=m["coord"])
    assert r.status_code == 200, r.text

    url = f"/conjuntos-conflito/{cj['id']}/conflitos"
    assert len(cliente.get(url, headers=m["coord"]).json()) == 2
    dele = cliente.get(url, headers=m["externo"]).json()
    assert [c["guid_b"] for c in dele] == ["GB1"]
    resumo = cliente.get(f"/obras/{obra_id}/conflitos/resumo", headers=m["externo"]).json()
    assert resumo["abertos"] == 1 and all("CHK-ARQ-PE-002" != d["codigo"] for d in resumo["documentos"])
    # E não entra modelo de outra disciplina na rodada dele.
    r = cliente.post(f"/conjuntos-conflito/{cj['id']}/rodadas",
                     json={"arquivos": [outro], "achados": []}, headers=m["externo"])
    assert r.status_code == 404


def test_chat_segue_a_disciplina_em_conflitos_e_pedidos(cliente, admin, m):
    from app.db import SessionLocal
    from app.models import Usuario
    from app.services.chat_ferramentas import Ferramentas

    enviar_outro = cliente.post(f"/documentos/{m['doc_arq']}/solicitacoes",
                                json={"descricao": "Pedido da arquitetura, para o checkup."}, headers=m["coord"])
    assert enviar_outro.status_code == 201, enviar_outro.text
    with SessionLocal() as db:
        pessoa = db.query(Usuario).filter(Usuario.email == "extchk@fora.exemplo.com").one()
        f = Ferramentas(db, pessoa)
        pedidos = f.listar_solicitacoes(obra="CHK")
        assert all(not s["codigo"].startswith("CHK-ARQ") for s in pedidos["solicitacoes"])
        conflitos = f.consultar_conflitos(obra="CHK", listar=True, situacao="todos")
        for o in conflitos["conflitos_obras"]:
            for c in o.get("conflitos", []):
                assert "HID" in c["disciplinas"]


def test_ata_diz_quem_a_fez(cliente, m):
    """A tela usa isto: quem fez a análise vê o link dela."""
    from app.schemas import AtaResumo

    assert "criada_por_id" in AtaResumo.model_fields


# ------------------------------------------------------------ modelo 3D


def test_substituir_o_ifc_descarta_o_modelo_3d_antigo(cliente, m):
    """O .frag fica ao lado do IFC, com o mesmo nome: sem isto, depois de trocar
    o IFC o visualizador continuava abrindo o modelo velho."""
    from app.api.arquivos import chave_indice, chave_modelo, chave_resumo
    from app.db import SessionLocal
    from app.models import Arquivo

    obra_id = m["obra"]["id"]
    r = enviar_arquivo(cliente, m["coord"], obra_id, "CHK-EST-PE-001-R00.ifc", IFC)
    arquivo_id = r.json()["arquivo"]["id"]
    with SessionLocal() as db:
        a = db.get(Arquivo, arquivo_id)
        chaves = [chave_modelo(a), chave_resumo(a), chave_indice(a)]
    for chave in chaves:
        armazenamento.gravar_bytes(chave, b"velho", "application/octet-stream")
    assert cliente.get(f"/arquivos/{arquivo_id}/modelo", headers=m["coord"]).json()["modelo_url"]

    r = enviar_arquivo(cliente, m["coord"], obra_id, "CHK-EST-PE-001-R00.ifc", IFC + b"novo", substituir=True)
    assert r.status_code == 200, r.text
    for chave in chaves:
        assert not armazenamento.info(chave)[0], chave
    novo = cliente.get(f"/arquivos/{arquivo_id}/modelo", headers=m["coord"]).json()
    assert novo["modelo_url"] is None and novo["ifc_url"]


# ------------------------------------------------------------ revisão fora de ordem


def test_revisao_nova_precisa_ser_maior_que_a_ultima(cliente, m):
    """R01 depois da R02 autorizada ficava presa: criada, mas impossível de liberar."""
    obra_id = m["obra"]["id"]
    r = enviar_arquivo(cliente, m["coord"], obra_id, "CHK-FUN-PE-001-R02.pdf", PDF)
    assert r.status_code == 200, r.text
    p = cliente.post(f"/revisoes/{r.json()['revisao']['id']}/publicar", json={"avisar": False}, headers=m["coord"])
    assert p.status_code == 200, p.text
    autorizar(cliente, m["coord"], obra_id, "CHK-FUN-PE-001")

    v = cliente.post(f"/obras/{obra_id}/nomenclatura/validar", json={"nomes": ["CHK-FUN-PE-001-R01.pdf"]}, headers=m["coord"])
    assert not v.json()["resultados"][0]["valido"] and "R02" in " ".join(v.json()["resultados"][0]["erros"])
    r = cliente.post(f"/obras/{obra_id}/uploads/iniciar", json={
        "nome_arquivo": "CHK-FUN-PE-001-R01.pdf", "tamanho": 10, "descricao": "Fora de ordem"}, headers=m["coord"])
    assert r.status_code == 409
    assert enviar_arquivo(cliente, m["coord"], obra_id, "CHK-FUN-PE-001-R03.pdf", PDF).status_code == 200


# ------------------------------------------------------------ equipe


def test_projetista_promovido_deixa_de_ficar_preso_as_disciplinas(cliente, admin, m):
    from app.db import SessionLocal
    from app.models import Evento

    pessoa, dados = _externo(cliente, admin, m["obra"], "promchk", ["HID"])
    usuario_id = next(u["id"] for u in cliente.get("/usuarios", headers=admin).json() if u["email"] == "promchk@fora.exemplo.com")
    assert cliente.get(f"/documentos/{m['doc_arq']}", headers=pessoa).status_code == 404
    r = cliente.post(f"/obras/{m['obra']['id']}/membros", json={"usuario_id": usuario_id, "papel": "coordenador"}, headers=admin)
    assert r.status_code in (200, 201), r.text
    assert r.json()["disciplinas"] is None
    assert cliente.get(f"/documentos/{m['doc_arq']}", headers=pessoa).status_code == 200
    with SessionLocal() as db:  # e fica no registro, como qualquer mudança de equipe
        assert db.query(Evento).filter(Evento.acao == "membro_papel_alterado").count() >= 1


# ------------------------------------------------------------ formulário e e-mail


@pytest.mark.parametrize("nome", ["   ", "\n\n\n", " a "])
def test_pedido_de_acesso_recusa_nome_vazio(cliente, nome):
    r = cliente.post("/acesso/solicitacoes", json={
        "nome": nome, "email": "vazio@fora.exemplo.com", "funcao": "comercial", "senha": SENHA})
    assert r.status_code == 422


def test_quebra_de_linha_no_nome_nao_derruba_o_pedido(cliente, admin):
    r = cliente.post("/acesso/solicitacoes", json={
        "nome": "Fulano\nBcc: x@y.com", "email": "quebra@fora.exemplo.com", "funcao": "comercial", "senha": SENHA})
    assert r.status_code == 201, r.text
    pedido = next(s for s in cliente.get("/acesso/solicitacoes?situacao=pendente", headers=admin).json()
                  if s["email"] == "quebra@fora.exemplo.com")
    assert "\n" not in pedido["nome"]


def test_email_nao_quebra_com_linha_no_assunto():
    from app.services import email

    msg = email._montar(email.Mensagem(para="a@b.com", assunto="Pedido\r\nBcc: x@y.com", texto="oi"))
    assert "\n" not in msg["Subject"] and msg["Bcc"] is None


def test_primeiro_nome_de_nome_vazio_nao_quebra():
    from app.services.email_modelo import primeiro_nome

    assert primeiro_nome("  Maria  da Silva ") == "Maria"
    assert primeiro_nome("   ") == ""


def test_usuario_sem_nome_de_verdade_e_recusado(cliente, admin):
    r = cliente.post("/usuarios", json={"nome": "    ", "email": "semnome@chk.teste.com.br"}, headers=admin)
    assert r.status_code == 422


# ------------------------------------------------------------ limites


def test_login_bloqueia_depois_de_muitas_tentativas(cliente, admin, m, monkeypatch):
    monkeypatch.setattr(settings, "login_tentativas_max", 3)
    email = "travachk@chk.teste.com.br"
    cliente.post("/usuarios", json={"nome": "Trava", "email": email, "senha": SENHA}, headers=admin)
    for _ in range(3):
        assert cliente.post("/auth/login", json={"email": email, "senha": "errada-123"}).status_code == 401
    r = cliente.post("/auth/login", json={"email": email, "senha": SENHA})
    assert r.status_code == 429 and "tentativas" in r.text
    # Outra pessoa não paga pelo erro desta.
    assert cliente.post("/auth/login", json={"email": "admin@teste.com.br", "senha": "senha-de-teste-1234"}).status_code == 200


def test_pedido_de_acesso_tem_limite_por_endereco(cliente, monkeypatch):
    from app.db import SessionLocal
    from app.models import Evento

    with SessionLocal() as db:
        ja = db.query(Evento).filter(Evento.acao == "acesso_solicitado", Evento.ip == "testclient").count()
    monkeypatch.setattr(settings, "acesso_pedidos_por_hora", ja + 1)
    corpo = {"nome": "Robô Um", "funcao": "comercial", "senha": SENHA}
    assert cliente.post("/acesso/solicitacoes", json={**corpo, "email": "robo1@fora.exemplo.com"}).status_code == 201
    r = cliente.post("/acesso/solicitacoes", json={**corpo, "email": "robo2@fora.exemplo.com"})
    assert r.status_code == 429


# ------------------------------------------------------------ chat


def test_conversa_longa_comeca_pela_pergunta(cliente, m, monkeypatch):
    """A 7ª pergunta cortava o histórico numa resposta do assistente, e a API do
    Claude recusa conversa que não começa pela pessoa."""
    from app.api import chat as rota
    from app.db import SessionLocal
    from app.models import Usuario
    from app.services import chat_modelo

    recebido = {}

    def falso(sistema, historico, ferramentas):
        recebido["historico"] = historico
        return "ok"

    monkeypatch.setattr(chat_modelo, "conversar", falso)
    mensagens = []
    for i in range(7):
        mensagens.append(rota.TurnoEntrada(papel="usuario", texto=f"pergunta {i}"))
        if i < 6:
            mensagens.append(rota.TurnoEntrada(papel="assistente", texto=f"resposta {i}"))
    with SessionLocal() as db:
        pessoa = db.query(Usuario).filter(Usuario.admin.is_(True)).first()
        rota._responder(db, pessoa, rota.PerguntaEntrada(mensagens=mensagens))
    assert recebido["historico"][0].papel == "usuario"
    assert recebido["historico"][-1].texto == "pergunta 6"


def test_resposta_longa_nao_trava_a_conversa():
    """Com o limite maior de resposta, passar de 8.000 caracteres fazia a pergunta
    seguinte voltar 422."""
    from app.api.chat import PerguntaEntrada

    longa = "x" * 30000
    p = PerguntaEntrada(mensagens=[
        {"papel": "usuario", "texto": "pergunta"}, {"papel": "assistente", "texto": longa},
        {"papel": "usuario", "texto": "outra"},
    ])
    assert p.mensagens[1].texto


def test_guia_do_chat_conhece_as_telas_novas(cliente, m):
    from app.api.chat import _instrucoes
    from app.db import SessionLocal
    from app.models import Usuario

    with SessionLocal() as db:
        pessoa = db.query(Usuario).filter(Usuario.admin.is_(True)).first()
        texto = _instrucoes(db, pessoa, None)
    for tela in ("Cronograma de projetos", "Atas de análise crítica", "Fornecedores de projetos"):
        assert tela in texto


# ------------------------------------------------------------ cronograma


def test_renomear_fase_para_uma_existente_junta_as_linhas(cliente, admin):
    obra = _obra(cliente, admin, "CHKGNT")
    url = f"/obras/{obra['id']}/cronograma"
    cliente.post(url, json={"inicio": "2026-11-02", "modelo": False}, headers=admin)
    for fase, nome in (("A", "a1"), ("B", "b1"), ("C", "c1")):
        cliente.post(f"{url}/atividades", json={"fase": fase, "nome": nome}, headers=admin)
    c = cliente.patch(f"{url}/fases", json={"de": "C", "para": "A"}, headers=admin).json()
    fases = [a["fase"] for a in c["atividades"]]
    assert fases == ["A", "A", "B"]  # a numeração não pode pular entre fases


def test_nova_atividade_abaixo_de_outra_fase_vai_para_a_fase_certa(cliente, admin):
    obra = _obra(cliente, admin, "CHKGN2")
    url = f"/obras/{obra['id']}/cronograma"
    cliente.post(url, json={"inicio": "2026-11-02", "modelo": False}, headers=admin)
    a = cliente.post(f"{url}/atividades", json={"fase": "A", "nome": "a1"}, headers=admin).json()["atividades"][0]
    cliente.post(f"{url}/atividades", json={"fase": "B", "nome": "b1"}, headers=admin)
    c = cliente.post(f"{url}/atividades", json={"fase": "B", "nome": "b2", "depois_de": a["id"]}, headers=admin).json()
    assert [x["fase"] for x in c["atividades"]] == ["A", "B", "B"]


def test_docs_da_api_fechada_em_producao():
    from app.main import enderecos_da_documentacao

    assert enderecos_da_documentacao("producao", "/api") == {"docs_url": None, "redoc_url": None, "openapi_url": None}
    assert enderecos_da_documentacao("dev", "")["docs_url"] == "/docs"


# ------------------------------------------------------------ conjuntos de conflito


def test_conjunto_de_conflitos_nao_repete_nome(cliente, m):
    url = f"/obras/{m['obra']['id']}/conjuntos-conflito"
    config = {"a": {"disciplinas": []}, "b": {"disciplinas": []}, "modo": "interferencia"}
    a = cliente.post(url, json={"nome": "Repetido", "config": config}, headers=m["coord"])
    assert a.status_code == 201, a.text
    assert cliente.post(url, json={"nome": " repetido ", "config": config}, headers=m["coord"]).status_code == 409
    b = cliente.post(url, json={"nome": "Outro nome", "config": config}, headers=m["coord"])
    assert b.status_code == 201, b.text
    r = cliente.patch(f"/conjuntos-conflito/{b.json()['id']}", json={"nome": "Repetido", "config": config}, headers=m["coord"])
    assert r.status_code == 409
    # Mudar o conjunto sem mudar o nome continua valendo.
    r = cliente.patch(f"/conjuntos-conflito/{a.json()['id']}", json={"nome": "Repetido", "config": config}, headers=m["coord"])
    assert r.status_code == 200, r.text


def test_conjunto_pronto_repetido_conta_so_a_disciplina_da_pessoa(cliente, m):
    obra_id = m["obra"]["id"]
    config = {"a": {"disciplinas": []}, "b": {"disciplinas": []}, "modo": "interferencia"}
    corpo = {"nome": "Pronto do checkup", "config": config, "pronto": "pronto-checkup"}
    cj = cliente.post(f"/obras/{obra_id}/conjuntos-conflito", json=corpo, headers=m["coord"]).json()
    outro = enviar_arquivo(cliente, m["coord"], obra_id, "CHK-ARQ-PE-003-R00.ifc", IFC).json()["arquivo"]["id"]
    achados = [_achado(m["ARQ"]["arquivo"], m["HID"]["arquivo"]),
               {**_achado(m["ARQ"]["arquivo"], outro), "guids_a": ["GA3"], "guid_b": "GB3"}]
    r = cliente.post(f"/conjuntos-conflito/{cj['id']}/rodadas",
                     json={"arquivos": [m["ARQ"]["arquivo"], m["HID"]["arquivo"], outro], "achados": achados}, headers=m["coord"])
    assert r.status_code == 200, r.text
    # Quem só é de HID não fica sabendo, pela contagem, do conflito ARQ × ARQ.
    dele = cliente.post(f"/obras/{obra_id}/conjuntos-conflito", json=corpo, headers=m["externo"])
    assert dele.status_code == 201, dele.text
    assert sum(dele.json()["contagem"].values()) == 1


def test_conferir_nome_avisa_arquivo_ja_liberado(cliente, m):
    nome = "CHK-ARQ-PE-001-R00.ifc"
    r = cliente.post(f"/obras/{m['obra']['id']}/nomenclatura/validar", json={"nomes": [nome, "nome ruim.ifc", "CHK-ARQ-PE-001-R00.pdf"]}, headers=m["coord"])
    assert r.status_code == 200, r.text
    liberado, ruim, novo = r.json()["resultados"]
    # O envio recusaria: a conferência diz antes, e não é problema de nome.
    assert not liberado["valido"] and liberado["nome_no_padrao"] and "liberada" in liberado["erros"][0]
    assert not ruim["valido"] and not ruim["nome_no_padrao"]
    # O PDF que falta nessa revisão continua podendo entrar.
    assert novo["valido"], novo["erros"]


# ------------------------------------------------------------ erros de validação


def test_erros_de_validacao_em_portugues_sem_devolver_a_senha(cliente, admin):
    def msgs(corpo):
        r = cliente.post("/usuarios", json=corpo, headers=admin)
        assert r.status_code == 422, r.text
        assert "input" not in r.text and "should" not in r.text and "valid email" not in r.text
        return r, [d["msg"] for d in r.json()["detail"]]

    _, m = msgs({"nome": "Fulano", "email": "fulano@empresa", "senha": "abcdefgh1"})
    assert m == ["E-mail inválido: confira se está completo, como nome@empresa.com.br."]
    r, m = msgs({"nome": "Fulano", "email": "ok@chk.teste.com.br", "senha": "s3cr3t"})
    assert m == ["Senha: precisa ter pelo menos 8 caracteres."]
    assert "s3cr3t" not in r.text
    _, m = msgs({"email": "ok@chk.teste.com.br", "senha": "abcdefgh1"})
    assert m == ["Nome: preenchimento obrigatório."]


def test_mensagem_do_nosso_validador_sai_sem_prefixo(cliente, admin):
    r = cliente.post("/usuarios", json={"nome": "\n\n", "email": "ok@chk.teste.com.br", "senha": "abcdefgh1"}, headers=admin)
    assert r.status_code == 422, r.text
    assert "Value error" not in r.text


# ------------------------------------------------------------ conta


def test_conta_externa_nao_vira_email_da_treele(cliente, m):
    corpo = {"nome": "Externo Novo", "email": "chegou@treele.com.br", "senha_atual": SENHA}
    r = cliente.patch("/auth/perfil", json=corpo, headers=m["externo"])
    assert r.status_code == 400 and "externa" in r.json()["detail"]
    # O nome ela continua mudando.
    eu = cliente.get("/auth/eu", headers=m["externo"]).json()
    r = cliente.patch("/auth/perfil", json={"nome": "Externo Novo", "email": eu["email"]}, headers=m["externo"])
    assert r.status_code == 200, r.text
