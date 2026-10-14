from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import ContextoObra, montar_contexto, usuario_atual
from ..enums import StatusArquivo, StatusRevisao, TipoArquivo
from ..models import Arquivo, Usuario
from ..schemas import ArquivoOut, DownloadSaida, RevisaoOut, UploadConfirmarSaida
from ..services import auditoria, notificacoes
from ..services.revisoes import remover_do_armazenamento
from ..services.storage import armazenamento

router = APIRouter(prefix="/arquivos", tags=["arquivos"])


def _carregar(db: Session, usuario: Usuario, arquivo_id: int) -> tuple[Arquivo, ContextoObra]:
    arquivo = db.get(Arquivo, arquivo_id)
    if arquivo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Arquivo não encontrado.")
    ctx = montar_contexto(db, usuario, arquivo.revisao.documento.obra_id)
    if not ctx.ve_disciplina(arquivo.revisao.documento.disciplina.codigo):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Arquivo não encontrado.")
    return arquivo, ctx


@router.post("/{arquivo_id}/confirmar", response_model=UploadConfirmarSaida)
def confirmar(
    arquivo_id: int,
    request: Request,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    """Confere no storage que os bytes chegaram e marca o arquivo disponível."""
    arquivo, ctx = _carregar(db, usuario, arquivo_id)
    ctx.exigir("enviar")

    existe, tamanho = armazenamento.info(arquivo.storage_key)
    if not existe:
        arquivo.status = StatusArquivo.erro
        db.commit()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "O arquivo não chegou ao armazenamento. Tente enviar novamente.",
        )

    arquivo.status = StatusArquivo.disponivel
    arquivo.tamanho = tamanho

    auditoria.registrar(
        db, acao="upload_concluido", entidade="arquivo", entidade_id=arquivo.id,
        usuario=usuario, obra_id=ctx.obra.id,
        detalhes={"arquivo": arquivo.nome_original, "tamanho": tamanho},
        request=request,
    )
    # Revisão em andamento recebeu arquivo: os coordenadores sabem da revisão
    # nova — uma vez só, no primeiro arquivo (o serviço confere).
    avisos = []
    if arquivo.revisao.status == StatusRevisao.em_revisao:
        db.flush()
        avisos = notificacoes.ao_enviar_revisao(db, arquivo.revisao, usuario)
    db.commit()
    notificacoes.enviar_emails(db, avisos)
    db.refresh(arquivo.revisao)

    return UploadConfirmarSaida(
        arquivo=ArquivoOut.model_validate(arquivo),
        revisao=RevisaoOut.model_validate(arquivo.revisao),
    )


def _conferir_leitura(arquivo: Arquivo, ctx: ContextoObra) -> str | None:
    """Pode ler (baixar ou visualizar) este arquivo? Devolve o aviso, se houver.

    Baixar e visualizar são a mesma leitura: a regra é uma só, e quem não
    pode baixar uma revisão obsoleta também não pode abri-la no navegador.
    """
    revisao = arquivo.revisao

    if arquivo.status != StatusArquivo.disponivel:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Este arquivo ainda não está disponível."
        )

    aviso = None
    if revisao.status == StatusRevisao.obsoleto:
        if not ctx.pode("ver_obsoletos"):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Esta revisão está obsoleta e seu papel não permite baixá-la.",
            )
        aviso = (
            f"ATENÇÃO: a revisão R{revisao.numero} está OBSOLETA. "
            "Não use este arquivo para execução."
        )
    elif revisao.status == StatusRevisao.cancelado:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Esta revisão foi cancelada."
        )
    elif revisao.status == StatusRevisao.reprovado:
        if not ctx.pode("ver_em_revisao"):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Esta revisão foi reprovada."
            )
        aviso = (
            f"ATENÇÃO: a revisão R{revisao.numero} foi REPROVADA na análise "
            "crítica. Não use este arquivo para execução."
        )
    elif revisao.status == StatusRevisao.em_revisao:
        if not ctx.pode("ver_em_revisao"):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Esta revisão ainda não foi liberada para obra.",
            )
        aviso = (
            f"A revisão R{revisao.numero} ainda está EM REVISÃO "
            "e não foi liberada para obra."
        )

    return aviso


