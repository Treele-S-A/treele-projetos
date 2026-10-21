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
  descartar(): void;
}

const COR_SELECAO = new THREE.Color("#f0a500");

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
  const aoDuploClique = () => {
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

  return {
    async carregar(modelId, frag) {
      await fragments.core.load(frag, { modelId });
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
      const marcados = highlighter.selection.select ?? {};
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
      const dados = renderer.domElement.toDataURL("image/png");
      return await (await fetch(dados)).blob();
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
    descartar() {
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
