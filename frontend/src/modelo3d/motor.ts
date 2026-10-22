/** O motor do visualizador 3D (TREELE, 21/10/2026): That Open (three.js +
 *  fragments). Tudo que é da biblioteca mora aqui; a tela (Modelo3D.tsx) só
 *  chama estas funções.
 *
 *  Os modelos chegam já no formato leve (fragments): ou o que ficou guardado
 *  no servidor, ou o que acabou de ser convertido do IFC (converter()). */

import * as OBC from "@thatopen/components";
import * as OBCF from "@thatopen/components-front";
import * as FRAGS from "@thatopen/fragments";
import CameraControls from "camera-controls";
import * as THREE from "three";
import {
  caixaDasPecas,
  contarCategorias,
  detectar,
  type ConjuntoConflito,
  type Conflito,
  type Fase,
} from "./conflitos";
import type { PedidoConversao, RespostaConversao } from "./conversor.worker";
import type { ResumoIfc } from "./resumo-ifc";

export type Valor = string | number | boolean | null;

/** Propriedades do elemento clicado, já prontas para a tela. */
export interface Propriedades {
  modelId: string;
  localId: number;
  nome: string | null;
  categoria: string | null;
  guid: string | null;
  atributos: [string, Valor][];
  grupos: { titulo: string; linhas: [string, Valor][] }[];
}

type Ponto3 = [number, number, number];

/** O que uma vista guarda da cena (o resto — modelos, ocultos — a tela sabe). */
export interface EstadoCena {
  /** fov: ângulo de visão vertical (graus), para as marcações voltarem do
   *  mesmo tamanho. */
  camera: { posicao: Ponto3; alvo: Ponto3; fov?: number | null; aspecto?: number | null };
  cortes: { normal: Ponto3; ponto: Ponto3 }[];
  /** modelId → GlobalIds selecionados. */
  selecao: Record<string, string[]>;
}

/** Um pavimento do modelo (IfcBuildingStorey) e as peças nele, por categoria. */
export interface Pavimento {
  localId: number;
  nome: string;
  /** Na unidade do IFC (o Revit exporta em metro ou centímetro). */
  elevacao: number | null;
  pecas: Record<string, number[]>;
}

export type ModoMedida = "distancia" | "area";

export interface Medida {
  tipo: ModoMedida;
  /** m ou m². */
  valor: number;
}

/** modelId → localIds. */
export type Pecas = Record<string, number[]>;

/** Um tópico para exportar em BCF: um conflito ou uma vista. */
export interface TopicoBcf {
  titulo: string;
  descricao?: string;
  /** "Clash" (conflito) ou "Issue" (apontamento). */
  tipo: string;
  /** "Open", "Resolved" ou "Closed". */
  situacao: string;
  rotulos: string[];
  comentarios: string[];
  /** GlobalIds das peças em destaque. */
  guids: string[];
  /** Põe a câmera no lugar do tópico (enquadra o conflito, aplica a vista).
   *  `paraFoto`: false quando não vai foto — basta a câmera, sem destaque. */
  posicionar: (paraFoto: boolean) => Promise<void>;
  /** A foto pronta (a imagem marcada da vista); sem ela, fotografa a tela. */
  foto?: Blob;
}

/** Um tópico lido de um arquivo BCF de outro programa. */
export interface TopicoImportado {
  guid: string;
  titulo: string;
  descricao: string;
  tipo: string;
  situacao: string;
  autor: string;
  data: string;
  comentarios: { autor: string; texto: string; data: string }[];
  viewpoint: string | null;
  /** URL local da foto do ponto de vista, se veio. */
  foto: string | null;
  guids: string[];
}

