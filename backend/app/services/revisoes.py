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

from dataclasses import dataclass
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


def publicar(db: Session, revisao: Revisao, usuario_id: int) -> list[Revisao]:
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

    # A revisão nova saiu: os pedidos de alteração do documento estão atendidos.
    from .solicitacoes import atender_ao_liberar

    atender_ao_liberar(db, revisao)

    db.flush()
    return anteriores


def cancelar(db: Session, revisao: Revisao) -> None:
    revisao.status = StatusRevisao.cancelado
    revisao.obsoleta_em = datetime.now(timezone.utc)
    db.flush()


@dataclass
class Exclusao:
    chaves: list[str]
    arquivos: list[str]
    restaurada: Revisao | None
    documento_excluido: bool


def excluir_revisao(db: Session, revisao: Revisao) -> Exclusao:
    """Apaga a revisão e os arquivos dela. Não faz commit nem mexe no storage.

    Se ela era a liberada, a anterior que ela tinha tornado obsoleta volta a
    valer — senão a obra ficaria sem nenhuma revisão válida do documento,
    justamente quando a que saiu foi excluída por estar errada. Se era a única
    revisão, o documento sai junto: documento sem revisão é um código vazio no
    acervo.
    """
    documento = revisao.documento
    chaves = [a.storage_key for a in revisao.arquivos]
    nomes = [a.nome_original for a in revisao.arquivos]

    restaurada = None
    if revisao.status == StatusRevisao.liberado_para_obra:
        restaurada = db.scalar(
            select(Revisao)
            .where(
                Revisao.documento_id == documento.id,
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

    restantes = [r for r in documento.revisoes if r.id != revisao.id]
    if not restantes:
        # O documento sai inteiro, e com ele os pedidos de revisão e os anexos.
        chaves += [a.storage_key for s in documento.solicitacoes for a in s.anexos]
    if restantes:
        documento.revisoes.remove(revisao)
        db.delete(revisao)
    else:
        db.delete(documento)
    db.flush()

    return Exclusao(
        chaves=chaves,
        arquivos=nomes,
        restaurada=restaurada,
        documento_excluido=not restantes,
    )


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
