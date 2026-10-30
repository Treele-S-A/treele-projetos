/** Detecção de conflitos entre disciplinas (TREELE, 22/10/2026), no jeito do
 *  Trimble Connect e do Navisworks: um conjunto ("clash set") diz quais
 *  elementos formam o grupo A e o grupo B, o tipo de teste e a tolerância.
 *
 *  Duas etapas:
 *  1. Triagem pelas caixas de cada elemento, numa grade: descarta quase todos
 *     os pares sem olhar a geometria. Na interferência, as caixas precisam se
 *     sobrepor mais que a tolerância nos três eixos — tubo encostado na face
 *     da viga não entra.
 *  2. Teste exato das malhas, só nos pares que sobraram, num worker
 *     (conflitos.worker.ts).
 *
 *  O que fica de fora é decidido pelo conjunto: sem lajes no grupo B, furo de
 *  laje não aparece. */

import type { FragmentsModel } from "@thatopen/fragments";
import * as THREE from "three";
import type { PedidoTeste, RespostaTeste } from "./conflitos.worker";
import { CATEGORIAS } from "./resumo-ifc";

export type ModoConflito = "interferencia" | "folga";

export interface GrupoConflito {
  /** Códigos das disciplinas (ARQ, EST, HID…): vale para qualquer revisão. */
  disciplinas: string[];
  /** Classes IFC (IFCBEAM…); vazio = todas as que entram em conflito. */
  categorias: string[];
  /** Com todas as categorias: as que ficam de fora. */
  excluir?: string[];
  /** Peças cujo nome (família e tipo, no Revit) contém um destes trechos
   *  ficam de fora, ex.: "Flexível" tira o eletroduto flexível embutido. */
  excluirNomes?: string[];
}

export interface ConjuntoConflito {
  id: string;
  nome: string;
  a: GrupoConflito;
  b: GrupoConflito;
  modo: ModoConflito;
  /** Em metros: o quanto uma peça pode entrar na outra sem contar. */
  tolerancia: number;
  /** Em metros: a distância mínima exigida, no modo folga. */
  folga: number;
  /** Ignora pares dentro do mesmo modelo (tubo com a própria conexão). */
  ignorarMesmoModelo: boolean;
}

export interface LadoConflito {
  modelId: string;
  localIds: number[];
  /** Os GlobalIds das peças, na ordem dos localIds: é por eles que o
   *  servidor reconhece o mesmo conflito na rodada seguinte. */
  guids: string[];
  nome: string | null;
  categoria: string;
}

export interface Conflito {
  id: number;
  tipo: ModoConflito;
  a: LadoConflito;
  b: LadoConflito;
  centro: [number, number, number];
  /** A região do conflito, para enquadrar. */
  caixa: { min: [number, number, number]; max: [number, number, number] };
  /** Interferência: quanto uma peça entra na outra (estimado pelas caixas).
   *  Folga: a distância entre elas. Em metros. */
  medida: number;
}

export interface ModeloNaCena {
  modelId: string;
  disciplina: string;
  model: FragmentsModel;
}

/** Não são peças: não entram em conflito. */
export const CATEGORIAS_FORA = new Set([
  "IFCOPENINGELEMENT",
  "IFCSPACE",
  "IFCANNOTATION",
  "IFCGRID",
  "IFCSITE",
  "IFCBUILDING",
  "IFCBUILDINGSTOREY",
  "IFCPROJECT",
  "IFCVIRTUALELEMENT",
  "IFCZONE",
  "IFCGROUP",
  "IFCSYSTEM",
  "IFCDISTRIBUTIONSYSTEM",
  "IFCDISTRIBUTIONPORT",
]);