export interface Motor {
  carregar(modelId: string, frag: ArrayBuffer | Uint8Array): Promise<void>;
  /** A cena agora: câmera, cortes e seleção. */
  estado(): Promise<EstadoCena>;
  /** Volta a uma cena guardada. */
  aplicar(cena: EstadoCena): Promise<void>;
  /** A tela como PNG (com a seleção em destaque), vista da câmera dada —
   *  a mesma que a vista grava, mesmo com a câmera ainda em movimento. */
  fotografar(camera?: EstadoCena["camera"]): Promise<Blob>;
  mostrarModelo(modelId: string, visivel: boolean): Promise<void>;
  enquadrar(): Promise<void>;
  isolarSelecao(): Promise<void>;
  esconderSelecao(): Promise<void>;
  /** Mostra os elementos escondidos e tira os cortes. */
  mostrarTudo(): Promise<void>;
  /** Põe na cena os desenhos de uma vista, onde coincidem com a foto. */
  mostrarMarcacoes(url: string, camera: EstadoCena["camera"]): Promise<void>;
  verMarcacoes(visiveis: boolean): void;
  corte(ativo: boolean): void;
  limparCortes(): void;
  /** Elementos de cada categoria IFC do modelo (para montar os grupos). */
  categorias(modelId: string): Promise<Record<string, number>>;
  detectarConflitos(
    modelos: { modelId: string; disciplina: string }[],
    conjunto: ConjuntoConflito,
    aoProgredir: (fase: Fase, valor: number) => void,
  ): Promise<Conflito[]>;
  /** Enquadra o conflito: A em destaque (a seleção), B translúcido em
   *  vermelho, para ver a peça que o atravessa. null limpa. */
  focarConflito(conflito: Conflito | null, animar?: boolean): Promise<void>;
  /** Os localIds das peças, pelos GlobalIds (conflito de outra rodada). */
  idsDosGuids(modelId: string, guids: string[]): Promise<number[]>;
  /** Só a câmera no conflito, sem destaque nem redesenho. */
  cameraNoConflito(conflito: Conflito): Promise<void>;
  /** Os pavimentos do modelo, na ordem da elevação. */
  pavimentos(modelId: string): Promise<Pavimento[]>;
  mostrarPecas(pecas: Pecas, visiveis: boolean): Promise<void>;
  isolarPecas(pecas: Pecas): Promise<void>;
  enquadrarPecas(pecas: Pecas): Promise<void>;
  /** Liga a régua (distância), a área ou nada. Na distância, duplo clique
   *  nos dois pontos; na área, duplo clique na face. Delete apaga a medida
   *  sob o mouse. */
  medir(modo: ModoMedida | null): void;
  medidas(): Medida[];
  apagarMedidas(): void;
  /** Avisa a tela quando uma medida entra ou sai. */
  aoMudarMedidas(aviso: () => void): void;
  /** Gera o .bcfzip (BCF 2.1) com os tópicos: um ponto de vista por tópico,
   *  com a câmera, as peças em destaque e a foto. */
  bcfExportar(
    topicos: TopicoBcf[],
    aoProgredir: (feitos: number, total: number) => void,
    /** Fotografar cada tópico: o lento (destacar, redesenhar). Sem foto, a
     *  câmera e as peças vão do mesmo jeito, e sai em segundos. */
    comFotos?: boolean,
  ): Promise<Blob>;
  /** Lê um .bcfzip/.bcf de outro programa. */
  bcfImportar(bytes: Uint8Array): Promise<TopicoImportado[]>;
  /** Vai ao ponto de vista importado: câmera, cortes e peças em destaque. */
  bcfIr(viewpoint: string): Promise<void>;
  descartar(): void;
}

const COR_SELECAO = new THREE.Color("#f0a500");

/** De cima e de lado, sempre do mesmo jeito, a uma distância que mostra o
 *  entorno: a região de um conflito costuma ter centímetros. */
function olharPara(conflito: Conflito): [number, number, number, number, number, number] {
  const caixa = new THREE.Box3(new THREE.Vector3(...conflito.caixa.min), new THREE.Vector3(...conflito.caixa.max));
  const c = new THREE.Vector3(...conflito.centro);
  const d = Math.max(caixa.getSize(new THREE.Vector3()).length(), 1) * 1.5 + 2.5;
  return [c.x + d * 0.65, c.y + d * 0.55, c.z + d * 0.65, c.x, c.y, c.z];
}

/** O texto do BCF vem do XML sem decodificar (&quot; e companhia). */
function textoXml(texto: string | undefined | null): string {
  if (!texto) return "";
  return texto
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&#(\d+);/g, (_, n) => String.fromCharCode(Number(n)))
    .replace(/&amp;/g, "&");
}

function mapaDe(pecas: Pecas): OBC.ModelIdMap {
  const mapa: OBC.ModelIdMap = {};
  for (const [modelId, ids] of Object.entries(pecas)) if (ids.length) mapa[modelId] = new Set(ids);
  return mapa;
}
const COR_CONFLITO = new THREE.Color("#d61f9c"); // magenta: pilar costuma vir vermelho
const MATERIAL_A: FRAGS.MaterialDefinition = {
  color: COR_SELECAO,
  opacity: 1,
  transparent: false,
  renderedFaces: FRAGS.RenderedFaces.TWO,
};
const MATERIAL_B: FRAGS.MaterialDefinition = {
  color: COR_CONFLITO,
  opacity: 0.55,
  transparent: true,
  renderedFaces: FRAGS.RenderedFaces.TWO,
};

/** Converte um IFC em fragments num worker, com o andamento de 0 a 1. */
export function converter(
  bytes: Uint8Array,
  aoProgredir: (p: number) => void,
): Promise<{ frag: Uint8Array; resumo: ResumoIfc | null; indice: Uint8Array | null }> {
  return new Promise((resolver, rejeitar) => {
    const worker = new Worker(new URL("./conversor.worker.ts", import.meta.url), { type: "module" });
    worker.onmessage = (e: MessageEvent<RespostaConversao>) => {
      const r = e.data;
      if (r.tipo === "progresso") aoProgredir(r.valor);
      else {
        worker.terminate();
        if (r.tipo === "pronto") resolver({ frag: r.frag, resumo: r.resumo, indice: r.indice });
        else rejeitar(new Error(r.mensagem));
      }
    };
    worker.onerror = (e) => {
      worker.terminate();
      rejeitar(new Error(e.message || "A conversão do IFC falhou."));
    };
    const pedido: PedidoConversao = { bytes, wasm: new URL("/web-ifc/", location.origin).href };
    worker.postMessage(pedido, [bytes.buffer]);
  });
}

