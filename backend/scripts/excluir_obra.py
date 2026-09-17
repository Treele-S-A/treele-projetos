"""Exclui uma obra e tudo que pende dela. Operação irreversível.

    python scripts/excluir_obra.py TRL001              # mostra o que seria apagado
    python scripts/excluir_obra.py TRL001 --confirmar TRL001

É script, não botão de tela, de propósito: apagar uma obra inteira não deve
estar a um clique de distância de ninguém dentro do sistema.

Três cuidados que um DELETE cru não teria:

1. **Objetos no armazenamento.** Apagar as linhas do banco deixaria os arquivos
   no bucket para sempre, ocupando espaço sem nada apontando para eles.
2. **Trilha de auditoria.** Os eventos não são apagados: perdem o vínculo com a
   obra (`obra_id` vira nulo) e continuam registrando quem fez o quê. Apagar
   log é o oposto do que este sistema existe para fazer.
3. **Ordem.** O banco é alterado primeiro e só então o armazenamento é limpo.
   Se a limpeza falhar no meio, sobra lixo no bucket — que é recuperável.
   O contrário deixaria o catálogo apontando para arquivo inexistente.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, func, select, update  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import Arquivo, Documento, Evento, Obra, Revisao  # noqa: E402
from app.services.storage import armazenamento  # noqa: E402


def principal() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("codigo", help="Código da obra a excluir (ex.: TRL001)")
    p.add_argument(
        "--confirmar",
        metavar="CODIGO",
        help="Repita o código da obra para confirmar. Sem isto, nada é apagado.",
    )
    args = p.parse_args()
    codigo = args.codigo.upper()

    with SessionLocal() as db:
        obra = db.scalar(select(Obra).where(Obra.codigo == codigo))
        if obra is None:
            print(f"Obra '{codigo}' não existe.")
            return 1

        documentos = db.scalar(
            select(func.count()).select_from(Documento).where(Documento.obra_id == obra.id)
        )
        revisoes = db.scalar(
            select(func.count())
            .select_from(Revisao)
            .join(Documento, Documento.id == Revisao.documento_id)
            .where(Documento.obra_id == obra.id)
        )
        chaves = list(
            db.scalars(
                select(Arquivo.storage_key)
                .join(Revisao, Revisao.id == Arquivo.revisao_id)
                .join(Documento, Documento.id == Revisao.documento_id)
                .where(Documento.obra_id == obra.id)
            )
        )
        eventos = db.scalar(
            select(func.count()).select_from(Evento).where(Evento.obra_id == obra.id)
        )

        print(f"\nObra {obra.codigo} — {obra.nome}")
        print(f"  {documentos} documento(s)")
        print(f"  {revisoes} revisão(ões)")
        print(f"  {len(chaves)} arquivo(s) no armazenamento")
        print(f"  {eventos} evento(s) de auditoria (serão mantidos, sem vínculo)")

        if args.confirmar != codigo:
            print(
                f"\nNada foi apagado. Para confirmar:\n"
                f"  python scripts/excluir_obra.py {codigo} --confirmar {codigo}\n"
            )
            return 0

        # 1. Preserva a auditoria, soltando o vínculo com a obra.
        db.execute(
            update(Evento).where(Evento.obra_id == obra.id).values(obra_id=None)
        )

        # 2. DELETE no nível do Core: deixa as cascatas do banco cuidarem de
        #    membros, documentos, revisões, arquivos e padrão. Pelo ORM, o
        #    SQLAlchemy tentaria anular `documentos.obra_id`, que é NOT NULL.
        db.execute(delete(Obra).where(Obra.id == obra.id))
        db.commit()
        print(f"\nBanco: obra {codigo} removida.")

    # 3. Só agora o armazenamento.
    removidos = falhas = 0
    for chave in chaves:
        try:
            armazenamento.remover(chave)
            removidos += 1
        except Exception as e:  # pragma: no cover - depende do storage
            falhas += 1
            print(f"  não consegui remover {chave}: {e}")

    print(f"Armazenamento: {removidos} objeto(s) removido(s)", end="")
    print(f", {falhas} falha(s)." if falhas else ".")
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
