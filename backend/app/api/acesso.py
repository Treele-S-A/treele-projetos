"""Solicitação de acesso de quem é de fora da Treèle (TREELE, 30/10/2026).

Projetista e comercial externos não têm conta Microsoft @treele. Na tela de
login, "Solicitar acesso" abre o cadastro: nome, e-mail, função (comercial ou
projetista, este com as obras e disciplinas em que está envolvido) e a senha
com que vai entrar. Os administradores recebem aviso (com e-mail) e decidem em
Configurações → Solicitações de acesso, podendo ajustar a função. Aprovado,
o projetista entra só nas obras e disciplinas da aprovação.

Rotas públicas (sem login): ``GET /acesso/opcoes`` e ``POST /acesso/solicitacoes``.
As demais, só administrador.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..deps import usuario_admin
from ..enums import PapelObra, TipoNotificacao
from ..models import Disciplina, Notificacao, Obra, ObraMembro, SolicitacaoAcesso, Usuario
from ..security import gerar_hash_senha
from ..services import auditoria, email, email_modelo

router = APIRouter(prefix="/acesso", tags=["solicitação de acesso"])

DOMINIO = "@treele.com.br"
FUNCOES = ("comercial", "projetista")


class SolicitacaoEntrada(BaseModel):
    nome: str = Field(min_length=3, max_length=160)
    email: EmailStr
    empresa: str | None = Field(default=None, max_length=160)
    funcao: str
    obras: list[int] = []
    disciplinas: list[str] = []
    senha: str = Field(min_length=8, max_length=128)
    # Armadilha para robô: campo escondido na tela, que pessoa não preenche.
    site: str | None = None


class Decisao(BaseModel):
    funcao: str
    obras: list[int] = []
    disciplinas: list[str] = []


class Reprovacao(BaseModel):
    motivo: str | None = Field(default=None, max_length=2000)


class ObraCurta(BaseModel):
    id: int
    codigo: str
    nome: str


class SolicitacaoOut(BaseModel):
    id: int
    nome: str
    email: str
    empresa: str | None
    funcao: str
    obras: list[ObraCurta]
    disciplinas: list[str]
    status: str
    motivo: str | None
    criada_em: datetime
    decidida_em: datetime | None
    decidida_por: str | None


def _validar_funcao(db: Session, funcao: str, obras: list[int], disciplinas: list[str]) -> tuple[list[int], list[str]]:
    if funcao not in FUNCOES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Função: comercial ou projetista.")
    if funcao == "comercial":
        return [], []
    obras = list(dict.fromkeys(obras))
    codigos = {c for c in db.scalars(select(Disciplina.codigo).where(Disciplina.ativa.is_(True)))}
    disciplinas = [d for d in dict.fromkeys(d.upper() for d in disciplinas) if d in codigos]
    if not obras or not disciplinas:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Projetista: escolha a(s) obra(s) e a(s) disciplina(s) em que está envolvido.",
        )
    existentes = set(db.scalars(select(Obra.id).where(Obra.id.in_(obras), Obra.ativa.is_(True))))
    if set(obras) - existentes:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Alguma das obras escolhidas não existe.")
    return obras, disciplinas


def _saida(db: Session, s: SolicitacaoAcesso) -> SolicitacaoOut:
    obras = list(db.scalars(select(Obra).where(Obra.id.in_(s.obras or [])).order_by(Obra.codigo)))
    return SolicitacaoOut(
        id=s.id, nome=s.nome, email=s.email, empresa=s.empresa, funcao=s.funcao,
        obras=[ObraCurta(id=o.id, codigo=o.codigo, nome=o.nome) for o in obras],
        disciplinas=s.disciplinas or [], status=s.status, motivo=s.motivo, criada_em=s.criada_em,
        decidida_em=s.decidida_em, decidida_por=s.decidida_por.nome if s.decidida_por else None,
    )


def _email_simples(para: str, nome: str, assunto: str, tipo: str, titulo: str, texto: str, link: str, botao: str):
    saudacao = f"Olá, {nome.split()[0]}."
    return email.Mensagem(
        para=para,
        assunto=assunto,
        texto=f"{saudacao}\n\n{texto}\n\n{botao}: {link}\n\n—\nTreèle Projetos · aviso automático, não responda este e-mail.",
        html=email_modelo.html(
            tipo=tipo, saudacao=saudacao, titulo=titulo, texto=texto, obra="Treèle Projetos",
            cor_obra=None, link=link, rotulo_botao=botao, cid_simbolo=email.CID_SIMBOLO,
        ),
    )


# ------------------------------------------------------------------ público


@router.get("/opcoes")
def opcoes(db: Session = Depends(get_db)):
    """Obras ativas e disciplinas, para o projetista dizer em que está envolvido."""
    obras = db.scalars(select(Obra).where(Obra.ativa.is_(True)).order_by(Obra.codigo))
    disciplinas = db.scalars(
        select(Disciplina).where(Disciplina.ativa.is_(True), Disciplina.codigo != "COM").order_by(Disciplina.ordem)
    )
    return {
        "obras": [{"id": o.id, "codigo": o.codigo, "nome": o.nome} for o in obras],
        "disciplinas": [{"codigo": d.codigo, "nome": d.nome} for d in disciplinas],
    }


@router.post("/solicitacoes", status_code=status.HTTP_201_CREATED)
def solicitar(dados: SolicitacaoEntrada, request: Request, db: Session = Depends(get_db)):
    if dados.site:  # robô: finge que deu certo e não grava nada
        return {"ok": True}
    email_pedido = dados.email.lower().strip()
    if email_pedido.endswith(DOMINIO):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "E-mail @treele.com.br não precisa pedir acesso: entre com \"Entrar com Microsoft\".",
        )
    if db.scalar(select(Usuario.id).where(Usuario.email == email_pedido)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Este e-mail já tem acesso: entre com ele e a sua senha.")
    if db.scalar(select(SolicitacaoAcesso.id).where(
        SolicitacaoAcesso.email == email_pedido, SolicitacaoAcesso.status == "pendente",
    )):
        raise HTTPException(status.HTTP_409_CONFLICT, "Já existe uma solicitação deste e-mail aguardando análise.")
    obras, disciplinas = _validar_funcao(db, dados.funcao, dados.obras, dados.disciplinas)

    s = SolicitacaoAcesso(
        nome=dados.nome.strip(), email=email_pedido, empresa=(dados.empresa or "").strip() or None,
        funcao=dados.funcao, obras=obras, disciplinas=disciplinas, senha_hash=gerar_hash_senha(dados.senha),
        status="pendente",
    )
    db.add(s)
    db.flush()
    admins = list(db.scalars(select(Usuario).where(Usuario.admin.is_(True), Usuario.ativo.is_(True))))
    texto = (
        f"{s.nome} ({s.email}{', ' + s.empresa if s.empresa else ''}) pediu acesso ao Projetos como "
        f"{'projetista' if s.funcao == 'projetista' else 'comercial'}."
        + (f"\n\nObras: {', '.join(o.codigo for o in db.scalars(select(Obra).where(Obra.id.in_(obras))))}"
           f"\n\nDisciplinas: {', '.join(disciplinas)}" if s.funcao == "projetista" else "")
        + "\n\nAprove ou reprove em Configurações → Solicitações de acesso."
    )
    avisos = []
    for a in admins:
        n = Notificacao(usuario_id=a.id, tipo=TipoNotificacao.solicitacao_acesso, obra_id=None,
                        titulo=f"Pedido de acesso · {s.nome}"[:300], texto=texto)
        db.add(n)
        avisos.append(n)
    auditoria.registrar(db, acao="acesso_solicitado", entidade="solicitacao_acesso", entidade_id=s.id,
                        detalhes={"email": s.email, "funcao": s.funcao}, request=request)
    db.commit()

    if settings.email_ligado and avisos:
        link = f"{settings.endereco_site}/solicitacoes-acesso"
        mensagens = [
            _email_simples(db.get(Usuario, n.usuario_id).email, db.get(Usuario, n.usuario_id).nome,
                           f"[Projetos] Pedido de acesso · {s.nome}", "solicitacao_acesso",
                           f"Pedido de acesso de {s.nome}", texto, link, "Ver solicitação")
            for n in avisos
        ]
        agora = datetime.now(timezone.utc)
        for n, saiu in zip(avisos, email.enviar(mensagens)):
            if saiu:
                n.email_enviado_em = agora
        db.commit()
    return {"ok": True}


# ------------------------------------------------------------ administrador


@router.get("/solicitacoes", response_model=list[SolicitacaoOut])
def listar(situacao: str | None = None, admin: Usuario = Depends(usuario_admin), db: Session = Depends(get_db)):
    consulta = select(SolicitacaoAcesso).order_by(SolicitacaoAcesso.criada_em.desc())
    if situacao:
        consulta = consulta.where(SolicitacaoAcesso.status == situacao)
    return [_saida(db, s) for s in db.scalars(consulta)]


@router.get("/solicitacoes/pendentes")
def pendentes(admin: Usuario = Depends(usuario_admin), db: Session = Depends(get_db)):
    total = db.scalar(select(func.count()).select_from(SolicitacaoAcesso).where(SolicitacaoAcesso.status == "pendente"))
    return {"pendentes": total or 0}


def _pendente(db: Session, solicitacao_id: int) -> SolicitacaoAcesso:
    s = db.get(SolicitacaoAcesso, solicitacao_id)
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Solicitação não encontrada.")
    if s.status != "pendente":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Esta solicitação já foi {s.status}.")
    return s


@router.post("/solicitacoes/{solicitacao_id}/aprovar", response_model=SolicitacaoOut)
def aprovar(
    solicitacao_id: int, dados: Decisao, request: Request,
    admin: Usuario = Depends(usuario_admin), db: Session = Depends(get_db),
):
    s = _pendente(db, solicitacao_id)
    obras, disciplinas = _validar_funcao(db, dados.funcao, dados.obras, dados.disciplinas)
    if db.scalar(select(Usuario.id).where(Usuario.email == s.email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Já existe um usuário com este e-mail.")
    usuario = Usuario(nome=s.nome, email=s.email, senha_hash=s.senha_hash, admin=False,
                      comercial=dados.funcao == "comercial", ativo=True)
    db.add(usuario)
    db.flush()
    for obra_id in obras:
        db.add(ObraMembro(obra_id=obra_id, usuario_id=usuario.id, papel=PapelObra.projetista, disciplinas=disciplinas))
    s.funcao, s.obras, s.disciplinas = dados.funcao, obras, disciplinas
    s.status, s.decidida_em, s.decidida_por_id, s.usuario_id = "aprovada", datetime.now(timezone.utc), admin.id, usuario.id
    auditoria.registrar(db, acao="acesso_aprovado", entidade="solicitacao_acesso", entidade_id=s.id, usuario=admin,
                        detalhes={"email": s.email, "funcao": s.funcao, "obras": obras, "disciplinas": disciplinas},
                        request=request)
    db.commit()
    if settings.email_ligado:
        alcance = (
            "Você tem acesso comercial: vê e baixa o material comercial liberado."
            if s.funcao == "comercial"
            else f"Você tem acesso de projetista nas obras {', '.join(o.codigo for o in db.scalars(select(Obra).where(Obra.id.in_(obras))))}"
                 f", nas disciplinas {', '.join(disciplinas)}."
        )
        email.enviar([_email_simples(
            s.email, s.nome, "[Projetos] Seu acesso foi aprovado", "acesso_aprovado", "Acesso aprovado",
            f"Seu pedido de acesso ao Projetos da Treèle foi aprovado.\n\n{alcance}\n\n"
            "Entre com este e-mail e a senha que você escolheu ao pedir o acesso.",
            settings.endereco_site, "Entrar no Projetos",
        )])
    db.refresh(s)
    return _saida(db, s)


@router.post("/solicitacoes/{solicitacao_id}/reprovar", response_model=SolicitacaoOut)
def reprovar(
    solicitacao_id: int, dados: Reprovacao, request: Request,
    admin: Usuario = Depends(usuario_admin), db: Session = Depends(get_db),
):
    s = _pendente(db, solicitacao_id)
    s.status, s.decidida_em, s.decidida_por_id = "reprovada", datetime.now(timezone.utc), admin.id
    s.motivo = (dados.motivo or "").strip() or None
    auditoria.registrar(db, acao="acesso_reprovado", entidade="solicitacao_acesso", entidade_id=s.id, usuario=admin,
                        detalhes={"email": s.email, "motivo": s.motivo}, request=request)
    db.commit()
    if settings.email_ligado:
        email.enviar([_email_simples(
            s.email, s.nome, "[Projetos] Pedido de acesso não aprovado", "acesso_reprovado", "Acesso não aprovado",
            "Seu pedido de acesso ao Projetos da Treèle não foi aprovado."
            + (f"\n\nMotivo: {s.motivo}" if s.motivo else "")
            + "\n\nEm caso de dúvida, fale com o seu contato na Treèle.",
            settings.endereco_site, "Projetos da Treèle",
        )])
    db.refresh(s)
    return _saida(db, s)