export async function criarMotor(
  container: HTMLElement,
  aoSelecionar: (p: Propriedades | null) => void,
  /** Botão direito sobre um elemento: a posição do clique no palco. */
  aoMenu?: (posicao: { x: number; y: number }) => void,
): Promise<Motor> {
  const components = new OBC.Components();
  const world = components
    .get(OBC.Worlds)
    .create<OBC.SimpleScene, OBC.OrthoPerspectiveCamera, OBC.SimpleRenderer>();
  world.scene = new OBC.SimpleScene(components);
  world.scene.setup();
  world.scene.three.background = new THREE.Color("#eef2f3");
  world.renderer = new OBC.SimpleRenderer(components, container);
  world.camera = new OBC.OrthoPerspectiveCamera(components);
  components.init();
  // Controles (TREELE, 21/10/2026): esquerdo arrasta para mover, a roda
  // apertada gira, girar a roda aproxima e afasta, e o direito fica para o
  // menu de esconder e isolar.
  const botoes = world.camera.controls.mouseButtons;
  botoes.left = CameraControls.ACTION.TRUCK;
  botoes.middle = CameraControls.ACTION.ROTATE;
  botoes.right = CameraControls.ACTION.NONE;
  components.get(OBC.Grids).create(world);
  components.get(OBC.Raycasters).get(world);

  const fragments = components.get(OBC.FragmentsManager);
  // Copiado para public/ no build (scripts/copiar-web-ifc.mjs).
  fragments.init("/web-ifc/fragments-worker.mjs");
  world.camera.controls.addEventListener("update", () => fragments.core.update());
  fragments.list.onItemSet.add(({ value: model }) => {
    model.useCamera(world.camera.three);
    world.scene.three.add(model.object);
    fragments.core.update(true);
  });
  // Faces coincidentes de disciplinas diferentes piscam (z-fighting); um
  // pequeno deslocamento por material resolve, como no exemplo da biblioteca.
  fragments.core.models.materials.list.onItemSet.add(({ value: material }) => {
    if (!("isLodMaterial" in material && material.isLodMaterial)) {
      material.polygonOffset = true;
      material.polygonOffsetUnits = 1;
      material.polygonOffsetFactor = Math.random();
    }
  });

  const highlighter = components.get(OBCF.Highlighter);
  highlighter.setup({
    world,
    selectMaterialDefinition: {
      color: COR_SELECAO,
      opacity: 1,
      transparent: false,
      renderedFaces: FRAGS.RenderedFaces.TWO,
    },
  });
  let selecao: OBC.ModelIdMap = {};
  highlighter.events.select.onHighlight.add(async (mapa) => {
    selecao = mapa;
    aoSelecionar(await propriedades(fragments, mapa));
  });
  highlighter.events.select.onClear.add(() => {
    selecao = {};
    aoSelecionar(null);
  });

  const clipper = components.get(OBC.Clipper);
  clipper.enabled = false;
  // Medidas (22/10/2026): régua e área da biblioteca. Desligadas até a
  // pessoa escolher; com uma ligada, o duplo clique marca os pontos.
  const regua = components.get(OBCF.LengthMeasurement);
  regua.world = world;
  regua.color = new THREE.Color("#0070a8");
  regua.enabled = false;
  const areas = components.get(OBCF.AreaMeasurement);
  areas.world = world;
  areas.color = new THREE.Color("#0070a8");
  areas.enabled = false;
  // Área pela face clicada (a laje, a parede): um duplo clique dá a área da
  // face inteira. Os cantos livres exigem pontos no mesmo plano, e na prática
  // o clique pega a borda ou a peça de trás (testado em 22/10/2026).
  areas.mode = "face";
  let avisarMedidas: () => void = () => {};
  for (const lista of [regua.list, areas.list]) {
    lista.onItemAdded.add(() => avisarMedidas());
    lista.onItemDeleted.add(() => avisarMedidas());
    lista.onCleared.add(() => avisarMedidas());
  }
  const aoTeclar = (e: KeyboardEvent) => {
    if (!regua.enabled && !areas.enabled) return;
    if (e.key === "Enter" && areas.enabled) areas.endCreation();
    else if (e.key === "Escape") {
      regua.cancelCreation();
      areas.cancelCreation();
    } else if (e.key === "Delete" || e.key === "Backspace") {
      if (regua.enabled) regua.delete();
      if (areas.enabled) areas.delete();
    }
  };
  window.addEventListener("keydown", aoTeclar);

  const aoDuploClique = () => {
    if (regua.enabled) return void regua.create();
    if (areas.enabled) return void areas.create();
    if (clipper.enabled) void clipper.create(world);
  };
  container.addEventListener("dblclick", aoDuploClique);

  const hider = components.get(OBC.Hider);

  // Botão direito: seleciona o elemento sob o mouse e abre o menu.
  const aoMenuContexto = async (e: MouseEvent) => {
    e.preventDefault();
    await highlighter.highlight("select", true, false);
    if (!Object.keys(highlighter.selection.select ?? {}).length) return;
    const caixa = container.getBoundingClientRect();
    aoMenu?.({ x: e.clientX - caixa.left, y: e.clientY - caixa.top });
  };
  container.addEventListener("contextmenu", aoMenuContexto);

  let marcacoes: THREE.Mesh | null = null;

  async function fotografarCena(camera?: EstadoCena["camera"], formato: "image/png" | "image/jpeg" = "image/png"): Promise<Blob> {
    // Sem preserveDrawingBuffer o WebGL limpa a tela depois de mostrar:
    // desenha agora e lê na mesma hora. A câmera vai para os números que
    // a vista grava (o controle a move aos poucos, quadro a quadro).
    const cam = world.camera.three;
    if (camera) {
      cam.position.set(...camera.posicao);
      cam.up.set(0, 1, 0);
      cam.lookAt(new THREE.Vector3(...camera.alvo));
      cam.updateMatrixWorld();
    }
    await fragments.core.update(true);
    const renderer = world.renderer!.three;
    renderer.render(world.scene.three, world.camera.three);
    const dados = renderer.domElement.toDataURL(formato, 0.85);
    return await (await fetch(dados)).blob();
  }

  // BCF (22/10/2026): o formato aberto de apontamentos de BIM, que o Revit
  // (BCF Manager), o Solibri, o Trimble Connect e o BIMcollab leem. A
  // biblioteca converte a câmera para as coordenadas do IFC (Z para cima),
  // descontando o alinhamento entre modelos. Versão 2.1: a mais aceita.
  const bcf = components.get(OBC.BCFTopics);
  bcf.setup({
    version: "2.1",
    author: "projetos.treele.com.br",
    types: new Set(["Clash", "Issue"]),
    statuses: new Set(["Open", "Resolved", "Closed"]),
    strict: false,
    // Lê as peças pelo modelo: separa seleção de exceção (sem isso, a biblioteca
    // grava as peças em destaque também como exceção, e com a visibilidade
    // padrão ligada exceção quer dizer "esconder" — o Revit e o Solibri sumiam
    // justamente com elas) e manda o id do elemento no Revit (AuthoringToolId).
    includeSelectionTag: true,
    updateExtensionsOnImport: true,
    fallbackVersionOnImport: "2.1",
    ignoreIncompleteTopicsOnImport: false,
  });
  const pontosDeVista = components.get(OBC.Viewpoints);
  // Com um conflito em foco, o resto dos modelos fica translúcido; aqui, as
  // peças do conflito em foco (as únicas que não estão translúcidas).
  let emFoco: Map<string, Set<number>> | null = null;
  // As peças pintadas pelo conflito em foco, e a peça A (a "seleção").
  let destaque: Map<string, Set<number>> | null = null;
  let destaqueA: OBC.ModelIdMap = {};
  const comGeometria = new Map<string, Promise<Set<number>>>();
  const pecas = (modelId: string): Promise<Set<number>> => {
    let p = comGeometria.get(modelId);
    if (!p) {
      const model = fragments.list.get(modelId);
      p = model ? model.getItemsIdsWithGeometry().then((ids) => new Set(ids)) : Promise.resolve(new Set<number>());
      comGeometria.set(modelId, p);
    }
    return p;
  };

  return {
    async carregar(modelId, frag) {
      const model = await fragments.core.load(frag, { modelId });
      // A biblioteca desloca o modelo para alinhá-lo ao primeiro; a matriz
      // vai junto já, e não só quando a tela desenhar (ver conflitos.ts).
      model.object.updateMatrix();
      model.object.updateMatrixWorld(true);
    },
    async estado() {
      const posicao = world.camera.controls.getPosition(new THREE.Vector3());
      const alvo = world.camera.controls.getTarget(new THREE.Vector3());
      // O plano que corta de verdade é o `three`: arrastar a seta move o
      // corte, mas o `origin` da biblioteca fica onde o plano nasceu (uma
      // vista gravada assim reabria com os cortes fora do lugar).
      const cortes = [...clipper.list.values()].map((p) => ({
        normal: p.three.normal.toArray() as Ponto3,
        ponto: p.three.coplanarPoint(new THREE.Vector3()).toArray() as Ponto3,
      }));
      // A seleção da tela, ou a peça A do conflito em foco.
      const selecionados = highlighter.selection.select ?? {};
      const marcados = Object.keys(selecionados).length ? selecionados : destaqueA;
      const porModelo: Record<string, string[]> = {};
      for (const [modelId, ids] of Object.entries(marcados)) {
        const model = fragments.list.get(modelId);
        if (!model || !ids.size) continue;
        const guids = (await model.getGuidsByLocalIds([...ids])).filter((g): g is string => !!g);
        if (guids.length) porModelo[modelId] = guids;
      }
      const cam = world.camera.three;
      return {
        camera: {
          posicao: posicao.toArray() as Ponto3,
          alvo: alvo.toArray() as Ponto3,
          fov: cam instanceof THREE.PerspectiveCamera ? cam.fov : null,
          aspecto: cam instanceof THREE.PerspectiveCamera ? cam.aspect : null,
        },
        cortes,
        selecao: porModelo,
      };
    },
    async aplicar(cena) {
      const [px, py, pz] = cena.camera.posicao;
      const [ax, ay, az] = cena.camera.alvo;
      await world.camera.controls.setLookAt(px, py, pz, ax, ay, az, false);
      // Aplica já na câmera: o controle só passa a posição a ela no próximo
      // quadro, e a foto ou as marcações não podem esperar por ele.
      world.camera.controls.update(0);
      clipper.deleteAll();
      for (const c of cena.cortes) {
        clipper.createFromNormalAndCoplanarPoint(
          world,
          new THREE.Vector3(...c.normal),
          new THREE.Vector3(...c.ponto),
        );
      }
      const mapa: OBC.ModelIdMap = {};
      for (const [modelId, guids] of Object.entries(cena.selecao)) {
        const model = fragments.list.get(modelId);
        if (!model) continue;
        const ids = (await model.getLocalIdsByGuids(guids)).filter((i): i is number => i !== null);
        if (ids.length) mapa[modelId] = new Set(ids);
      }
      if (Object.keys(mapa).length) await highlighter.highlightByID("select", mapa, true, false);
      await fragments.core.update(true);
    },
    async fotografar(camera) {
      return await fotografarCena(camera);
    },
    async mostrarModelo(modelId, visivel) {
      const model = fragments.list.get(modelId);
      if (!model) return;
      model.object.visible = visivel;
      await fragments.core.update(true);
    },
    async enquadrar() {
      // Pela caixa de cada modelo visível: imediato. O fitToItems da
      // biblioteca mede elemento por elemento e segurava a tela por segundos.
      const caixa = new THREE.Box3();
      for (const model of fragments.list.values()) {
        if (model.object.visible) caixa.union(model.box);
      }
      if (!caixa.isEmpty()) await world.camera.controls.fitToBox(caixa, true);
    },
    async isolarSelecao() {
      if (Object.keys(selecao).length) await hider.isolate(selecao);
    },
    async esconderSelecao() {
      if (!Object.keys(selecao).length) return;
      await hider.set(false, selecao);
      await highlighter.clear("select");
    },
    async mostrarTudo() {
      await hider.set(true);
      clipper.deleteAll();
      await fragments.core.update(true);
    },
    async mostrarMarcacoes(url, camera) {
      // Os desenhos viram uma placa transparente no plano que passa pelo alvo
      // da câmera, de frente para ela e do tamanho exato do campo de visão:
      // no ângulo da vista, coincide com a foto; girando, deforma — são
      // desenhos 2D numa cena 3D.
      const textura = await new THREE.TextureLoader().setCrossOrigin("anonymous").loadAsync(url);
      textura.colorSpace = THREE.SRGBColorSpace;
      const posicao = new THREE.Vector3(...camera.posicao);
      const alvo = new THREE.Vector3(...camera.alvo);
      const cam = world.camera.three;
      const fov = camera.fov ?? (cam instanceof THREE.PerspectiveCamera ? cam.fov : 60);
      const altura = 2 * posicao.distanceTo(alvo) * Math.tan(THREE.MathUtils.degToRad(fov) / 2);
      const imagem = textura.image as { width: number; height: number };
      // A largura que a câmera via; sem o dado (vista antiga), a da imagem.
      const largura = altura * (camera.aspecto ?? imagem.width / imagem.height);
      if (marcacoes) {
        world.scene.three.remove(marcacoes);
        marcacoes.geometry.dispose();
      }
      marcacoes = new THREE.Mesh(
        new THREE.PlaneGeometry(largura, altura),
        new THREE.MeshBasicMaterial({
          map: textura,
          transparent: true,
          depthTest: false,
          depthWrite: false,
          side: THREE.DoubleSide,
        }),
      );
      marcacoes.renderOrder = 999; // por cima do modelo, sempre
      marcacoes.raycast = () => {}; // não atrapalha o clique nos elementos
      marcacoes.position.copy(alvo);
      marcacoes.quaternion.setFromRotationMatrix(
        new THREE.Matrix4().lookAt(posicao, alvo, new THREE.Vector3(0, 1, 0)),
      );
      world.scene.three.add(marcacoes);
    },
    verMarcacoes(visiveis) {
      if (marcacoes) marcacoes.visible = visiveis;
    },
    corte(ativo) {
      clipper.enabled = ativo;
    },
    limparCortes() {
      clipper.deleteAll();
    },
    async categorias(modelId) {
      const model = fragments.list.get(modelId);
      return model ? await contarCategorias(model) : {};
    },
    async detectarConflitos(modelos, conjunto, aoProgredir) {
      const naCena = modelos.flatMap(({ modelId, disciplina }) => {
        const model = fragments.list.get(modelId);
        return model ? [{ modelId, disciplina, model }] : [];
      });
      // A tela para de atualizar os modelos enquanto a geometria é lida: com
      // o desenho se refazendo no mesmo worker, a mesma detecção dava 59 numa
      // página e 107 na outra (22/10/2026). Espera o que estava pendente.
      for (const { model } of naCena) model.frozen = true;
      try {
        for (let i = 0; i < 100 && naCena.some(({ model }) => model.isBusy); i++) {
          await new Promise((r) => setTimeout(r, 50));
        }
        return await detectar(naCena, conjunto, aoProgredir);
      } finally {
        for (const { model } of naCena) model.frozen = false;
      }
    },
    async focarConflito(conflito, animar = true) {
      // As peças do conflito anterior voltam ao normal (e logo abaixo viram
      // fantasma com o resto).
      if (destaque) {
        for (const [modelId, ids] of destaque) {
          const model = fragments.list.get(modelId);
          if (model && ids.size) await model.resetHighlight([...ids]);
        }
      }
      if (!conflito) {
        destaque = null;
        destaqueA = {};
        if (emFoco) {
          for (const [modelId, model] of fragments.list) await model.resetOpacity([...(await pecas(modelId))]);
          emFoco = null;
        }
        aoSelecionar(null);
        await fragments.core.update(true);
        return;
      }
      if (Object.keys(highlighter.selection.select ?? {}).length) await highlighter.clear("select");
      // A em laranja e B em magenta translúcido, pintados direto no modelo:
      // pela ferramenta de seleção da biblioteca, cada conflito levava uns
      // 3 s (medido em 22/10/2026), e a exportação em BCF com fotos, minutos.
      // Um lado pode não estar na cena (conflito de outra rodada, modelo
      // fechado): enquadra do mesmo jeito, pela região guardada.
      const atuais = new Map<string, Set<number>>();
      for (const [lado, material] of [
        [conflito.a, MATERIAL_A],
        [conflito.b, MATERIAL_B],
      ] as const) {
        const model = lado.modelId ? fragments.list.get(lado.modelId) : undefined;
        if (!model || !lado.localIds.length) continue;
        await model.highlight(lado.localIds, material);
        const s = atuais.get(lado.modelId) ?? new Set<number>();
        lado.localIds.forEach((id) => s.add(id));
        atuais.set(lado.modelId, s);
      }
      // O resto vira fantasma: o conflito costuma estar atrás de laje e viga.
      // Da primeira vez, todas as peças; depois, só as do conflito anterior
      // (um modelo de arquitetura tem dezenas de milhares de peças).
      for (const [modelId, model] of fragments.list) {
        const alvo = emFoco ? (destaque?.get(modelId) ?? new Set<number>()) : await pecas(modelId);
        const ids = [...alvo].filter((id) => !atuais.get(modelId)?.has(id));
        if (ids.length) await model.setOpacity(ids, 0.12);
      }
      emFoco = atuais;
      destaque = atuais;
      // A peça A é a seleção: as propriedades aparecem, e Isolar, Esconder e
      // a Nova vista valem para ela.
      destaqueA = conflito.a.modelId && conflito.a.localIds.length
        ? { [conflito.a.modelId]: new Set(conflito.a.localIds) }
        : {};
      selecao = destaqueA;
      if (Object.keys(destaqueA).length) aoSelecionar(await propriedades(fragments, destaqueA));
      await world.camera.controls.setLookAt(...olharPara(conflito), animar);
      await fragments.core.update(true);
    },
    async cameraNoConflito(conflito) {
      const [px, py, pz, ax, ay, az] = olharPara(conflito);
      await world.camera.controls.setLookAt(px, py, pz, ax, ay, az, false);
      world.camera.controls.update(0);
    },
    async idsDosGuids(modelId, guids) {
      const model = fragments.list.get(modelId);
      if (!model || !guids.length) return [];
      return (await model.getLocalIdsByGuids(guids)).filter((i): i is number => i !== null);
    },
    async pavimentos(modelId) {
      const model = fragments.list.get(modelId);
      if (!model) return [];
      const arvore = await model.getSpatialStructure();
      const comMalha = new Set(await model.getItemsIdsWithGeometry());
      // Os pavimentos pela categoria do modelo; na árvore, a categoria pode
      // vir num nó de agrupamento acima deles, sem localId.
      const ehPavimento = new Set(
        Object.values(await model.getItemsOfCategories([/^IFCBUILDINGSTOREY$/i])).flat(),
      );
      const achados: { localId: number; pecas: Record<string, number[]> }[] = [];
      // Desce a árvore; dentro de um pavimento, junta as peças com geometria
      // pela categoria (os nós de categoria vêm sem localId).
      const juntar = (no: FRAGS.SpatialTreeItem, pecas: Record<string, number[]>, categoria: string | null) => {
        const cat = (no.category ?? categoria ?? "").toUpperCase();
        if (no.localId !== null && comMalha.has(no.localId)) (pecas[cat] ??= []).push(no.localId);
        for (const filho of no.children ?? []) juntar(filho, pecas, no.localId === null ? cat : null);
      };
      const descer = (no: FRAGS.SpatialTreeItem) => {
        if (no.localId !== null && ehPavimento.has(no.localId)) {
          const pecas: Record<string, number[]> = {};
          for (const filho of no.children ?? []) juntar(filho, pecas, null);
          achados.push({ localId: no.localId, pecas });
          return;
        }
        for (const filho of no.children ?? []) descer(filho);
      };
      descer(arvore);
      if (!achados.length) return [];
      const dados = (await model.getItemsData(
        achados.map((a) => a.localId),
        { attributesDefault: false, attributes: ["Name", "Elevation"], relationsDefault: { attributes: false, relations: false } },
      )) as unknown as Record<string, { value?: unknown } | undefined>[];
      const lista: Pavimento[] = [];
      for (const [i, a] of achados.entries()) {
        lista.push({
          localId: a.localId,
          nome: String(dados[i]?.Name?.value ?? `Pavimento ${i + 1}`),
          elevacao: typeof dados[i]?.Elevation?.value === "number" ? (dados[i]!.Elevation!.value as number) : null,
          pecas: a.pecas,
        });
      }
      return lista.sort((p, q) => (p.elevacao ?? 0) - (q.elevacao ?? 0));
    },
    async mostrarPecas(pecas, visiveis) {
      await hider.set(visiveis, mapaDe(pecas));
    },
    async isolarPecas(pecas) {
      await hider.isolate(mapaDe(pecas));
    },
    async enquadrarPecas(pecas) {
      const caixa = new THREE.Box3();
      for (const [modelId, ids] of Object.entries(pecas)) {
        const model = fragments.list.get(modelId);
        if (model && ids.length) caixa.union(await caixaDasPecas(model, ids));
      }
      if (!caixa.isEmpty()) await world.camera.controls.fitToBox(caixa, true);
    },
    medir(modo) {
      regua.enabled = modo === "distancia";
      areas.enabled = modo === "area";
      if (modo) clipper.enabled = false;
    },
    medidas() {
      return [
        ...[...regua.list].map((l) => ({ tipo: "distancia" as const, valor: l.value })),
        ...[...areas.list].map((a) => ({ tipo: "area" as const, valor: a.value })),
      ];
    },
    apagarMedidas() {
      regua.list.clear();
      areas.list.clear();
    },
    aoMudarMedidas(aviso) {
      avisarMedidas = aviso;
    },
    async bcfExportar(topicos, aoProgredir, comFotos = true) {
      const criados: OBC.Topic[] = [];
      const vistas: OBC.Viewpoint[] = [];
      try {
        for (const [i, t] of topicos.entries()) {
          await t.posicionar(comFotos);
          world.camera.controls.update(0);
          // JPEG: 258 conflitos com foto em PNG davam 50 MB (o BCF aceita os dois).
          const foto = t.foto ?? (comFotos ? await fotografarCena(undefined, "image/jpeg") : null);
          const vp = pontosDeVista.create();
          vp.world = world;
          await vp.updateCamera(false);
          // Sem título no ponto de vista: a biblioteca usa o título como nome do
          // arquivo, e "Tubo / duto" virava pasta no zip. O título vai no tópico.
          for (const guid of t.guids) vp.selectionComponents.add(guid);
          if (foto) {
            pontosDeVista.snapshots.set(vp.guid, new Uint8Array(await foto.arrayBuffer()));
            vp.snapshot = vp.guid;
          }
          vistas.push(vp);
          const topico = bcf.create({
            title: t.titulo,
            description: t.descricao,
            type: t.tipo,
            status: t.situacao,
            labels: new Set(t.rotulos),
          });
          topico.viewpoints.add(vp.guid);
          for (const texto of t.comentarios) topico.createComment(texto, vp.guid);
          criados.push(topico);
          aoProgredir(i + 1, topicos.length);
        }
        return await bcf.export(criados);
      } finally {
        // O BCF exportado não fica no visualizador.
        for (const t of criados) bcf.list.delete(t.guid);
        for (const vp of vistas) {
          pontosDeVista.snapshots.delete(vp.guid);
          pontosDeVista.list.delete(vp.guid);
        }
      }
    },
    async bcfImportar(bytes) {
      const { topics } = await bcf.load(bytes);
      return topics.map((t) => {
        const viewpoint = [...t.viewpoints][0] ?? null;
        const vp = viewpoint ? pontosDeVista.list.get(viewpoint) : undefined;
        const dadosFoto = vp?.snapshot ? pontosDeVista.snapshots.get(vp.snapshot) : undefined;
        const tipoFoto = vp?.snapshot ? pontosDeVista.getSnapshotExtension(vp.snapshot) : "png";
        return {
          guid: t.guid,
          titulo: textoXml(t.title),
          descricao: textoXml(t.description),
          tipo: textoXml(t.type),
          situacao: textoXml(t.status),
          autor: textoXml(t.creationAuthor),
          data: t.creationDate instanceof Date ? t.creationDate.toISOString() : String(t.creationDate ?? ""),
          comentarios: [...t.comments.values()].map((c) => ({
            autor: textoXml(c.author),
            texto: textoXml(c.comment),
            data: c.date instanceof Date ? c.date.toISOString() : String(c.date ?? ""),
          })),
          viewpoint: vp ? vp.guid : null,
          foto: dadosFoto
            ? URL.createObjectURL(new Blob([dadosFoto as BlobPart], { type: `image/${tipoFoto === "jpg" ? "jpeg" : tipoFoto}` }))
            : null,
          guids: vp ? [...vp.selectionComponents] : [],
        };
      });
    },
    async bcfIr(viewpoint) {
      const vp = pontosDeVista.list.get(viewpoint);
      if (!vp) return;
      vp.world = world;
      await vp.go({ applyVisibility: false, applyClippings: true, clippingsVisibility: false });
      // As peças pelos GlobalIds, em todos os modelos da cena (o mapa da
      // biblioteca vinha vazio para o ponto de vista importado).
      const guids = [...vp.selectionComponents];
      const mapa: OBC.ModelIdMap = {};
      for (const [modelId, model] of fragments.list) {
        const ids = (await model.getLocalIdsByGuids(guids)).filter((i): i is number => i !== null);
        if (ids.length) mapa[modelId] = new Set(ids);
      }
      if (Object.keys(mapa).length) await highlighter.highlightByID("select", mapa, true, false);
      else await highlighter.clear("select");
      await fragments.core.update(true);
    },
    descartar() {
      window.removeEventListener("keydown", aoTeclar);
      container.removeEventListener("dblclick", aoDuploClique);
      container.removeEventListener("contextmenu", aoMenuContexto);
      components.dispose();
    },
  };
}

