from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import (
    ContextoObra,
    codigos_disciplinas,
    codigos_fases,
    contexto_obra,
    permissoes_do_responsavel,
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
from ..services import solicitacoes as servico_solicitacoes
from ..services.nomenclatura import analisar, validar_definicao
from ..services.equipe import garantir_admins_coordenadores
from ..services.storage import armazenamento, chave_logo, detectar_imagem
from ..services.titulos import limpar_titulo

router = APIRouter(prefix="/obras", tags=["obras"])

# O administrador global ignora a matriz de papéis. A lista existe só para a
# interface saber o que desenhar para ele.
TUDO = sorted(set().union(*PERMISSOES.values()) | {"adicionar_membro", "remover_membro"})


def _com_papel(obra: Obra, papel, usuario: Usuario) -> ObraComPapel:
    saida = ObraComPapel.model_validate(obra)
    saida.papel = papel
    permissoes = set(PERMISSOES.get(papel, set())) if papel else set()
    saida.permissoes = sorted(permissoes | permissoes_do_responsavel(obra, usuario))
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
    # Comercial vê todas as obras, sem papel: o contexto restringe o resto.
    if not usuario.admin and not usuario.comercial:
        if not papeis:
            return []
        consulta = consulta.where(Obra.id.in_(papeis.keys()))
    if not incluir_inativas:
        consulta = consulta.where(Obra.ativa.is_(True))

    obras = list(db.scalars(consulta))
    saida = [_com_papel(o, papeis.get(o.id), usuario) for o in obras]
    if usuario.admin:
        for item in saida:
            item.permissoes = TUDO
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

    # Todo administrador — inclusive quem cria — entra como coordenador.
    garantir_admins_coordenadores(db, obra=obra)
    auditoria.registrar(
        db, acao="obra_criada", entidade="obra", entidade_id=obra.id,
        usuario=admin, obra_id=obra.id, detalhes={"codigo": codigo}, request=request,
    )
    db.commit()
    return obra


@router.get("/{obra_id}", response_model=ObraComPapel)
def detalhe(ctx: ContextoObra = Depends(contexto_obra)):
    saida = _com_papel(ctx.obra, ctx.papel, ctx.usuario)
    if ctx.usuario.admin:
        saida.permissoes = TUDO
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
    if dados.cor is not None:
        ctx.obra.cor = dados.cor.lower() or None
    if dados.responsavel_id is not None:
        if dados.responsavel_id == 0:
            ctx.obra.responsavel_id = None
        else:
            membro = ctx.db.scalar(
                select(ObraMembro).where(
                    ObraMembro.obra_id == ctx.obra.id,
                    ObraMembro.usuario_id == dados.responsavel_id,
                )
            )
            # Responsável precisa ser da equipe: alguém de fora não enxerga a
            # obra, então receberia notificação sobre o que não pode abrir.
            if membro is None:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    "O responsável precisa fazer parte da equipe desta obra. "
                    "Inclua a pessoa na equipe antes de defini-la como responsável.",
                )
            ctx.obra.responsavel_id = dados.responsavel_id

    auditoria.registrar(
        ctx.db, acao="obra_atualizada", entidade="obra", entidade_id=ctx.obra.id,
        usuario=ctx.usuario, obra_id=ctx.obra.id, request=request,
    )
    ctx.db.commit()
    return ctx.obra


# --------------------------------------------------------------------------
# Logo do empreendimento
# --------------------------------------------------------------------------

# A interface reduz a imagem antes de enviar (lado maior de 640 px), o que
# deixa um logo típico em dezenas de KB. O limite só barra quem burlar a tela.
LOGO_MAX_BYTES = 1024 * 1024


