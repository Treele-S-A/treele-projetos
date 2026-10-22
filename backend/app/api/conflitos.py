"""Conflitos entre disciplinas (TREELE, 22/10/2026).

A detecção roda no navegador, com os modelos abertos no visualizador
(frontend/src/modelo3d/conflitos.ts); o servidor guarda o que ela achou e
mantém a situação de cada conflito de uma rodada para a outra:

- novo: apareceu pela primeira vez nesta rodada;
- ativo: continua aparecendo;
- aprovado: aceito pelo coordenador, com justificativa (o furo na viga que o
  calculista previu) — não volta a "ativo" quando aparece de novo;
- resolvido: não apareceu numa rodada que tinha os dois modelos dele. Se
  voltar a aparecer, volta a ativo.

O mesmo conflito é reconhecido entre revisões pelo GlobalId da peça B e de
alguma das peças A — o GlobalId não muda entre exportações do mesmo modelo,
e o agrupamento das peças A (tubo e conexões vizinhas) pode mudar.

Quem faz o quê: a equipe da obra roda e registra; o coordenador aprova,
reabre e monta conjuntos. Os conjuntos prontos do sistema qualquer um usa.
O perfil comercial não vê conflitos.
"""

from collections import defaultdict
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import ContextoObra, montar_contexto, status_visiveis, usuario_atual
from ..enums import StatusRevisao, TipoArquivo
from ..models import Arquivo, Conflito, ConjuntoConflito, RodadaConflito, Usuario, VistaModelo
from ..services import auditoria

router = APIRouter(tags=["conflitos"])

ABERTOS = ("novo", "ativo")
MAX_ACHADOS = 3000

Ponto = list[float]


class GrupoConfig(BaseModel):
    disciplinas: list[str] = Field(default=[], max_length=40)
    categorias: list[str] = Field(default=[], max_length=200)
    excluir: list[str] = Field(default=[], max_length=200)
    # Trechos do nome da peça que tiram ela do grupo (ex.: "Flexível").
    excluirNomes: list[str] = Field(default=[], max_length=30)


class ConfigConjunto(BaseModel):
    a: GrupoConfig
    b: GrupoConfig
    modo: Literal["interferencia", "folga"] = "interferencia"
    tolerancia: float = Field(default=0.01, ge=0, le=1)
    folga: float = Field(default=0.05, ge=0.001, le=2)
    ignorarMesmoModelo: bool = True


class ConjuntoEntrada(BaseModel):
    nome: str = Field(min_length=1, max_length=80)
    config: ConfigConjunto
    # Conjunto pronto do sistema (ex.: "instalacoes-estrutura"): qualquer pessoa
    # da equipe o cria, na primeira rodada; o mesmo pronto não se repete.
    pronto: str | None = Field(default=None, max_length=40, pattern=r"^[a-z0-9-]+$")


class UltimaRodada(BaseModel):
    feita_em: datetime
    feita_por: str | None
    encontrados: int
    novos: int
    reabertos: int
    resolvidos: int


class ConjuntoOut(BaseModel):
    id: int
    nome: str
    pronto: str | None
    config: dict
    contagem: dict[str, int]
    ultima_rodada: UltimaRodada | None


class Achado(BaseModel):
    arquivo_a_id: int
    arquivo_b_id: int
    guids_a: list[str] = Field(min_length=1, max_length=200)
    guid_b: str = Field(min_length=1, max_length=40)
    categoria_a: str = Field(default="", max_length=60)
    categoria_b: str = Field(default="", max_length=60)
    nome_a: str | None = Field(default=None, max_length=300)
    nome_b: str | None = Field(default=None, max_length=300)
    tipo: Literal["interferencia", "folga"] = "interferencia"
    centro: Ponto = Field(min_length=3, max_length=3)
    caixa_min: Ponto = Field(min_length=3, max_length=3)
    caixa_max: Ponto = Field(min_length=3, max_length=3)
    medida: float = 0.0


class RodadaEntrada(BaseModel):
    # Os modelos que estavam na cena: só os conflitos entre documentos deles
    # podem ser dados como resolvidos.
    arquivos: list[int] = Field(min_length=1, max_length=50)
    achados: list[Achado] = Field(default=[], max_length=MAX_ACHADOS)