/* ------------------------------------------------------------ propriedades */

type DadoItem = Record<string, unknown>;

function valorDe(campo: unknown): Valor | undefined {
  if (campo && typeof campo === "object" && !Array.isArray(campo) && "value" in campo) {
    const v = (campo as { value: unknown }).value;
    if (v === null || ["string", "number", "boolean"].includes(typeof v)) return v as Valor;
  }
  return undefined;
}

function linhasDe(item: DadoItem): [string, Valor][] {
  const linhas: [string, Valor][] = [];
  for (const [nome, campo] of Object.entries(item)) {
    if (nome.startsWith("_")) continue;
    const v = valorDe(campo);
    if (v !== undefined && v !== null && v !== "") linhas.push([nome, v]);
  }
  return linhas;
}

/** Um conjunto de propriedades (IfcPropertySet / quantidades) vira um grupo:
 *  as propriedades dele (Name → NominalValue) ou, sem elas, os atributos. */
function grupoDe(item: DadoItem): { titulo: string; linhas: [string, Valor][] } | null {
  const titulo = String(valorDe(item.Name) ?? valorDe(item._category) ?? "Propriedades");
  const filhos = (item.HasProperties ?? item.Quantities) as DadoItem[] | undefined;
  if (Array.isArray(filhos)) {
    const linhas: [string, Valor][] = [];
    for (const p of filhos) {
      const nome = valorDe(p.Name);
      const v =
        valorDe(p.NominalValue) ??
        valorDe(p.LengthValue) ??
        valorDe(p.AreaValue) ??
        valorDe(p.VolumeValue) ??
        valorDe(p.CountValue) ??
        valorDe(p.WeightValue);
      if (nome != null && v !== undefined) linhas.push([String(nome), v]);
    }
    return linhas.length ? { titulo, linhas } : null;
  }
  const linhas = linhasDe(item).filter(([n]) => n !== "Name");
  return linhas.length ? { titulo, linhas } : null;
}