const MAIS_CATEGORIAS: Record<string, string> = {
  IFCDUCTFITTING: "Conexão de duto",
  IFCCABLECARRIERFITTING: "Conexão de eletrocalha",
  IFCCABLESEGMENT: "Cabo",
  IFCAIRTERMINAL: "Grelha / difusor",
  IFCFLOWMOVINGDEVICE: "Bomba / ventilador",
  IFCFLOWSTORAGEDEVICE: "Reservatório",
  IFCFLOWTREATMENTDEVICE: "Filtro / tratamento",
  IFCENERGYCONVERSIONDEVICE: "Equipamento",
  IFCDISTRIBUTIONCONTROLELEMENT: "Controle / sensor",
  IFCDISTRIBUTIONFLOWELEMENT: "Elemento de instalação",
  IFCDISCRETEACCESSORY: "Acessório",
  IFCMECHANICALFASTENER: "Fixação",
  IFCREINFORCINGBAR: "Armadura",
  IFCSANITARYTERMINAL: "Louça",
  IFCLIGHTFIXTURE: "Luminária",
  IFCOUTLET: "Tomada",
  IFCSWITCHINGDEVICE: "Interruptor",
  IFCJUNCTIONBOX: "Caixa de passagem",
  IFCVALVE: "Registro / válvula",
};

export function nomeCategoria(codigo: string): string {
  const c = codigo.toUpperCase();
  return CATEGORIAS[c] ?? MAIS_CATEGORIAS[c] ?? codigo.replace(/^IFC/i, "");
}

/** O que projetista de instalação modela sem ser instalação: a parede do
 *  reservatório, a laje da casa de bombas. Contra a estrutura, é ruído. */
const CONSTRUCAO = ["IFCWALL", "IFCWALLSTANDARDCASE", "IFCSLAB", "IFCCOVERING", "IFCROOF", "IFCCOLUMN", "IFCBEAM",
  "IFCMEMBER", "IFCPLATE", "IFCFOOTING", "IFCSTAIR", "IFCSTAIRFLIGHT", "IFCRAILING", "IFCDOOR", "IFCWINDOW",
  "IFCFURNISHINGELEMENT"];

/** Modelos prontos, como ponto de partida. Os do grupo B do primeiro são o
 *  pedido de origem: tubulação contra pilar e viga, sem os furos de laje. */
export function conjuntosProntos(disciplinas: string[]): ConjuntoConflito[] {
  const instalacoes = disciplinas.filter((d) => d !== "EST" && d !== "ARQ");
  const base = { tolerancia: 0.01, folga: 0.05, modo: "interferencia" as const, ignorarMesmoModelo: true };
  return [
    {
      ...base,
      id: "pronto-instalacoes-estrutura",
      nome: "Instalações × pilares e vigas",
      a: { disciplinas: instalacoes, categorias: [], excluir: CONSTRUCAO },
      b: { disciplinas: ["EST"], categorias: ["IFCCOLUMN", "IFCBEAM"] },
    },
    {
      ...base,
      id: "pronto-instalacoes-entre-si",
      nome: "Instalações entre si",
      a: { disciplinas: instalacoes, categorias: [], excluir: CONSTRUCAO },
      b: { disciplinas: instalacoes, categorias: [], excluir: CONSTRUCAO },
    },
    {
      ...base,
      id: "pronto-arquitetura-estrutura",
      nome: "Portas e janelas × pilares e vigas",
      a: { disciplinas: ["ARQ"], categorias: ["IFCDOOR", "IFCWINDOW"] },
      b: { disciplinas: ["EST"], categorias: ["IFCCOLUMN", "IFCBEAM"] },
    },
  ];
}

// Por modelo, uma vez: os elementos com geometria, por categoria. Só eles
// entram — a lista de todas as categorias traz também tipos, materiais e
// propriedades (mais de um milhão de itens num modelo de hidráulica).
const comGeometria = new WeakMap<FragmentsModel, Promise<Map<string, number[]>>>();

function pecasPorCategoria(model: FragmentsModel): Promise<Map<string, number[]>> {
  let p = comGeometria.get(model);
  if (!p) {
    p = (async () => {
      // Pela categoria, e não pela ordem de duas listas: cada elemento fica
      // com a categoria que o próprio modelo diz.
      const comMalha = new Set(await model.getItemsIdsWithGeometry());
      const mapa = new Map<string, number[]>();
      for (const [cat, ids] of Object.entries(await model.getItemsOfCategories([/.*/]))) {
        const c = cat.toUpperCase();
        if (CATEGORIAS_FORA.has(c)) continue;
        const pecas = ids.filter((id) => comMalha.has(id));
        if (pecas.length) mapa.set(c, [...(mapa.get(c) ?? []), ...pecas]);
      }
      return mapa;
    })();
    comGeometria.set(model, p);
  }
  return p;
}