@router.put("/{obra_id}/logo", response_model=ObraOut)
async def enviar_logo(request: Request, ctx: ContextoObra = Depends(contexto_obra)):
    """Troca o logo da obra. A imagem vem crua no corpo do PUT.

    Diferente dos arquivos de projeto, que vão do navegador direto para o
    armazenamento, o logo passa pela API: é pequeno, e precisa ser conferido
    byte a byte antes de ser guardado — é ele que aparece para todo mundo.
    """
    ctx.exigir("gerenciar")

    dados = bytearray()
    async for pedaco in request.stream():
        dados.extend(pedaco)
        if len(dados) > LOGO_MAX_BYTES:
            raise HTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                "O logo passa de 1 MB. Envie uma imagem menor.",
            )
    if not dados:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nenhuma imagem recebida.")

    imagem = detectar_imagem(bytes(dados[:16]))
    if imagem is None:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "Envie o logo em PNG, JPG ou WebP. SVG não é aceito.",
        )

    # Banco e armazenamento são chamadas bloqueantes (o R2 é rede): fora do
    # laço de eventos, para um envio não travar as outras requisições.
    return await run_in_threadpool(_trocar_logo, ctx, bytes(dados), *imagem, request)


def _trocar_logo(
    ctx: ContextoObra, dados: bytes, tipo: str, extensao: str, request: Request
) -> Obra:
    anterior = ctx.obra.logo_chave
    chave = chave_logo(ctx.obra.codigo, extensao)

    # Grava antes de apontar o banco para ele: se a gravação falhar, a obra
    # continua com o logo que tinha, em vez de apontar para o vazio.
    armazenamento.gravar_bytes(chave, dados, tipo)
    ctx.obra.logo_chave = chave
    ctx.obra.logo_tipo = tipo
    auditoria.registrar(
        ctx.db, acao="obra_logo_alterado", entidade="obra", entidade_id=ctx.obra.id,
        usuario=ctx.usuario, obra_id=ctx.obra.id,
        detalhes={"tipo": tipo, "tamanho": len(dados)}, request=request,
    )
    ctx.db.commit()

    if anterior:
        _apagar_imagem(anterior)
    return ctx.obra


@router.delete("/{obra_id}/logo", status_code=status.HTTP_204_NO_CONTENT)
def remover_logo(request: Request, ctx: ContextoObra = Depends(contexto_obra)):
    ctx.exigir("gerenciar")
    anterior = ctx.obra.logo_chave
    if anterior is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    ctx.obra.logo_chave = None
    ctx.obra.logo_tipo = None
    auditoria.registrar(
        ctx.db, acao="obra_logo_removido", entidade="obra", entidade_id=ctx.obra.id,
        usuario=ctx.usuario, obra_id=ctx.obra.id, request=request,
    )
    ctx.db.commit()
    _apagar_imagem(anterior)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _apagar_imagem(chave: str) -> None:
    """Apaga o logo substituído. Falhar aqui não desfaz nada: o banco já não
    aponta para ele, e o pior caso é uma imagem órfã no armazenamento."""
    try:
        armazenamento.remover(chave)
    except Exception as erro:  # noqa: BLE001 — limpeza, nunca motivo de erro
        print(f"aviso: logo antigo não apagado ({chave}): {erro}", flush=True)


# --------------------------------------------------------------------------
# Equipe
# --------------------------------------------------------------------------


