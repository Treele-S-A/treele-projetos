/** Árvore por pavimento no visualizador 3D (TREELE, 22/10/2026). Cada modelo
 *  traz os próprios pavimentos (IfcBuildingStorey); os da mesma elevação em
 *  disciplinas diferentes viram uma linha só, para ver, esconder ou isolar o
 *  pavimento inteiro de uma vez. Abrindo a linha, cada modelo com as
 *  categorias e quantas peças.
 *
 *  Pela elevação, e não pelo nome: no SER, o mesmo andar é "3 PAV" na
 *  estrutura, "3° PAV" na hidráulica e "03 - 3º PAVIMENTO" na elétrica — e
 *  "TIPO-001" na estrutura é o "5° PAV" das outras. As elevações batem (6,91,
 *  6,79 e 6,79 m). */

import { useEffect, useMemo, useState } from "react";
import { nomeCategoria } from "./conflitos";
import type { Motor, Pavimento, Pecas } from "./motor";

export interface ModeloPavimentos {
  modelId: string;
  disciplina: string;
  documento: string;
}

interface Grupo {
  chave: string;
  nome: string;
  /** Os outros nomes do mesmo andar, nas outras disciplinas. */
  outrosNomes: string[];
  /** Em m; null quando o IFC não traz a elevação. */
  elevacao: number | null;
  porModelo: { modelo: ModeloPavimentos; pavimento: Pavimento }[];
}

// Um andar junta os pavimentos de elevação próxima, de qualquer modelo — e do
// mesmo modelo também: no UNO, o térreo vem em três níveis por bloco de
// torres ("TÉRREO - (T02 e 04)" a 0,80 m, "(T01, 03, 06 e 08)" a 1,25 m,
// "(T05 e 07)" a 1,45 m), e o projeto de incêndio trouxe dezenas de níveis
// soltos entre eles (TREELE, 30/10/2026). O andar continua enquanto o próximo
// nível está a menos de SALTO do anterior e a menos de ALTURA_MAXIMA do
// primeiro (pé-direito típico de 2,72 a 2,88 m).
const SALTO = 1.0;
const ALTURA_MAXIMA = 2.0;

// O nome que aparece: sem o bloco ("- (T02 e 04)") e sem a disciplina na
// frente ("ELE - PAVIMENTO TÉRREO"); o de andar de verdade ganha do resto.
function limparNome(nome: string): string {
  return nome
    .replace(/\s*-?\s*\([^)]*\)\s*$/, "")
    .replace(/^[A-Z]{2,4}\s*-\s*/, "")
    .trim() || nome.trim();
}

function prioridade(nome: string): number {
  if (/t[ée]rreo|pav|subsolo|cobertura|barrilete|[áa]tico|mezanino|garagem|sobressolo/i.test(nome)) return 0;
  if (/n[íi]vel|piso|laje/i.test(nome)) return 1;
  return 2;
}

/** A elevação vem na unidade do IFC: o maior valor diz qual é (um prédio
 *  não tem 300 m; em centímetro ou milímetro, passa disso). */
function fatorParaMetro(pavimentos: Pavimento[]): number {
  const maior = Math.max(0, ...pavimentos.map((p) => Math.abs(p.elevacao ?? 0)));
  if (maior > 3000) return 0.001;
  if (maior > 300) return 0.01;
  return 1;
}

function pecasDo(grupo: Grupo, categoria?: string, modelId?: string): Pecas {
  const pecas: Pecas = {};
  for (const { modelo, pavimento } of grupo.porModelo) {
    if (modelId && modelo.modelId !== modelId) continue;
    const ids = categoria
      ? (pavimento.pecas[categoria] ?? [])
      : Object.values(pavimento.pecas).flat();
    if (ids.length) pecas[modelo.modelId] = [...(pecas[modelo.modelId] ?? []), ...ids];
  }
  return pecas;
}

function total(pecas: Pecas) {
  return Object.values(pecas).reduce((s, ids) => s + ids.length, 0);
}

