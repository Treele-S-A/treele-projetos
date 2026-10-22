# Visualizador 3D de IFC

Abre os modelos IFC do acervo no navegador, sem instalar nada. Várias
disciplinas na mesma cena (modelo federado), cada uma ligando e desligando.

## Onde abrir

- **Página do documento:** botão **Ver em 3D** ao lado de cada arquivo IFC.
- **Acervo:** marque documentos de várias disciplinas e use **Ver em 3D** na
  barra de baixo. Os IFC dos marcados abrem juntos.
- Endereço: `/modelos?arquivos=12,34`, com os ids dos arquivos IFC.

## O que dá para fazer (21/10/2026)

- **Controles:** botão esquerdo arrasta para mover; a roda apertada arrasta
  para girar; girar a roda aproxima e afasta. O botão direito sobre um
  elemento abre o menu **Esconder / Isolar / Mostrar tudo**. **Enquadrar**
  volta a ver tudo.
- Ligar e desligar cada disciplina; **Tirar da cena** remove uma.
- Clicar num elemento: ele fica em destaque e as propriedades aparecem à
  direita (nome, tipo IFC, GlobalId e os conjuntos de propriedades, como os do
  TQS ou do Revit).
- **Isolar seleção**, **Esconder seleção**, **Mostrar tudo** — que traz de
  volta os elementos escondidos, tira os cortes e religa as disciplinas.
- **Corte:** com ele ligado, um duplo clique numa face cria um plano de corte
  ali, e a seta arrasta o plano. **Limpar cortes** tira todos.

As regras são as do download: a obra só abre o que está liberado para obra.
Cada abertura fica no registro de atividades como visualização.

## Conversão: lenta uma vez, rápida depois

O IFC é pesado para o navegador (os da Serra chegam a 200 MB). Na primeira
abertura, a tela converte o IFC para o formato leve de visualização da That
Open (*fragments*): o de climatização da Serra, com 207 MB, vira 4,4 MB em cerca de 40
segundos. Se quem abriu é da equipe (pode enviar projetos), o resultado fica
guardado no Storage, ao lado do IFC (`<chave do IFC>.v1.frag`), e as próximas
aberturas, de qualquer pessoa, levam segundos — duas disciplinas da Serra
abriram em 3,6 s.

- A obra também converte, mas só para si: o modelo que todos vão ver não vem
  dela.
- Revisão nova é arquivo novo: converte de novo na primeira abertura.
- Excluir um IFC em análise apaga o modelo convertido junto.
- Se a biblioteca mudar de formato, sobe a versão (`VERSAO_MODELO` em
  `backend/app/api/arquivos.py`): os antigos deixam de ser usados e cada IFC
  converte de novo na primeira abertura.

## Técnica