/** Quantas peças de cada categoria o modelo tem. */
export async function contarCategorias(model: FragmentsModel): Promise<Record<string, number>> {
  const saida: Record<string, number> = {};
  for (const [cat, ids] of await pecasPorCategoria(model)) saida[cat] = ids.length;
  return saida;
}

/* ------------------------------------------------------------- detecção */

interface Item {
  modelo: number;
  localId: number;
  categoria: string;
  caixa: THREE.Box3;
}

const LOTE_GEOMETRIA = 300;
const CELULA = 2; // m: a grade da triagem
const MAX_PARES = 400_000;
const JUNTAR_A_MENOS_DE = 0.6; // m: o mesmo B atravessado várias vezes ali perto vira um conflito só

/** Onde o modelo está na cena. Ao carregar, a biblioteca desloca cada modelo
 *  para alinhá-lo ao primeiro (autoCoordinate), mudando a posição do objeto;
 *  o matrixWorld só acompanha quando a tela desenha. Lido sem desenhar, ele
 *  vinha zerado e os modelos ficavam desalinhados no cálculo — o esgoto 28 m
 *  abaixo da estrutura, e a mesma detecção dava 59 numa máquina e 258 na
 *  outra (22/10/2026). Por isso a matriz sai da posição, na hora. */
function noMundo(model: FragmentsModel): THREE.Matrix4 {
  const objeto = model.object;
  objeto.updateMatrix();
  objeto.updateMatrixWorld(true);
  return objeto.matrixWorld.clone();
}

// As caixas saem da própria geometria, e não do getBoxes da biblioteca (que
// também depende do matrixWorld). Calculadas uma vez por modelo, e de novo
// se o modelo mudar de lugar.
const caixasCalculadas = new WeakMap<FragmentsModel, { onde: string; caixas: Map<number, THREE.Box3> }>();

async function caixas(modelo: ModeloNaCena, ids: number[], aoAvancar: (n: number) => void): Promise<Map<number, THREE.Box3>> {
  const mundo = noMundo(modelo.model);
  const onde = mundo.elements.join(",");
  let cache = caixasCalculadas.get(modelo.model);
  if (!cache || cache.onde !== onde) {
    cache = { onde, caixas: new Map() };
    caixasCalculadas.set(modelo.model, cache);
  }
  const guardadas = cache.caixas;
  const faltam = ids.filter((id) => !guardadas.has(id));
  const local = new THREE.Box3();
  const v = new THREE.Vector3();
  for (let k = 0; k < faltam.length; k += LOTE_GEOMETRIA) {
    const lote = faltam.slice(k, k + LOTE_GEOMETRIA);
    const malhasPorItem = await modelo.model.getItemsGeometry(lote);
    malhasPorItem.forEach((malhas, j) => {
      const caixa = new THREE.Box3();
      for (const m of malhas) {
        if (!m.positions || m.positions.length < 9) continue;
        // A caixa da malha no sistema dela, e os 8 cantos levados à cena:
        // bem mais barato que transformar vértice por vértice.
        local.makeEmpty();
        for (let p = 0; p < m.positions.length; p += 3) {
          v.set(m.positions[p], m.positions[p + 1], m.positions[p + 2]);
          local.expandByPoint(v);
        }
        const total = matriz(m.transform as Transformacao).premultiply(mundo);
        for (let c = 0; c < 8; c++) {
          v.set(c & 1 ? local.max.x : local.min.x, c & 2 ? local.max.y : local.min.y, c & 4 ? local.max.z : local.min.z);
          caixa.expandByPoint(v.applyMatrix4(total));
        }
      }
      const dono = malhas.find((m) => m.localId !== undefined)?.localId ?? lote[j];
      guardadas.set(dono, caixa);
    });
    aoAvancar(lote.length);
  }
  return guardadas;
}

