"""Cronograma de projetos em Gantt — PRO-FL-001 (TREELE, 03/11/2026).

Um por obra, no módulo Qualidade. Quem vê e mexe: os coordenadores da obra
(administrador é coordenador de todas). O cálculo das datas, da folga e do
caminho crítico está em services/cronograma.py; aqui, o que se guarda e quem
pode. Toda alteração devolve o cronograma inteiro já recalculado: a tela
desenha o que o servidor calculou, sem conta própria.
"""

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import ContextoObra, contexto_obra, usuario_atual
from ..enums import PapelObra
from ..models import Cronograma, CronogramaAtividade, CronogramaVinculo, Obra, ObraMembro, Usuario
from ..services import auditoria
from ..services.cronograma import MODELO, STATUS, TIPOS, CicloNoCronograma, calcular, gera_ciclo

router = APIRouter(tags=["cronograma de projetos"])

SO_COORDENADOR = "O cronograma de projetos é só dos coordenadores da obra."


def _exigir(ctx: ContextoObra) -> None:
    ctx.exigir("gerenciar", SO_COORDENADOR)


def _cronograma(db: Session, ctx: ContextoObra) -> Cronograma:
    c = db.scalar(select(Cronograma).where(Cronograma.obra_id == ctx.obra.id))
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Esta obra ainda não tem cronograma.")
    return c


def _atividade(c: Cronograma, atividade_id: int) -> CronogramaAtividade:
    a = next((x for x in c.atividades if x.id == atividade_id), None)
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Atividade não encontrada neste cronograma.")
    return a


def _tocar(c: Cronograma, usuario: Usuario) -> None:
    c.atualizado_em = datetime.now(timezone.utc)
    c.atualizado_por_id = usuario.id


def _saida(db: Session, ctx: ContextoObra, c: Cronograma | None) -> dict:
    obra = {"id": ctx.obra.id, "codigo": ctx.obra.codigo, "nome": ctx.obra.nome}
    if c is None:
        return {"obra": obra, "existe": False, "atividades": []}
    db.refresh(c)
    try:
        calc = calcular(c)
    except CicloNoCronograma:  # não deveria acontecer: os vínculos são conferidos ao gravar
        calc = {}
    atividades = []
    for n, a in enumerate(c.atividades, start=1):
        r = calc.get(a.id)
        atividades.append({
            "id": a.id, "numero": n, "fase": a.fase, "nome": a.nome, "area": a.area,
            "responsavel": a.responsavel, "duracao": a.duracao, "inicio_fixo": a.inicio_fixo,
            "status": a.status, "observacao": a.observacao,
            "inicio_planejado": r.inicio_planejado if r else c.inicio,
            "termino_planejado": r.termino_planejado if r else c.inicio,
            "plano_congelado": a.inicio_base is not None,
            "inicio_real": a.inicio_real, "termino_real": a.termino_real,
            "inicio": r.inicio if r else c.inicio, "termino": r.termino if r else c.inicio,
            "folga": r.folga if r else 0, "critica": bool(r and r.critica),
            "atraso": r.atraso if r else 0, "atrasada": bool(r and r.atrasada),
            "predecessoras": [
                {"predecessora_id": v.predecessora_id, "tipo": v.tipo, "defasagem": v.defasagem}
                for v in a.predecessoras
            ],
        })
    concluidas = [x for x in atividades if x["status"] == "concluido"]
    return {
        "obra": obra,
        "existe": True,
        "inicio": c.inicio,
        "termino": max((x["termino"] for x in atividades), default=c.inicio),
        "termino_planejado": max((x["termino_planejado"] for x in atividades), default=c.inicio),
        "total": len(atividades),
        "concluidas": len(concluidas),
        "no_prazo": sum(1 for x in concluidas if x["atraso"] <= 0),
        "concluidas_com_atraso": sum(1 for x in concluidas if x["atraso"] > 0),
        "atrasadas": sum(1 for x in atividades if x["atrasada"]),
        "atualizado_em": c.atualizado_em,
        "atualizado_por": c.atualizado_por.nome if c.atualizado_por else None,
        "atividades": atividades,
    }


# --------------------------------------------------------------- leitura


