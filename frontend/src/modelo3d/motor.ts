/** O motor do visualizador 3D (TREELE, 21/10/2026): That Open (three.js +
 *  fragments). Tudo que é da biblioteca mora aqui; a tela (Modelo3D.tsx) só
 *  chama estas funções.
 *
 *  Os modelos chegam já no formato leve (fragments): ou o que ficou guardado
 *  no servidor, ou o que acabou de ser convertido do IFC (converter()). */

import * as OBC from "@thatopen/components";
import * as OBCF from "@thatopen/components-front";
import * as FRAGS from "@thatopen/fragments";
import * as THREE from "three";
import type { PedidoConversao, RespostaConversao } from "./conversor.worker";

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

export interface Motor {
  carregar(modelId: string, frag: ArrayBuffer | Uint8Array): Promise<void>;
  mostrarModelo(modelId: string, visivel: boolean): Promise<void>;
  enquadrar(): Promise<void>;
  isolarSelecao(): Promise<void>;
  esconderSelecao(): Promise<void>;
  mostrarTudo(): Promise<void>;
  corte(ativo: boolean): void;
  limparCortes(): void;
  descartar(): void;
}

const COR_SELECAO = new THREE.Color("#f0a500");

/** Converte um IFC em fragments num worker, com o andamento de 0 a 1. */
export function converter(bytes: Uint8Array, aoProgredir: (p: number) => void): Promise<Uint8Array> {
  return new Promise((resolver, rejeitar) => {
    const worker = new Worker(new URL("./conversor.worker.ts", import.meta.url), { type: "module" });
    worker.onmessage = (e: MessageEvent<RespostaConversao>) => {
      const r = e.data;
      if (r.tipo === "progresso") aoProgredir(r.valor);
      else {
        worker.terminate();
        if (r.tipo === "pronto") resolver(r.frag);
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

  return {
    async carregar(modelId, frag) {
      await fragments.core.load(frag, { modelId });
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
    },
    corte(ativo) {
      clipper.enabled = ativo;
    },
    limparCortes() {
      clipper.deleteAll();
    },
    descartar() {
      container.removeEventListener("dblclick", aoDuploClique);
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