/** A caixa que envolve as peças, na cena, pela geometria delas (o
 *  getMergedBox da biblioteca sofre do mesmo problema do getBoxes). Com
 *  muitas peças, uma amostra espalhada de até 400 basta para enquadrar. */
export async function caixaDasPecas(model: FragmentsModel, ids: number[]): Promise<THREE.Box3> {
  const passo = Math.max(1, Math.ceil(ids.length / 400));
  const amostra = ids.filter((_, i) => i % passo === 0);
  const doModelo = await caixas({ modelId: "", disciplina: "", model }, amostra, () => {});
  const caixa = new THREE.Box3();
  for (const id of amostra) {
    const c = doModelo.get(id);
    if (c && !c.isEmpty()) caixa.union(c);
  }
  return caixa;
}

/** Onde o conflito está, na cena de agora, pela geometria das peças: a parte
 *  em que as caixas de A e de B se cruzam (na folga, o trecho entre as duas).
 *  O ponto guardado no servidor pode estar em outra referência — conflito de
 *  antes de 26/10/2026, ou de uma sessão com outro modelo aberto primeiro — e
 *  a câmera ia parar longe (TREELE, 30/10/2026). null sem peças na cena. */
export async function regiaoDoConflito(
  modelA: FragmentsModel | undefined,
  idsA: number[],
  modelB: FragmentsModel | undefined,
  idsB: number[],
): Promise<{ centro: THREE.Vector3; caixa: THREE.Box3 } | null> {
  if (!modelA || !modelB || !idsA.length || !idsB.length) return null;
  const doA = await caixas({ modelId: "", disciplina: "", model: modelA }, idsA, () => {});
  const doB = await caixas({ modelId: "", disciplina: "", model: modelB }, idsB, () => {});
  const caixaB = new THREE.Box3();
  for (const c of doB.values()) if (!c.isEmpty()) caixaB.union(c);
  if (caixaB.isEmpty()) return null;
  const cruzamento = new THREE.Box3();
  const todasA = new THREE.Box3();
  for (const c of doA.values()) {
    if (c.isEmpty()) continue;
    todasA.union(c);
    const parte = c.clone().intersect(caixaB);
    if (!parte.isEmpty()) cruzamento.union(parte);
  }
  if (todasA.isEmpty()) return null;
  if (!cruzamento.isEmpty()) return { centro: cruzamento.getCenter(new THREE.Vector3()), caixa: cruzamento };
  // Folga: os pontos mais próximos entre as duas caixas.
  const pA = todasA.clampPoint(caixaB.getCenter(new THREE.Vector3()), new THREE.Vector3());
  const pB = caixaB.clampPoint(pA, new THREE.Vector3());
  const caixa = new THREE.Box3().setFromPoints([pA, pB]);
  return { centro: caixa.getCenter(new THREE.Vector3()), caixa };
}

function semAcento(texto: string): string {
  return texto.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
}

// Os nomes das peças, lidos uma vez por modelo (só quando um conjunto filtra
// por nome).
const nomesLidos = new WeakMap<FragmentsModel, Map<number, string>>();

async function nomesDas(model: FragmentsModel, ids: number[]): Promise<Map<number, string>> {
  let guardados = nomesLidos.get(model);
  if (!guardados) {
    guardados = new Map();
    nomesLidos.set(model, guardados);
  }
  const faltam = ids.filter((id) => !guardados!.has(id));
  for (let k = 0; k < faltam.length; k += 2000) {
    const lote = faltam.slice(k, k + 2000);
    const dados = (await model.getItemsData(lote, {
      attributesDefault: false,
      attributes: ["Name", "ObjectType"],
      relationsDefault: { attributes: false, relations: false },
    })) as unknown as Record<string, { value?: unknown } | undefined>[];
    lote.forEach((id, n) => {
      const nome = [dados[n]?.Name?.value, dados[n]?.ObjectType?.value].filter((v) => typeof v === "string").join(" ");
      guardados!.set(id, semAcento(nome));
    });
  }
  return guardados;
}