@router.get("/cronogramas")
def obras_com_cronograma(usuario: Usuario = Depends(usuario_atual), db: Session = Depends(get_db)):
    """As obras de que a pessoa é coordenadora, e se já têm cronograma."""
    if usuario.admin:
        obras = list(db.scalars(select(Obra).where(Obra.ativa.is_(True)).order_by(Obra.codigo)))
    else:
        obras = list(db.scalars(
            select(Obra).join(ObraMembro, ObraMembro.obra_id == Obra.id)
            .where(ObraMembro.usuario_id == usuario.id, ObraMembro.papel == PapelObra.coordenador,
                   Obra.ativa.is_(True))
            .order_by(Obra.codigo)
        ))
    tem = {c.obra_id: c for c in db.scalars(select(Cronograma).where(Cronograma.obra_id.in_([o.id for o in obras])))}
    return [
        {"id": o.id, "codigo": o.codigo, "nome": o.nome, "tem_cronograma": o.id in tem,
         "atualizado_em": tem[o.id].atualizado_em if o.id in tem else None}
        for o in obras
    ]


@router.get("/obras/{obra_id}/cronograma")
def ver(ctx: ContextoObra = Depends(contexto_obra), db: Session = Depends(get_db)):
    _exigir(ctx)
    return _saida(db, ctx, db.scalar(select(Cronograma).where(Cronograma.obra_id == ctx.obra.id)))


# --------------------------------------------------------------- o cronograma


class NovoCronograma(BaseModel):
    inicio: date
    # Com as atividades do modelo (PRO-FL-001 + macrofluxo) ou em branco.
    modelo: bool = True


