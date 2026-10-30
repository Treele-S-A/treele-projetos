# Papéis e permissões

Uma pessoa tem **um papel por obra**. O mesmo projetista pode ser coordenador na
Obra A e projetista na Obra B. Além disso existe o perfil global de
**administrador**, que cria obras, usuários e catálogos.

## Matriz

| | Coordenador | Projetista | Obra |
|---|:--:|:--:|:--:|
| Ver documentos liberados | ✓ | ✓ | ✓ |
| **Solicitar revisão** de projeto liberado | ✓ | | ✓ |
| **Autorizar ou recusar revisão** | ✓ | | |
| Baixar documentos liberados | ✓ | ✓ | ✓ |
| Ver e baixar revisões obsoletas | ✓ | ✓ | ✓ |
| Ver revisões ainda em revisão | ✓ | ✓ | |
| Enviar arquivos | ✓ | ✓ | |
| Editar título e descrição | ✓ | ✓ | |
| **Análise crítica: liberar para obra ou reprovar** | ✓ | | |
| Cancelar revisão em revisão | ✓ | | |
| Gerenciar equipe da obra | ✓ | | |
| Alterar nomenclatura da obra | ✓ | | |
| Ver registro de atividades | ✓ | | | |

O administrador tem todas as permissões em todas as obras — e duas a mais,
que nenhum papel de obra tem: **cancelar revisão em qualquer status, a
qualquer tempo** (inclusive a liberada) e **excluir um arquivo avulso** que
entrou trocado — só enquanto a revisão está em revisão (14/10/2026); depois
da análise, o arquivo é histórico. **Revisões e obras não se excluem** (09/10/2026, PBQP-H): o
controle de documentos guarda o histórico. Além disso,
**todo administrador é coordenador de todas as obras** (02/10/2026),
inclusive as criadas depois, e todo administrador criado depois também passa
a ser. Por isso ele aparece na equipe de cada obra e não pode ser removido
dela nem trocar de papel.

## Solicitação e autorização de revisão

Quem está em campo encontra o problema; o coordenador decide; quem desenha
atende (02/10 e 05/10/2026):

- **Quem pede:** a obra. Projetista não pede (é quem atende); o comercial não
  vê pedidos.
- **Quem decide:** o coordenador. Na tela do documento, cada pedido da obra
  traz **Autorizar revisão** e **Recusar**. Recusar exige motivo, e quem pediu
  é avisado com ele.
- **Revisão sem pedido:** o coordenador autoriza direto, no mesmo lugar —
  mudança que vem do cliente, do escritório ou da compatibilização. O pedido
  dele já nasce autorizado.
- **Sem autorização, não há revisão nova.** Documento já liberado para obra
  só aceita a R01, R02… depois de uma revisão autorizada. Com a revisão
  anterior ainda em revisão, também não: os arquivos vão para ela, ou o
  coordenador a cancela. A tela de envio avisa antes de subir o arquivo.
  Documento novo, e arquivo novo numa revisão já liberada (o DWG depois do
  PDF), seguem como sempre.
- **Sobre o quê:** o projeto **liberado para obra** — é o que está sendo
  executado. Documento sem revisão liberada não aceita pedido.
- **Como:** com descrição **obrigatória** do que deve mudar. Fotos e PDFs
  marcados são opcionais (até 25 MB cada, até 10 por pedido); só quem fez o
  pedido anexa, e só enquanto ele está aberto ou autorizado.
- **Onde aparece:** as marcas *Revisão solicitada* (esperando o coordenador)
  e *Revisão autorizada* ao lado do status, na lista e na pasta, e a lista dos
  pedidos na tela do documento. O status continua *Liberado para obra*: o
  projeto vale até sair o novo.
- **Quando fecha:** na liberação da revisão nova para obra, quem libera marca
  numa lista quais revisões autorizadas ela atende — vêm todas marcadas. As
  marcadas fecham ali ("atendida pela R01"); as desmarcadas continuam
  autorizadas.
- **Quem é avisado:** ver [notificacoes.md](notificacoes.md).
- **Revisão reprovada** na análise crítica também abre a revisão nova, sem
  outra autorização: a reprovação já pede a correção.
- **Painel de todas as obras** (06/10/2026): os administradores têm no menu
  *Solicitações de revisão*, com os pedidos de todas as obras — filtro por
  situação e por obra — e um contador dos que aguardam autorização. Clicar
  num pedido abre o documento já nele.

## Análise crítica (PBQP-H)

Revisão **em revisão** é a análise crítica que o PBQP-H exige (TREELE,
09/10/2026). O coordenador tem duas saídas, cada uma com uma caixa
**Observação**:

- **Liberar para obra** — observação opcional. Dá para liberar várias de uma
  vez: no acervo (lista), marcar as revisões em revisão e usar *Liberar para
  obra…*; cada uma passa pelas mesmas conferências, e as que não podem sair
  voltam com o motivo. Fica na revisão ("Observação
  da liberação") e no registro de atividades.
- **Reprovar** — observação **obrigatória**. A revisão vira *Reprovada* e
  fica no histórico, com arquivos, quem reprovou, quando e o motivo: é o
  registro da análise. Quem enviou a revisão (quem a criou ou mandou arquivo
  dela) recebe o motivo no sistema e por e-mail.

A reprovada não se libera nem recebe arquivo; a correção vem numa **revisão
nova** (R01 reprovada → R02), sem precisar de outra autorização. A liberada
anterior, se houver, segue valendo para a obra, que não vê a reprovada.

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
| Liberar, reprovar, cancelar, excluir | |
| Ver equipe, nomenclatura ou registro de atividades | |
| Criar ou ver usuários, obras e catálogos | |

A regra mora num lugar só (`deps.py`): o mesmo filtro vale para a lista, a
árvore, as pastas, o documento, a lista mestra e o download. O que está fora
do alcance responde "não encontrado" — nem o código do documento aparece.

O comercial **nunca entra em equipe** de obra: um papel ali daria permissões
que o perfil não pode ter. E um usuário é administrador ou comercial, nunca os
dois.

## Tipo de acesso (30/10/2026)

Cada pessoa tem um dos quatro tipos da planilha de cargos da TREELE. O
administrador troca o tipo depois em **Usuários → Editar acesso**. A regra
fica em `services/acesso.py`.

| Tipo | O que vê |
|---|---|
| Administrador | Tudo; entra como coordenador em toda obra |
| Comercial | Todas as obras, só a disciplina COM liberada (acima) |
| Usuário de todas as obras | Papel **obra** em toda obra, inclusive nas criadas depois, sem estar na equipe. Recebe os avisos de liberação de toda obra |
| Usuário de obra específica | Só as obras da equipe dele; entrando por aqui, com papel **obra** (o papel muda na equipe da obra) |

Trocar o tipo arruma a equipe junto:
- o administrador rebaixado deixa de ser coordenador das obras em que só
  estava por ser administrador;
- quem vira comercial ou "todas as obras" sai das equipes, porque o tipo já dá
  o acesso;
- em obra específica, ficam só as obras marcadas.

**Senha**: usuário criado sem senha entra com **Entrar com Microsoft**, pela
conta corporativa. O login acha a pessoa pelo e-mail, e a senha local fica uma
que ninguém sabe. Assim a senha é sempre a da Microsoft, e trocá-la lá vale
aqui também.

Os acessos da planilha de cargos (97 pessoas) foram cadastrados assim em
30/10/2026. Quem já existia não foi recriado: só o tipo foi ajustado.

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

Existia também um papel *Cliente*, só com o liberado. Saiu em 02/10/2026: a
TREELE não o usa. Quem precisa só baixar o liberado é o perfil comercial.

**Revisão liberada aceita arquivo novo, mas nunca substituição.** É comum
liberar o PDF para a obra não ficar esperando e mandar o DWG depois — isso é
permitido, e o acréscimo fica marcado no registro de atividades.

O que continua proibido é **trocar** um arquivo já liberado. Quem baixou ficaria
com uma versão diferente da que está no sistema, sem saber. Para corrigir
conteúdo, publica-se uma revisão nova. É essa distinção — acrescentar pode,
alterar não — que mantém o histórico confiável.

Revisão obsoleta, reprovada ou cancelada não aceita nada.

**Nada se exclui: revisão que não vale é cancelada** (09/10/2026). Cancelada,
ela fica no histórico, com os arquivos, dizendo que não vale. O coordenador
cancela a que está em revisão; o administrador, qualquer uma, a qualquer
tempo. Cancelar a **liberada** devolve a validade à liberada anterior — sem
isso, a obra ficaria sem nenhuma revisão válida do documento. O registro de
atividades guarda o status que a revisão tinha e o que voltou a valer.

Até 09/10/2026 o administrador também excluía revisões e obras inteiras; isso
saiu porque um controle de documentos auditado não apaga histórico. As
exclusões antigas continuam no registro de atividades.

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

**O responsável inclui e remove pessoas da equipe da própria obra**
(02/10/2026), seja qual for o papel dele nela — aparece para ele o item
*Equipe da obra* no menu. Inclui pessoas já cadastradas e remove quem está na
equipe, com três limites: não nomeia nem remove coordenador (quem libera para
obra continua sendo decisão de quem gerencia), não troca o papel de quem já
está e não tira a si mesmo. Deixou de ser o responsável, perde a permissão.

Se o próprio responsável sair da equipe (removido pelo coordenador), a obra
fica sem responsável — ele precisa ser da equipe.

Ser responsável, por si só, não faz receber notificação: quem recebe é
definido pelo papel na equipe — ver [notificacoes.md](notificacoes.md).

## Registro de atividades

Todo evento relevante fica gravado, com usuário, IP e horário: login, envio,
conclusão de envio, download, liberação, reprovação (com a observação), cancelamento,
exclusão de arquivo, mudança de equipe,
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