/** Tira do grupo as peças cujo nome contém algum dos trechos. */
async function semOsNomes(modelos: ModeloNaCena[], itens: Item[], trechos?: string[]): Promise<Item[]> {
  const termos = (trechos ?? []).map((t) => semAcento(t.trim())).filter(Boolean);
  if (!termos.length) return itens;
  const porModelo = new Map<number, number[]>();
  for (const i of itens) porModelo.set(i.modelo, [...(porModelo.get(i.modelo) ?? []), i.localId]);
  const nomes = new Map<number, Map<number, string>>();
  for (const [m, ids] of porModelo) nomes.set(m, await nomesDas(modelos[m].model, ids));
  return itens.filter((i) => {
    const nome = nomes.get(i.modelo)?.get(i.localId) ?? "";
    return !termos.some((t) => nome.includes(t));
  });
}

async function itensDoGrupo(
  modelos: ModeloNaCena[],
  grupo: GrupoConflito,
  aoProgredir: (valor: number) => void,
): Promise<Item[]> {
  const escolhidas = new Set(grupo.categorias.map((c) => c.toUpperCase()));
  const fora = new Set((grupo.excluir ?? []).map((c) => c.toUpperCase()));
  const pedidos: { i: number; c: string; ids: number[] }[] = [];
  for (const [i, m] of modelos.entries()) {
    if (!grupo.disciplinas.includes(m.disciplina)) continue;
    for (const [c, ids] of await pecasPorCategoria(m.model)) {
      if (escolhidas.size ? !escolhidas.has(c) : fora.has(c)) continue;
      pedidos.push({ i, c, ids });
    }
  }
  const total = pedidos.reduce((s, p) => s + p.ids.length, 0) || 1;
  let feitos = 0;
  const itens: Item[] = [];
  for (const { i, c, ids } of pedidos) {
    const doModelo = await caixas(modelos[i], ids, (n) => aoProgredir((feitos += n) / total));
    for (const localId of ids) {
      const caixa = doModelo.get(localId);
      if (caixa && !caixa.isEmpty()) itens.push({ modelo: i, localId, categoria: c, caixa });
    }
  }
  return itens;
}

function celulas(caixa: THREE.Box3): [number, number, number, number, number, number] {
  return [
    Math.floor(caixa.min.x / CELULA), Math.floor(caixa.min.y / CELULA), Math.floor(caixa.min.z / CELULA),
    Math.floor(caixa.max.x / CELULA), Math.floor(caixa.max.y / CELULA), Math.floor(caixa.max.z / CELULA),
  ];
}

/** Os pares cujas caixas se tocam do jeito que o modo pede. */
function triar(a: Item[], b: Item[], conjunto: ConjuntoConflito, mesmos: boolean): [number, number][] {
  const grade = new Map<string, number[]>();
  b.forEach((item, j) => {
    const [x0, y0, z0, x1, y1, z1] = celulas(item.caixa);
    for (let x = x0; x <= x1; x++)
      for (let y = y0; y <= y1; y++)
        for (let z = z0; z <= z1; z++) {
          const chave = `${x},${y},${z}`;
          const lista = grade.get(chave);
          if (lista) lista.push(j);
          else grade.set(chave, [j]);
        }
  });
  const folga = conjunto.modo === "folga" ? conjunto.folga : 0;
  const tol = conjunto.modo === "interferencia" ? conjunto.tolerancia : -Infinity;
  const pares: [number, number][] = [];
  const vistos = new Set<string>();
  const ampliada = new THREE.Box3();
  for (const [i, item] of a.entries()) {
    ampliada.copy(item.caixa).expandByScalar(folga);
    const candidatos = new Set<number>();
    const [x0, y0, z0, x1, y1, z1] = celulas(ampliada);
    for (let x = x0; x <= x1; x++)
      for (let y = y0; y <= y1; y++)
        for (let z = z0; z <= z1; z++) for (const j of grade.get(`${x},${y},${z}`) ?? []) candidatos.add(j);
    for (const j of candidatos) {
      const outro = b[j];
      if (outro.modelo === item.modelo) {
        if (conjunto.ignorarMesmoModelo || outro.localId === item.localId) continue;
      }
      if (!ampliada.intersectsBox(outro.caixa)) continue;
      if (conjunto.modo === "interferencia" && sobreposicao(item.caixa, outro.caixa) <= tol) continue;
      // Com A e B iguais (instalações entre si), cada par conta uma vez só.
      if (mesmos) {
        const chave = [`${item.modelo}:${item.localId}`, `${outro.modelo}:${outro.localId}`].sort().join("|");
        if (vistos.has(chave)) continue;
        vistos.add(chave);
      }
      pares.push([i, j]);
      if (pares.length > MAX_PARES) {
        throw new Error(
          "O conjunto é amplo demais: pares demais para testar. Escolha menos categorias ou disciplinas.",
        );
      }
    }
  }
  return pares;
}