- Biblioteca: [That Open](https://thatopen.com) (MIT) — `@thatopen/components`
  3.4.8, `components-front` 3.4.4, `fragments` 3.4.7, `web-ifc` 0.0.77
  (MPL-2.0), `three` 0.185.1. Versões fixas no `package.json`: a API muda
  entre versões.
- `frontend/src/modelo3d/motor.ts`: tudo que é da biblioteca (cena, carga,
  seleção, corte). `conversor.worker.ts`: a conversão do IFC num worker, para
  a tela não travar. `paginas/Modelo3D.tsx`: a tela.
- O WASM do web-ifc e o worker do fragments são copiados para
  `public/web-ifc/` no build (`scripts/copiar-web-ifc.mjs`), e o site os serve
  — nada depende de CDN externa.
- O visualizador carrega só quando alguém abre um modelo (1,3 MB comprimido);
  o resto do sistema não fica mais pesado.
- Servidor: `GET /api/arquivos/{id}/modelo` devolve o modelo convertido, ou o
  IFC e o endereço para guardar a conversão.

## Vistas e pedido de correção (21/10/2026)

**Nova vista** fotografa a tela e abre o painel de marcações:

- Caneta, seta, retângulo, elipse e texto, em quatro cores, com desfazer.
- A vista guarda os modelos da cena (e quais estavam desligados), a câmera,
  os cortes e os elementos selecionados, pelo GlobalId, que não muda entre
  conversões. A imagem marcada fica no Storage
  (`obras/<obra>/_vistas/...png`).
- **Pedir correção** (coordenador e obra): marca uma ou mais disciplinas
  da cena (vem marcada a do elemento selecionado) — cada uma diz o que vai
  acontecer com ela: pedir revisão (liberada), reprovar (em análise, só o
  coordenador) ou nada, com o motivo. Um texto só, e, se for coordenador,
  marca os projetistas. Sai um pedido por disciplina, todos com a mesma
  vista; a falha de um não segura os outros, e o painel mostra o resultado
  de cada. Vira solicitação de revisão com a imagem
  marcada como anexo (uma cópia: a mesma vista pode servir a pedidos de
  várias disciplinas) e com o link **Abrir a vista no 3D**.
  - Pedido do coordenador já nasce autorizado: o projetista da última
    revisão e os marcados recebem o aviso e o e-mail, que cita a vista.
  - Pedido da obra vai para o coordenador autorizar, como os outros.
  - Documento **em análise**: o mesmo botão reprova a revisão (só o
    coordenador), com o motivo e a vista (`POST /revisoes/{id}/reprovar`
    aceita `vista_id`). Quem enviou a revisão recebe o aviso, que cita a
    vista; na página do documento, a reprovação mostra a imagem marcada e o
    link para abrir a vista no 3D.
- **Marcações na cena:** a vista guarda também os desenhos em fundo
  transparente, com o ângulo de visão e a proporção da câmera. Reabrindo a
  vista, eles viram uma placa transparente no plano do alvo da câmera, do
  tamanho do campo de visão: no ângulo da vista, a cena fica idêntica à
  imagem anexada; mexendo a câmera, os desenhos deformam (são 2D numa cena
  3D). **Mostrar as marcações** liga e desliga; **Voltar ao ângulo da
  vista** recoloca a câmera.
- **Vistas da obra**, na lateral do visualizador, com miniatura: qualquer
  pessoa da obra reabre (`/modelos?vista=ID`) e vê a cena como foi marcada.
  Quem abre só vê modelos que poderia abrir sozinho.

Servidor: `POST /obras/{id}/vistas` (devolve o envio da imagem), `POST
/vistas/{id}/imagem` (confirma), `GET /vistas/{id}`, `GET /obras/{id}/vistas`;
`POST /documentos/{id}/solicitacoes` aceita `vista_id` e `mencionados`.

## Conflitos entre disciplinas (22/10/2026)

Botão **Conflitos** no visualizador, com os modelos das disciplinas na cena.
Como no Trimble Connect e no Navisworks, um **conjunto** define o teste:

- **Grupo A** e **grupo B**: disciplinas (EST, HID, ELE…) e categorias IFC
  (Pilar, Viga, Tubo…). "Todas, menos as desmarcadas" ou só as marcadas. O
  conjunto escolhe por disciplina e categoria, não por arquivo, e vale para
  qualquer revisão.
- **Interferência** (uma peça entra na outra mais que a tolerância, padrão
  1 cm) ou **folga** (ficam a menos de X cm; inclui as interferências).
- **Ignorar pares do mesmo modelo** (tubo com a própria conexão).

Furo de laje não aparece porque a laje fica fora do grupo B. Três conjuntos
prontos: instalações × pilares e vigas (sem as paredes e lajes que o
projetista de instalação modela, como as do reservatório), instalações entre
si, e portas e janelas × pilares e vigas.

Resultado em lista, por cota. Clicar enquadra o conflito: A em laranja (a
seleção, com as propriedades), B em magenta translúcido e o resto quase
transparente. **Nova vista** fotografa o conflito e abre a vista com título,
descrição e a disciplina de A marcada para corrigir — o pedido de revisão (ou a
reprovação) sai pelo caminho de sempre. **Ignorar** esconde da lista.

Como funciona (`modelo3d/conflitos.ts` e `conflitos.worker.ts`):

1. As peças de cada grupo saem das categorias do modelo, só as com geometria.
2. A caixa de cada peça é calculada da própria malha e guardada por modelo.
   Não use o `getBoxes` da biblioteca: ele desloca as caixas guardadas ao
   montar os blocos de desenho (`box.translate` em `buildSampleInTile`), e o
   resultado mudava conforme a tela desenhava (caso real: 33 ou 94 conflitos
   no mesmo conjunto).
3. Triagem numa grade de 2 m: na interferência, as caixas precisam se
   sobrepor mais que a tolerância nos três eixos.
4. Teste exato das malhas num worker (three-mesh-bvh): triângulo contra
   triângulo, e peça inteira dentro da outra. Na folga, a menor distância.
5. Achados do mesmo B a menos de 60 cm, no mesmo modelo A, viram um conflito.

Durante a leitura, os modelos ficam congelados (`model.frozen`): o desenho
não se refaz no mesmo worker enquanto a geometria é lida.

Medido no SER (EST, HID água e esgoto, ELE, ARQ): instalações × pilares e
vigas, 59 conflitos (13 s na primeira vez, que calcula as caixas; menos de 2 s
depois); folga de 5 cm, 107; portas e janelas, 94; instalações entre si, 21.

"Entra ~X cm" é estimado pelas caixas.

### Guardados no servidor, com situação (22/10/2026)

A detecção roda no navegador; cada rodada é registrada no servidor
(`api/conflitos.py`, tabelas `conjuntos_conflito`, `rodadas_conflito` e
`conflitos`), que mantém a situação de cada conflito, como no Navisworks:

| Situação | Quando |
|---|---|
| Novo | Apareceu pela primeira vez nesta rodada |
| Ativo | Continua aparecendo (ou voltou depois de resolvido) |
| Aprovado | O coordenador aceitou, com justificativa (o furo que o calculista previu). Não volta a ativo quando aparece de novo |
| Resolvido | Não apareceu numa rodada que tinha **os dois modelos** dele na cena |

- **Mesmo conflito entre revisões**: a mesma peça B (GlobalId) e alguma peça
  A em comum. O GlobalId não muda entre exportações do mesmo modelo; o
  agrupamento das peças A (tubo e conexões vizinhas) pode mudar.
- Rodada sem um dos modelos na cena não resolve os conflitos dele — abrir só a
  hidráulica e a estrutura não "resolve" os da elétrica.
- **Conjuntos da obra**, compartilhados. Os prontos qualquer pessoa da equipe
  usa e nascem na primeira rodada (com as disciplinas da cena de agora); os
  montados são do coordenador (`gerenciar`). Configurar um pronto cria uma
  cópia da obra. Os conjuntos do protótipo, que ficavam no navegador, o
  coordenador leva para a obra ao abrir o painel.
- **Quem faz o quê**: a equipe detecta e cria vistas; o coordenador
  (`autorizar_revisao`) aprova e reabre; o comercial não vê.
- A vista criada de um conflito fica ligada a ele ("Abrir a vista").
- O painel abre com a lista guardada (filtros Abertos, Aprovados, Resolvidos,
  Todos) e a última detecção; o resumo da obra soma os abertos por par de
  disciplinas, contando uma vez o mesmo par de peças em dois conjuntos.

Rotas: `GET/POST /obras/{id}/conjuntos-conflito`, `PATCH/DELETE
/conjuntos-conflito/{id}`, `POST /conjuntos-conflito/{id}/rodadas`, `GET
/conjuntos-conflito/{id}/conflitos`, `PATCH /conflitos/{id}` (situação,
justificativa, vista), `GET /obras/{id}/conflitos/resumo`.

## Próximos passos

1. Prazo e situação por apontamento, no padrão BCF, para exportar e importar
   de outros programas.
2. Importar os conflitos do Navisworks (relatório XML) como vistas.
3. Medidas e árvore por pavimento.
4. O chat responder sobre conflitos ("quantos abertos na hidráulica do
   Serra?").
