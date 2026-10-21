from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import ContextoObra, montar_contexto, usuario_atual
from ..enums import StatusArquivo, StatusRevisao, TipoArquivo
from ..models import Arquivo, Usuario
from ..schemas import (
    ArquivoOut,
    ConfirmarEntrada,
    DownloadSaida,
    EnvioModelo,
    ModeloSaida,
    RevisaoOut,
    UploadConfirmarSaida,
)
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
    dados: ConfirmarEntrada | None = None,
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
    # Só coordenador (ou administrador) pode calar o aviso; o envio do
    # projetista sempre avisa os coordenadores (TREELE, 15/10/2026).
    avisar = (dados.avisar if dados else True) or not ctx.pode("publicar")
    if avisar and arquivo.revisao.status == StatusRevisao.em_revisao:
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


# Versão do formato de visualização (fragments da That Open 3.4). Sobe quando a
# biblioteca mudar de formato: os modelos antigos deixam de ser usados e cada
# um é convertido de novo na primeira abertura.
VERSAO_MODELO = "v1"


def chave_modelo(arquivo: Arquivo) -> str:
    """O modelo convertido mora ao lado do IFC, com o mesmo nome."""
    return f"{arquivo.storage_key}.{VERSAO_MODELO}.frag"


# Versão do resumo de quantitativos (frontend/src/modelo3d/resumo-ifc.ts).
VERSAO_RESUMO = "r1"


def chave_resumo(arquivo: Arquivo) -> str:
    """Resumo de quantitativos do IFC, para o chat (21/10/2026)."""
    return f"{arquivo.storage_key}.{VERSAO_RESUMO}.resumo.json"


@router.get("/{arquivo_id}/modelo", response_model=ModeloSaida)
def modelo(
    arquivo_id: int,
    request: Request,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
):
    """Abre um IFC no visualizador 3D. Mesma regra do download, e a abertura
    fica no registro como visualização."""
    arquivo, ctx = _carregar(db, usuario, arquivo_id)
    if arquivo.tipo != TipoArquivo.ifc:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "Só IFC abre no visualizador 3D.",
        )
    aviso = _conferir_leitura(arquivo, ctx)
    revisao = arquivo.revisao
    doc = revisao.documento
    saida = ModeloSaida(
        arquivo_id=arquivo.id, nome=arquivo.nome_original, obra_id=ctx.obra.id,
        obra=ctx.obra.codigo, documento=doc.codigo,
        documento_id=doc.id, titulo=doc.titulo, disciplina=doc.disciplina.codigo,
        revisao_id=revisao.id, revisao=revisao.numero, status_revisao=revisao.status.value, aviso=aviso,
        tamanho_ifc=arquivo.tamanho,
    )
    chave = chave_modelo(arquivo)
    pronto, tamanho = armazenamento.info(chave)
    if pronto and tamanho > 0:
        saida.modelo_url = armazenamento.url_download(chave, arquivo.nome_original + ".frag")
        saida.tamanho_modelo = tamanho
    else:
        saida.ifc_url = armazenamento.url_download(arquivo.storage_key, arquivo.nome_original)
        # Quem envia projetos (equipe) guarda a conversão para todos. A obra
        # converte só para si: o modelo que os outros vão ver não vem dela.
        if ctx.pode("enviar"):
            destino = armazenamento.destino_upload(chave, "application/octet-stream")
            saida.envio = EnvioModelo(url=destino.url, metodo=destino.metodo, headers=destino.headers)
    # O resumo sai da mesma conversão: quem guarda o modelo guarda o resumo.
    saida.resumo_pronto = armazenamento.info(chave_resumo(arquivo))[0]
    if not saida.resumo_pronto and ctx.pode("enviar") and saida.envio:
        destino = armazenamento.destino_upload(chave_resumo(arquivo), "application/json")
        saida.envio_resumo = EnvioModelo(url=destino.url, metodo=destino.metodo, headers=destino.headers)
    _registrar_leitura(db, "visualizacao", arquivo, ctx, usuario, request)
    return saida


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
    # O modelo 3D convertido vai junto (se houver; apagar o que não existe não falha).
    chaves = (
        [chave, chave_modelo(arquivo), chave_resumo(arquivo)] if arquivo.tipo == TipoArquivo.ifc else [chave]
    )

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
    remover_do_armazenamento(db, chaves)
