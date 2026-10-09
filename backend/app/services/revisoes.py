"""Regras de ciclo de vida da revisão.

Duas regras concentram quase todo o valor do sistema:

1. **Arquivo companheiro.** Não se libera um DWG sem o PDF plotado, nem um RVT
   sem o IFC exportado. Isso não é burocracia: é o que garante que sempre exista
   um formato legível por máquina para o diff automático da Fase 3, e um formato
   legível por humano para quem está na obra.

2. **Obsolescência automática.** Publicou a R02, a R01 vira obsoleta no mesmo
   instante. É o inverso da pasta de rede, onde a revisão velha continua ali
   parecendo válida até alguém imprimir e executar errado.
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..enums import StatusArquivo, StatusRevisao, TipoArquivo
from ..models import Arquivo, Revisao
from .storage import armazenamento


def tipos_disponiveis(revisao: Revisao) -> set[str]:
    return {
        a.tipo.value
        for a in revisao.arquivos
        if a.status == StatusArquivo.disponivel
    }


def conferir_companheiros(revisao: Revisao, regra: dict | None) -> list[str]:
    """Erros que impedem a liberação por falta de arquivo companheiro."""
    if not regra:
        return []

    presentes = tipos_disponiveis(revisao)
    erros: list[str] = []

    for tipo, exigidos in regra.items():
        if tipo not in presentes:
            continue
        exigidos = [e.lower() for e in (exigidos or [])]
        if not exigidos or presentes.intersection(exigidos):
            continue
        rotulo = {
            "dwg": "o PDF plotado",
            "rvt": "o IFC exportado",
        }.get(tipo, " ou ".join(f".{e}" for e in exigidos))
        erros.append(
            f"Esta revisão tem .{tipo} mas não tem {rotulo}. "
            f"Envie um arquivo {' ou '.join(f'.{e}' for e in exigidos)} "
            f"antes de liberar para obra."
        )
    return erros


def conferir_publicacao(
    db: Session, revisao: Revisao, regra: dict | None
) -> list[str]:
    """Todos os impedimentos para liberar esta revisão."""
    erros: list[str] = []

    if revisao.status == StatusRevisao.liberado_para_obra:
        erros.append("Esta revisão já está liberada para obra.")
        return erros
    if revisao.status == StatusRevisao.cancelado:
        erros.append("Esta revisão foi cancelada e não pode ser liberada.")
        return erros
    if revisao.status == StatusRevisao.reprovado:
        erros.append(
            "Esta revisão foi reprovada na análise crítica. A correção vem numa "
            "revisão nova."
        )
        return erros
    if revisao.status != StatusRevisao.em_revisao:
        erros.append(f"Esta revisão está {revisao.status.rotulo.lower()}.")
        return erros

    disponiveis = [a for a in revisao.arquivos if a.status == StatusArquivo.disponivel]
    if not disponiveis:
        erros.append(
            "Esta revisão não tem nenhum arquivo concluído. "
            "Conclua o envio antes de liberar."
        )
        return erros

    erros.extend(conferir_companheiros(revisao, regra))

    mais_nova = db.scalar(
        select(Revisao)
        .where(
            Revisao.documento_id == revisao.documento_id,
            Revisao.status == StatusRevisao.liberado_para_obra,
            Revisao.ordem > revisao.ordem,
        )
        .order_by(Revisao.ordem.desc())
        .limit(1)
    )
    if mais_nova is not None:
        erros.append(
            f"Já existe uma revisão mais recente liberada (R{mais_nova.numero}). "
            f"Liberar a R{revisao.numero} agora deixaria a obra com projeto antigo."
        )

    return erros


def publicar(
    db: Session, revisao: Revisao, usuario_id: int, observacao: str | None = None
) -> list[Revisao]:
    """Libera a revisão e devolve as que ficaram obsoletas."""
    agora = datetime.now(timezone.utc)

    anteriores = list(
        db.scalars(
            select(Revisao).where(
                Revisao.documento_id == revisao.documento_id,
                Revisao.id != revisao.id,
                Revisao.status == StatusRevisao.liberado_para_obra,
                Revisao.ordem < revisao.ordem,
            )
        )
    )
    for anterior in anteriores:
        anterior.status = StatusRevisao.obsoleto
        anterior.obsoleta_em = agora

    revisao.status = StatusRevisao.liberado_para_obra
    revisao.publicada_em = agora
    revisao.publicada_por_id = usuario_id
    revisao.observacao = (observacao or "").strip() or None

    db.flush()
    return anteriores


def reprovar(db: Session, revisao: Revisao, usuario_id: int, observacao: str) -> None:
    """Reprova na análise crítica. A revisão fica no histórico, com arquivos e
    observação; a liberada anterior, se houver, segue valendo."""
    revisao.status = StatusRevisao.reprovado
    revisao.reprovada_em = datetime.now(timezone.utc)
    revisao.reprovada_por_id = usuario_id
    revisao.observacao = observacao.strip()
    db.flush()


def cancelar(db: Session, revisao: Revisao) -> Revisao | None:
    """Cancela a revisão. Ela fica no histórico, dizendo que não vale.

    Nada se exclui (TREELE, 09/10/2026): o administrador cancela em qualquer
    status. Se a cancelada era a liberada, a liberada anterior — que ela tinha
    tornado obsoleta — volta a valer, senão a obra ficaria sem nenhuma revisão
    válida do documento. Devolve a que voltou, se alguma voltou.
    """
    restaurada = None
    if revisao.status == StatusRevisao.liberado_para_obra:
        restaurada = db.scalar(
            select(Revisao)
            .where(
                Revisao.documento_id == revisao.documento_id,
                Revisao.id != revisao.id,
                Revisao.status == StatusRevisao.obsoleto,
                Revisao.ordem < revisao.ordem,
            )
            .order_by(Revisao.ordem.desc())
            .limit(1)
        )
        if restaurada is not None:
            restaurada.status = StatusRevisao.liberado_para_obra
            restaurada.obsoleta_em = None

    revisao.status = StatusRevisao.cancelado
    revisao.obsoleta_em = datetime.now(timezone.utc)
    db.flush()
    return restaurada


def remover_do_armazenamento(db: Session, chaves: list[str]) -> None:
    """Apaga os objetos depois do commit — o banco já não aponta para eles.

    Chave que outro arquivo ainda usa fica. Falha aqui não volta atrás: o
    registro já saiu do banco, e um objeto órfão no storage é só espaço, não
    inconsistência. Fica o aviso no log para limpar depois.
    """
    for chave in chaves:
        if db.scalar(select(Arquivo.id).where(Arquivo.storage_key == chave).limit(1)):
            continue
        try:
            armazenamento.remover(chave)
        except Exception as erro:  # noqa: BLE001 - storage externo, qualquer falha
            print(f"aviso: objeto '{chave}' ficou no armazenamento ({erro})", flush=True)


def proxima_revisao(db: Session, documento_id: int, formato: str = "numerico") -> str:
    """Sugestão do próximo número de revisão para o documento."""
    ultima = db.scalar(
        select(Revisao)
        .where(Revisao.documento_id == documento_id)
        .order_by(Revisao.ordem.desc())
        .limit(1)
    )
    if ultima is None:
        return "A" if formato == "alfabetico" else "00"
    if formato == "alfabetico":
        return chr(ord(ultima.numero[-1].upper()) + 1)
    largura = len(ultima.numero)
    return str(ultima.ordem + 1).zfill(largura)


def rotulo_tipo(tipo: TipoArquivo) -> str:
    return {
        TipoArquivo.dwg: "AutoCAD",
        TipoArquivo.rvt: "Revit",
        TipoArquivo.pdf: "PDF",
        TipoArquivo.ifc: "IFC",
        TipoArquivo.outro: "Outro",
    }[tipo]