def _registrar_leitura(db, acao, arquivo, ctx, usuario, request) -> None:
    revisao = arquivo.revisao
    auditoria.registrar(
        db, acao=acao, entidade="arquivo", entidade_id=arquivo.id,
        usuario=usuario, obra_id=ctx.obra.id,
        detalhes={
            "arquivo": arquivo.nome_original,
            "documento": revisao.documento.codigo,
            "revisao": revisao.numero,
            "status_revisao": revisao.status.value,
        },
        request=request,
    )
    db.commit()


@router.get("/{arquivo_id}/download", response_model=DownloadSaida)
def download(
    arquivo_id: int,
    request: Request,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    """Devolve uma URL assinada de curta duração — e registra quem baixou."""
    arquivo, ctx = _carregar(db, usuario, arquivo_id)
    aviso = _conferir_leitura(arquivo, ctx)
    url = armazenamento.url_download(arquivo.storage_key, arquivo.nome_original)
    _registrar_leitura(db, "download", arquivo, ctx, usuario, request)
    return DownloadSaida(url=url, nome_arquivo=arquivo.nome_original, aviso=aviso)


@router.get("/{arquivo_id}/visualizar", response_model=DownloadSaida)
def visualizar(
    arquivo_id: int,
    request: Request,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    """URL assinada que ABRE o PDF no navegador, em vez de baixar.

    Só PDF: é o formato que o navegador mostra sozinho. O tipo e o "inline"
    vão dentro da assinatura — quem tem o link não troca nenhum dos dois.
    """
    arquivo, ctx = _carregar(db, usuario, arquivo_id)
    if arquivo.tipo != TipoArquivo.pdf:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "Só PDF abre no navegador. Para os outros formatos, baixe o arquivo.",
        )
    aviso = _conferir_leitura(arquivo, ctx)
    url = armazenamento.url_visualizar(arquivo.storage_key, arquivo.nome_original)
    _registrar_leitura(db, "visualizacao", arquivo, ctx, usuario, request)
    return DownloadSaida(url=url, nome_arquivo=arquivo.nome_original, aviso=aviso)


@router.delete("/{arquivo_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover(
    arquivo_id: int,
    request: Request,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    """Exclui o arquivo de vez — banco e armazenamento. Só administrador, e só
    de revisão ainda em revisão (TREELE, 14/10/2026).

    É a saída para o arquivo que entrou trocado enquanto a revisão está em
    análise. Depois da análise — liberada, reprovada, obsoleta, cancelada — o
    arquivo é histórico e não sai mais: o que não vale se resolve cancelando
    a revisão. O registro de atividades guarda o que saiu.
    """
    arquivo, ctx = _carregar(db, usuario, arquivo_id)
    if not usuario.admin:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Somente um administrador pode excluir arquivos."
        )

    revisao = arquivo.revisao
    if revisao.status != StatusRevisao.em_revisao:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"A R{revisao.numero} está {revisao.status.rotulo.lower()}: o arquivo faz "
            "parte do histórico e não pode ser excluído. Se a revisão não deve valer, "
            "cancele-a.",
        )
    chave = arquivo.storage_key

    db.delete(arquivo)
    auditoria.registrar(
        db, acao="arquivo_removido", entidade="arquivo", entidade_id=arquivo_id,
        usuario=usuario, obra_id=ctx.obra.id,
        detalhes={
            "documento": revisao.documento.codigo,
            "revisao": revisao.numero,
            "arquivo": arquivo.nome_original,
            "situacao_revisao": revisao.status.value,
        },
        request=request,
    )
    db.commit()
    remover_do_armazenamento(db, [chave])
