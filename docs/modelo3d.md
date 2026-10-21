# Visualizador 3D de IFC

Abre os modelos IFC do acervo no navegador, sem instalar nada. Várias
disciplinas na mesma cena (modelo federado), cada uma ligando e desligando.

## Onde abrir

- **Página do documento:** botão **Ver em 3D** ao lado de cada arquivo IFC.
- **Acervo:** marque documentos de várias disciplinas e use **Ver em 3D** na
  barra de baixo. Os IFC dos marcados abrem juntos.
- Endereço: `/modelos?arquivos=12,34`, com os ids dos arquivos IFC.

## O que dá para fazer (21/10/2026)

- Girar, mover e aproximar; **Enquadrar** volta a ver tudo.
- Ligar e desligar cada disciplina; **Tirar da cena** remove uma.
- Clicar num elemento: ele fica em destaque e as propriedades aparecem à
  direita (nome, tipo IFC, GlobalId e os conjuntos de propriedades, como os do
  TQS ou do Revit).
- **Isolar seleção**, **Esconder seleção**, **Mostrar tudo**.
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
- **Vistas da obra**, na lateral do visualizador, com miniatura: qualquer
  pessoa da obra reabre (`/modelos?vista=ID`) e vê a cena como foi marcada.
  Quem abre só vê modelos que poderia abrir sozinho.

Servidor: `POST /obras/{id}/vistas` (devolve o envio da imagem), `POST
/vistas/{id}/imagem` (confirma), `GET /vistas/{id}`, `GET /obras/{id}/vistas`;
`POST /documentos/{id}/solicitacoes` aceita `vista_id` e `mencionados`.

## Próximos passos

1. Prazo e situação por apontamento (aberto, em correção, resolvido), no
   padrão BCF, para exportar e importar de outros programas.
2. Importar os conflitos do Navisworks (relatório XML) como vistas.
3. Medidas e árvore por pavimento.
