"""Fornecedores de projetos — PRO-FL-002 (TREELE, 29/10/2026).

O cadastro dos projetistas, a qualificação documental (registro no conselho e
portfólio) e a avaliação de desempenho ao término das entregas contratadas
(item 5.3 do procedimento): qualidade do serviço, conformidade da
documentação, prazo de entrega e atendimento/comunicação, de 1 a 10. Média 6
ou mais (a régua da planilha): continua qualificado para novas contratações;
abaixo, desqualificado, com o motivo registrado.

Quem vê e mexe: só administradores (módulo Qualidade, 30/10/2026).
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import usuario_atual
from ..models import AvaliacaoFornecedor, FornecedorProjeto, Obra, Usuario
from ..services import auditoria

router = APIRouter(prefix="/fornecedores", tags=["fornecedores de projetos"])

# As colunas da planilha, na mesma ordem.
ESCOPOS = [
    ("ARQ", "Arquitetura"), ("INT", "Interiores"), ("ELE", "Elétrica"), ("HID", "Hidrossanitário"),
    ("DRE", "Drenagem"), ("PPCI", "Incêndio (PPCI)"), ("GAS", "Gás"), ("CLI", "Climatização"),
    ("TERR", "Terraplenagem"), ("PLAN", "Planialtimétrico"), ("EST", "Estrutura"), ("FUN", "Fundação"),
    ("COM", "Comercial"), ("SON", "Sondagem"), ("PAV", "Pavimentação"), ("COB", "Cobertura"),
    ("IMP", "Impermeabilização"), ("MET", "Estrutura metálica"), ("COMP", "Compatibilização"),
    ("GESTAO", "Gestão de projetos"), ("DECORADO", "Decorado"), ("DESEMP", "Desempenho NBR 15575"),
]
PADROES = [("MCMV", "MCMV"), ("SBPE", "SBPE"), ("ALTO", "Alto padrão")]
CRITERIOS = ("qualidade", "documentacao", "prazo", "atendimento")
NOTA_MINIMA = 6.0


def _exigir_acesso(db: Session, usuario: Usuario) -> None:
    # Módulo Qualidade: só administradores (TREELE, 30/10/2026).
    if not usuario.admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Fornecedores de projetos são só do administrador.")


class FornecedorEntrada(BaseModel):
    cod_sienge: str | None = Field(default=None, max_length=20)
    razao_social: str = Field(min_length=2, max_length=200)
    nome_fantasia: str | None = Field(default=None, max_length=200)
    cnpj: str | None = Field(default=None, max_length=20)
    contato: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=200)
    telefone: str | None = Field(default=None, max_length=40)
    observacoes: str | None = Field(default=None, max_length=4000)
    registro_conselho: str | None = None
    portfolio: bool | None = None
    escopos: list[str] = []
    padroes: list[str] = []
    ativo: bool = True

    @field_validator("registro_conselho")
    @classmethod
    def _registro(cls, v):
        if v in (None, ""):
            return None
        if v not in ("SIM", "NAO", "NA"):
            raise ValueError("Registro no conselho: SIM, NAO ou NA.")
        return v

    @field_validator("escopos")
    @classmethod
    def _escopos(cls, v):
        validos = {c for c, _ in ESCOPOS}
        return [e for e in dict.fromkeys(v) if e in validos]

    @field_validator("padroes")
    @classmethod
    def _padroes(cls, v):
        validos = {c for c, _ in PADROES}
        return [p for p in dict.fromkeys(v) if p in validos]


class AvaliacaoEntrada(BaseModel):
    obra_id: int | None = None
    empreendimento: str | None = Field(default=None, max_length=200)
    escopo: str | None = Field(default=None, max_length=20)
    data: datetime
    qualidade: int = Field(ge=1, le=10)
    documentacao: int = Field(ge=1, le=10)
    prazo: int = Field(ge=1, le=10)
    atendimento: int = Field(ge=1, le=10)
    motivo: str | None = Field(default=None, max_length=4000)
    comentario: str | None = Field(default=None, max_length=4000)


class AvaliacaoOut(BaseModel):
    id: int
    obra_id: int | None
    empreendimento: str
    escopo: str | None
    data: datetime
    qualidade: int
    documentacao: int
    prazo: int
    atendimento: int
    media: float
    continua_qualificado: bool
    motivo: str | None
    comentario: str | None
    avaliado_por: str | None
    criada_em: datetime


class FornecedorOut(BaseModel):
    id: int
    cod_sienge: str | None
    razao_social: str
    nome_fantasia: str | None
    cnpj: str | None
    contato: str | None
    email: str | None
    telefone: str | None
    observacoes: str | None
    registro_conselho: str | None
    portfolio: bool | None
    escopos: list[str]
    padroes: list[str]
    ativo: bool
    # Calculados como na planilha.
    qualificacao: str | None
    avaliado: bool
    continua_qualificado: bool | None
    situacao: str
    ultima_avaliacao: AvaliacaoOut | None
    total_avaliacoes: int
    media_geral: float | None


class FornecedorDetalhe(FornecedorOut):
    avaliacoes: list[AvaliacaoOut]


def _avaliacao(a: AvaliacaoFornecedor) -> AvaliacaoOut:
    return AvaliacaoOut(
        id=a.id, obra_id=a.obra_id, empreendimento=a.empreendimento, escopo=a.escopo, data=a.data,
        qualidade=a.qualidade, documentacao=a.documentacao, prazo=a.prazo, atendimento=a.atendimento,
        media=a.media, continua_qualificado=a.continua_qualificado, motivo=a.motivo, comentario=a.comentario,
        avaliado_por=a.avaliado_por.nome if a.avaliado_por else None, criada_em=a.criada_em,
    )


def _situacao(f: FornecedorProjeto) -> str:
    """qualificado | desqualificado | pendente — o "resultado" da planilha,
    com a última avaliação valendo sobre a qualificação documental."""
    ultima = f.avaliacoes[0] if f.avaliacoes else None
    if f.qualificacao == "desqualificado" or (ultima and not ultima.continua_qualificado):
        return "desqualificado"
    if f.qualificacao is None:
        return "pendente"
    return "qualificado"


def _saida(f: FornecedorProjeto, detalhe: bool = False):
    ultima = f.avaliacoes[0] if f.avaliacoes else None
    base = dict(
        id=f.id, cod_sienge=f.cod_sienge, razao_social=f.razao_social, nome_fantasia=f.nome_fantasia,
        cnpj=f.cnpj, contato=f.contato, email=f.email, telefone=f.telefone, observacoes=f.observacoes,
        registro_conselho=f.registro_conselho, portfolio=f.portfolio, escopos=f.escopos or [],
        padroes=f.padroes or [], ativo=f.ativo, qualificacao=f.qualificacao, avaliado=ultima is not None,
        continua_qualificado=ultima.continua_qualificado if ultima else None, situacao=_situacao(f),
        ultima_avaliacao=_avaliacao(ultima) if ultima else None, total_avaliacoes=len(f.avaliacoes),
        media_geral=round(sum(a.media for a in f.avaliacoes) / len(f.avaliacoes), 2) if f.avaliacoes else None,
    )
    if detalhe:
        return FornecedorDetalhe(**base, avaliacoes=[_avaliacao(a) for a in f.avaliacoes])
    return FornecedorOut(**base)


def _limpo(texto: str | None) -> str | None:
    return (texto or "").strip() or None


def _carregar(db: Session, fornecedor_id: int) -> FornecedorProjeto:
    f = db.get(FornecedorProjeto, fornecedor_id)
    if f is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fornecedor não encontrado.")
    return f


@router.get("/opcoes")
def opcoes(usuario: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    _exigir_acesso(db, usuario)
    return {
        "escopos": [{"codigo": c, "nome": n} for c, n in ESCOPOS],
        "padroes": [{"codigo": c, "nome": n} for c, n in PADROES],
        "nota_minima": NOTA_MINIMA,
    }


@router.get("", response_model=list[FornecedorOut])
def listar(usuario: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    _exigir_acesso(db, usuario)
    fornecedores = db.scalars(select(FornecedorProjeto).order_by(FornecedorProjeto.razao_social)).all()
    return [_saida(f) for f in fornecedores]


@router.get("/{fornecedor_id}", response_model=FornecedorDetalhe)
def detalhe(fornecedor_id: int, usuario: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    _exigir_acesso(db, usuario)
    return _saida(_carregar(db, fornecedor_id), detalhe=True)


@router.post("", response_model=FornecedorDetalhe, status_code=status.HTTP_201_CREATED)
def criar(
    dados: FornecedorEntrada, request: Request,
    usuario: Usuario = Depends(usuario_atual), db: Session = Depends(get_db),
):
    _exigir_acesso(db, usuario)
    f = FornecedorProjeto(**_campos(dados))
    db.add(f)
    db.flush()
    auditoria.registrar(
        db, acao="fornecedor_cadastrado", entidade="fornecedor_projeto", entidade_id=f.id,
        usuario=usuario, detalhes={"razao_social": f.razao_social}, request=request,
    )
    db.commit()
    db.refresh(f)
    return _saida(f, detalhe=True)


def _campos(dados: FornecedorEntrada) -> dict:
    campos = dados.model_dump()
    for k in ("cod_sienge", "nome_fantasia", "cnpj", "contato", "email", "telefone", "observacoes"):
        campos[k] = _limpo(campos[k])
    campos["razao_social"] = campos["razao_social"].strip()
    return campos


@router.put("/{fornecedor_id}", response_model=FornecedorDetalhe)
def atualizar(
    fornecedor_id: int, dados: FornecedorEntrada, request: Request,
    usuario: Usuario = Depends(usuario_atual), db: Session = Depends(get_db),
):
    _exigir_acesso(db, usuario)
    f = _carregar(db, fornecedor_id)
    for k, v in _campos(dados).items():
        setattr(f, k, v)
    f.atualizado_em = datetime.now(timezone.utc)
    auditoria.registrar(
        db, acao="fornecedor_atualizado", entidade="fornecedor_projeto", entidade_id=f.id,
        usuario=usuario, detalhes={"razao_social": f.razao_social}, request=request,
    )
    db.commit()
    db.refresh(f)
    return _saida(f, detalhe=True)


@router.post("/{fornecedor_id}/avaliacoes", response_model=FornecedorDetalhe, status_code=status.HTTP_201_CREATED)
def avaliar(
    fornecedor_id: int, dados: AvaliacaoEntrada, request: Request,
    usuario: Usuario = Depends(usuario_atual), db: Session = Depends(get_db),
):
    """Avaliação de desempenho ao término das entregas contratadas (5.3)."""
    _exigir_acesso(db, usuario)
    f = _carregar(db, fornecedor_id)
    empreendimento = _limpo(dados.empreendimento)
    if dados.obra_id is not None:
        obra = db.get(Obra, dados.obra_id)
        if obra is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Obra não encontrada.")
        empreendimento = f"{obra.codigo} · {obra.nome}"
    if not empreendimento:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Diga de qual empreendimento é a entrega avaliada.")
    notas = [getattr(dados, c) for c in CRITERIOS]
    media = round(sum(notas) / len(notas), 2)
    continua = media >= NOTA_MINIMA
    motivo = _limpo(dados.motivo)
    if not continua and not motivo:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Média {media:.1f}: abaixo de {NOTA_MINIMA:.0f}, o projetista fica desqualificado — registre o motivo.",
        )
    a = AvaliacaoFornecedor(
        fornecedor_id=f.id, obra_id=dados.obra_id, empreendimento=empreendimento, escopo=_limpo(dados.escopo),
        data=dados.data, media=media, continua_qualificado=continua, motivo=motivo if not continua else None,
        comentario=_limpo(dados.comentario), avaliado_por_id=usuario.id,
        **{c: getattr(dados, c) for c in CRITERIOS},
    )
    db.add(a)
    db.flush()
    auditoria.registrar(
        db, acao="fornecedor_avaliado", entidade="fornecedor_projeto", entidade_id=f.id,
        usuario=usuario, obra_id=dados.obra_id,
        detalhes={"razao_social": f.razao_social, "media": media, "continua_qualificado": continua},
        request=request,
    )
    db.commit()
    db.expire(f, ["avaliacoes"])
    return _saida(f, detalhe=True)