class ConflitoOut(BaseModel):
    id: int
    conjunto_id: int
    status: str
    tipo: str
    documento_a_id: int | None
    documento_b_id: int | None
    documento_a: str | None
    documento_b: str | None
    disciplina_a: str | None
    disciplina_b: str | None
    revisao_a: str
    revisao_b: str
    categoria_a: str
    categoria_b: str
    nome_a: str | None
    nome_b: str | None
    guids_a: list[str]
    guid_b: str
    centro: list[float]
    caixa: dict
    medida: float
    criado_em: datetime
    visto_em: datetime
    resolvido_em: datetime | None
    vista_id: int | None
    justificativa: str | None
    atualizado_por: str | None


class RodadaSaida(BaseModel):
    conjunto: ConjuntoOut
    # Na ordem dos achados enviados: o id do conflito de cada um.
    ids: list[int]
    conflitos: list[ConflitoOut]


class ConflitoMudar(BaseModel):
    status: Literal["aprovado", "ativo"] | None = None
    justificativa: str | None = Field(default=None, max_length=2000)
    vista_id: int | None = None


class ResumoPar(BaseModel):
    disciplina_a: str
    disciplina_b: str
    novo: int = 0
    ativo: int = 0
    aprovado: int = 0
    resolvido: int = 0


class DocumentoComConflitos(BaseModel):
    documento_id: int
    codigo: str
    titulo: str | None
    disciplina: str
    abertos: int
    novos: int


class UltimaDeteccao(BaseModel):
    feita_em: datetime
    feita_por: str | None
    conjunto_id: int
    conjunto: str
    pronto: str | None


class ResumoObra(BaseModel):
    abertos: int
    pares: list[ResumoPar]
    # O quadro da página da obra (22/10/2026).
    novos: int = 0
    aprovados: int = 0
    resolvidos: int = 0
    documentos: list[DocumentoComConflitos] = []
    ultima_deteccao: UltimaDeteccao | None = None
    # Os IFC atuais (a revisão mais recente que a pessoa vê) dos documentos
    # com conflito aberto: o "Abrir no 3D" do quadro.
    arquivos_3d: list[int] = []


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _contexto(db: Session, usuario: Usuario, obra_id: int) -> ContextoObra:
    ctx = montar_contexto(db, usuario, obra_id)
    ctx.somente_equipe()
    return ctx


def _conjunto(db: Session, usuario: Usuario, conjunto_id: int) -> tuple[ConjuntoConflito, ContextoObra]:
    conjunto = db.get(ConjuntoConflito, conjunto_id)
    if conjunto is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conjunto não encontrado.")
    return conjunto, _contexto(db, usuario, conjunto.obra_id)


def _contagem(db: Session, conjunto_id: int) -> dict[str, int]:
    linhas = db.execute(
        select(Conflito.status, func.count()).where(Conflito.conjunto_id == conjunto_id).group_by(Conflito.status)
    ).all()
    return {st: n for st, n in linhas}


def _saida_conjunto(db: Session, c: ConjuntoConflito) -> ConjuntoOut:
    rodada = db.scalars(
        select(RodadaConflito)
        .where(RodadaConflito.conjunto_id == c.id)
        .order_by(RodadaConflito.feita_em.desc(), RodadaConflito.id.desc())
        .limit(1)
    ).first()
    return ConjuntoOut(
        id=c.id, nome=c.nome, pronto=c.pronto, config=c.config, contagem=_contagem(db, c.id),
        ultima_rodada=UltimaRodada(
            feita_em=rodada.feita_em,
            feita_por=rodada.feita_por.nome if rodada.feita_por else None,
            encontrados=rodada.encontrados, novos=rodada.novos,
            reabertos=rodada.reabertos, resolvidos=rodada.resolvidos,
        ) if rodada else None,
    )


