"""Enumerações de domínio.

Os valores gravados no banco são as strings em snake_case; os rótulos servem
para exibição na interface e nas mensagens de erro.
"""

import enum


class StatusRevisao(str, enum.Enum):
    em_revisao = "em_revisao"
    liberado_para_obra = "liberado_para_obra"
    obsoleto = "obsoleto"
    cancelado = "cancelado"

    @property
    def rotulo(self) -> str:
        return {
            "em_revisao": "Em revisão",
            "liberado_para_obra": "Liberado para obra",
            "obsoleto": "Obsoleto",
            "cancelado": "Cancelado",
        }[self.value]


class TipoArquivo(str, enum.Enum):
    dwg = "dwg"
    rvt = "rvt"
    pdf = "pdf"
    ifc = "ifc"
    outro = "outro"

    @classmethod
    def da_extensao(cls, nome_arquivo: str) -> "TipoArquivo":
        ext = nome_arquivo.rsplit(".", 1)[-1].lower() if "." in nome_arquivo else ""
        try:
            return cls(ext)
        except ValueError:
            return cls.outro


class StatusArquivo(str, enum.Enum):
    """Ciclo de vida do upload: a linha nasce antes do byte chegar ao storage."""

    pendente = "pendente"
    disponivel = "disponivel"
    erro = "erro"


class StatusSolicitacao(str, enum.Enum):
    """A solicitação de revisão fica aberta até sair a revisão nova liberada."""

    aberta = "aberta"
    atendida = "atendida"


class PapelObra(str, enum.Enum):
    coordenador = "coordenador"
    projetista = "projetista"
    obra = "obra"
    # Existiu "cliente" até 02/10/2026; a TREELE não usa esse papel. Quem só
    # precisa baixar o liberado de todas as obras é o perfil comercial.

    @property
    def rotulo(self) -> str:
        return {
            "coordenador": "Coordenador",
            "projetista": "Projetista",
            "obra": "Obra",
        }[self.value]


# Matriz de permissões por papel. `admin` global ignora esta tabela.
#
#   ver_obsoletos ..... enxerga e baixa revisões obsoletas (sempre com aviso)
#   ver_em_revisao .... enxerga o que ainda não foi liberado: revisões em
#                       andamento e canceladas
#
# São duas chaves separadas de propósito. Histórico e trabalho em andamento são
# coisas diferentes: a obra precisa do primeiro para conferir o que executou, e
# não deve ver o segundo — projeto ainda em elaboração não é projeto.
#   enviar ............ cria documento e sobe arquivo (nasce "em revisão")
#   publicar .......... libera para obra e torna a anterior obsoleta
#   cancelar .......... cancela uma revisão que não deve mais existir
#   gerenciar ......... membros da obra e padrão de nomenclatura
#   solicitar_revisao . pede alteração num projeto liberado, com descrição
#                       obrigatória e anexos opcionais (TREELE, 02/10/2026)
PERMISSOES: dict[PapelObra, set[str]] = {
    PapelObra.coordenador: {
        "ver_obsoletos",
        "ver_em_revisao",
        "enviar",
        "publicar",
        "cancelar",
        "gerenciar",
        "solicitar_revisao",
    },
    PapelObra.projetista: {"ver_obsoletos", "ver_em_revisao", "enviar"},
    # A obra vê o histórico — precisa dele para conferir o que executou semana
    # passada (TREELE, 22/09/2026) — mas não vê o que ainda está em elaboração.
    PapelObra.obra: {"ver_obsoletos", "solicitar_revisao"},
}
