from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import (
    ContextoObra,
    codigos_disciplinas,
    codigos_fases,
    contexto_obra,
    padrao_da_obra,
    usuario_admin,
    usuario_atual,
)
from ..enums import PERMISSOES, PapelObra, TipoArquivo
from ..models import (
    Documento,
    Obra,
    ObraMembro,
    PadraoNomenclatura,
    Revisao,
    Usuario,
)
from ..schemas import (
    MembroCriar,
    MembroOut,
    NomeAnalisado,
    ObraAtualizar,
    ObraComPapel,
    ObraCriar,
    ObraOut,
    PadraoCriar,
    PadraoOut,
    ValidarNomeEntrada,
    ValidarNomeSaida,
)
from ..services import auditoria
from ..services.nomenclatura import analisar, validar_definicao

router = APIRouter(prefix="/obras", tags=["obras"])


def _com_papel(obra: Obra, papel) -> ObraComPapel:
    saida = ObraComPapel.model_validate(obra)
    saida.papel = papel
    saida.permissoes = sorted(PERMISSOES.get(papel, set())) if papel else []
    return saida


@router.get("", response_model=list[ObraComPapel])
def listar(
    incluir_inativas: bool = False,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    papeis = {
        m.obra_id: m.papel
        for m in db.scalars(
            select(ObraMembro).where(ObraMembro.usuario_id == usuario.id)
        )
    }

    consulta = select(Obra).order_by(Obra.codigo)
    if not usuario.admin:
        if not papeis:
            return []
        consulta = consulta.where(Obra.id.in_(papeis.keys()))
    if not incluir_inativas:
        consulta = consulta.where(Obra.ativa.is_(True))

    obras = list(db.scalars(consulta))
    saida = [_com_papel(o, papeis.get(o.id)) for o in obras]
    if usuario.admin:
        for item in saida:
            item.permissoes = sorted(
                {"ver_obsoletos", "enviar", "publicar", "cancelar", "gerenciar"}
            )
    return saida


@router.post("", response_model=ObraOut, status_code=status.HTTP_201_CREATED)
def criar(
    dados: ObraCriar,
    request: Request,
    admin: Usuario = Depends(usuario_admin),
    db: Session = Depends(get_db),
):
    codigo = dados.codigo.upper()
    if db.scalar(select(Obra).where(Obra.codigo == codigo)):
        raise HTTPException(status.HTTP_409_CONFLICT, f"A obra {codigo} já existe.")

    obra = Obra(
        codigo=codigo,
        nome=dados.nome.strip(),
        cliente=dados.cliente,
        regra_companheiro=dados.regra_companheiro
        or {"dwg": ["pdf"], "rvt": ["ifc"]},
    )
    db.add(obra)
    db.flush()

    # Quem cria a obra entra como coordenador, senão ninguém consegue operá-la.
    db.add(
        ObraMembro(
            obra_id=obra.id, usuario_id=admin.id, papel=PapelObra.coordenador
        )
    )
    auditoria.registrar(
        db, acao="obra_criada", entidade="obra", entidade_id=obra.id,
        usuario=admin, obra_id=obra.id, detalhes={"codigo": codigo}, request=request,
    )
    db.commit()
    return obra


@router.get("/{obra_id}", response_model=ObraComPapel)
def detalhe(ctx: ContextoObra = Depends(contexto_obra)):
    saida = _com_papel(ctx.obra, ctx.papel)
    if ctx.usuario.admin:
        saida.permissoes = sorted(
            {"ver_obsoletos", "enviar", "publicar", "cancelar", "gerenciar"}
        )
    return saida


@router.patch("/{obra_id}", response_model=ObraOut)
def atualizar(
    dados: ObraAtualizar,
    request: Request,
    ctx: ContextoObra = Depends(contexto_obra),
):
    ctx.exigir("gerenciar")
    if dados.nome is not None:
        ctx.obra.nome = dados.nome.strip()
    if dados.cliente is not None:
        ctx.obra.cliente = dados.cliente
    if dados.ativa is not None:
        ctx.obra.ativa = dados.ativa
    if dados.regra_companheiro is not None:
        ctx.obra.regra_companheiro = dados.regra_companheiro

    auditoria.registrar(
        ctx.db, acao="obra_atualizada", entidade="obra", entidade_id=ctx.obra.id,
        usuario=ctx.usuario, obra_id=ctx.obra.id, request=request,
    )
    ctx.db.commit()
    return ctx.obra


# --------------------------------------------------------------------------
# Equipe
# --------------------------------------------------------------------------


@router.get("/{obra_id}/membros", response_model=list[MembroOut])
def listar_membros(ctx: ContextoObra = Depends(contexto_obra)):
    return list(
        ctx.db.scalars(
            select(ObraMembro).where(ObraMembro.obra_id == ctx.obra.id)
        )
    )


@router.post(
    "/{obra_id}/membros", response_model=MembroOut, status_code=status.HTTP_201_CREATED
)
def adicionar_membro(
    dados: MembroCriar,
    request: Request,
    ctx: ContextoObra = Depends(contexto_obra),
):
    ctx.exigir("gerenciar")
    if ctx.db.get(Usuario, dados.usuario_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuário não encontrado.")

    existente = ctx.db.scalar(
        select(ObraMembro).where(
            ObraMembro.obra_id == ctx.obra.id,
            ObraMembro.usuario_id == dados.usuario_id,
        )
    )
    if existente is not None:
        existente.papel = dados.papel
        ctx.db.commit()
        return existente

    membro = ObraMembro(
        obra_id=ctx.obra.id, usuario_id=dados.usuario_id, papel=dados.papel
    )
    ctx.db.add(membro)
    auditoria.registrar(
        ctx.db, acao="membro_adicionado", entidade="obra_membro",
        usuario=ctx.usuario, obra_id=ctx.obra.id,
        detalhes={"usuario_id": dados.usuario_id, "papel": dados.papel.value},
        request=request,
    )
    ctx.db.commit()
    return membro


@router.delete("/{obra_id}/membros/{membro_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover_membro(
    membro_id: int,
    request: Request,
    ctx: ContextoObra = Depends(contexto_obra),
):
    ctx.exigir("gerenciar")
    membro = ctx.db.get(ObraMembro, membro_id)
    if membro is None or membro.obra_id != ctx.obra.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Membro não encontrado.")

    restantes = ctx.db.scalars(
        select(ObraMembro).where(
            ObraMembro.obra_id == ctx.obra.id,
            ObraMembro.papel == PapelObra.coordenador,
            ObraMembro.id != membro_id,
        )
    ).all()
    if membro.papel == PapelObra.coordenador and not restantes:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "A obra ficaria sem coordenador. Promova outra pessoa antes de remover.",
        )

    ctx.db.delete(membro)
    auditoria.registrar(
        ctx.db, acao="membro_removido", entidade="obra_membro", entidade_id=membro_id,
        usuario=ctx.usuario, obra_id=ctx.obra.id, request=request,
    )
    ctx.db.commit()


# --------------------------------------------------------------------------
# Padrão de nomenclatura
# --------------------------------------------------------------------------


@router.get("/{obra_id}/padrao", response_model=PadraoOut)
def ver_padrao(ctx: ContextoObra = Depends(contexto_obra)):
    return padrao_da_obra(ctx.db, ctx.obra.id)


@router.put("/{obra_id}/padrao", response_model=PadraoOut)
def definir_padrao(
    dados: PadraoCriar,
    request: Request,
    ctx: ContextoObra = Depends(contexto_obra),
):
    ctx.exigir("gerenciar")

    erros = validar_definicao(dados.template, dados.tokens)
    if erros:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, {"erros": erros})

    extensoes = [e.lower().lstrip(".") for e in dados.extensoes]
    if not extensoes:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Informe ao menos uma extensão aceita."
        )

    padrao = ctx.db.scalar(
        select(PadraoNomenclatura).where(
            PadraoNomenclatura.obra_id == ctx.obra.id,
            PadraoNomenclatura.ativo.is_(True),
        )
    )
    if padrao is None:
        padrao = PadraoNomenclatura(obra_id=ctx.obra.id)
        ctx.db.add(padrao)

    padrao.nome = dados.nome
    padrao.template = dados.template
    padrao.tokens = dados.tokens
    padrao.extensoes = extensoes
    padrao.exemplo = dados.exemplo
    padrao.ativo = True

    auditoria.registrar(
        ctx.db, acao="padrao_definido", entidade="padrao_nomenclatura",
        usuario=ctx.usuario, obra_id=ctx.obra.id,
        detalhes={"template": dados.template}, request=request,
    )
    ctx.db.commit()
    return padrao


