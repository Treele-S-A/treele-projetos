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

O administrador tem todas as permissões em todas as obras.

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

**Não dá para liberar uma revisão antiga depois de uma mais nova.** Publicar a
R00 depois da R01 já estar liberada deixaria a obra com projeto velho marcado
como válido. O sistema recusa e explica.

## Engenheiro responsável

Cada obra tem um **engenheiro responsável**, definido em Configurações da obra.
Não é o mesmo que coordenador: coordenador é permissão e pode haver vários;
responsável é quem responde pela obra, e é um só.

O responsável precisa fazer parte da equipe da obra — alguém de fora não
enxergaria a obra e receberia notificação sobre o que não pode abrir.

Quando as notificações entrarem (Fase 1.5), é para ele que elas vão primeiro.

## Registro de atividades

Todo evento relevante fica gravado, com usuário, IP e horário: login, envio,
conclusão de envio, download, liberação, cancelamento, mudança de equipe,
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