@router.get("/{obra_id}/membros", response_model=list[MembroOut])
def listar_membros(ctx: ContextoObra = Depends(contexto_obra)):
    ctx.somente_equipe()
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
    gerencia = ctx.pode("gerenciar")
    if not gerencia:
        ctx.exigir(
            "adicionar_membro",
            "Somente o coordenador ou o engenheiro responsável incluem pessoas na equipe.",
        )
        if dados.papel == PapelObra.coordenador:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "O engenheiro responsável inclui pessoas na equipe, mas não nomeia "
                "coordenador — isso é com o coordenador da obra.",
            )
    novo = ctx.db.get(Usuario, dados.usuario_id)
    if novo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuário não encontrado.")
    if novo.comercial:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "O perfil comercial já vê todas as obras e não entra em equipe — "
            "um papel aqui daria permissões que ele não pode ter.",
        )

    existente = ctx.db.scalar(
        select(ObraMembro).where(
            ObraMembro.obra_id == ctx.obra.id,
            ObraMembro.usuario_id == dados.usuario_id,
        )
    )
    if existente is not None and novo.admin:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{novo.nome} é administrador, e administradores são coordenadores de "
            "todas as obras.",
        )
    if existente is not None:
        if not gerencia:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"{novo.nome} já faz parte da equipe. Trocar o papel é com o coordenador.",
            )
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
    gerencia = ctx.pode("gerenciar")
    if not gerencia:
        ctx.exigir(
            "remover_membro",
            "Somente o coordenador ou o engenheiro responsável removem pessoas da equipe.",
        )
    membro = ctx.db.get(ObraMembro, membro_id)
    if membro is None or membro.obra_id != ctx.obra.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Membro não encontrado.")
    if membro.usuario.admin:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"{membro.usuario.nome} é administrador, e administradores são "
            "coordenadores de todas as obras.",
        )
    if not gerencia:
        if membro.papel == PapelObra.coordenador:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "O engenheiro responsável não remove coordenador — isso é com o "
                "coordenador da obra.",
            )
        if membro.usuario_id == ctx.usuario.id:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Você é o engenheiro responsável desta obra e precisa continuar na "
                "equipe. Peça ao coordenador para trocar o responsável antes.",
            )

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

    # Responsável precisa ser da equipe (ver atualizar): quem sai deixa de ser.
    if ctx.obra.responsavel_id == membro.usuario_id:
        ctx.obra.responsavel_id = None

    detalhes = {"usuario_id": membro.usuario_id, "papel": membro.papel.value}
    ctx.db.delete(membro)
    auditoria.registrar(
        ctx.db, acao="membro_removido", entidade="obra_membro", entidade_id=membro_id,
        usuario=ctx.usuario, obra_id=ctx.obra.id, detalhes=detalhes, request=request,
    )
    ctx.db.commit()


# --------------------------------------------------------------------------
# Padrão de nomenclatura
# --------------------------------------------------------------------------


@router.get("/{obra_id}/padrao", response_model=PadraoOut)
def ver_padrao(ctx: ContextoObra = Depends(contexto_obra)):
    ctx.somente_equipe()
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
    ctx.somente_equipe()
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
        revisao = None
        if r.valido and r.codigo_documento:
            documento = ctx.db.scalar(
                select(Documento).where(
                    Documento.obra_id == ctx.obra.id,
                    Documento.codigo == r.codigo_documento,
                )
            )
            if documento is not None and r.revisao_numero:
                revisao = ctx.db.scalar(
                    select(Revisao).where(
                        Revisao.documento_id == documento.id,
                        Revisao.numero == r.revisao_numero,
                    )
                )

        # Revisão nova num documento sem autorização: mostra antes de subir.
        erros = list(r.erros)
        if r.valido and documento is not None and revisao is None:
            bloqueio = servico_solicitacoes.bloqueio_de_revisao_nova(documento, r.revisao_numero)
            if bloqueio:
                erros.append(bloqueio)
        valido = r.valido and not erros

        resultados.append(
            NomeAnalisado(
                nome_arquivo=nome,
                valido=valido,
                erros=erros,
                codigo_documento=r.codigo_documento,
                disciplina=r.disciplina_codigo,
                fase=r.fase_codigo,
                revisao=r.revisao_numero,
                titulo=r.titulo,
                tipo=TipoArquivo.da_extensao(nome) if r.extensao else None,
                documento_existe=documento is not None,
                documento_titulo=documento.titulo if documento is not None else None,
                precisa_titulo=bool(
                    valido
                    and not (documento is not None and documento.titulo)
                    and not limpar_titulo(r.titulo)
                ),
                revisao_existe=revisao is not None,
                precisa_descricao=bool(valido and revisao is None),
                revisao_status=revisao.status if revisao is not None else None,
            )
        )

    return ValidarNomeSaida(padrao=PadraoOut.model_validate(padrao), resultados=resultados)
