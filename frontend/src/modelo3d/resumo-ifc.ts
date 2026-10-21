/** Resumo de quantitativos de um IFC (TREELE, 21/10/2026), para o chat do
 *  acervo responder "qual a área de reboco?" sem abrir o modelo inteiro.
 *
 *  Lê, com o web-ifc, o que o programa de projeto exportou: para cada
 *  elemento, a categoria, o tipo, o pavimento, os materiais (as camadas, com
 *  espessura) e as quantidades (BaseQuantities / Qto_*: áreas, volumes,
 *  comprimentos). Soma por categoria + tipo + pavimento. O resultado é um
 *  JSON pequeno, guardado ao lado do IFC.
 *
 *  Roda no worker da conversão (navegador) e em Node (scripts), com o mesmo
 *  código. */

import {
  IFCAREAMEASURE,
  IFCBUILDINGSTOREY,
  IFCELEMENTQUANTITY,
  IFCPROJECT,
  IFCPROPERTYSET,
  IFCRELASSOCIATESMATERIAL,
  IFCRELCONTAINEDINSPATIALSTRUCTURE,
  IFCRELDEFINESBYPROPERTIES,
  IFCRELDEFINESBYTYPE,
  IfcAPI,
} from "web-ifc";

export const VERSAO_RESUMO = 1;

type Grandeza = "area" | "volume" | "comprimento" | "contagem" | "peso";

export interface GrupoResumo {
  categoria: string;
  tipo: string;
  pavimento: string | null;
  /** Quantos elementos. */
  n: number;
  /** Nome da quantidade (como no IFC) → soma, já em m, m², m³, kg. */
  q: Record<string, number>;
}

export interface ResumoIfc {
  versao: number;
  elementos: number;
  /** Nome da quantidade → o que ela mede. */
  grandezas: Record<string, Grandeza>;
  pavimentos: string[];
  /** Tipo → materiais (com espessura das camadas, quando houver). */
  materiais: Record<string, string[]>;
  grupos: GrupoResumo[];
}

/** Categorias IFC em português (as que não estão aqui ficam com o nome IFC). */
const CATEGORIAS: Record<string, string> = {
  IFCWALL: "Parede",
  IFCWALLSTANDARDCASE: "Parede",
  IFCSLAB: "Laje / piso",
  IFCROOF: "Cobertura",
  IFCCOVERING: "Revestimento",
  IFCDOOR: "Porta",
  IFCWINDOW: "Janela",
  IFCCOLUMN: "Pilar",
  IFCBEAM: "Viga",
  IFCMEMBER: "Perfil / montante",
  IFCPLATE: "Placa",
  IFCSTAIR: "Escada",
  IFCSTAIRFLIGHT: "Lance de escada",
  IFCRAMP: "Rampa",
  IFCRAMPFLIGHT: "Lance de rampa",
  IFCRAILING: "Guarda-corpo",
  IFCCURTAINWALL: "Pele de vidro",
  IFCFOOTING: "Fundação",
  IFCPILE: "Estaca",
  IFCFURNISHINGELEMENT: "Mobiliário",
  IFCFLOWTERMINAL: "Terminal (louça, ponto)",
  IFCFLOWSEGMENT: "Tubo / duto",
  IFCFLOWFITTING: "Conexão",
  IFCFLOWCONTROLLER: "Registro / válvula",
  IFCPIPESEGMENT: "Tubo",
  IFCPIPEFITTING: "Conexão",
  IFCDUCTSEGMENT: "Duto",
  IFCCABLECARRIERSEGMENT: "Eletrocalha / eletroduto",
  IFCBUILDINGELEMENTPROXY: "Outro elemento",
  IFCSPACE: "Ambiente",
  IFCOPENINGELEMENT: "Abertura",
};

/** Texto IFC com \X\HH (latin-1) e \X2\HHHH…\X0\ (UTF-16) decodificado. */
export function textoIfc(valor: unknown): string {
  if (typeof valor !== "string") return "";
  return valor
    .replace(/\\X2\\((?:[0-9A-Fa-f]{4})+)\\X0\\/g, (_, hex: string) =>
      String.fromCharCode(...(hex.match(/.{4}/g) ?? []).map((h) => parseInt(h, 16))),
    )
    .replace(/\\X\\([0-9A-Fa-f]{2})/g, (_, h: string) => String.fromCharCode(parseInt(h, 16)))
    .replace(/\\S\\(.)/g, (_, c: string) => String.fromCharCode(c.charCodeAt(0) + 128));
}