/** O menor dos três lados da sobreposição das caixas: quanto uma peça entra
 *  na outra, estimado. */
function sobreposicao(p: THREE.Box3, q: THREE.Box3): number {
  return Math.min(
    Math.min(p.max.x, q.max.x) - Math.max(p.min.x, q.min.x),
    Math.min(p.max.y, q.max.y) - Math.max(p.min.y, q.min.y),
    Math.min(p.max.z, q.max.z) - Math.max(p.min.z, q.min.z),
  );
}

type Transformacao = THREE.Matrix4 | { elements: number[] } | number[];

function matriz(t: Transformacao | undefined): THREE.Matrix4 {
  if (!t) return new THREE.Matrix4();
  if (t instanceof THREE.Matrix4) return t.clone();
  return new THREE.Matrix4().fromArray(Array.isArray(t) ? t : t.elements);
}

/** As malhas de cada elemento juntas, já nas coordenadas da cena. */
async function geometrias(
  modelo: ModeloNaCena,
  localIds: number[],
): Promise<{ localId: number; posicoes: Float32Array; indices: Uint32Array }[]> {
  const mundo = noMundo(modelo.model);
  const saida: { localId: number; posicoes: Float32Array; indices: Uint32Array }[] = [];
  const v = new THREE.Vector3();
  for (let k = 0; k < localIds.length; k += LOTE_GEOMETRIA) {
    const lote = localIds.slice(k, k + LOTE_GEOMETRIA);
    const malhasPorItem = await modelo.model.getItemsGeometry(lote);
    malhasPorItem.forEach((malhas, j) => {
      let vertices = 0;
      let triangulos = 0;
      for (const m of malhas) {
        if (!m.positions) continue;
        vertices += m.positions.length / 3;
        triangulos += m.indices ? m.indices.length : m.positions.length / 3;
      }
      if (triangulos < 3) return;
      const posicoes = new Float32Array(vertices * 3);
      const indices = new Uint32Array(triangulos);
      let pv = 0;
      let pi = 0;
      for (const m of malhas) {
        if (!m.positions) continue;
        const total = matriz(m.transform as Transformacao).premultiply(mundo);
        const base = pv;
        for (let p = 0; p < m.positions.length; p += 3) {
          v.set(m.positions[p], m.positions[p + 1], m.positions[p + 2]).applyMatrix4(total);
          posicoes[pv * 3] = v.x;
          posicoes[pv * 3 + 1] = v.y;
          posicoes[pv * 3 + 2] = v.z;
          pv++;
        }
        if (m.indices) for (let q = 0; q < m.indices.length; q++) indices[pi++] = base + m.indices[q];
        else for (let q = 0; q < m.positions.length / 3; q++) indices[pi++] = base + q;
      }
      // A malha diz de quem é; a posição na lista fica só de reserva.
      const dono = malhas.find((m) => m.localId !== undefined)?.localId ?? lote[j];
      saida.push({ localId: dono, posicoes, indices });
    });
  }
  return saida;
}

export type Fase = "elementos" | "triagem" | "geometria" | "teste" | "nomes";

