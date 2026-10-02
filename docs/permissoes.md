# Papéis e permissões

Uma pessoa tem **um papel por obra**. O mesmo projetista pode ser coordenador na
Obra A e projetista na Obra B. Além disso existe o perfil global de
**administrador**, que cria obras, usuários e catálogos.

## Matriz

| | Coordenador | Projetista | Obra | Cliente |
|---|:--:|:--:|:--:|:--:|
| Ver documentos liberados | ✓ | ✓ | ✓ | ✓ |
| Baixar documentos liberados | ✓ | ✓ | ✓ | ✓ |
| Ver e baixar revisões obsoletas | ✓ | ✓ | ✓ | |
| Ver revisões ainda em revisão | ✓ | ✓ | | |
| Enviar arquivos | ✓ | ✓ | | |
| Editar título e descrição | ✓ | ✓ | | |
| **Liberar para obra** | ✓ | | | |
| Cancelar revisão | ✓ | | | |
| Gerenciar equipe da obra | ✓ | | | |
| Alterar nomenclatura da obra | ✓ | | | |
| Ver registro de atividades | ✓ | | | |

O administrador tem todas as permissões em todas as obras — e uma a mais,
que nenhum papel de obra tem: **excluir arquivos e revisões**.

## Perfil comercial

Um perfil global, como o de administrador, mas no extremo oposto — o acesso
mais restrito do sistema (pedido da TREELE, 02/10/2026):

| | Comercial |
|---|:--:|
| Quais obras | **Todas**, sem precisar estar em equipe |
| Quais documentos | Só os da disciplina **COM** |
| Quais revisões | Só as **liberadas para obra** — nem obsoletas, nem em andamento |
| Baixar | ✓ |
| Enviar, editar título ou descrição | |
| Liberar, cancelar, excluir | |
| Ver equipe, nomenclatura ou registro de atividades | |
| Criar ou ver usuários, obras e catálogos | |

A regra mora num lugar só (`deps.py`): o mesmo filtro vale para a lista, a
árvore, as pastas, o documento, a lista mestra e o download. O que está fora
do alcance responde "não encontrado" — nem o código do documento aparece.

O comercial **nunca entra em equipe** de obra: um papel ali daria permissões
que o perfil não pode ter. E um usuário é administrador ou comercial, nunca os
dois.

## As escolhas por trás disso

**Projetista envia mas não libera.** É a separação que faz o controle existir.
Quem desenha sobe o arquivo — ele entra como *em revisão* e fica visível para a
equipe de projeto, mas invisível para a obra. Só o coordenador decide que aquilo
virou o projeto oficial. Sem essa separação, o sistema é uma pasta compartilhada
com aparência de sistema.

**A obra vê o histórico, mas não o trabalho em andamento.** São duas coisas
diferentes, e por isso são duas permissões separadas:

- **Revisão obsoleta** é histórico. Quem está em campo às vezes precisa dela
  para conferir o que foi executado semana passada, ou para entender o que
  mudou. O download vem com aviso explícito de que aquela revisão está obsoleta,
  e fica registrado quem baixou.
- **Revisão em andamento** é rascunho. Projeto em elaboração não é projeto, e
  mostrá-lo em campo convida alguém a executar o que ainda vai mudar. Isso a
  obra não vê — nem na lista, nem na árvore, nem no histórico do documento.

O cliente só enxerga o que está liberado: para ele, revisão antiga é ruído.

A diferença entre obra e cliente cresce na Fase 1.5: **a obra poderá solicitar
revisão, o cliente não.**

**Revisão liberada aceita arquivo novo, mas nunca substituição.** É comum
liberar o PDF para a obra não ficar esperando e mandar o DWG depois — isso é
permitido, e o acréscimo fica marcado no registro de atividades.

O que continua proibido é **trocar** um arquivo já liberado. Quem baixou ficaria
com uma versão diferente da que está no sistema, sem saber. Para corrigir
conteúdo, publica-se uma revisão nova. É essa distinção — acrescentar pode,
alterar não — que mantém o histórico confiável.

Revisão obsoleta ou cancelada não aceita nada.

**Excluir é só do administrador, e vale para qualquer status.** Cancelar deixa
a revisão no histórico dizendo que não vale; excluir apaga de vez, banco e
arquivo. É a saída para o que nunca deveria ter entrado — obra errada, arquivo
trocado — e por ser definitiva não fica com papel nenhum da obra. Duas regras
evitam que a exclusão bagunce o acervo:

- Excluir a revisão **liberada** devolve a validade à anterior. Sem isso, a
  obra ficaria sem nenhuma revisão válida do documento.
- Excluir a **única** revisão tira o documento do acervo, e o código pode ser
  enviado de novo do zero.

O registro de atividades guarda o que saiu: documento, revisão, arquivos e o
que voltou a valer.

**Não dá para liberar uma revisão antiga depois de uma mais nova.** Publicar a
R00 depois da R01 já estar liberada deixaria a obra com projeto velho marcado
como válido. O sistema recusa e explica.

## Engenheiro responsável

Cada obra tem um **engenheiro responsável**, definido em Configurações da obra.
Não é o mesmo que coordenador: coordenador é permissão e pode haver vários;
responsável é quem responde pela obra, e é um só.

O responsável pode ter **qualquer papel** na equipe — inclusive *Obra*, que é o
caso comum do engenheiro de campo. Só precisa fazer parte da equipe: alguém de
fora não enxergaria a obra e receberia notificação sobre o que não pode abrir.

**O responsável inclui pessoas na equipe da própria obra** (02/10/2026), seja
qual for o papel dele nela — aparece para ele o item *Equipe da obra* no menu.
Só inclui pessoas já cadastradas. Não nomeia coordenador (quem libera para
obra continua sendo decisão de quem gerencia), não troca o papel de quem já
está e não remove ninguém. Deixou de ser o responsável, perde a permissão.

Quando as notificações entrarem (Fase 1.5), é para ele que elas vão primeiro.

## Registro de atividades

Todo evento relevante fica gravado, com usuário, IP e horário: login, envio,
conclusão de envio, download, liberação, cancelamento, exclusão, mudança de equipe,
alteração de nomenclatura e exportação da lista mestra.

O registro de **download** é o que responde à pergunta que aparece em toda
discussão contratual: *quem tinha qual revisão em mãos, e desde quando.* Ele
guarda também o status da revisão no momento do download — então fica
documentado se alguém baixou algo já obsoleto.

A aplicação nunca edita nem apaga eventos.

## Primeiro acesso

O primeiro administrador é criado na primeira inicialização do sistema. A senha
aparece **uma única vez** no console, a menos que você defina `ADMIN_SENHA` no
`.env`. Troque-a depois do primeiro acesso.

Usuários novos são criados pelo administrador em **Usuários**, com uma senha
inicial que deve ser passada por um canal seguro — a pessoa troca depois em
`POST /auth/senha`.

> Quando vocês quiserem, dá para trocar o login por SSO com a conta Microsoft da
> empresa (Entra ID), já que a TREELE usa Microsoft 365. Ninguém precisa de senha
> nova e o acesso de quem sai da empresa é cortado junto com a conta corporativa.