@router.post("/{obra_id}/nomenclatura/validar", response_model=ValidarNomeSaida)
def validar_nomes(
    dados: ValidarNomeEntrada,
    ctx: ContextoObra = Depends(contexto_obra),
):
    """Confere nomes sem enviar nada.

    A interface chama isto assim que a pessoa escolhe os arquivos, para que o
    erro de nomenclatura apareça antes de subir 700 MB.
    """
    padrao = padrao_da_obra(ctx.db, ctx.obra.id)
    disciplinas = codigos_disciplinas(ctx.db)
    fases = codigos_fases(ctx.db)

    resultados: list[NomeAnalisado] = []
    for nome in dados.nomes:
        r = analisar(
            nome,
            padrao.template,
            padrao.tokens,
            padrao.extensoes,
            obra_codigo=ctx.obra.codigo,
            disciplinas=disciplinas,
            fases=fases,
        )

        documento = None
        revisao_existe = False
        if r.valido and r.codigo_documento:
            documento = ctx.db.scalar(
                select(Documento).where(
                    Documento.obra_id == ctx.obra.id,
                    Documento.codigo == r.codigo_documento,
                )
            )
            if documento is not None and r.revisao_numero:
                revisao_existe = (
                    ctx.db.scalar(
                        select(Revisao.id).where(
                            Revisao.documento_id == documento.id,
                            Revisao.numero == r.revisao_numero,
                        )
                    )
                    is not None
                )

        resultados.append(
            NomeAnalisado(
                nome_arquivo=nome,
                valido=r.valido,
                erros=r.erros,
                codigo_documento=r.codigo_documento,
                disciplina=r.disciplina_codigo,
                fase=r.fase_codigo,
                revisao=r.revisao_numero,
                titulo=r.titulo,
                tipo=TipoArquivo.da_extensao(nome) if r.extensao else None,
                documento_existe=documento is not None,
                revisao_existe=revisao_existe,
            )
        )

    return ValidarNomeSaida(padrao=PadraoOut.model_validate(padrao), resultados=resultados)