export async function detectar(
  modelos: ModeloNaCena[],
  conjunto: ConjuntoConflito,
  aoProgredir: (fase: Fase, valor: number) => void,
): Promise<Conflito[]> {
  aoProgredir("elementos", 0);
  const a = await semOsNomes(
    modelos,
    await itensDoGrupo(modelos, conjunto.a, (v) => aoProgredir("elementos", v / 2)),
    conjunto.a.excluirNomes,
  );
  const b = await semOsNomes(
    modelos,
    await itensDoGrupo(modelos, conjunto.b, (v) => aoProgredir("elementos", 0.5 + v / 2)),
    conjunto.b.excluirNomes,
  );
  if (!a.length || !b.length) return [];
  aoProgredir("triagem", 0);
  const mesmos = JSON.stringify(conjunto.a) === JSON.stringify(conjunto.b);
  const pares = triar(a, b, conjunto, mesmos);
  if (!pares.length) return [];

  // Cada elemento envolvido ganha uma chave única para o worker.
  const chaves = new Map<string, number>();
  const chaveDe = (item: Item) => {
    const k = `${item.modelo}:${item.localId}`;
    let c = chaves.get(k);
    if (c === undefined) {
      c = chaves.size;
      chaves.set(k, c);
    }
    return c;
  };
  const paresChaves = new Int32Array(pares.length * 2);
  pares.forEach(([i, j], n) => {
    paresChaves[2 * n] = chaveDe(a[i]);
    paresChaves[2 * n + 1] = chaveDe(b[j]);
  });

  const worker = new Worker(new URL("./conflitos.worker.ts", import.meta.url), { type: "module" });
  try {
    // As geometrias, modelo por modelo.
    const porModelo = new Map<number, number[]>();
    for (const k of chaves.keys()) {
      const [modelo, localId] = k.split(":").map(Number);
      const lista = porModelo.get(modelo);
      if (lista) lista.push(localId);
      else porModelo.set(modelo, [localId]);
    }
    let feitos = 0;
    for (const [modelo, ids] of porModelo) {
      for (let k = 0; k < ids.length; k += LOTE_GEOMETRIA * 4) {
        const lote = await geometrias(modelos[modelo], ids.slice(k, k + LOTE_GEOMETRIA * 4));
        const itens = lote.map((g) => ({
          chave: chaves.get(`${modelo}:${g.localId}`)!,
          posicoes: g.posicoes,
          indices: g.indices,
        }));
        const pedido: PedidoTeste = { tipo: "itens", itens };
        worker.postMessage(pedido, itens.flatMap((x) => [x.posicoes.buffer, x.indices.buffer]));
        feitos += Math.min(LOTE_GEOMETRIA * 4, ids.length - k);
        aoProgredir("geometria", feitos / chaves.size);
      }
    }

    aoProgredir("teste", 0);
    const achados = await new Promise<Float64Array>((resolver, rejeitar) => {
      worker.onmessage = (e: MessageEvent<RespostaTeste>) => {
        const r = e.data;
        if (r.tipo === "progresso") aoProgredir("teste", r.valor);
        else if (r.tipo === "pronto") resolver(r.achados);
        else rejeitar(new Error(r.mensagem));
      };
      worker.onerror = (e) => rejeitar(new Error(e.message || "O teste dos conflitos falhou."));
      const pedido: PedidoTeste = { tipo: "pares", pares: paresChaves, modo: conjunto.modo, folga: conjunto.folga };
      worker.postMessage(pedido);
    });

    aoProgredir("nomes", 0);
    return await montar(modelos, a, b, pares, achados, conjunto.modo);
  } finally {
    worker.terminate();
  }
}

interface Bruto {
  ia: number;
  ib: number;
  medida: number;
  centro: THREE.Vector3;
  caixa: THREE.Box3;
}

/** Junta os achados que são o mesmo problema (a mesma viga atravessada pelo
 *  tubo e pela conexão dele, a 20 cm um do outro) e põe os nomes. */
