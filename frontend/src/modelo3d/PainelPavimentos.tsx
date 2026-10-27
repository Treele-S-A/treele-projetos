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

// Andares a menos disso, em disciplinas diferentes, são o mesmo (pé-direito
// típico de 2,88 m; a diferença entre disciplinas no SER foi de 12 cm).
const MESMO_ANDAR = 0.5;

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
        itens.push({ modelo, pavimento, elevacao: pavimento.elevacao === null ? null : pavimento.elevacao * fator });
      }
    }
    // Em ordem de elevação; um andar novo começa quando a próxima elevação
    // passa da tolerância ou o modelo já tem um pavimento no andar.
    const comCota = itens.filter((x) => x.elevacao !== null).sort((a, b) => a.elevacao! - b.elevacao!);
    const lista: Grupo[] = [];
    for (const x of comCota) {
      const g = lista[lista.length - 1];
      const cabe =
        g &&
        g.elevacao !== null &&
        x.elevacao! - g.elevacao < MESMO_ANDAR &&
        !g.porModelo.some((y) => y.modelo.modelId === x.modelo.modelId);
      if (cabe) {
        g.porModelo.push({ modelo: x.modelo, pavimento: x.pavimento });
        if (g.nome !== x.pavimento.nome && !g.outrosNomes.includes(x.pavimento.nome)) g.outrosNomes.push(x.pavimento.nome);
      } else {
        lista.push({
          chave: `${x.modelo.modelId}:${x.pavimento.localId}`,
          nome: x.pavimento.nome,
          outrosNomes: [],
          elevacao: x.elevacao,
          porModelo: [{ modelo: x.modelo, pavimento: x.pavimento }],
        });
      }
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
    // O nome que aparece: o que diz "pav" e é mais curto ("5° PAV", e não
    // "TIPO-001" nem "05 - 5º PAVIMENTO"); os outros vão para o detalhe.
    for (const g of lista) {
      const nomes = [g.nome, ...g.outrosNomes];
      const nota = (n: string) => (/pav/i.test(n) ? 0 : 100) + n.length;
      const melhor = nomes.reduce((a, b) => (nota(b) < nota(a) ? b : a));
      g.nome = melhor;
      g.outrosNomes = nomes.filter((n) => n !== melhor);
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
                    <li key={modelo.modelId}>
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
