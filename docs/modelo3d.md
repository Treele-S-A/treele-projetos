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

## Próximos passos

1. Apontamentos para os projetistas no modelo (to-dos no padrão BCF), com foto da
   vista, elemento marcado e prazo.
2. Importar os conflitos do Navisworks (relatório XML) como apontamentos.
3. Medidas e árvore por pavimento.