async function montar(
  modelos: ModeloNaCena[],
  a: Item[],
  b: Item[],
  pares: [number, number][],
  achados: Float64Array,
  modo: ModoConflito,
): Promise<Conflito[]> {
  const brutos: Bruto[] = [];
  for (let k = 0; k < achados.length; k += 5) {
    const [ia, ib] = pares[achados[k]];
    const caixa = a[ia].caixa.clone().intersect(b[ib].caixa);
    if (caixa.isEmpty()) caixa.copy(a[ia].caixa).union(b[ib].caixa);
    const centro = Number.isNaN(achados[k + 2])
      ? caixa.getCenter(new THREE.Vector3())
      : new THREE.Vector3(achados[k + 2], achados[k + 3], achados[k + 4]);
    if (modo === "folga") caixa.expandByPoint(centro);
    const medida = achados[k + 1] > 0 ? achados[k + 1] : Math.max(0, sobreposicao(a[ia].caixa, b[ib].caixa));
    brutos.push({ ia, ib, medida, centro, caixa });
  }

  type Grupo = { b: number; itensA: Set<number>; brutos: Bruto[] };
  const grupos: Grupo[] = [];
  // Só junta com o mesmo elemento B e o mesmo modelo A.
  const porDono = new Map<string, Grupo[]>();
  for (const br of brutos) {
    const dono = `${br.ib}|${a[br.ia].modelo}`;
    const candidatos = porDono.get(dono) ?? [];
    const g = candidatos.find((x) => x.brutos.some((y) => y.centro.distanceTo(br.centro) < JUNTAR_A_MENOS_DE));
    if (g) {
      g.itensA.add(br.ia);
      g.brutos.push(br);
    } else {
      const novo = { b: br.ib, itensA: new Set([br.ia]), brutos: [br] };
      grupos.push(novo);
      porDono.set(dono, [...candidatos, novo]);
    }
  }

  // Os nomes, de uma vez por modelo.
  const pedidos = new Map<number, Set<number>>();
  const pedir = (item: Item) => {
    const s = pedidos.get(item.modelo) ?? new Set<number>();
    s.add(item.localId);
    pedidos.set(item.modelo, s);
  };
  for (const g of grupos) {
    pedir(b[g.b]);
    for (const ia of g.itensA) pedir(a[ia]);
  }
  const nomes = new Map<string, string | null>();
  const guids = new Map<string, string>();
  for (const [modelo, ids] of pedidos) {
    const lista = [...ids];
    const globais = await modelos[modelo].model.getGuidsByLocalIds(lista);
    lista.forEach((id, n) => {
      if (globais[n]) guids.set(`${modelo}:${id}`, globais[n]!);
    });
    const dados = (await modelos[modelo].model.getItemsData(lista, {
      attributesDefault: false,
      attributes: ["Name"],
      relationsDefault: { attributes: false, relations: false },
    })) as unknown as Record<string, { value?: unknown } | undefined>[];
    lista.forEach((id, n) => {
      const v = dados[n]?.Name?.value;
      nomes.set(`${modelo}:${id}`, typeof v === "string" ? v : null);
    });
  }

  const lado = (itens: Item[]): LadoConflito => {
    const localIds = [...new Set(itens.map((i) => i.localId))];
    return {
      modelId: modelos[itens[0].modelo].modelId,
      localIds,
      guids: localIds.flatMap((id) => guids.get(`${itens[0].modelo}:${id}`) ?? []),
      nome: nomes.get(`${itens[0].modelo}:${itens[0].localId}`) ?? null,
      categoria: itens[0].categoria,
    };
  };

  return grupos
    .map((g, n) => {
      const caixa = new THREE.Box3();
      const centro = new THREE.Vector3();
      for (const br of g.brutos) {
        caixa.union(br.caixa);
        centro.add(br.centro);
      }
      centro.divideScalar(g.brutos.length);
      const medidas = g.brutos.map((x) => x.medida);
      return {
        id: n + 1,
        tipo: (modo === "folga" && Math.min(...medidas) > 0 ? "folga" : "interferencia") as ModoConflito,
        a: lado([...g.itensA].map((i) => a[i])),
        b: lado([b[g.b]]),
        centro: centro.toArray() as [number, number, number],
        caixa: {
          min: caixa.min.toArray() as [number, number, number],
          max: caixa.max.toArray() as [number, number, number],
        },
        medida: modo === "folga" ? Math.min(...medidas) : Math.max(...medidas),
      };
    })
    .sort((p, q) => p.centro[1] - q.centro[1] || p.centro[0] - q.centro[0])
    .map((c, n) => ({ ...c, id: n + 1 }));
}