async function propriedades(
  fragments: OBC.FragmentsManager,
  mapa: OBC.ModelIdMap,
): Promise<Propriedades | null> {
  const [modelId, ids] = Object.entries(mapa)[0] ?? [];
  const localId = ids ? [...ids][0] : undefined;
  const model = modelId ? fragments.list.get(modelId) : undefined;
  if (!model || localId === undefined) return null;
  const [item] = (await model.getItemsData([localId], {
    attributesDefault: true,
    relations: {
      IsDefinedBy: { attributes: true, relations: true },
      HasAssociations: { attributes: true, relations: false },
    },
    relationsDefault: { attributes: false, relations: false },
  })) as unknown as DadoItem[];
  if (!item) return null;
  const grupos: Propriedades["grupos"] = [];
  for (const rel of ["IsDefinedBy", "HasAssociations"]) {
    const lista = item[rel];
    if (Array.isArray(lista)) {
      for (const filho of lista as DadoItem[]) {
        const g = grupoDe(filho);
        if (g) grupos.push(g);
      }
    }
  }
  return {
    modelId,
    localId,
    nome: (valorDe(item.Name) as string) ?? null,
    categoria: (valorDe(item._category) as string) ?? null,
    guid: (valorDe(item._guid) as string) ?? null,
    atributos: linhasDe(item),
    grupos,
  };
}