def _saida_conflito(c: Conflito) -> ConflitoOut:
    return ConflitoOut(
        id=c.id, conjunto_id=c.conjunto_id, status=c.status, tipo=c.tipo,
        documento_a_id=c.documento_a_id, documento_b_id=c.documento_b_id,
        documento_a=c.documento_a.codigo if c.documento_a else None,
        documento_b=c.documento_b.codigo if c.documento_b else None,
        disciplina_a=c.documento_a.disciplina.codigo if c.documento_a else None,
        disciplina_b=c.documento_b.disciplina.codigo if c.documento_b else None,
        revisao_a=c.revisao_a, revisao_b=c.revisao_b,
        categoria_a=c.categoria_a, categoria_b=c.categoria_b, nome_a=c.nome_a, nome_b=c.nome_b,
        guids_a=c.guids_a or [], guid_b=c.guid_b, centro=c.centro or [], caixa=c.caixa or {},
        medida=c.medida, criado_em=c.criado_em, visto_em=c.visto_em, resolvido_em=c.resolvido_em,
        vista_id=c.vista_id, justificativa=c.justificativa,
        atualizado_por=c.atualizado_por.nome if c.atualizado_por else None,
    )


PRIORIDADE = {"novo": 0, "ativo": 1, "aprovado": 2, "resolvido": 3}


def conflitos_unicos(db: Session, obra_id: int) -> list[Conflito]:
    """Os conflitos da obra, de todos os conjuntos, contando uma vez o mesmo
    par de peças que aparece em dois conjuntos (o pronto e um montado com mais
    tolerância), pela situação mais aberta. A tela (resumo) e o chat usam."""
    # O mesmo de sempre: a mesma peça B e alguma peça A em comum (o grupo de
    # peças A muda de um conjunto para outro — com um filtro por nome, saem
    # algumas).
    por_b: dict[str, list[tuple[set[str], Conflito]]] = defaultdict(list)
    for c in db.scalars(select(Conflito).where(Conflito.obra_id == obra_id).order_by(Conflito.id)):
        pecas = set(c.guids_a or [])
        lista = por_b[c.guid_b]
        achado = next((i for i, (p, _) in enumerate(lista) if p & pecas), None)
        if achado is None:
            lista.append((pecas, c))
            continue
        juntas, atual = lista[achado]
        melhor = c if PRIORIDADE.get(c.status, 9) < PRIORIDADE.get(atual.status, 9) else atual
        lista[achado] = (juntas | pecas, melhor)
    return [c for lista in por_b.values() for _, c in lista]


def _conflitos(db: Session, conjunto_id: int) -> list[Conflito]:
    return list(db.scalars(
        select(Conflito).where(Conflito.conjunto_id == conjunto_id).order_by(Conflito.id)
    ))


# ------------------------------------------------------------- conjuntos


