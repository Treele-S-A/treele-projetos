from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import montar_contexto, status_visiveis, usuario_atual
from ..models import Revisao, Usuario, VistaModelo
from ..enums import StatusRevisao
from ..enums import StatusSolicitacao
from ..enums import StatusArquivo
from ..schemas import (
    ArquivoLote,
    ArquivosLoteEntrada,
    ArquivosLoteSaida,
    ItemLote,
    LiberarLoteEntrada,
    LiberarLoteSaida,
    PublicarEntrada,
    ReprovarEntrada,
    RevisaoAtualizar,
    RevisaoOut,
)
from ..services import auditoria
from ..services import revisoes as servico
from ..services import notificacoes
from ..services import solicitacoes as servico_solicitacoes

router = APIRouter(prefix="/revisoes", tags=["revisões"])


def _carregar(db: Session, usuario: Usuario, revisao_id: int):
    revisao = db.get(Revisao, revisao_id)
    if revisao is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Revisão não encontrada.")
    ctx = montar_contexto(db, usuario, revisao.documento.obra_id)
    # A mesma regra das listas: o que a pessoa não vê, não existe para ela —
    # nem pelo número da revisão no endereço.
    if revisao.status not in status_visiveis(ctx) or not ctx.ve_disciplina(
        revisao.documento.disciplina.codigo
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Revisão não encontrada.")
    return revisao, ctx


@router.get("/{revisao_id}", response_model=RevisaoOut)
def detalhe(
    revisao_id: int,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    revisao, _ = _carregar(db, usuario, revisao_id)
    return revisao


@router.get("/{revisao_id}/verificar")
def verificar(
    revisao_id: int,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    """O que ainda impede esta revisão de ser liberada.

    A interface consulta isto para explicar o botão desabilitado em vez de só
    recusar a ação depois do clique.
    """
    revisao, ctx = _carregar(db, usuario, revisao_id)
    impedimentos = servico.conferir_publicacao(
        db, revisao, ctx.obra.regra_companheiro
    )
    return {
        "pode_publicar": ctx.pode("publicar") and not impedimentos,
        "tem_permissao": ctx.pode("publicar"),
        "impedimentos": impedimentos,
        "tipos_presentes": sorted(servico.tipos_disponiveis(revisao)),
        "regra_companheiro": ctx.obra.regra_companheiro,
    }


@router.patch("/{revisao_id}", response_model=RevisaoOut)
def atualizar(
    revisao_id: int,
    dados: RevisaoAtualizar,
    request: Request,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    revisao, ctx = _carregar(db, usuario, revisao_id)
    ctx.exigir("enviar")

    if dados.descricao is not None:
        revisao.descricao = dados.descricao.strip() or None

    auditoria.registrar(
        db, acao="revisao_atualizada", entidade="revisao", entidade_id=revisao.id,
        usuario=usuario, obra_id=ctx.obra.id, request=request,
    )
    db.commit()
    return revisao


@router.post("/{revisao_id}/publicar", response_model=RevisaoOut)
def publicar(
    revisao_id: int,
    dados: PublicarEntrada,
    request: Request,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    """Libera para obra — o lado "aprovado" da análise crítica. Torna
    obsoletas as revisões anteriores liberadas."""
    revisao, ctx = _carregar(db, usuario, revisao_id)
    ctx.exigir("publicar", "Somente o coordenador da obra pode liberar revisões.")

    impedimentos = servico.conferir_publicacao(
        db, revisao, ctx.obra.regra_companheiro
    )
    if impedimentos:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {
                "mensagem": "Esta revisão ainda não pode ser liberada para obra.",
                "erros": impedimentos,
            },
        )

    # Pedidos de revisão que esta revisão atende, marcados por quem libera.
    # Conferidos antes de liberar: um pedido inválido não libera nada.
    atendidos = servico_solicitacoes.pedidos_marcados(db, revisao, dados.solicitacoes_atendidas)
    if atendidos is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Alguma das solicitações marcadas não está aberta neste documento. "
            "Recarregue a página e marque de novo.",
        )

    if dados.descricao:
        revisao.descricao = dados.descricao.strip()

    avisos = _liberar(db, revisao, ctx, usuario, atendidos, dados.observacao, dados.avisar, request)
    db.commit()
    notificacoes.enviar_emails(db, avisos)
    db.refresh(revisao)
    return revisao


def _liberar(db, revisao, ctx, usuario, atendidos, observacao, avisar, request, lote=False):
    """Libera uma revisão já conferida. Não faz commit. Devolve os avisos."""
    obsoletas = servico.publicar(db, revisao, usuario.id, observacao)
    servico_solicitacoes.atender(db, revisao, atendidos)
    detalhes = {
        "documento": revisao.documento.codigo,
        "revisao": revisao.numero,
        "obsoletadas": [r.numero for r in obsoletas],
        "solicitacoes_atendidas": [s.id for s in atendidos],
        "observacao": revisao.observacao,
        "avisos": avisar,
    }
    if lote:
        detalhes["lote"] = True
    auditoria.registrar(
        db, acao="revisao_publicada", entidade="revisao", entidade_id=revisao.id,
        usuario=usuario, obra_id=ctx.obra.id, detalhes=detalhes, request=request,
    )
    return notificacoes.ao_liberar(db, revisao, usuario, obsoletas) if avisar else []


@router.post("/liberar-lote", response_model=LiberarLoteSaida)
def liberar_lote(
    dados: LiberarLoteEntrada,
    request: Request,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    """Libera várias revisões de uma vez (TREELE, 15/10/2026).

    Cada uma passa pelas mesmas conferências da liberação avulsa. As que não
    podem ser liberadas voltam com o motivo, e as outras seguem — uma prancha
    sem o PDF não segura as outras cem. Os pedidos de revisão autorizados de
    cada documento fecham como atendidos, como na tela avulsa (lá vêm todos
    marcados). A observação, se houver, vale para todas.
    """
    liberadas: list[ItemLote] = []
    recusadas: list[ItemLote] = []
    carregadas = []
    for revisao_id in dict.fromkeys(dados.revisao_ids):
        try:
            revisao, ctx = _carregar(db, usuario, revisao_id)
        except HTTPException:
            recusadas.append(ItemLote(revisao_id=revisao_id, motivos=["Revisão não encontrada."]))
            continue
        carregadas.append((revisao, ctx))
    # A mais antiga primeiro: R00 e R01 do mesmo documento no mesmo lote
    # terminam com a R01 valendo, como se liberadas uma depois da outra.
    carregadas.sort(key=lambda rc: (rc[0].documento_id, rc[0].ordem))

    avisos = []
    for revisao, ctx in carregadas:
        item = ItemLote(revisao_id=revisao.id, documento=revisao.documento.codigo, revisao=revisao.numero)
        if not ctx.pode("publicar"):
            item.motivos = ["Somente o coordenador da obra pode liberar revisões."]
            recusadas.append(item)
            continue
        impedimentos = servico.conferir_publicacao(db, revisao, ctx.obra.regra_companheiro)
        if impedimentos:
            item.motivos = impedimentos
            recusadas.append(item)
            continue
        autorizados = [s.id for s in revisao.documento.solicitacoes if s.status == StatusSolicitacao.autorizada]
        atendidos = servico_solicitacoes.pedidos_marcados(db, revisao, autorizados) or []
        avisos += _liberar(db, revisao, ctx, usuario, atendidos, dados.observacao, dados.avisar, request, lote=True)
        db.flush()
        liberadas.append(item)
    db.commit()
    notificacoes.enviar_emails(db, avisos)
    return LiberarLoteSaida(liberadas=liberadas, recusadas=recusadas)


@router.post("/arquivos-lote", response_model=ArquivosLoteSaida)
def arquivos_lote(
    dados: ArquivosLoteEntrada,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    """Arquivos das revisões marcadas, para o download em lote (TREELE,
    21/10/2026). Só lista: a tela escolhe os formatos e baixa cada arquivo
    pelo download avulso, que confere de novo e registra quem baixou.

    A regra é a do download avulso (`_conferir_leitura`): o que a pessoa não
    poderia baixar sozinho não entra no lote.
    """
    from .arquivos import _conferir_leitura

    arquivos: list[ArquivoLote] = []
    recusadas: list[ItemLote] = []
    for revisao_id in dict.fromkeys(dados.revisao_ids):
        try:
            revisao, ctx = _carregar(db, usuario, revisao_id)
        except HTTPException:
            recusadas.append(ItemLote(revisao_id=revisao_id, motivos=["Revisão não encontrada."]))
            continue
        doc = revisao.documento
        item = ItemLote(revisao_id=revisao.id, documento=doc.codigo, revisao=revisao.numero)
        disponiveis = [a for a in revisao.arquivos if a.status == StatusArquivo.disponivel]
        if not disponiveis:
            item.motivos = ["A revisão não tem arquivo disponível."]
            recusadas.append(item)
            continue
        try:
            aviso = _conferir_leitura(disponiveis[0], ctx)
        except HTTPException as erro:
            item.motivos = [erro.detail]
            recusadas.append(item)
            continue
        for a in sorted(disponiveis, key=lambda a: a.nome_original):
            arquivos.append(ArquivoLote(
                id=a.id, nome=a.nome_original, tipo=a.tipo.value, tamanho=a.tamanho,
                documento=doc.codigo, revisao=revisao.numero,
                pasta=f"{ctx.obra.codigo}/{doc.disciplina.codigo}", aviso=aviso,
            ))
    return ArquivosLoteSaida(arquivos=arquivos, recusadas=recusadas)


@router.post("/{revisao_id}/reprovar", response_model=RevisaoOut)
def reprovar(
    revisao_id: int,
    dados: ReprovarEntrada,
    request: Request,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    """Reprova na análise crítica (TREELE, 09/10/2026). A observação é
    obrigatória e vai para quem enviou a revisão, no sistema e por e-mail. A
    correção vem numa revisão nova, que não precisa de outra autorização."""
    revisao, ctx = _carregar(db, usuario, revisao_id)
    ctx.exigir("publicar", "Somente o coordenador da obra pode reprovar revisões.")
    if revisao.status != StatusRevisao.em_revisao:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"A R{revisao.numero} está {revisao.status.rotulo.lower()}: só revisão "
            "em revisão passa pela análise crítica.",
        )
    observacao = dados.observacao.strip()
    if not observacao:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Escreva a observação: é o que o projetista precisa corrigir.",
        )

    # Vista do modelo 3D com o problema marcado (21/10/2026): desta obra e com
    # a imagem já guardada.
    vista = None
    if dados.vista_id is not None:
        vista = db.get(VistaModelo, dados.vista_id)
        if vista is None or vista.obra_id != ctx.obra.id or not vista.imagem_tamanho:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Vista do modelo 3D não encontrada.")
        revisao.vista_reprovacao_id = vista.id

    servico.reprovar(db, revisao, usuario.id, observacao)
    auditoria.registrar(
        db, acao="revisao_reprovada", entidade="revisao", entidade_id=revisao.id,
        usuario=usuario, obra_id=ctx.obra.id,
        detalhes={
            "documento": revisao.documento.codigo,
            "revisao": revisao.numero,
            "observacao": observacao,
            **({"vista": vista.titulo} if vista else {}),
        },
        request=request,
    )
    avisos = notificacoes.ao_reprovar(db, revisao, usuario)
    db.commit()
    notificacoes.enviar_emails(db, avisos)
    db.refresh(revisao)
    return revisao


@router.post("/{revisao_id}/cancelar", response_model=RevisaoOut)
def cancelar(
    revisao_id: int,
    request: Request,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    """Cancela a revisão: ela fica no histórico, dizendo que não vale.

    Revisões não se excluem (TREELE, 09/10/2026). O coordenador cancela a que
    está em revisão; o administrador, em qualquer status, a qualquer tempo —
    inclusive a liberada, e aí a liberada anterior volta a valer.
    """
    revisao, ctx = _carregar(db, usuario, revisao_id)
    ctx.exigir("cancelar", "Somente o coordenador da obra pode cancelar revisões.")

    if revisao.status == StatusRevisao.cancelado:
        raise HTTPException(status.HTTP_409_CONFLICT, "Esta revisão já está cancelada.")
    if revisao.status != StatusRevisao.em_revisao and not usuario.admin:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"A R{revisao.numero} está {revisao.status.rotulo.lower()}. Só um "
            "administrador cancela revisão fora da análise.",
        )

    situacao = revisao.status.value
    restaurada = servico.cancelar(db, revisao)
    auditoria.registrar(
        db, acao="revisao_cancelada", entidade="revisao", entidade_id=revisao.id,
        usuario=usuario, obra_id=ctx.obra.id,
        detalhes={
            "documento": revisao.documento.codigo,
            "revisao": revisao.numero,
            "situacao_revisao": situacao,
            "restaurada": restaurada.numero if restaurada else None,
        },
        request=request,
    )
    db.commit()
    db.refresh(revisao)
    return revisao