const PREFIXOS: Record<string, number> = {
  KILO: 1e3,
  HECTO: 1e2,
  DECA: 1e1,
  DECI: 1e-1,
  CENTI: 1e-2,
  MILLI: 1e-3,
  MICRO: 1e-6,
};

export async function resumirIfc(
  bytes: Uint8Array,
  wasm: { path: string; absolute: boolean },
): Promise<ResumoIfc> {
  const api = new IfcAPI();
  api.SetWasmPath(wasm.path, wasm.absolute);
  await api.Init();
  const modelo = api.OpenModel(bytes, { COORDINATE_TO_ORIGIN: false });
  try {
    return extrair(api, modelo);
  } finally {
    api.CloseModel(modelo);
  }
}

type Linha = Record<string, unknown> & { type: number; expressID: number };

function extrair(api: IfcAPI, modelo: number): ResumoIfc {
  const cache = new Map<number, Linha>();
  const linha = (id: number): Linha | null => {
    if (id < 0) return null;
    if (!cache.has(id)) {
      try {
        cache.set(id, api.GetLine(modelo, id, false) as Linha);
      } catch {
        return null;
      }
    }
    return cache.get(id) ?? null;
  };
  const ref = (v: unknown): number | null =>
    v && typeof v === "object" && "value" in v && typeof (v as { value: unknown }).value === "number"
      ? ((v as { value: number }).value)
      : null;
  const valor = (v: unknown): unknown => (v && typeof v === "object" && "value" in v ? (v as { value: unknown }).value : v);
  const lista = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
  const ids = (tipo: number): number[] => {
    const vetor = api.GetLineIDsWithType(modelo, tipo, true);
    const saida: number[] = [];
    for (let i = 0; i < vetor.size(); i++) saida.push(vetor.get(i));
    return saida;
  };

  // ---- unidades (o Revit exporta comprimento em cm, por exemplo)
  const fator: Record<Grandeza, number> = { comprimento: 1, area: 1, volume: 1, contagem: 1, peso: 1 };
  for (const pid of ids(IFCPROJECT)) {
    const projeto = linha(pid);
    const contexto = projeto && linha(ref(projeto.UnitsInContext) ?? -1);
    for (const u of lista(contexto?.Units)) {
      const unidade = linha(ref(u) ?? -1);
      if (!unidade) continue;
      const tipo = String(valor(unidade.UnitType) ?? "");
      const grandeza: Grandeza | null =
        tipo === "LENGTHUNIT" ? "comprimento" : tipo === "AREAUNIT" ? "area" : tipo === "VOLUMEUNIT" ? "volume" : tipo === "MASSUNIT" ? "peso" : null;
      if (!grandeza) continue;
      const prefixo = PREFIXOS[String(valor(unidade.Prefix) ?? "")] ?? 1;
      if (unidade.Prefix !== undefined || unidade.Name !== undefined) {
        const exp = grandeza === "area" ? 2 : grandeza === "volume" ? 3 : 1;
        // Massa: a unidade SI é o grama; com KILO, já é kg.
        fator[grandeza] = grandeza === "peso" ? prefixo / 1e3 : prefixo ** exp;
      }
      const conversao = linha(ref(unidade.ConversionFactor) ?? -1);
      if (conversao) {
        const v = Number(valor(conversao.ValueComponent));
        if (Number.isFinite(v) && v > 0) fator[grandeza] = v;
      }
    }
  }

  // ---- quantidades de cada conjunto (IfcElementQuantity)
  const grandezas: Record<string, Grandeza> = {};
  const conjuntos = new Map<number, { nome: string; q: Record<string, number> }>();
  for (const qid of ids(IFCELEMENTQUANTITY)) {
    const eq = linha(qid);
    if (!eq) continue;
    const q: Record<string, number> = {};
    for (const r of lista(eq.Quantities)) {
      const item = linha(ref(r) ?? -1);
      if (!item) continue;
      const nome = textoIfc(valor(item.Name));
      let g: Grandeza | null = null;
      let v: unknown;
      if ("AreaValue" in item) [g, v] = ["area", item.AreaValue];
      else if ("VolumeValue" in item) [g, v] = ["volume", item.VolumeValue];
      else if ("LengthValue" in item) [g, v] = ["comprimento", item.LengthValue];
      else if ("CountValue" in item) [g, v] = ["contagem", item.CountValue];
      else if ("WeightValue" in item) [g, v] = ["peso", item.WeightValue];
      const n = Number(valor(v));
      if (!g || !nome || !Number.isFinite(n)) continue;
      q[nome] = n * fator[g];
      grandezas[nome] ??= g;
    }
    conjuntos.set(qid, { nome: textoIfc(valor(eq.Name)), q });
  }

  // ---- área nos conjuntos de propriedades do Revit ("Cotas" / "Dimensions"):
  // fica de reserva para o elemento que veio sem área nas quantidades.
  const CONJUNTOS_COTAS = new Set(["cotas", "dimensoes", "dimensions"]);
  const areasPset = new Map<number, number>();
  for (const pid of ids(IFCPROPERTYSET)) {
    const ps = linha(pid);
    const nome = textoIfc(valor(ps?.Name)).normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
    if (!ps || !CONJUNTOS_COTAS.has(nome)) {
      cache.delete(pid);
      continue;
    }
    for (const r of lista(ps.HasProperties)) {
      const pr = linha(ref(r) ?? -1);
      const nomeProp = textoIfc(valor(pr?.Name)).normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
      const nominal = pr?.NominalValue as { type?: number; value?: unknown; constructor?: { name?: string } } | undefined;
      const ehArea =
        !!nominal &&
        ((nominal as { name?: string }).name === "IFCAREAMEASURE" ||
          nominal.type === IFCAREAMEASURE ||
          nominal.constructor?.name === "IfcAreaMeasure");
      if (nomeProp === "area" && ehArea) {
        const v = Number(valor(nominal));
        if (Number.isFinite(v) && v > 0) areasPset.set(pid, v * fator.area);
      }
    }
  }

  // ---- elemento → quantidades (o primeiro conjunto vence: nada se soma duas vezes)
  const areaInformada = new Map<number, number>();
  const quantidades = new Map<number, Record<string, number>>();
  for (const rid of ids(IFCRELDEFINESBYPROPERTIES)) {
    const rel = linha(rid);
    const definicao = ref(rel?.RelatingPropertyDefinition) ?? -1;
    const area = areasPset.get(definicao);
    if (rel && area !== undefined) {
      for (const o of lista(rel.RelatedObjects)) {
        const el = ref(o);
        if (el !== null && !areaInformada.has(el)) areaInformada.set(el, area);
      }
    }
    const conj = conjuntos.get(definicao);
    if (!rel || !conj) {
      cache.delete(rid);
      continue;
    }
    for (const o of lista(rel.RelatedObjects)) {
      const el = ref(o);
      if (el === null) continue;
      const atual = quantidades.get(el) ?? {};
      for (const [k, v] of Object.entries(conj.q)) if (!(k in atual)) atual[k] = v;
      quantidades.set(el, atual);
    }
    cache.delete(rid);
  }

  // ---- elemento → tipo
  const tipos = new Map<number, string>();
  for (const rid of ids(IFCRELDEFINESBYTYPE)) {
    const rel = linha(rid);
    const tipo = linha(ref(rel?.RelatingType) ?? -1);
    const nome = textoIfc(valor(tipo?.Name));
    if (!rel || !nome) continue;
    for (const o of lista(rel.RelatedObjects)) {
      const el = ref(o);
      if (el !== null) tipos.set(el, nome);
    }
  }

  // ---- elemento → pavimento
  const pavimentoDe = new Map<number, string>();
  const pavimentos = new Set<string>();
  for (const rid of ids(IFCRELCONTAINEDINSPATIALSTRUCTURE)) {
    const rel = linha(rid);
    const estrutura = linha(ref(rel?.RelatingStructure) ?? -1);
    if (!rel || !estrutura || estrutura.type !== IFCBUILDINGSTOREY) continue;
    const nome = textoIfc(valor(estrutura.Name)) || textoIfc(valor(estrutura.LongName));
    pavimentos.add(nome);
    for (const o of lista(rel.RelatedElements)) {
      const el = ref(o);
      if (el !== null) pavimentoDe.set(el, nome);
    }
  }

  // ---- elemento → materiais (camadas com espessura)
  const materiaisDe = new Map<number, string[]>();
  const nomeMaterial = (id: number | null): string[] => {
    const m = linha(id ?? -1);
    if (!m) return [];
    const nome = textoIfc(valor(m.Name));
    if ("ForLayerSet" in m) return nomeMaterial(ref(m.ForLayerSet));
    if ("MaterialLayers" in m) {
      return lista(m.MaterialLayers).flatMap((c) => {
        const camada = linha(ref(c) ?? -1);
        if (!camada) return [];
        const esp = Number(valor(camada.LayerThickness)) * fator.comprimento * 100;
        return nomeMaterial(ref(camada.Material)).map((n) =>
          Number.isFinite(esp) && esp > 0 ? `${n} (${Number(esp.toFixed(2))} cm)` : n,
        );
      });
    }
    if ("Materials" in m) return lista(m.Materials).flatMap((x) => nomeMaterial(ref(x)));
    if ("MaterialConstituents" in m)
      return lista(m.MaterialConstituents).flatMap((x) => nomeMaterial(ref(linha(ref(x) ?? -1)?.Material)));
    if ("Material" in m) return nomeMaterial(ref(m.Material));
    return nome ? [nome] : [];
  };
  for (const rid of ids(IFCRELASSOCIATESMATERIAL)) {
    const rel = linha(rid);
    if (!rel) continue;
    const nomes = [...new Set(nomeMaterial(ref(rel.RelatingMaterial)))];
    if (!nomes.length) continue;
    for (const o of lista(rel.RelatedObjects)) {
      const el = ref(o);
      if (el !== null) materiaisDe.set(el, nomes);
    }
  }

  // ---- soma por categoria + tipo + pavimento
  const elementos = new Set<number>([...quantidades.keys(), ...tipos.keys(), ...pavimentoDe.keys()]);
  const grupos = new Map<string, GrupoResumo>();
  const materiais: Record<string, string[]> = {};
  let contados = 0;
  for (const el of elementos) {
    let codigo: string;
    try {
      codigo = api.GetNameFromTypeCode(api.GetLineType(modelo, el));
    } catch {
      continue;
    }
    // Tipos, ambientes e aberturas não são o que se quantifica.
    if (!codigo || codigo.endsWith("TYPE") || codigo === "IFCOPENINGELEMENT" || codigo.startsWith("IFCREL")) continue;
    if (codigo === "IFCBUILDINGSTOREY" || codigo === "IFCBUILDING" || codigo === "IFCSITE" || codigo === "IFCPROJECT") continue;
    const categoria = CATEGORIAS[codigo] ?? codigo;
    let tipo = tipos.get(el);
    if (!tipo) {
      const l = linha(el);
      tipo = textoIfc(valor(l?.ObjectType)) || textoIfc(valor(l?.Name)).replace(/:\d+$/, "") || "(sem tipo)";
      cache.delete(el);
    }
    const pavimento = pavimentoDe.get(el) ?? null;
    const chave = `${categoria}|${tipo}|${pavimento ?? ""}`;
    const g = grupos.get(chave) ?? { categoria, tipo, pavimento, n: 0, q: {} };
    g.n += 1;
    const q = { ...(quantidades.get(el) ?? {}) };
    // Sem nenhuma área nas quantidades (o Revit faz isso com IfcWall que não
    // é reta), vale o parâmetro "Área" do programa de projeto.
    const temArea = Object.keys(q).some((k) => grandezas[k] === "area");
    const informada = areaInformada.get(el);
    if (!temArea && informada !== undefined) {
      q.AreaInformada = informada;
      grandezas.AreaInformada = "area";
    }
    for (const [k, v] of Object.entries(q)) {
      // Comprimento só soma o "Length" (largura e altura somadas não dizem nada).
      if (grandezas[k] === "comprimento" && k !== "Length") continue;
      g.q[k] = (g.q[k] ?? 0) + v;
    }
    grupos.set(chave, g);
    const mats = materiaisDe.get(el);
    if (mats) {
      const atuais = new Set(materiais[tipo] ?? []);
      for (const m of mats) if (atuais.size < 15) atuais.add(m);
      materiais[tipo] = [...atuais];
    }
    contados += 1;
  }

  const arredondar = (v: number) => Math.round(v * 1000) / 1000;
  return {
    versao: VERSAO_RESUMO,
    elementos: contados,
    grandezas,
    pavimentos: [...pavimentos],
    materiais,
    grupos: [...grupos.values()].map((g) => ({
      ...g,
      q: Object.fromEntries(Object.entries(g.q).map(([k, v]) => [k, arredondar(v)])),
    })),
  };
}