@router.get("/obras/{obra_id}/conjuntos-conflito", response_model=list[ConjuntoOut])
def listar_conjuntos(obra_id: int, usuario: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    _contexto(db, usuario, obra_id)
    conjuntos = db.scalars(
        select(ConjuntoConflito).where(ConjuntoConflito.obra_id == obra_id).order_by(ConjuntoConflito.nome)
    )
    return [_saida_conjunto(db, c) for c in conjuntos]


@router.post(
    "/obras/{obra_id}/conjuntos-conflito", response_model=ConjuntoOut, status_code=status.HTTP_201_CREATED
)
def criar_conjunto(
    obra_id: int,
    dados: ConjuntoEntrada,
    request: Request,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    ctx = _contexto(db, usuario, obra_id)
    if dados.pronto:
        # O pronto é um só por obra: pedir de novo devolve o que já existe.
        existente = db.scalar(
            select(ConjuntoConflito).where(
                ConjuntoConflito.obra_id == obra_id, ConjuntoConflito.pronto == dados.pronto
            )
        )
        if existente:
            return _saida_conjunto(db, existente)
    else:
        ctx.exigir("gerenciar", "Só o coordenador monta conjuntos de conflito da obra.")
    conjunto = ConjuntoConflito(
        obra_id=obra_id, nome=dados.nome.strip(), pronto=dados.pronto,
        config=dados.config.model_dump(), criado_por_id=usuario.id,
    )
    db.add(conjunto)
    db.flush()
    auditoria.registrar(
        db, acao="conjunto_conflito_criado", entidade="conjunto_conflito", entidade_id=conjunto.id,
        usuario=usuario, obra_id=obra_id, detalhes={"nome": conjunto.nome, "pronto": dados.pronto},
        request=request,
    )
    db.commit()
    return _saida_conjunto(db, conjunto)


@router.patch("/conjuntos-conflito/{conjunto_id}", response_model=ConjuntoOut)
def mudar_conjunto(
    conjunto_id: int,
    dados: ConjuntoEntrada,
    request: Request,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    conjunto, ctx = _conjunto(db, usuario, conjunto_id)
    ctx.exigir("gerenciar", "Só o coordenador muda conjuntos de conflito da obra.")
    conjunto.nome = dados.nome.strip()
    conjunto.config = dados.config.model_dump()
    # Mudado à mão, deixa de ser o pronto do sistema.
    conjunto.pronto = None
    conjunto.atualizado_em = _agora()
    auditoria.registrar(
        db, acao="conjunto_conflito_alterado", entidade="conjunto_conflito", entidade_id=conjunto.id,
        usuario=usuario, obra_id=conjunto.obra_id, detalhes={"nome": conjunto.nome}, request=request,
    )
    db.commit()
    return _saida_conjunto(db, conjunto)


@router.delete("/conjuntos-conflito/{conjunto_id}", status_code=status.HTTP_204_NO_CONTENT)
def apagar_conjunto(
    conjunto_id: int,
    request: Request,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    conjunto, ctx = _conjunto(db, usuario, conjunto_id)
    ctx.exigir("gerenciar", "Só o coordenador apaga conjuntos de conflito da obra.")
    auditoria.registrar(
        db, acao="conjunto_conflito_apagado", entidade="conjunto_conflito", entidade_id=conjunto.id,
        usuario=usuario, obra_id=conjunto.obra_id,
        detalhes={"nome": conjunto.nome, "conflitos": sum(_contagem(db, conjunto.id).values())},
        request=request,
    )
    for c in _conflitos(db, conjunto.id):
        db.delete(c)
    for r in db.scalars(select(RodadaConflito).where(RodadaConflito.conjunto_id == conjunto.id)):
        db.delete(r)
    db.delete(conjunto)
    db.commit()


# ------------------------------------------------------------- rodadas


def _arquivo_da_cena(db: Session, ctx: ContextoObra, arquivo_id: int) -> Arquivo:
    from .arquivos import _conferir_leitura

    a = db.get(Arquivo, arquivo_id)
    if a is None or a.tipo != TipoArquivo.ifc or a.revisao.documento.obra_id != ctx.obra.id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Modelo {arquivo_id} não é desta obra.")
    _conferir_leitura(a, ctx)
    return a


@router.post("/conjuntos-conflito/{conjunto_id}/rodadas", response_model=RodadaSaida)
def registrar_rodada(
    conjunto_id: int,
    dados: RodadaEntrada,
    request: Request,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    conjunto, ctx = _conjunto(db, usuario, conjunto_id)
    na_cena = {i: _arquivo_da_cena(db, ctx, i) for i in dict.fromkeys(dados.arquivos)}
    documentos_na_cena = {a.revisao.documento_id for a in na_cena.values()}
    agora = _agora()

    existentes = _conflitos(db, conjunto.id)
    por_guid_b: dict[str, list[Conflito]] = defaultdict(list)
    for c in existentes:
        por_guid_b[c.guid_b].append(c)

    vistos: set[int] = set()
    ids: list[int] = []
    novos = reabertos = 0
    for achado in dados.achados:
        if achado.arquivo_a_id not in na_cena or achado.arquivo_b_id not in na_cena:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "Um conflito aponta para um modelo fora da cena."
            )
        arq_a, arq_b = na_cena[achado.arquivo_a_id], na_cena[achado.arquivo_b_id]
        guids_a = list(dict.fromkeys(achado.guids_a))
        # O mesmo conflito: a mesma peça B e alguma peça A em comum.
        conflito = next(
            (c for c in por_guid_b[achado.guid_b]
             if c.id not in vistos and set(c.guids_a or []) & set(guids_a)),
            None,
        )
        if conflito is None:
            conflito = Conflito(
                conjunto_id=conjunto.id, obra_id=conjunto.obra_id, status="novo",
                guid_b=achado.guid_b, criado_em=agora,
            )
            db.add(conflito)
            por_guid_b[achado.guid_b].append(conflito)
            novos += 1
        elif conflito.status == "resolvido":
            conflito.status = "ativo"
            conflito.resolvido_em = None
            reabertos += 1
        elif conflito.status == "novo":
            conflito.status = "ativo"
        conflito.tipo = achado.tipo
        conflito.documento_a_id = arq_a.revisao.documento_id
        conflito.documento_b_id = arq_b.revisao.documento_id
        conflito.revisao_a = arq_a.revisao.numero
        conflito.revisao_b = arq_b.revisao.numero
        conflito.categoria_a = achado.categoria_a
        conflito.categoria_b = achado.categoria_b
        conflito.nome_a = achado.nome_a
        conflito.nome_b = achado.nome_b
        conflito.guids_a = guids_a
        conflito.centro = achado.centro
        conflito.caixa = {"min": achado.caixa_min, "max": achado.caixa_max}
        conflito.medida = achado.medida
        conflito.visto_em = agora
        db.flush()
        vistos.add(conflito.id)
        ids.append(conflito.id)

    # Não apareceu, e os dois modelos dele estavam na cena: resolvido.
    resolvidos = 0
    for c in existentes:
        if (
            c.id not in vistos
            and c.status in ABERTOS
            and c.documento_a_id in documentos_na_cena
            and c.documento_b_id in documentos_na_cena
        ):
            c.status = "resolvido"
            c.resolvido_em = agora
            resolvidos += 1

    db.add(RodadaConflito(
        conjunto_id=conjunto.id, arquivos=list(na_cena), encontrados=len(dados.achados),
        novos=novos, reabertos=reabertos, resolvidos=resolvidos, feita_por_id=usuario.id, feita_em=agora,
    ))
    auditoria.registrar(
        db, acao="conflitos_detectados", entidade="conjunto_conflito", entidade_id=conjunto.id,
        usuario=usuario, obra_id=conjunto.obra_id,
        detalhes={"encontrados": len(dados.achados), "novos": novos, "reabertos": reabertos,
                  "resolvidos": resolvidos, "arquivos": list(na_cena)},
        request=request,
    )
    db.commit()
    return RodadaSaida(
        conjunto=_saida_conjunto(db, conjunto),
        ids=ids,
        conflitos=[_saida_conflito(c) for c in _conflitos(db, conjunto.id)],
    )


@router.get("/conjuntos-conflito/{conjunto_id}/conflitos", response_model=list[ConflitoOut])
def listar_conflitos(
    conjunto_id: int,
    situacao: str | None = Query(default=None, description="novo, ativo, aprovado, resolvido"),
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    conjunto, _ = _conjunto(db, usuario, conjunto_id)
    lista = _conflitos(db, conjunto.id)
    if situacao:
        lista = [c for c in lista if c.status == situacao]
    return [_saida_conflito(c) for c in lista]


@router.patch("/conflitos/{conflito_id}", response_model=ConflitoOut)
def mudar_conflito(
    conflito_id: int,
    dados: ConflitoMudar,
    request: Request,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    conflito = db.get(Conflito, conflito_id)
    if conflito is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conflito não encontrado.")
    ctx = _contexto(db, usuario, conflito.obra_id)
    detalhes: dict = {}
    if dados.status:
        ctx.exigir("autorizar_revisao", "Só o coordenador aprova ou reabre conflitos.")
        if dados.status == "aprovado":
            justificativa = (dados.justificativa or "").strip()
            if len(justificativa) < 5:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "Diga por que o conflito é aceito (ex.: furo previsto na viga pelo calculista).",
                )
            conflito.justificativa = justificativa
        else:
            conflito.justificativa = None
        conflito.status = dados.status
        conflito.resolvido_em = None
        detalhes["status"] = dados.status
    if dados.vista_id is not None:
        vista = db.get(VistaModelo, dados.vista_id)
        if vista is None or vista.obra_id != conflito.obra_id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Vista não é desta obra.")
        conflito.vista_id = vista.id
        detalhes["vista_id"] = vista.id
    if not detalhes:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Nada para mudar.")
    conflito.atualizado_por_id = usuario.id
    conflito.atualizado_em = _agora()
    auditoria.registrar(
        db, acao="conflito_alterado", entidade="conflito", entidade_id=conflito.id,
        usuario=usuario, obra_id=conflito.obra_id, detalhes=detalhes, request=request,
    )
    db.commit()
    db.refresh(conflito)
    return _saida_conflito(conflito)


@router.get("/obras/{obra_id}/conflitos/resumo", response_model=ResumoObra)
def resumo(obra_id: int, usuario: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    """Por par de disciplinas, quantos em cada situação — todos os conjuntos —,
    os documentos com mais conflitos abertos, a última detecção e os IFC para
    abrir no 3D."""
    ctx = _contexto(db, usuario, obra_id)
    pares: dict[tuple[str, str], ResumoPar] = {}
    por_doc: dict[int, DocumentoComConflitos] = {}
    for c in conflitos_unicos(db, obra_id):
        da = c.documento_a.disciplina.codigo if c.documento_a else "?"
        dbb = c.documento_b.disciplina.codigo if c.documento_b else "?"
        par = pares.setdefault((da, dbb), ResumoPar(disciplina_a=da, disciplina_b=dbb))
        setattr(par, c.status, getattr(par, c.status, 0) + 1)
        if c.status not in ABERTOS:
            continue
        for doc in {d.id: d for d in (c.documento_a, c.documento_b) if d}.values():
            item = por_doc.setdefault(doc.id, DocumentoComConflitos(
                documento_id=doc.id, codigo=doc.codigo, titulo=doc.titulo,
                disciplina=doc.disciplina.codigo, abertos=0, novos=0,
            ))
            item.abertos += 1
            item.novos += c.status == "novo"
    lista = sorted(pares.values(), key=lambda p: -(p.novo + p.ativo))

    rodada = db.scalars(
        select(RodadaConflito)
        .join(ConjuntoConflito, ConjuntoConflito.id == RodadaConflito.conjunto_id)
        .where(ConjuntoConflito.obra_id == obra_id)
        .order_by(RodadaConflito.feita_em.desc(), RodadaConflito.id.desc())
        .limit(1)
    ).first()
    ultima = None
    if rodada:
        conjunto = db.get(ConjuntoConflito, rodada.conjunto_id)
        ultima = UltimaDeteccao(
            feita_em=rodada.feita_em, feita_por=rodada.feita_por.nome if rodada.feita_por else None,
            conjunto_id=conjunto.id, conjunto=conjunto.nome, pronto=conjunto.pronto,
        )

    return ResumoObra(
        abertos=sum(p.novo + p.ativo for p in lista),
        pares=lista,
        novos=sum(p.novo for p in lista),
        aprovados=sum(p.aprovado for p in lista),
        resolvidos=sum(p.resolvido for p in lista),
        documentos=sorted(por_doc.values(), key=lambda d: (-d.abertos, d.codigo))[:12],
        ultima_deteccao=ultima,
        arquivos_3d=_ifcs_atuais(db, ctx, list(por_doc)),
    )


def _ifcs_atuais(db: Session, ctx: ContextoObra, documento_ids: list[int]) -> list[int]:
    """O IFC da revisão mais recente que a pessoa vê, de cada documento — os
    conflitos podem ter sido achados numa revisão que já mudou."""
    from ..models import Documento
    from .arquivos import _conferir_leitura

    visiveis = status_visiveis(ctx)
    saida = []
    for doc_id in documento_ids:
        doc = db.get(Documento, doc_id)
        if doc is None or not ctx.ve_disciplina(doc.disciplina.codigo):
            continue
        revisoes = sorted(
            (r for r in doc.revisoes if r.status in visiveis and r.status != StatusRevisao.cancelado),
            key=lambda r: r.ordem, reverse=True,
        )
        arquivo = next(
            (a for r in revisoes for a in r.arquivos if a.tipo == TipoArquivo.ifc and a.status.value == "disponivel"),
            None,
        )
        if arquivo is None:
            continue
        try:
            _conferir_leitura(arquivo, ctx)
        except HTTPException:
            continue
        saida.append((doc.disciplina.codigo != "EST", doc.disciplina.codigo != "ARQ", doc.codigo, arquivo.id))
    # A estrutura primeiro: o primeiro modelo da cena é a referência de
    # alinhamento (e das coordenadas do BCF).
    return [arquivo_id for *_, arquivo_id in sorted(saida)]