export default function PainelPavimentos({
  motor,
  modelos,
  aoMostrarTudo,
}: {
  motor: Motor;
  modelos: ModeloPavimentos[];
  aoMostrarTudo: () => Promise<void>;
}) {
  const [porModelo, setPorModelo] = useState<Record<string, Pavimento[]> | null>(null);
  const [escondidos, setEscondidos] = useState<Set<string>>(new Set());
  const [aberto, setAberto] = useState<string | null>(null);

  useEffect(() => {
    let vivo = true;
    (async () => {
      const lido: Record<string, Pavimento[]> = {};
      for (const m of modelos) lido[m.modelId] = await motor.pavimentos(m.modelId);
      if (vivo) setPorModelo(lido);
    })();
    return () => {
      vivo = false;
    };
  }, [motor, modelos]);

  const grupos = useMemo<Grupo[]>(() => {
    if (!porModelo) return [];
    const itens: { modelo: ModeloPavimentos; pavimento: Pavimento; elevacao: number | null }[] = [];
    for (const modelo of modelos) {
      const pavimentos = porModelo[modelo.modelId] ?? [];
      const fator = fatorParaMetro(pavimentos);
      for (const pavimento of pavimentos) {
        // Pavimento sem peça nenhuma só polui a lista (o UNO tem dezenas).
        if (!Object.values(pavimento.pecas).some((ids) => ids.length)) continue;
        itens.push({ modelo, pavimento, elevacao: pavimento.elevacao === null ? null : pavimento.elevacao * fator });
      }
    }
    // Em ordem de elevação; o andar continua enquanto a próxima elevação está
    // perto da anterior e o andar não passou da altura máxima.
    const comCota = itens.filter((x) => x.elevacao !== null).sort((a, b) => a.elevacao! - b.elevacao!);
    const lista: Grupo[] = [];
    let anterior: number | null = null;
    for (const x of comCota) {
      const g = lista[lista.length - 1];
      const cabe =
        g && g.elevacao !== null && anterior !== null &&
        x.elevacao! - anterior < SALTO && x.elevacao! - g.elevacao < ALTURA_MAXIMA;
      if (cabe) g.porModelo.push({ modelo: x.modelo, pavimento: x.pavimento });
      else
        lista.push({
          chave: `${x.modelo.modelId}:${x.pavimento.localId}`,
          nome: x.pavimento.nome,
          outrosNomes: [],
          elevacao: x.elevacao,
          porModelo: [{ modelo: x.modelo, pavimento: x.pavimento }],
        });
      anterior = x.elevacao;
    }
    for (const x of itens.filter((y) => y.elevacao === null)) {
      lista.push({
        chave: `${x.modelo.modelId}:${x.pavimento.localId}`,
        nome: x.pavimento.nome,
        outrosNomes: [],
        elevacao: null,
        porModelo: [{ modelo: x.modelo, pavimento: x.pavimento }],
      });
    }
    // O nome do andar: o de andar de verdade (térreo, pavimento, subsolo,
    // cobertura) antes de "nível" e de nome solto; entre eles, o que tem mais
    // peças. Os outros nomes, limpos e sem repetir, vão para o detalhe.
    for (const g of lista) {
      const pesos = new Map<string, number>();
      for (const { pavimento } of g.porModelo) {
        const n = limparNome(pavimento.nome);
        pesos.set(n, (pesos.get(n) ?? 0) + Object.values(pavimento.pecas).reduce((s, ids) => s + ids.length, 0));
      }
      const nomes = [...pesos.keys()];
      nomes.sort((a, b) => prioridade(a) - prioridade(b) || pesos.get(b)! - pesos.get(a)! || a.length - b.length);
      g.nome = nomes[0];
      // Nome solto ("Salãuu", do incêndio do UNO) não entra no "também".
      g.outrosNomes = nomes.slice(1).filter((n) => prioridade(n) < 2 || prioridade(nomes[0]) === 2);
    }
    return lista;
  }, [porModelo, modelos]);

  async function alternar(g: Grupo) {
    const visivel = escondidos.has(g.chave);
    await motor.mostrarPecas(pecasDo(g), visivel);
    const novo = new Set(escondidos);
    if (visivel) novo.delete(g.chave);
    else novo.add(g.chave);
    setEscondidos(novo);
  }

  async function isolar(pecas: Pecas) {
    await motor.isolarPecas(pecas);
    await motor.enquadrarPecas(pecas);
    setEscondidos(new Set());
  }

  // Para ver 2 de 50 andares: esconde tudo e marca só os que quer. Esconde
  // também o que não está em pavimento nenhum (terreno, entorno).
  async function ocultarTodos() {
    await motor.isolarPecas({});
    setEscondidos(new Set(grupos.map((g) => g.chave)));
  }

  return (
    <div className="painel-pavimentos">
      <div className="linha" style={{ gap: 10 }}>
        <span className="rotulo">Pavimentos</span>
        <div className="espaco" />
        <button
          className="link-pequeno"
          disabled={grupos.length === 0}
          onClick={ocultarTodos}
          title="Esconde todos os pavimentos; depois marque só os que quer ver"
        >
          Ocultar todos
        </button>
        <button
          className="link-pequeno"
          onClick={async () => {
            await aoMostrarTudo();
            setEscondidos(new Set());
          }}
        >
          Mostrar todos
        </button>
      </div>
      {!porModelo && <p className="silencioso" style={{ fontSize: 12.5, margin: 0 }}>Lendo os pavimentos…</p>}
      {porModelo && grupos.length === 0 && (
        <p className="silencioso" style={{ fontSize: 12.5, margin: 0 }}>
          Os modelos abertos não trazem pavimentos (IfcBuildingStorey).
        </p>
      )}
      <ul className="lista-pavimentos">
        {grupos.map((g) => {
          const todas = pecasDo(g);
          const discs = [...new Set(g.porModelo.map((x) => x.modelo.disciplina))].join(", ");
          return (
            <li key={g.chave}>
              <div className="linha-pavimento">
                <input
                  type="checkbox"
                  checked={!escondidos.has(g.chave)}
                  onChange={() => alternar(g)}
                  aria-label={`Mostrar ${g.nome}`}
                />
                <button
                  className="nome-pavimento"
                  onClick={() => setAberto(aberto === g.chave ? null : g.chave)}
                  aria-expanded={aberto === g.chave}
                  title={g.outrosNomes.length ? `Também: ${g.outrosNomes.join(", ")}` : undefined}
                >
                  <span>{aberto === g.chave ? "▾" : "▸"}</span> {g.nome}
                  {g.elevacao !== null && (
                    <span className="silencioso mono">
                      {" "}
                      {g.elevacao >= 0 ? "+" : ""}
                      {g.elevacao.toFixed(2).replace(".", ",")}
                    </span>
                  )}
                  <span className="silencioso"> · {discs} · {total(todas)} peças</span>
                </button>
                <button className="link-pequeno" onClick={() => isolar(todas)} title="Mostra só este pavimento">
                  Isolar
                </button>
              </div>
              {aberto === g.chave && (
                <ul className="pavimento-modelos">
                  {g.porModelo.map(({ modelo, pavimento }) => (
                    <li key={`${modelo.modelId}:${pavimento.localId}`}>
                      <button
                        className="link-pequeno mono"
                        onClick={() => isolar(pecasDo(g, undefined, modelo.modelId))}
                        title="Isola este pavimento só deste modelo"
                      >
                        {modelo.disciplina} · {modelo.documento}
                      </button>
                      <span className="silencioso" style={{ fontSize: 11.5 }}>
                        {" "}
                        — {pavimento.nome}
                      </span>
                      <div className="categorias-pavimento">
                        {Object.entries(pavimento.pecas)
                          .sort((a, b) => b[1].length - a[1].length)
                          .map(([cat, ids]) => (
                            <button
                              key={cat}
                              className="etiqueta-categoria"
                              onClick={() => isolar(pecasDo(g, cat, modelo.modelId))}
                              title={`Isola ${nomeCategoria(cat).toLowerCase()} deste pavimento`}
                            >
                              {nomeCategoria(cat)} <span>{ids.length}</span>
                            </button>
                          ))}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