@router.post("/obras/{obra_id}/cronograma", status_code=status.HTTP_201_CREATED)
def criar(
    dados: NovoCronograma,
    request: Request,
    ctx: ContextoObra = Depends(contexto_obra),
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    _exigir(ctx)
    if db.scalar(select(Cronograma).where(Cronograma.obra_id == ctx.obra.id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Esta obra já tem cronograma.")
    c = Cronograma(obra_id=ctx.obra.id, inicio=dados.inicio)
    _tocar(c, usuario)
    db.add(c)
    db.flush()
    if dados.modelo:
        chaves: dict[str, CronogramaAtividade] = {}
        ordem = 0
        for fase, itens in MODELO:
            for chave, nome, area, responsavel, duracao, _ in itens:
                ordem += 1
                a = CronogramaAtividade(cronograma_id=c.id, ordem=ordem, fase=fase, nome=nome, area=area,
                                        responsavel=responsavel, duracao=duracao, status="nao_iniciado")
                db.add(a)
                chaves[chave] = a
        db.flush()
        for _, itens in MODELO:
            for chave, *_, preds in itens:
                for p, tipo, defasagem in preds:
                    db.add(CronogramaVinculo(predecessora_id=chaves[p].id, sucessora_id=chaves[chave].id,
                                             tipo=tipo, defasagem=defasagem))
    auditoria.registrar(db, acao="cronograma_criado", entidade="cronograma", entidade_id=c.id,
                        usuario=usuario, obra_id=ctx.obra.id,
                        detalhes={"inicio": dados.inicio.isoformat(), "modelo": dados.modelo}, request=request)
    db.commit()
    return _saida(db, ctx, c)


class AlterarCronograma(BaseModel):
    inicio: date


@router.patch("/obras/{obra_id}/cronograma")
def alterar(
    dados: AlterarCronograma,
    ctx: ContextoObra = Depends(contexto_obra),
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    _exigir(ctx)
    c = _cronograma(db, ctx)
    c.inicio = dados.inicio
    _tocar(c, usuario)
    db.commit()
    return _saida(db, ctx, c)


@router.delete("/obras/{obra_id}/cronograma", status_code=status.HTTP_204_NO_CONTENT)
def apagar(
    request: Request,
    ctx: ContextoObra = Depends(contexto_obra),
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    _exigir(ctx)
    c = _cronograma(db, ctx)
    auditoria.registrar(db, acao="cronograma_apagado", entidade="cronograma", entidade_id=c.id,
                        usuario=usuario, obra_id=ctx.obra.id,
                        detalhes={"atividades": len(c.atividades)}, request=request)
    db.delete(c)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class Ordem(BaseModel):
    ids: list[int]


@router.put("/obras/{obra_id}/cronograma/ordem")
def reordenar(
    dados: Ordem,
    ctx: ContextoObra = Depends(contexto_obra),
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    _exigir(ctx)
    c = _cronograma(db, ctx)
    if sorted(dados.ids) != sorted(a.id for a in c.atividades):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A nova ordem precisa ter todas as atividades, uma vez cada.")
    posicao = {i: n for n, i in enumerate(dados.ids, start=1)}
    for a in c.atividades:
        a.ordem = posicao[a.id]
    _tocar(c, usuario)
    db.commit()
    return _saida(db, ctx, c)


class RenomearFase(BaseModel):
    de: str
    para: str = Field(min_length=1, max_length=120)


@router.patch("/obras/{obra_id}/cronograma/fases")
def renomear_fase(
    dados: RenomearFase,
    ctx: ContextoObra = Depends(contexto_obra),
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    _exigir(ctx)
    c = _cronograma(db, ctx)
    for a in c.atividades:
        if a.fase == dados.de:
            a.fase = dados.para.strip()
    _tocar(c, usuario)
    db.commit()
    return _saida(db, ctx, c)


# --------------------------------------------------------------- atividades


def _limpar(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip()
    return v or None


class NovaAtividade(BaseModel):
    fase: str = Field(min_length=1, max_length=120)
    nome: str = Field(min_length=1, max_length=200)
    duracao: int = Field(default=5, ge=0, le=2000)
    responsavel: str | None = Field(default=None, max_length=120)
    area: str | None = Field(default=None, max_length=60)
    # Entra logo abaixo desta; sem ela, no fim da fase (ou do cronograma).
    depois_de: int | None = None


@router.post("/obras/{obra_id}/cronograma/atividades", status_code=status.HTTP_201_CREATED)
def criar_atividade(
    dados: NovaAtividade,
    ctx: ContextoObra = Depends(contexto_obra),
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    _exigir(ctx)
    c = _cronograma(db, ctx)
    lista = list(c.atividades)
    if dados.depois_de is not None:
        anterior = _atividade(c, dados.depois_de)
        pos = lista.index(anterior) + 1
    else:
        da_fase = [i for i, a in enumerate(lista) if a.fase == dados.fase.strip()]
        pos = (da_fase[-1] + 1) if da_fase else len(lista)
    nova = CronogramaAtividade(
        cronograma_id=c.id, fase=dados.fase.strip(), nome=dados.nome.strip(), duracao=dados.duracao,
        responsavel=_limpar(dados.responsavel), area=_limpar(dados.area), status="nao_iniciado",
    )
    lista.insert(pos, nova)
    db.add(nova)
    for n, a in enumerate(lista, start=1):
        a.ordem = n
    _tocar(c, usuario)
    db.commit()
    return _saida(db, ctx, c)


class AlterarAtividade(BaseModel):
    fase: str | None = Field(default=None, min_length=1, max_length=120)
    nome: str | None = Field(default=None, min_length=1, max_length=200)
    area: str | None = Field(default=None, max_length=60)
    responsavel: str | None = Field(default=None, max_length=120)
    duracao: int | None = Field(default=None, ge=0, le=2000)
    # null tira a data fixada (a atividade volta a seguir as predecessoras).
    inicio_fixo: date | None = None
    status: str | None = None
    # null apaga o registro.
    inicio_real: date | None = None
    termino_real: date | None = None
    observacao: str | None = Field(default=None, max_length=4000)

    @field_validator("status")
    @classmethod
    def _status(cls, v: str | None) -> str | None:
        if v is not None and v not in STATUS:
            raise ValueError("O status é nao_iniciado, em_andamento ou concluido.")
        return v


def _registrar_realizado(a: CronogramaAtividade, dados: "AlterarAtividade", campos: set[str], antes) -> None:
    """Status e datas realizadas andam juntos: marcar em andamento registra o
    início (hoje, se não veio data); concluído, o término; preencher as
    datas acerta o status. Ao começar, o planejado congela (inicio_base e
    termino_base): é com ele que o atraso fica registrado."""
    if not campos & {"status", "inicio_real", "termino_real"}:
        return
    hoje = date.today()
    previsto = antes.inicio if antes else hoje
    if "inicio_real" in campos:
        a.inicio_real = dados.inicio_real
    if "termino_real" in campos:
        a.termino_real = dados.termino_real
    if "status" in campos and dados.status:
        if dados.status == "nao_iniciado":
            a.inicio_real = a.termino_real = None
        elif dados.status == "em_andamento":
            a.inicio_real = a.inicio_real or min(previsto, hoje)
            a.termino_real = None
        else:
            a.termino_real = a.termino_real or hoje
            a.inicio_real = a.inicio_real or min(previsto, a.termino_real)
        a.status = dados.status
    else:
        if a.termino_real and not a.inicio_real:
            a.inicio_real = min(previsto, a.termino_real)
        a.status = "concluido" if a.termino_real else "em_andamento" if a.inicio_real else "nao_iniciado"
    if a.inicio_real and a.termino_real and a.termino_real < a.inicio_real:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "O término realizado é antes do início realizado.")
    if a.inicio_real and a.inicio_base is None and antes:
        a.inicio_base = antes.inicio_planejado
        a.termino_base = antes.termino_planejado
    if not a.inicio_real and a.status == "nao_iniciado":
        a.inicio_base = a.termino_base = None


@router.patch("/obras/{obra_id}/cronograma/atividades/{atividade_id}")
def alterar_atividade(
    atividade_id: int,
    dados: AlterarAtividade,
    ctx: ContextoObra = Depends(contexto_obra),
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    _exigir(ctx)
    c = _cronograma(db, ctx)
    a = _atividade(c, atividade_id)
    try:
        antes = calcular(c).get(a.id)
    except CicloNoCronograma:
        antes = None
    fase_antes = a.fase
    campos = dados.model_fields_set
    for campo in campos - {"status", "inicio_real", "termino_real"}:
        valor = getattr(dados, campo)
        if campo in ("fase", "nome"):
            if valor is None:
                continue
            valor = valor.strip()
        elif campo in ("area", "responsavel", "observacao"):
            valor = _limpar(valor)
        elif campo == "duracao" and valor is None:
            continue
        setattr(a, campo, valor)
    _registrar_realizado(a, dados, campos, antes)
    if a.fase != fase_antes:
        # Mudou de fase: vai para o fim dela, para a fase seguir contínua.
        lista = [x for x in c.atividades if x is not a]
        da_fase = [i for i, x in enumerate(lista) if x.fase == a.fase]
        lista.insert((da_fase[-1] + 1) if da_fase else len(lista), a)
        for n, x in enumerate(lista, start=1):
            x.ordem = n
    _tocar(c, usuario)
    db.commit()
    return _saida(db, ctx, c)


@router.delete("/obras/{obra_id}/cronograma/atividades/{atividade_id}")
def apagar_atividade(
    atividade_id: int,
    ctx: ContextoObra = Depends(contexto_obra),
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    _exigir(ctx)
    c = _cronograma(db, ctx)
    a = _atividade(c, atividade_id)
    # Os vínculos em que ela é predecessora saem junto (os da própria saem
    # pelo cascade).
    for v in db.scalars(select(CronogramaVinculo).where(CronogramaVinculo.predecessora_id == a.id)):
        db.delete(v)
    db.delete(a)
    _tocar(c, usuario)
    db.commit()
    return _saida(db, ctx, c)


class Predecessora(BaseModel):
    predecessora_id: int
    tipo: str = "TI"
    defasagem: int = Field(default=0, ge=-2000, le=2000)

    @field_validator("tipo")
    @classmethod
    def _tipo(cls, v: str) -> str:
        v = v.strip().upper()
        if v not in TIPOS:
            raise ValueError("O tipo do vínculo é TI, II ou TT.")
        return v


@router.put("/obras/{obra_id}/cronograma/atividades/{atividade_id}/predecessoras")
def definir_predecessoras(
    atividade_id: int,
    dados: list[Predecessora],
    ctx: ContextoObra = Depends(contexto_obra),
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    _exigir(ctx)
    c = _cronograma(db, ctx)
    a = _atividade(c, atividade_id)
    ids = {x.id: x for x in c.atividades}
    novas: dict[int, Predecessora] = {}
    for p in dados:
        if p.predecessora_id == a.id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Uma atividade não pode ser predecessora dela mesma.")
        if p.predecessora_id not in ids:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Predecessora fora deste cronograma.")
        novas[p.predecessora_id] = p
    if gera_ciclo(list(c.atividades), a.id, list(novas)):
        nomes = ", ".join(f"{list(c.atividades).index(ids[i]) + 1}" for i in novas)
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Isso fecha um ciclo: alguma das predecessoras ({nomes}) já depende desta atividade.",
        )
    a.predecessoras.clear()
    db.flush()
    for p in novas.values():
        a.predecessoras.append(CronogramaVinculo(predecessora_id=p.predecessora_id, tipo=p.tipo, defasagem=p.defasagem))
    _tocar(c, usuario)
    db.commit()
    return _saida(db, ctx, c)

